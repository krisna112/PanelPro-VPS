"""Nginx and Apache adapters: detection, vhost rendering, control.

Site configurations are rendered from original Jinja2 templates shipped in
``panelpro/templates`` and written to the webserver's include directory.
"""

from __future__ import annotations

import logging
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which

DOMAIN_RE = re.compile(r"(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
PROXY_URL_RE = re.compile(r"https?://[a-zA-Z0-9.:\[\]/_%~?&=+@,-]+")
CA_BUNDLES = (Path("/etc/ssl/certs/ca-certificates.crt"), Path("/etc/pki/tls/certs/ca-bundle.crt"))
CONFIG_LOCK = RLock()
log = logging.getLogger(__name__)


def validate_domain(domain: str) -> str:
    try:
        domain = domain.strip().removesuffix(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise PanelError("Invalid website domain.", 400) from exc
    if len(domain) > 253 or not DOMAIN_RE.fullmatch(domain):
        raise PanelError(f"Invalid domain: {domain}", 400)
    return domain


def php_socket_path(version: str) -> str:
    from panelpro.services.phpmgr import socket_path

    return socket_path(version).as_posix()


def validate_php_runtime(version: str | None) -> str | None:
    if not version:
        return None
    if not Path(php_socket_path(version)).is_socket():
        raise PanelError(f"PHP {version} FPM socket is unavailable. Install and start PHP-FPM first.", 400)
    return version


def validate_proxy_target(target: str, server: str) -> str:
    try:
        if len(target) > 255 or not PROXY_URL_RE.fullmatch(target):
            raise ValueError
        url = urlsplit(target)
        if not url.hostname or url.username is not None or url.port == 0:
            raise ValueError
        if not re.fullmatch(r"[a-zA-Z0-9.:-]+", url.hostname):
            raise ValueError
        if server == "apache" and "?" in target:
            raise ValueError
    except ValueError as exc:
        raise PanelError("Enter a valid HTTP or HTTPS backend URL without credentials or a fragment.", 400) from exc
    return target


def config_path_arg(path: str) -> str:
    if any(character in path for character in "\r\n\x00$"):
        raise PanelError("Unsupported character in webserver path.", 400)
    if re.fullmatch(r"[a-zA-Z0-9_./:-]+", path):
        return path
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_config(path: Path, content: bytes, mode: int = 0o644) -> None:
    """Replace a configuration file atomically within its own directory."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".panelpro-")
    temporary_path = Path(name)
    try:
        with os.fdopen(fd, "wb") as temp:
            temp.write(content)
        temporary_path.chmod(mode)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def serialized(operation):
    """Serialize webserver mutations from their initial database read."""
    @wraps(operation)
    def locked(*args, **kwargs):
        with CONFIG_LOCK:
            return operation(*args, **kwargs)

    return locked


@contextmanager
def config_transaction(adapter: WebserverAdapter, paths: list[Path]):
    """Restore previous files and activation state when applying a change fails."""
    with CONFIG_LOCK:
        previous = {}
        for path in dict.fromkeys(paths):
            if path.is_symlink():
                previous[path] = (os.readlink(path), None)
            elif path.exists():
                previous[path] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            else:
                previous[path] = (None, None)

        reload_attempted = False

        def apply() -> None:
            nonlocal reload_attempted
            adapter.test_config()
            reload_attempted = True
            adapter.reload()

        try:
            yield apply
        except BaseException:
            try:
                for path, (content, mode) in previous.items():
                    if isinstance(content, bytes):
                        write_config(path, content, mode)
                    else:
                        path.unlink(missing_ok=True)
                        if isinstance(content, str):
                            path.symlink_to(content)
                if reload_attempted:
                    adapter.reload()
            except Exception:
                log.exception("Failed to restore %s configuration", adapter.name)
            raise


def _web_owner() -> str | None:
    """Best-effort web user for chown of site roots."""
    for name in ("www-data", "apache", "nginx"):
        if which("id") and run(["id", "-u", name], check=False).code == 0:
            return name
    return None


class WebserverAdapter:
    name = "base"
    binary = ""
    config_test_binary = None

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(CFG.templates_dir)),
            keep_trailing_newline=True,
        )
        self.env.filters["config_path"] = config_path_arg

    def available(self) -> bool:
        return which(self.binary) is not None

    # -- overridden by implementations -------------------------------------
    def conf_path(self, domain: str) -> Path:
        raise NotImplementedError

    def log_paths(self, domain: str) -> tuple[str, str]:
        raise NotImplementedError

    def enable(self, domain: str) -> None:
        inactive = self.inactive_path(domain)
        if inactive.exists():
            inactive.replace(self.conf_path(domain))

    def disable(self, domain: str) -> None:
        active = self.conf_path(domain)
        if active.exists():
            active.replace(self.inactive_path(domain))

    def inactive_path(self, domain: str) -> Path:
        return self.conf_path(domain).with_suffix(".conf.disabled")

    def config_paths(self, domain: str) -> list[Path]:
        return [self.conf_path(domain), self.inactive_path(domain)]

    def editable_path(self, domain: str) -> Path:
        active = self.conf_path(domain)
        return active if active.exists() else self.inactive_path(domain)

    # -- shared --------------------------------------------------------------
    def render(self, template: str, ctx: dict) -> str:
        return self.env.get_template(template).render(**ctx)

    def test_config(self) -> None:
        res = run([self.config_test_binary or self.binary, "-t"], timeout=30)
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
            self.config_test_binary = "apache2ctl"
            self.sites_available = debian / "sites-available"
            self.sites_enabled = debian / "sites-enabled"
            self.conf_dir = self.sites_available
            self.use_symlink = True
        else:
            self.binary = "httpd"
            self.unit = "httpd"
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
            return super().enable(domain)
        src = self.conf_path(domain)
        dst = self.sites_enabled / f"{domain}.conf"
        if src.exists() and not dst.exists() and not dst.is_symlink():
            dst.symlink_to(src)

    def disable(self, domain: str) -> None:
        if not self.use_symlink:
            return super().disable(domain)
        dst = self.sites_enabled / f"{domain}.conf"
        if dst.is_symlink() or dst.exists():
            dst.unlink(missing_ok=True)

    def config_paths(self, domain: str) -> list[Path]:
        if self.use_symlink:
            return [self.conf_path(domain), self.sites_enabled / f"{domain}.conf"]
        return super().config_paths(domain)

    def editable_path(self, domain: str) -> Path:
        if self.use_symlink:
            return self.conf_path(domain)
        return super().editable_path(domain)


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
        f"{preferred or 'A supported webserver (nginx or Apache)'} is not installed on this host.",
        400,
    )


def chown_webroot(root: str) -> None:
    owner = _web_owner()
    if owner:
        run(["chown", f"{owner}:{owner}", root], timeout=30, check=True)


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
    waf_include: str | None = None,
) -> str:
    """Write and activate (or park) a generated vhost inside a transaction."""
    domain = validate_domain(domain)
    aliases = [validate_domain(alias) for alias in aliases]
    access_log, error_log = adapter.log_paths(domain)
    proxy_value = proxy_target
    if proxy_value and proxy_value.startswith("upstream:"):
        from panelpro.services.lb import validate_name

        if adapter.name != "nginx":
            raise PanelError("Load-balanced upstreams require nginx.", 400)
        proxy_value = "http://" + validate_name(proxy_value.split(":", 1)[1])
    elif proxy_value:
        proxy_value = validate_proxy_target(proxy_value, adapter.name)
    proxy_ca_bundle = None
    if proxy_value and proxy_value.startswith("https://"):
        proxy_ca_bundle = next((str(bundle) for bundle in CA_BUNDLES if bundle.is_file()), None)
        if proxy_ca_bundle is None:
            raise PanelError("Install the system CA certificates before connecting to an HTTPS backend.", 400)
    ctx = {
        "domain": domain,
        "aliases": [a for a in aliases if a],
        "root": root,
        "php_version": php_version,
        "php_socket": php_socket_path(php_version) if php_version else None,
        "proxy_target": proxy_value,
        "proxy_ca_bundle": proxy_ca_bundle,
        "force_https": force_https,
        "ssl_cert": ssl_cert_path,
        "ssl_key": ssl_key_path,
        "access_log": access_log,
        "error_log": error_log,
        "server": adapter.name,
        "waf_include": waf_include,
    }
    conf = adapter.render(adapter.template, ctx)
    path = adapter.editable_path(domain)
    if not path.exists():
        path = adapter.conf_path(domain)
    write_config(path, conf.encode("utf-8"))
    (adapter.enable if enabled else adapter.disable)(domain)
    return str(adapter.editable_path(domain))


def remove_vhost(adapter: WebserverAdapter, domain: str) -> None:
    adapter.disable(domain)
    for path in adapter.config_paths(domain):
        path.unlink(missing_ok=True)
