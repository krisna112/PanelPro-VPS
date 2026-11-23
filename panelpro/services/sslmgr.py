"""SSL certificate service: Let's Encrypt (certbot), self-signed and
custom certificates, with expiry monitoring and auto-renew."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from panelpro.config import CFG
from panelpro.core import certs as cert_util
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run, which

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


def issue_letsencrypt(
    domain: str,
    aliases: list[str],
    webroot: str,
    email: str,
) -> dict:
    """Issue/renew via certbot webroot; returns parsed cert info + paths."""
    domain = validate_cert_domain(domain)
    aliases = [validate_cert_domain(a) for a in aliases if a]
    require("certbot", "Install certbot (apt/yum install certbot).")
    require("mkdir")
    run(["mkdir", "-p", webroot], check=True)
    domains: list[str] = []
    for d in [domain, *aliases]:
        if d and d not in domains:
            domains.append(d)
    args = ["certbot", "certonly", "--webroot", "-w", webroot, "--non-interactive",
            "--agree-tos", "--keep-until-expiring"]
    for d in domains:
        args += ["-d", d]
    args += ["-m", email or "admin@" + domain]
    res = run(args, timeout=180)
    if res.code != 0:
        raise PanelError(f"certbot failed: {(res.stderr or res.stdout)[-400:]}", 500)
    live = Path("/etc/letsencrypt/live") / domain
    cert_path = str(live / "fullchain.pem")
    key_path = str(live / "privkey.pem")
    info = cert_util.parse_cert_file(cert_path)
    return {"info": info, "cert_path": cert_path, "key_path": key_path}


def renew_all() -> dict:
    if not certbot_available():
        raise PanelError("certbot is not installed.", 400)
    res = run(["certbot", "renew", "--quiet"], timeout=600)
    return {"ok": res.code == 0, "output": (res.stdout + res.stderr)[-400:]}


def issue_selfsigned(domain: str, aliases: list[str] | None = None, days: int = 3650) -> dict:
    domain = validate_cert_domain(domain)
    aliases = [validate_cert_domain(a) for a in (aliases or []) if a]
    cert_pem, key_pem = cert_util.generate_selfsigned(domain, days=days, extra_domains=aliases)
    out_dir = CFG.ssl_dir / domain
    out_dir.mkdir(parents=True, exist_ok=True)
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
    domain = parsed["subject"] or name
    out_dir = CFG.ssl_dir / re.sub(r"[^a-zA-Z0-9._-]", "_", domain)
    out_dir.mkdir(parents=True, exist_ok=True)
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
        for row in rows:
            if not row.not_after:
                continue
            days_left = (row.not_after - datetime.utcnow()).days
            if days_left > 30:
                continue
            if row.source == "letsencrypt" and row.auto_renew and certbot_available():
                try:
                    renew_all()
                    info = cert_util.parse_cert_file(row.cert_path)
                    row.not_after = datetime.fromisoformat(info["not_after"])
                    db.commit()
                    continue
                except PanelError:
                    pass
            notify.notify_event(
                "ssl_expiry",
                "Certificate expiring",
                f"{row.domain} expires in {days_left} days "
                f"({row.not_after.date().isoformat()}, source={row.source}).",
            )
    finally:
        db.close()
