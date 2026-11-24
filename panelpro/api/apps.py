"""App store endpoints: one-click installers from JSON manifests."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.core.notify import notify_event
from panelpro.models.tables import InstalledApp
from panelpro.services import apps as apps_svc

router = APIRouter(prefix="/api/apps", tags=["apps"])


class InstallBody(BaseModel):
    app_id: str
    params: dict = {}


class UninstallBody(BaseModel):
    pass


@router.get("")
def list_apps(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    available = apps_svc.list_manifests()
    installed_rows = db.query(InstalledApp).order_by(InstalledApp.created_at.desc()).all()
    installed = []
    for row in installed_rows:
        payload = {
            "id": row.id,
            "app_id": row.app_id,
            "name": row.name,
            "version": row.version,
            "type": row.type,
            "install_path": row.install_path,
            "port": row.port,
            "domain": row.domain,
            "status": apps_svc.app_status(
                {"type": row.type, "app_id": row.app_id, "port": row.port, "status": row.status}
            ),
            "loopback": row.app_id == "phpmyadmin" and row.type == "native",
            "created_at": row.created_at.isoformat(),
        }
        installed.append(payload)
    return api_ok({"available": available, "installed": installed})


@router.post("/install")
def install(body: InstallBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    manifest = apps_svc.load_manifest(body.app_id)
    if manifest.get("type") == "native" and ctx.role != "admin":
        raise PanelError("Administrator access is required to install system packages.", 403)
    row, result = apps_svc.install_app(db, manifest, body.params)
    notify_event("app_installed", "App installed",
                 f"{row.name} ({row.version}) installed.")
    return api_ok({"installed": manifest["name"], "detail": result})


@router.post("/{app_row_id}/uninstall")
def uninstall(app_row_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(InstalledApp).filter(InstalledApp.id == app_row_id).first()
    if not row:
        raise PanelError("Installed app not found.", 404)
    if row.type == "native" and ctx.role != "admin":
        raise PanelError("Administrator access is required to remove native app access.", 403)
    try:
        manifest = apps_svc.load_manifest(row.app_id)
    except PanelError:
        manifest = {"id": row.app_id, "type": row.type, "name": row.name}
    if manifest.get("type") != row.type:
        raise PanelError("This app entry was created by an older installer and requires manual removal.", 409)
    result = apps_svc.uninstall(manifest, row.install_path)
    db.delete(row)
    db.commit()
    return api_ok(result)


@router.post("/{app_row_id}/status")
def refresh_status(app_row_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    row = db.query(InstalledApp).filter(InstalledApp.id == app_row_id).first()
    if not row:
        raise PanelError("Installed app not found.", 404)
    status = apps_svc.app_status({"type": row.type, "app_id": row.app_id, "port": row.port, "status": row.status})
    row.status = status
    db.commit()
    return api_ok({"status": status})
