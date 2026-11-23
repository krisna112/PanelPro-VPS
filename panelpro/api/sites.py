"""Website management endpoints (nginx/apache sites)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.config import CFG
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.core.notify import notify_event
from panelpro.core.syscmd import run
from panelpro.models.tables import Site, SslCert
from panelpro.services import webservers

router = APIRouter(prefix="/api/sites", tags=["sites"])


class CreateSiteBody(BaseModel):
    domain: str
    aliases: list[str] = []
    server: str = "nginx"
    php_version: str | None = None
    create_db: dict | None = None  # {"type": "mysql", "name": ..., "user": ..., "password": ...}


class ConfBody(BaseModel):
    content: str


class DomainBody(BaseModel):
    domain: str


class ProxyBody(BaseModel):
    target: str | None = None


class PhpBody(BaseModel):
    version: str | None = None


class HttpsBody(BaseModel):
    force: bool


class DeploySslBody(BaseModel):
    cert_id: int


def _render_site(site: Site, db: Session) -> None:
    """Re-write the vhost file for a site row (source of truth = DB)."""
    adapter = webservers.detect_webserver(site.server)
    cert_path = key_path = None
    if site.ssl_cert_id:
        cert = db.query(SslCert).filter(SslCert.id == site.ssl_cert_id).first()
        if cert is not None:
            cert_path, key_path = cert.cert_path, cert.key_path
    webservers.write_vhost(
        adapter,
        site.name,
        site.aliases or [],
        site.root,
        site.php_version,
        site.proxy_target,
        site.force_https,
        cert_path,
        key_path,
        enabled=site.enabled,
    )


def _webserver_action(action: str) -> None:
    adapter = webservers.detect_webserver()
    if action == "reload":
        adapter.reload()
    elif action == "restart":
        adapter.restart()
    else:
        raise PanelError(f"Unknown action: {action}", 400)


@router.get("")
def list_sites(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(Site).order_by(Site.created_at.desc()).all()
    out = []
    for r in rows:
        cert = db.query(SslCert).filter(SslCert.id == r.ssl_cert_id).first() if r.ssl_cert_id else None
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "server": r.server,
                "root": r.root,
                "aliases": r.aliases,
                "php_version": r.php_version,
                "proxy_target": r.proxy_target,
                "force_https": r.force_https,
                "enabled": r.enabled,
                "ssl": (
                    {"cert_id": cert.id, "issuer": cert.issuer,
                     "not_after": cert.not_after.isoformat() if cert.not_after else None}
                    if cert else None
                ),
                "created_at": r.created_at.isoformat(),
            }
        )
    return api_ok(out)


@router.post("")
def create_site(body: CreateSiteBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    domain = webservers.validate_domain(body.domain)
    if db.query(Site).filter(Site.name == domain).first():
        raise PanelError(f"Site '{domain}' already exists.", 400)
    server = body.server if body.server in ("nginx", "apache") else "nginx"
    adapter = webservers.detect_webserver(server)

    root = str(CFG.www_root / domain)
    site = Site(
        name=domain,
        server=server,
        root=root,
        aliases=[],
        php_version=body.php_version,
    )
    Path(root).mkdir(parents=True, exist_ok=True)
    (Path(root) / "index.html").write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{domain}</title></head>"
        f"<body><h1>{domain}</h1><p>Site created by PanelPro.</p></body></html>",
        encoding="utf-8",
    )
    webservers.chown_webroot(root)

    # optional database provisioning
    db_note = ""
    if body.create_db and body.create_db.get("type"):
        from panelpro.services import dbmgr

        db_type = body.create_db["type"]
        manager = dbmgr.get_manager(db_type)
        db_name = dbmgr.validate_ident(body.create_db.get("name") or domain.replace(".", "_").replace("-", "_")[:64], "database name")
        user_name = dbmgr.validate_ident(body.create_db.get("user") or db_name[:32] + "_u", "database user")
        password = body.create_db.get("password")
        if not password:
            from panelpro.core.keyvault import random_password

            password = random_password(16)
        manager.create_database(db_name)
        manager.create_user(user_name, "localhost", password)
        manager.grant(user_name, "localhost", db_name)
        from panelpro.models.tables import DatabaseRow

        db.add(DatabaseRow(name=db_name, type=db_type, owner_user=user_name))
        db_note = {"database": db_name, "user": user_name, "password": password}

    try:
        site.enabled = True
        db.add(site)
        db.commit()
        _render_site(site, db)
    except PanelError:
        db.rollback()
        raise
    adapter.reload()
    notify_event("site_created", "Site created", f"{domain} ({server})")
    return api_ok({"site": {"id": site.id, "name": site.name, "root": site.root}, "db": db_note})


@router.post("/{site_id}/delete")
def delete_site(site_id: int, remove_files: bool = False, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    adapter = webservers.detect_webserver(site.server)
    webservers.remove_vhost(adapter, site.name)
    adapter.reload()
    if remove_files:
        from panelpro.core import fsutil

        fsutil.delete_paths([site.root], use_trash=True)
    db.delete(site)
    db.commit()
    notify_event("site_deleted", "Site deleted", site.name)
    return api_ok({"deleted": site.name})


@router.get("/{site_id}/conf")
def get_conf(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    adapter = webservers.detect_webserver(site.server)
    path = adapter.conf_path(site.name)
    if not path.exists():
        raise PanelError("vhost file not found.", 404)
    return api_ok({"path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")})


@router.post("/{site_id}/conf")
def save_conf(site_id: int, body: ConfBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    adapter = webservers.detect_webserver(site.server)
    path = adapter.conf_path(site.name)
    backup = path.with_suffix(".conf.pp-bak")
    backup.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    path.write_text(body.content, encoding="utf-8")
    try:
        adapter.test_config()
    except PanelError:
        backup.replace(path)
        raise
    adapter.reload()
    return api_ok({"saved": str(path), "backup": str(backup)})


@router.post("/{site_id}/domains")
def add_domain(site_id: int, body: DomainBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    domain = webservers.validate_domain(body.domain)
    aliases = list(site.aliases or [])
    if domain == site.name:
        raise PanelError("That is the primary domain already.", 400)
    if domain not in aliases:
        aliases.append(domain)
    site.aliases = aliases
    db.commit()
    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"aliases": aliases})


@router.post("/{site_id}/domains/remove")
def remove_domain(site_id: int, body: DomainBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    aliases = [a for a in (site.aliases or []) if a != webservers.validate_domain(body.domain)]
    site.aliases = aliases
    db.commit()
    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"aliases": aliases})


@router.post("/{site_id}/proxy")
def set_proxy(site_id: int, body: ProxyBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    target = body.target
    if target and not target.startswith(("http://", "https://")):
        raise PanelError("Proxy target must start with http:// or https://", 400)
    site.proxy_target = target
    db.commit()
    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"proxy_target": target})


@router.post("/{site_id}/php")
def set_php(site_id: int, body: PhpBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    site.php_version = body.version or None
    db.commit()
    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"php_version": site.php_version})


@router.post("/{site_id}/https")
def set_https(site_id: int, body: HttpsBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    site.force_https = body.force
    db.commit()
    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"force_https": site.force_https})


@router.post("/{site_id}/ssl")
def deploy_ssl(site_id: int, body: DeploySslBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    cert = db.query(SslCert).filter(SslCert.id == body.cert_id).first()
    if not cert:
        raise PanelError("Certificate not found.", 404)
    site.ssl_cert_id = cert.id
    db.commit()
    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"deployed": cert.name})


@router.post("/{site_id}/toggle")
def toggle_site(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    site.enabled = not site.enabled
    db.commit()
    adapter = webservers.detect_webserver(site.server)
    if site.enabled:
        adapter.enable(site.name)
    else:
        adapter.disable(site.name)
    adapter.test_config()
    adapter.reload()
    return api_ok({"enabled": site.enabled})


@router.get("/{site_id}/logs")
def site_logs(site_id: int, type: str = "access", lines: int = 200, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    adapter = webservers.detect_webserver(site.server)
    access, error = adapter.log_paths(site.name)
    log_file = access if type == "access" else error
    p = Path(log_file)
    if not p.exists():
        return api_ok({"log": "", "path": log_file})
    with open(p, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 1_000_000))
        content = fh.read().decode("utf-8", errors="replace")
    return api_ok({"log": "\n".join(content.splitlines()[-lines:]), "path": log_file})


@router.post("/reload")
def reload_webserver(ctx=Depends(require_role("operator"))):
    _webserver_action("reload")
    return api_ok({"reloaded": True})


@router.get("/server-status")
def server_status(ctx=Depends(require_auth)):
    adapter = webservers.detect_webserver()
    active = False
    try:
        res = run(["systemctl", "is-active", "--quiet", adapter.unit], check=False)
        active = res.code == 0
    except PanelError:
        pass
    return api_ok({"server": adapter.name, "unit": adapter.unit, "active": active})
