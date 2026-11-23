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
                {"type": row.type, "app_id": row.app_id, "port": row.port}
            ),
            "created_at": row.created_at.isoformat(),
        }
        installed.append(payload)
    return api_ok({"available": available, "installed": installed})


@router.post("/install")
def install(body: InstallBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    manifest = apps_svc.load_manifest(body.app_id)
    result = apps_svc.install(manifest, body.params)
    row = InstalledApp(
        app_id=manifest["id"],
        name=manifest["name"],
        version=manifest.get("version", ""),
        type=manifest.get("type", "script"),
        install_path=result.get("app_home", ""),
        port=manifest.get("port"),
        domain=body.params.get("domain"),
    )
    db.add(row)
    db.commit()
    notify_event("app_installed", "App installed",
                 f"{manifest['name']} ({manifest.get('version', '')}) installed.")
    return api_ok({"installed": manifest["name"], "detail": result})


@router.post("/{app_row_id}/uninstall")
def uninstall(app_row_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(InstalledApp).filter(InstalledApp.id == app_row_id).first()
    if not row:
        raise PanelError("Installed app not found.", 404)
    try:
        manifest = apps_svc.load_manifest(row.app_id)
    except PanelError:
        manifest = {"id": row.app_id, "type": row.type, "name": row.name}
    result = apps_svc.uninstall(manifest, row.install_path)
    db.delete(row)
    db.commit()
    return api_ok(result)


@router.post("/{app_row_id}/status")
def refresh_status(app_row_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    row = db.query(InstalledApp).filter(InstalledApp.id == app_row_id).first()
    if not row:
        raise PanelError("Installed app not found.", 404)
    status = apps_svc.app_status({"type": row.type, "app_id": row.app_id, "port": row.port})
    row.status = status
    db.commit()
    return api_ok({"status": status})
