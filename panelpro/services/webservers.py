"""Nginx and Apache adapters: detection, vhost rendering, control.

Site configurations are rendered from original Jinja2 templates shipped in
``panelpro/templates`` and written to the webserver's include directory.
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which

DOMAIN_RE = re.compile(
    r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE
)


def validate_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if not DOMAIN_RE.match(domain):
        raise PanelError(f"Invalid domain: {domain}", 400)
    return domain


def php_socket_path(version: str) -> str:
    return f"/run/php/php{version}-fpm.sock"


def _web_owner() -> str | None:
    """Best-effort web user for chown of site roots."""
    for name in ("www-data", "apache", "nginx"):
        if which("id") and run(["id", "-u", name], check=False).code == 0:
            return name
    return None


class WebserverAdapter:
    name = "base"
    binary = ""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(CFG.templates_dir)),
            keep_trailing_newline=True,
        )

    def available(self) -> bool:
        return which(self.binary) is not None

    # -- overridden by implementations -------------------------------------
    def conf_path(self, domain: str) -> Path:
        raise NotImplementedError

    def log_paths(self, domain: str) -> tuple[str, str]:
        raise NotImplementedError

    def enable(self, domain: str) -> None:
        pass

    def disable(self, domain: str) -> None:
        pass

    # -- shared --------------------------------------------------------------
    def render(self, template: str, ctx: dict) -> str:
        return self.env.get_template(template).render(**ctx)

    def test_config(self) -> None:
        res = run([self.binary, "-t"], timeout=30)
        if res.code != 0:
            raise PanelError(f"Configuration test failed: {res.stderr[-400:]}", 500)

    def reload(self) -> None:
        run(["systemctl", "reload", self.unit], timeout=30, check=True)

    def restart(self) -> None:
        run(["systemctl", "restart", self.unit], timeout=40, check=True)


class NginxAdapter(WebserverAdapter):
    name = "nginx"
    binary = "nginx"
    unit = "nginx"
    template = "nginx_site.conf.j2"
    candidates = [
        Path("/etc/nginx/conf.d"),
        Path("/etc/nginx/sites-enabled"),
        Path("/usr/local/nginx/conf/conf.d"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.conf_dir = next((d for d in self.candidates if d.is_dir()), self.candidates[0])
        self.log_dir = Path("/var/log/nginx")

    def conf_path(self, domain: str) -> Path:
        return self.conf_dir / f"{domain}.conf"

    def log_paths(self, domain: str) -> tuple[str, str]:
        return (
            str(self.log_dir / f"{domain}.access.log"),
            str(self.log_dir / f"{domain}.error.log"),
        )


class ApacheAdapter(WebserverAdapter):
    name = "apache"
    binary = "apache2"
    unit = "apache2"
    template = "apache_site.conf.j2"

    def __init__(self) -> None:
        super().__init__()
        debian = Path("/etc/apache2")
        rhel = Path("/etc/httpd")
        if debian.is_dir():
            self.sites_available = debian / "sites-available"
            self.sites_enabled = debian / "sites-enabled"
            self.conf_dir = self.sites_available
            self.use_symlink = True
        else:
            self.conf_dir = rhel / "conf.d"
            self.sites_available = self.conf_dir
            self.sites_enabled = self.conf_dir
            self.use_symlink = False
        self.log_dir = Path("/var/log/apache2") if debian.is_dir() else Path("/var/log/httpd")

    def conf_path(self, domain: str) -> Path:
        return self.sites_available / f"{domain}.conf"

    def log_paths(self, domain: str) -> tuple[str, str]:
        return (
            str(self.log_dir / f"{domain}.access.log"),
            str(self.log_dir / f"{domain}.error.log"),
        )

    def enable(self, domain: str) -> None:
        if not self.use_symlink:
            return
        src = self.conf_path(domain)
        dst = self.sites_enabled / f"{domain}.conf"
        if src.exists() and not dst.exists():
            dst.symlink_to(src)

    def disable(self, domain: str) -> None:
        dst = self.sites_enabled / f"{domain}.conf"
        if dst.is_symlink() or dst.exists():
            dst.unlink(missing_ok=True)


ADAPTERS = {"nginx": NginxAdapter, "apache": ApacheAdapter}


def detect_webserver(preferred: str | None = None) -> WebserverAdapter:
    """Return an adapter for the installed webserver (or the preferred one)."""
    order = [preferred] if preferred else ["nginx", "apache"]
    for key in order:
        cls = ADAPTERS.get(key or "")
        if not cls:
            continue
        adapter = cls()
        if adapter.available():
            return adapter
    raise PanelError(
        "No supported webserver (nginx/apache) is installed. Install one from the "
        "Apps or Services page first.",
        400,
    )


def chown_webroot(root: str) -> None:
    owner = _web_owner()
    if owner:
        run(["chown", "-R", f"{owner}:{owner}", root], timeout=120, check=False)


def write_vhost(
    adapter: WebserverAdapter,
    domain: str,
    aliases: list[str],
    root: str,
    php_version: str | None,
    proxy_target: str | None,
    force_https: bool,
    ssl_cert_path: str | None,
    ssl_key_path: str | None,
    enabled: bool = True,
) -> str:
    """Render + write the vhost file, then verify the server config."""
    for d in [domain, *aliases]:
        validate_domain(d)
    access_log, error_log = adapter.log_paths(domain)
    ctx = {
        "domain": domain,
        "aliases": [a for a in aliases if a],
        "root": root,
        "php_version": php_version,
        "php_socket": php_socket_path(php_version) if php_version else None,
        "proxy_target": proxy_target,
        "force_https": force_https,
        "ssl_cert": ssl_cert_path,
        "ssl_key": ssl_key_path,
        "access_log": access_log,
        "error_log": error_log,
        "server": adapter.name,
    }
    conf = adapter.render(adapter.template, ctx)
    adapter.conf_path(domain).write_text(conf, encoding="utf-8")
    if enabled:
        adapter.enable(domain)
    adapter.test_config()
    return str(adapter.conf_path(domain))


def remove_vhost(adapter: WebserverAdapter, domain: str) -> None:
    adapter.disable(domain)
    path = adapter.conf_path(domain)
    if path.exists():
        path.unlink()
    adapter.test_config()
