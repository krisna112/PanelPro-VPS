"""Publish the PanelPro login on a dedicated HTTPS hostname."""

from __future__ import annotations

import logging
import secrets
import time
from hashlib import sha256
from pathlib import Path

from panelpro.core import settings_store
from panelpro.core.database import SessionLocal
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run
from panelpro.models.tables import Site
from panelpro.services import sslmgr, webservers

ACME_ROOT = Path("/var/www/panelpro-acme")
MANAGED_HEADER = "# Managed by PanelPro setup-domain\n"
log = logging.getLogger(__name__)


def _probe(args: list[str], expected: str, error: str) -> None:
    for attempt in range(12):
        result = run(["curl", "--noproxy", "*", "-fsS", "--max-time", "3", *args], timeout=5)
        if result.ok and expected in result.stdout:
            return
        if attempt < 11:
            time.sleep(0.5)
    raise PanelError(error, 502)


def _check_domain_available(domain: str) -> None:
    with SessionLocal() as db:
        for name, aliases in db.query(Site.name, Site.aliases):
            if domain == name or domain in (aliases or []):
                raise PanelError(f"'{domain}' is already assigned to website '{name}'. Use a separate hostname.", 409)


def setup_domain(domain: str, email: str) -> str:
    domain = webservers.validate_domain(domain)
    if domain.startswith("*."):
        raise PanelError("Use a hostname such as panel.example.com for the panel login.", 400)
    email = email.strip()
    if "@" not in email or email.startswith("-") or any(char.isspace() for char in email):
        raise PanelError("Provide a valid email address for Let's Encrypt.", 400)

    _check_domain_available(domain)
    require("certbot", "Install Certbot before configuring the panel domain.")
    require("curl")
    adapter = webservers.detect_webserver("nginx")
    config_path = adapter.conf_dir / "panelpro-panel.conf"
    previous_config = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    if (config_path.exists() or config_path.is_symlink()) and not previous_config.startswith(MANAGED_HEADER):
        raise PanelError(f"'{config_path}' is already managed outside PanelPro.", 409)

    entry = settings_store.get_setting("entry_path")
    if not entry:
        raise PanelError("Start PanelPro before configuring its public domain.", 400)
    port = int(settings_store.get_setting("panel_port"))
    backend_tls = bool(settings_store.get_setting("panel_ssl"))
    backend = f"{'https' if backend_tls else 'http'}://127.0.0.1:{port}"
    _probe([*(["--insecure"] if backend_tls else []), f"{backend}/api/health"], '"app":"PanelPro"',
           f"PanelPro is unavailable at {backend}. Check the panelpro service and configured port.")

    challenge_dir = ACME_ROOT / ".well-known" / "acme-challenge"
    challenge_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    probe_file = challenge_dir / f"panelpro-{token}"
    context = {"domain": domain, "acme_root": str(ACME_ROOT), "backend": backend, "certificate": None}

    previous_domain = settings_store.get_setting("panel_domain")
    previous_trust = settings_store.get_setting("trust_proxy")
    settings_store.set_setting("panel_domain", domain)
    restart_attempted = False
    try:
        with webservers.config_transaction(adapter, [config_path]) as apply:
            if f"    server_name {domain};\n" not in previous_config:
                bootstrap = adapter.render("nginx_panel.conf.j2", context)
                webservers.write_config(config_path, bootstrap.encode("utf-8"))
                apply()
            webservers.write_config(probe_file, token.encode("ascii"))
            try:
                _probe(["--resolve", f"{domain}:80:127.0.0.1",
                        f"http://{domain}/.well-known/acme-challenge/{probe_file.name}"], token,
                       f"Nginx did not serve the ACME challenge for {domain}. Check for a conflicting vhost.")
            finally:
                probe_file.unlink(missing_ok=True)

            lineage = "panelpro-login-" + sha256(domain.encode("ascii")).hexdigest()[:24]
            context["certificate"] = sslmgr.issue_letsencrypt(
                domain, [], str(ACME_ROOT), email, cert_name=lineage,
                deploy_hook="systemctl reload nginx",
            )
            config = adapter.render("nginx_panel.conf.j2", context)
            webservers.write_config(config_path, config.encode("utf-8"))
            if not previous_trust:
                settings_store.set_setting("trust_proxy", True)
                restart_attempted = True
                run(["systemctl", "restart", "panelpro"], check=True)
            apply()
            _probe(["--resolve", f"{domain}:443:127.0.0.1", f"https://{domain}/api/health"],
                   '"app":"PanelPro"', f"HTTPS did not reach PanelPro at {domain}.")
    except BaseException:
        try:
            settings_store.set_setting("panel_domain", previous_domain)
            if restart_attempted:
                settings_store.set_setting("trust_proxy", previous_trust)
                run(["systemctl", "restart", "panelpro"], check=True)
        except Exception:
            log.exception("Failed to restore the previous panel settings")
        raise
    return f"https://{domain}/{entry}"
