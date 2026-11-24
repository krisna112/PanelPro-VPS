"""Fleet (multi-server) endpoints: manage remote PanelPro nodes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_role
from panelpro.core import keyvault
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import RemoteServer
from panelpro.services import fleet as fleet_svc

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


class ServerBody(BaseModel):
    name: str
    base_url: str
    entry_path: str = ""
    api_key: str = ""  # plaintext in, encrypted at rest
    enabled: bool = True


@router.get("")
def list_servers(db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    rows = db.query(RemoteServer).order_by(RemoteServer.created_at.desc()).all()
    return api_ok({"servers": [fleet_svc.payload(r) for r in rows]})


@router.get("/overview")
def overview(db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    return api_ok(fleet_svc.overview(db))


@router.post("")
def create_server(body: ServerBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    base_url = fleet_svc.validate_base_url(body.base_url)
    row = RemoteServer(
        name=body.name[:100],
        base_url=base_url,
        entry_path=(body.entry_path or "").strip()[:64],
        api_key_enc=keyvault.encrypt_str(body.api_key) if body.api_key else "",
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    return api_ok(fleet_svc.payload(row))


@router.post("/{server_id}/update")
def update_server(server_id: int, body: ServerBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(RemoteServer).filter(RemoteServer.id == server_id).first()
    if not row:
        raise PanelError("Server not found.", 404)
    row.name = body.name[:100]
    row.base_url = fleet_svc.validate_base_url(body.base_url)
    row.entry_path = (body.entry_path or "").strip()[:64]
    row.enabled = body.enabled
    if body.api_key:  # only overwrite when a new key is provided
        row.api_key_enc = keyvault.encrypt_str(body.api_key)
    db.commit()
    return api_ok(fleet_svc.payload(row))


@router.post("/{server_id}/delete")
def delete_server(server_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(RemoteServer).filter(RemoteServer.id == server_id).first()
    if not row:
        raise PanelError("Server not found.", 404)
    name = row.name
    db.delete(row)
    db.commit()
    return api_ok({"deleted": name})


@router.post("/{server_id}/test")
def test_server(server_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(RemoteServer).filter(RemoteServer.id == server_id).first()
    if not row:
        raise PanelError("Server not found.", 404)
    try:
        return api_ok(fleet_svc.test_server(db, row))
    except PanelError:
        raise
    except Exception as exc:
        raise PanelError(f"Connection failed: {str(exc)[:200]}", 502) from exc


@router.get("/{server_id}/sites")
def remote_sites(server_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(RemoteServer).filter(RemoteServer.id == server_id).first()
    if not row:
        raise PanelError("Server not found.", 404)
    return api_ok({"sites": fleet_svc.call(row, "GET", "/api/sites")})
