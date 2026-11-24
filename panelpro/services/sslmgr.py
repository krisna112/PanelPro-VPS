"""SSL certificate service: Let's Encrypt (certbot), self-signed and
custom certificates, with expiry monitoring and auto-renew."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from panelpro.config import CFG
from panelpro.core import certs as cert_util
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run, which

log = logging.getLogger(__name__)

# Domains become filesystem paths under CFG.ssl_dir, so they must be strict
# hostnames — this also blocks path traversal via a crafted domain.
DOMAIN_RE = re.compile(r"^(?:\*\.)?[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")


def validate_cert_domain(domain: str) -> str:
    domain = (domain or "").strip().lower().rstrip(".")
    if (
        not domain
        or len(domain) > 253
        or not DOMAIN_RE.match(domain)
        or ".." in domain
        or "/" in domain
        or "\\" in domain
    ):
        raise PanelError(f"Invalid certificate domain: {domain}", 400)
    return domain


def certbot_available() -> bool:
    return which("certbot") is not None


def _certbot_name(domain: str) -> str:
    return "panelpro-" + ("wildcard-" + domain[2:] if domain.startswith("*.") else domain)


def issue_letsencrypt(
    domain: str,
    aliases: list[str],
    webroot: str,
    email: str,
    *,
    cert_name: str | None = None,
    deploy_hook: str | None = None,
) -> dict:
    """Issue/renew via certbot webroot; returns parsed cert info + paths."""
    domain = validate_cert_domain(domain)
    aliases = [validate_cert_domain(a) for a in aliases if a]
    if any(name.startswith("*.") for name in [domain, *aliases]):
        raise PanelError("Wildcard certificates require the DNS-01 challenge.", 400)
    require("certbot", "Install certbot (apt/yum install certbot).")
    require("mkdir")
    run(["mkdir", "-p", webroot], check=True)
    domains: list[str] = []
    for d in [domain, *aliases]:
        if d and d not in domains:
            domains.append(d)
    name = cert_name or _certbot_name(domain)
    args = ["certbot", "certonly", "--webroot", "-w", webroot, "--non-interactive",
            "--agree-tos", "--keep-until-expiring", "--expand", "--cert-name", name]
    for d in domains:
        args += ["-d", d]
    args += ["-m", email or "admin@" + domain]
    if deploy_hook:
        args += ["--deploy-hook", deploy_hook]
    res = run(args, timeout=180)
    if res.code != 0:
        raise PanelError(f"certbot failed: {(res.stderr or res.stdout)[-400:]}", 500)
    live = Path("/etc/letsencrypt/live") / name
    cert_path = str(live / "fullchain.pem")
    key_path = str(live / "privkey.pem")
    info = cert_util.parse_cert_file(cert_path)
    return {"info": info, "cert_path": cert_path, "key_path": key_path}


def renew_all() -> dict:
    if not certbot_available():
        raise PanelError("certbot is not installed.", 400)
    res = run(["certbot", "renew", "--quiet"], timeout=600)
    _refresh_renewed_certs()
    return {"ok": res.code == 0, "output": (res.stdout + res.stderr)[-400:]}


def _refresh_renewed_certs() -> None:
    from panelpro.core.database import SessionLocal
    from panelpro.models.tables import Site, SslCert
    from panelpro.services import webservers

    with webservers.CONFIG_LOCK, SessionLocal() as db:
        changed = []
        for cert in db.query(SslCert).filter(SslCert.source.in_(("letsencrypt", "letsencrypt-dns"))):
            try:
                info = cert_util.parse_cert_file(cert.cert_path)
            except (OSError, PanelError):
                log.warning("Could not read renewed certificate %s", cert.name)
                continue
            expiry = datetime.fromisoformat(info["not_after"])
            if cert.not_after != expiry:
                cert.not_after = expiry
                cert.not_before = datetime.fromisoformat(info["not_before"])
                changed.append(cert.id)
        servers = db.query(Site.server).filter(Site.ssl_cert_id.in_(changed), Site.enabled.is_(True)).distinct()
        for (server,) in servers:
            adapter = webservers.detect_webserver(server)
            adapter.test_config()
            adapter.reload()
        db.commit()


# ---------------------------------------------------------------------------
# DNS-01 challenge (wildcard certificates via DNS provider APIs)
# ---------------------------------------------------------------------------

# provider -> (certbot dns plugin flag, credentials file ini section header)
DNS_PROVIDERS = {
    "cloudflare": ("dns-cloudflare", "dns_cloudflare_api_token"),
    "digitalocean": ("dns-digitalocean", "dns_digitalocean_token"),
    "dnspod": ("dns-dnspod", "dns_dnspod_id\ndns_dnspod_token"),
    "aliyun": ("dns-aliyun", "dns_aliyun_access_key_id\ndns_aliyun_access_key_secret"),
    "godaddy": ("dns-godaddy", "dns_godaddy_key\ndns_godaddy_secret"),
}


def dns_provider_list() -> list[str]:
    return sorted(DNS_PROVIDERS)


def _dns_credentials_body(provider: str, config: dict) -> str:
    """Render the certbot credentials ini body; raises on missing fields."""
    if provider not in DNS_PROVIDERS:
        raise PanelError(
            f"Unsupported DNS provider '{provider}'. "
            f"Available: {', '.join(sorted(DNS_PROVIDERS))}.",
            400,
        )
    _, cred_keys = DNS_PROVIDERS[provider]
    prefix = f"dns_{provider.replace('-', '_')}_"
    body = ""
    for key in (k for k in cred_keys.split("\n") if k):
        short = key.replace(prefix, "")
        value = str(config.get(short, "") or config.get(key, ""))
        if not value or any(character in value for character in "\r\n\x00"):
            raise PanelError(f"Missing DNS credential field: {short}", 400)
        body += f"{key} = {value}\n"
    return body


def issue_letsencrypt_dns(
    domain: str,
    aliases: list[str],
    provider: str,
    config: dict,
    email: str,
) -> dict:
    """Issue (wildcard) certificates via certbot DNS-01 with provider creds.

    The credentials file is written with mode 0600 into the panel tmp dir
    and deleted right after certbot finishes.
    """
    domain = validate_cert_domain(domain)
    aliases = [validate_cert_domain(a) for a in aliases if a]
    if provider not in DNS_PROVIDERS:
        raise PanelError(
            f"Unsupported DNS provider '{provider}'. "
            f"Available: {', '.join(sorted(DNS_PROVIDERS))}.",
            400,
        )
    require("certbot", "Install certbot (apt/yum install certbot).")
    flag = DNS_PROVIDERS[provider][0]
    body = _dns_credentials_body(provider, config)

    name = _certbot_name(domain)
    fd, filename = tempfile.mkstemp(prefix="dns-", suffix=".ini", dir=CFG.ssl_dir)
    cred_file = Path(filename)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as credentials:
            credentials.write(body)
        domains: list[str] = []
        for d in [domain, *aliases]:
            if d and d not in domains:
                domains.append(d)
        args = ["certbot", "certonly", f"--{flag}", "--non-interactive",
                "--agree-tos", "--keep-until-expiring", "--expand", "--cert-name", name,
                f"--{flag}-credentials", str(cred_file),
                f"--{flag}-propagation-seconds", "60"]
        for d in domains:
            args += ["-d", d]
        args += ["-m", email or "admin@" + domain.lstrip("*.")]
        res = run(args, timeout=300)
        if not res.ok:
            raise PanelError(
                f"certbot DNS-01 failed: {(res.stderr or res.stdout)[-400:]} "
                f"(is the certbot DNS plugin '{flag}' installed?)", 500,
            )
    except Exception:
        cred_file.unlink(missing_ok=True)
        raise
    live = Path("/etc/letsencrypt/live") / name
    cert_path = str(live / "fullchain.pem")
    key_path = str(live / "privkey.pem")
    info = cert_util.parse_cert_file(cert_path)
    return {"info": info, "cert_path": cert_path, "key_path": key_path}


def issue_selfsigned(domain: str, aliases: list[str] | None = None, days: int = 3650) -> dict:
    domain = validate_cert_domain(domain)
    aliases = [validate_cert_domain(a) for a in (aliases or []) if a]
    cert_pem, key_pem = cert_util.generate_selfsigned(domain, days=days, extra_domains=aliases)
    out_dir = Path(tempfile.mkdtemp(prefix="self-", dir=CFG.ssl_dir))
    cert_path = out_dir / "cert.pem"
    key_path = out_dir / "key.pem"
    cert_path.write_text(cert_pem, encoding="utf-8")
    key_path.write_text(key_pem, encoding="utf-8")
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    info = cert_util.parse_cert_pem(cert_pem)
    return {"info": info, "cert_path": str(cert_path), "key_path": str(key_path)}


def import_custom(name: str, cert_pem: str, key_pem: str) -> dict:
    if not cert_util.verify_key_matches(cert_pem, key_pem):
        raise PanelError("Certificate and private key do not match.", 400)
    parsed = cert_util.parse_cert_pem(cert_pem)
    out_dir = Path(tempfile.mkdtemp(prefix="custom-", dir=CFG.ssl_dir))
    cert_path = out_dir / "cert.pem"
    key_path = out_dir / "key.pem"
    cert_path.write_text(cert_pem, encoding="utf-8")
    key_path.write_text(key_pem, encoding="utf-8")
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return {"info": parsed, "cert_path": str(cert_path), "key_path": str(key_path)}


def check_ssl_expiry_job() -> None:
    """Scheduler job: warn (and renew) certificates expiring within 30 days."""
    from panelpro.core import notify
    from panelpro.core.database import SessionLocal
    from panelpro.models.tables import SslCert

    db = SessionLocal()
    try:
        rows = db.query(SslCert).all()
        if certbot_available():
            try:
                for row in rows:
                    if (row.source in {"letsencrypt", "letsencrypt-dns"} and row.auto_renew
                            and row.not_after and (row.not_after - datetime.utcnow()).days <= 30):
                        name = Path(row.cert_path).parent.name
                        run(["certbot", "renew", "--cert-name", name, "--quiet"], timeout=600, check=True)
                _refresh_renewed_certs()
            except PanelError:
                log.exception("Certificate renewal failed")
            db.expire_all()
        for row in rows:
            if not row.not_after:
                continue
            days_left = (row.not_after - datetime.utcnow()).days
            if days_left > 30:
                continue
            notify.notify_event(
                "ssl_expiry",
                "Certificate expiring",
                f"{row.domain} expires in {days_left} days "
                f"({row.not_after.date().isoformat()}, source={row.source}).",
            )
    finally:
        db.close()
