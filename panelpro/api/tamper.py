"""Tamper protection endpoints: file-integrity watches per site."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import Site, TamperWatch
from panelpro.services import tamper as tamper_svc

router = APIRouter(prefix="/api/tamper", tags=["tamper"])


class TamperBody(BaseModel):
    site_id: int
    enabled: bool = True
    mode: str = "alert"  # alert | auto_restore


@router.get("")
def list_watches(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(TamperWatch).all()
    return api_ok({"watches": [tamper_svc.watch_payload(r) for r in rows],
                   "modes": ["alert", "auto_restore"]})


@router.post("")
def upsert_watch(body: TamperBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == body.site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    if body.mode not in ("alert", "auto_restore"):
        raise PanelError("Mode must be 'alert' or 'auto_restore'.", 400)
    row = db.query(TamperWatch).filter(TamperWatch.site_id == body.site_id).first()
    if row is None:
        row = TamperWatch(site_id=body.site_id)
        db.add(row)
    row.enabled = body.enabled
    row.mode = body.mode
    db.commit()
    return api_ok(tamper_svc.watch_payload(row))


@router.post("/{watch_id}/baseline")
def build_baseline(watch_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(TamperWatch).filter(TamperWatch.id == watch_id).first()
    if not row:
        raise PanelError("Watch not found.", 404)
    return api_ok(tamper_svc.build_baseline(db, row))


@router.post("/{watch_id}/scan")
def scan_now(watch_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(TamperWatch).filter(TamperWatch.id == watch_id).first()
    if not row:
        raise PanelError("Watch not found.", 404)
    return api_ok(tamper_svc.scan(db, row))


@router.post("/{watch_id}/delete")
def delete_watch(watch_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(TamperWatch).filter(TamperWatch.id == watch_id).first()
    if not row:
        raise PanelError("Watch not found.", 404)
    import shutil

    shutil.rmtree(tamper_svc.snapshot_dir(row.site_id), ignore_errors=True)
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.id})
