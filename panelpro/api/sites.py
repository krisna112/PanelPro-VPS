"""Website management endpoints (nginx/apache sites)."""

from __future__ import annotations

import logging
from contextlib import ExitStack, suppress
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.config import CFG
from panelpro.core import certs, keyvault
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.core.notify import notify_event
from panelpro.core.syscmd import run
from panelpro.models.tables import (
    DatabaseRow,
    DbUser,
    Setting,
    Site,
    SslCert,
    TamperWatch,
    Upstream,
    WafProfile,
)
from panelpro.services import dbmgr, lb, traffic, waf, webservers

router = APIRouter(prefix="/api/sites", tags=["sites"])
log = logging.getLogger(__name__)


class SiteDatabaseBody(BaseModel):
    type: Literal["mysql", "postgres"] = "mysql"
    name: str = ""
    user: str = ""
    password: str | None = None


class CreateSiteBody(BaseModel):
    domain: str
    aliases: list[str] = []
    server: Literal["nginx", "apache"] = "nginx"
    php_version: str | None = None
    proxy_target: str | None = None
    create_db: SiteDatabaseBody | None = None


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


def _get_site(db: Session, site_id: int) -> Site:
    site = db.get(Site, site_id)
    if not site:
        raise PanelError("Site not found.", 404)
    return site


def _check_domains(db: Session, domains: list[str], site_id: int | None = None) -> None:
    requested = set(domains)
    panel_domain = db.get(Setting, "panel_domain")
    if panel_domain and panel_domain.value in requested:
        raise PanelError(f"Domain '{panel_domain.value}' is reserved for the PanelPro login.", 409)
    for site in db.query(Site).all():
        if site.id == site_id:
            continue
        if conflict := requested.intersection([site.name, *(site.aliases or [])]):
            raise PanelError(f"Domain '{min(conflict)}' already belongs to {site.name}.", 409)


def _proxy_target(db: Session, target: str | None, server: str) -> str | None:
    if not target:
        return None
    if target.startswith("upstream:"):
        name = lb.validate_name(target.split(":", 1)[1])
        if server != "nginx" or db.query(Upstream).filter_by(name=name).first() is None:
            raise PanelError("Select an existing nginx upstream pool.", 400)
        return f"upstream:{name}"
    return webservers.validate_proxy_target(target, server)


def _render_site(site: Site, db: Session, adapter: webservers.WebserverAdapter) -> None:
    cert = db.get(SslCert, site.ssl_cert_id) if site.ssl_cert_id else None
    profile = db.query(WafProfile).filter_by(site_id=site.id).first()
    webservers.write_vhost(
        adapter, site.name, site.aliases or [], site.root, site.php_version,
        site.proxy_target, site.force_https,
        cert.cert_path if cert else None, cert.key_path if cert else None,
        enabled=site.enabled,
        waf_include=str(waf.site_conf_path(site.name)) if profile and profile.enabled else None,
    )


def _apply_site(site: Site, db: Session, adapter: webservers.WebserverAdapter | None = None) -> None:
    adapter = adapter or webservers.detect_webserver(site.server)
    try:
        with webservers.config_transaction(adapter, adapter.config_paths(site.name)) as apply:
            db.flush()
            _render_site(site, db, adapter)
            apply()
            db.commit()
    except Exception:
        db.rollback()
        raise


def _cleanup_failed_create(callback, *args) -> None:
    try:
        callback(*args)
    except (OSError, PanelError):
        log.exception("Failed to roll back a website provisioning step")


def _provision_db(db: Session, body: SiteDatabaseBody, domain: str, rollback: ExitStack) -> dict:
    manager = dbmgr.get_manager(body.type)
    default_name = domain.replace(".", "_").replace("-", "_")[:63]
    db_name = dbmgr.validate_ident(body.name or default_name, "database name")
    max_user_length = 32 if body.type == "mysql" else 63
    user = dbmgr.validate_ident(body.user or db_name[:max_user_length - 2] + "_u", "database user")
    if len(user) > max_user_length or (body.type == "postgres" and len(db_name) > 63):
        raise PanelError("Database name or user is too long for this engine.", 400)
    password = body.password or keyvault.random_password(16)
    manager.create_database(db_name)
    rollback.callback(_cleanup_failed_create, manager.delete_database, db_name)
    manager.create_user(user, "localhost", password)
    rollback.callback(_cleanup_failed_create, manager.delete_user, user, "localhost")
    manager.grant(user, "localhost", db_name)
    charset = "utf8mb4" if body.type == "mysql" else "UTF8"
    db.add(DatabaseRow(name=db_name, type=body.type, owner_user=user, charset=charset))
    db.add(DbUser(name=user, type=body.type, host="localhost", password_enc=keyvault.encrypt_str(password)))
    return {"database": db_name, "user": user, "password": password}


@router.get("")
def list_sites(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(Site).order_by(Site.created_at.desc()).all()
    cert_ids = {row.ssl_cert_id for row in rows if row.ssl_cert_id is not None}
    certs = {cert.id: cert for cert in db.query(SslCert).filter(SslCert.id.in_(cert_ids)).all()}
    out = []
    for row in rows:
        cert = certs.get(row.ssl_cert_id)
        out.append({
            "id": row.id,
            "name": row.name,
            "server": row.server,
            "root": row.root,
            "aliases": row.aliases,
            "php_version": row.php_version,
            "proxy_target": row.proxy_target,
            "force_https": row.force_https,
            "enabled": row.enabled,
            "ssl": ({
                "cert_id": cert.id, "issuer": cert.issuer,
                "not_after": cert.not_after.isoformat() if cert.not_after else None,
            } if cert else None),
            "created_at": row.created_at.isoformat(),
        })
    return api_ok(out)


@router.post("")
def create_site(body: CreateSiteBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    domain = webservers.validate_domain(body.domain)
    if domain.startswith("*."):
        raise PanelError("Use a concrete primary domain. Wildcards can be added as aliases.", 400)
    aliases = list(dict.fromkeys(webservers.validate_domain(alias) for alias in body.aliases if alias.strip()))
    aliases = [alias for alias in aliases if alias != domain]
    with webservers.CONFIG_LOCK:
        _check_domains(db, [domain, *aliases])
        adapter = webservers.detect_webserver(body.server)
        if any(path.exists() or path.is_symlink() for path in adapter.config_paths(domain)):
            raise PanelError(f"A webserver configuration for '{domain}' already exists.", 409)
        php_version = webservers.validate_php_runtime(body.php_version)
        proxy_target = _proxy_target(db, body.proxy_target, body.server)
        root = CFG.www_root / domain
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise PanelError("Site root must be a regular directory.", 409)
        site = Site(name=domain, server=body.server, root=str(root), aliases=aliases,
                    php_version=php_version, proxy_target=proxy_target, enabled=True)
        with ExitStack() as rollback:
            if not root.exists():
                root.mkdir()
                rollback.callback(_cleanup_failed_create, root.rmdir)
                if not proxy_target:
                    index = root / "index.html"
                    with index.open("x", encoding="utf-8") as file:
                        rollback.callback(_cleanup_failed_create, index.unlink)
                        file.write(f"<!doctype html><meta charset='utf-8'><title>{domain}</title>"
                                   f"<h1>{domain}</h1><p>Site created by PanelPro.</p>")
                    if php_version:
                        webservers.chown_webroot(str(root))
            db_note = _provision_db(db, body.create_db, domain, rollback) if body.create_db else None
            db.add(site)
            _apply_site(site, db, adapter)
            rollback.pop_all()
    notify_event("site_created", "Site created", f"{domain} ({site.server})")
    return api_ok({"site": {"id": site.id, "name": site.name, "root": site.root}, "db": db_note})


@router.post("/{site_id}/delete")
def delete_site(site_id: int, remove_files: bool = False, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    with webservers.CONFIG_LOCK:
        site = _get_site(db, site_id)
        adapter = webservers.detect_webserver(site.server)
        profile = db.query(WafProfile).filter_by(site_id=site.id).first()
        waf_paths = []
        if profile and site.server == "nginx":
            waf_paths = [waf.zone_conf_path(site.name), waf.site_conf_path(site.name)]
        paths = [*adapter.config_paths(site.name), *waf_paths]
        with webservers.config_transaction(adapter, paths) as apply:
            webservers.remove_vhost(adapter, site.name)
            for path in waf_paths:
                path.unlink(missing_ok=True)
            if profile:
                db.delete(profile)
            db.query(TamperWatch).filter_by(site_id=site.id).delete()
            traffic.reset_site(db, site.id)
            db.delete(site)
            apply()
            db.commit()
        warning = None
        if remove_files:
            from panelpro.core import fsutil

            try:
                if Path(site.root).exists():
                    fsutil.delete_paths([site.root], use_trash=True)
            except (OSError, PanelError):
                log.exception("Failed to move website files to trash")
                warning = "Website removed. Its files could not be moved to trash."
    notify_event("site_deleted", "Site deleted", site.name)
    return api_ok({"deleted": site.name, **({"warning": warning} if warning else {})})


@router.get("/{site_id}/conf")
def get_conf(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    with webservers.CONFIG_LOCK:
        site = _get_site(db, site_id)
        adapter = webservers.detect_webserver(site.server)
        path = adapter.editable_path(site.name)
        if not path.is_file():
            raise PanelError("vhost file not found.", 404)
        return api_ok({"path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")})


@router.post("/{site_id}/conf")
@webservers.serialized
def save_conf(site_id: int, body: ConfBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    site = _get_site(db, site_id)
    adapter = webservers.detect_webserver(site.server)
    path = adapter.editable_path(site.name)
    if not path.is_file():
        raise PanelError("vhost file not found.", 404)
    if not site.enabled:
        raise PanelError("Enable the website to validate and edit its configuration.", 409)
    backup = adapter.conf_path(site.name).with_suffix(".conf.pp-bak")
    with webservers.config_transaction(adapter, [path, backup]) as apply:
        webservers.write_config(backup, path.read_bytes(), 0o600)
        webservers.write_config(path, body.content.encode("utf-8"))
        apply()
    return api_ok({"saved": str(path), "backup": str(backup)})


@router.post("/{site_id}/domains")
@webservers.serialized
def add_domain(site_id: int, body: DomainBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    domain = webservers.validate_domain(body.domain)
    aliases = list(site.aliases or [])
    if domain == site.name:
        raise PanelError("That is the primary domain already.", 400)
    if domain not in aliases:
        _check_domains(db, [domain], site.id)
        site.aliases = [*aliases, domain]
        _apply_site(site, db)
    return api_ok({"aliases": site.aliases or []})


@router.post("/{site_id}/domains/remove")
@webservers.serialized
def remove_domain(site_id: int, body: DomainBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    domain = webservers.validate_domain(body.domain)
    if domain in (site.aliases or []):
        site.aliases = [alias for alias in site.aliases if alias != domain]
        _apply_site(site, db)
    return api_ok({"aliases": site.aliases or []})


@router.post("/{site_id}/proxy")
@webservers.serialized
def set_proxy(site_id: int, body: ProxyBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    site.proxy_target = _proxy_target(db, body.target, site.server)
    _apply_site(site, db)
    return api_ok({"proxy_target": site.proxy_target})


@router.post("/{site_id}/php")
@webservers.serialized
def set_php(site_id: int, body: PhpBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    site.php_version = webservers.validate_php_runtime(body.version)
    _apply_site(site, db)
    return api_ok({"php_version": site.php_version})


@router.post("/{site_id}/https")
@webservers.serialized
def set_https(site_id: int, body: HttpsBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    if body.force and not (site.ssl_cert_id and db.get(SslCert, site.ssl_cert_id)):
        raise PanelError("Deploy a certificate before forcing HTTPS.", 400)
    site.force_https = body.force
    _apply_site(site, db)
    return api_ok({"force_https": site.force_https})


def _attach_certificate(db: Session, site_id: int, cert: SslCert) -> Site:
    with webservers.CONFIG_LOCK:
        site = _get_site(db, site_id)
        try:
            info = certs.parse_cert_file(cert.cert_path)
        except OSError as exc:
            raise PanelError("Certificate file is unavailable.", 409) from exc
        if not datetime.fromisoformat(info["not_before"]) <= datetime.utcnow() < datetime.fromisoformat(info["not_after"]):
            raise PanelError("This certificate is outside its validity period.", 400)
        names = {name.lower() for name in info["dns_names"] or [info["subject"]]}
        for domain in [site.name, *(site.aliases or [])]:
            wildcard = "*." + domain.partition(".")[2]
            if domain not in names and wildcard not in names:
                raise PanelError(f"The certificate does not cover '{domain}'.", 400)
        site.ssl_cert_id = cert.id
        _apply_site(site, db)
        return site


@router.post("/{site_id}/ssl")
def deploy_ssl(site_id: int, body: DeploySslBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    with webservers.CONFIG_LOCK:
        cert = db.get(SslCert, body.cert_id)
        if not cert:
            raise PanelError("Certificate not found.", 404)
        _attach_certificate(db, site_id, cert)
        return api_ok({"deployed": cert.name})


@router.post("/{site_id}/ssl/remove")
@webservers.serialized
def detach_ssl(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    site.ssl_cert_id = None
    site.force_https = False
    _apply_site(site, db)
    return api_ok({"ssl": None, "force_https": False})


@router.post("/{site_id}/toggle")
@webservers.serialized
def toggle_site(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = _get_site(db, site_id)
    adapter = webservers.detect_webserver(site.server)
    with webservers.config_transaction(adapter, adapter.config_paths(site.name)) as apply:
        site.enabled = not site.enabled
        if adapter.editable_path(site.name).exists():
            (adapter.enable if site.enabled else adapter.disable)(site.name)
        else:
            _render_site(site, db, adapter)
        apply()
        db.commit()
    return api_ok({"enabled": site.enabled})


@router.get("/{site_id}/logs")
def site_logs(site_id: int, type: Literal["access", "error"] = "access",
              lines: int = Query(200, ge=1, le=5000), db: Session = Depends(get_db), ctx=Depends(require_auth)):
    site = _get_site(db, site_id)
    adapter = webservers.detect_webserver(site.server)
    access, error = adapter.log_paths(site.name)
    log_file = access if type == "access" else error
    content = ""
    with suppress(FileNotFoundError), open(log_file, "rb") as file:
        file.seek(0, 2)
        file.seek(max(0, file.tell() - 1_000_000))
        content = file.read().decode("utf-8", errors="replace")
    return api_ok({"log": "\n".join(content.splitlines()[-lines:]), "path": log_file})


@router.post("/reload")
@webservers.serialized
def reload_webserver(server: Literal["nginx", "apache"] | None = None, ctx=Depends(require_role("operator"))):
    adapter = webservers.detect_webserver(server)
    adapter.test_config()
    adapter.reload()
    return api_ok({"reloaded": True})


@router.get("/server-status")
def server_status(ctx=Depends(require_auth)):
    servers = []
    for server in webservers.ADAPTERS:
        try:
            adapter = webservers.detect_webserver(server)
        except PanelError:
            continue
        active = False
        with suppress(PanelError):
            active = run(["systemctl", "is-active", "--quiet", adapter.unit]).ok
        servers.append({"server": adapter.name, "unit": adapter.unit, "active": active})
    primary = next((entry for entry in servers if entry["active"]), servers[0] if servers else {})
    return api_ok({"server": None, "unit": None, "active": False, **primary, "servers": servers})
