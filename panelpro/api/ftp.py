"""FTP account endpoints (pure-ftpd / proftpd)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import FtpUser
from panelpro.services import ftpmgr

router = APIRouter(prefix="/api/ftp", tags=["ftp"])


class CreateFtpBody(BaseModel):
    name: str
    password: str
    directory: str


class FtpPasswordBody(BaseModel):
    password: str


@router.get("")
def list_ftp(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    backend = ftpmgr.detect_backend()
    rows = db.query(FtpUser).order_by(FtpUser.created_at.desc()).all()
    return api_ok(
        {
            "backend": backend,
            "users": [
                {
                    "id": r.id,
                    "name": r.name,
                    "directory": r.directory,
                    "backend": r.backend,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }
    )


@router.post("")
def create_ftp(body: CreateFtpBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    import re

    if not re.match(r"^[a-zA-Z0-9._-]{2,64}$", body.name):
        raise PanelError("Invalid FTP username (letters, digits, . _ - only).", 400)
    if len(body.password) < 8:
        raise PanelError("Password must be at least 8 characters.", 400)
    manager = ftpmgr.FtpManager()
    manager.add_user(body.name, body.password, body.directory)
    row = FtpUser(name=body.name, directory=body.directory, backend=manager.backend)
    db.add(row)
    db.commit()
    return api_ok({"id": row.id, "name": body.name})


@router.post("/{ftp_id}/password")
def change_password(ftp_id: int, body: FtpPasswordBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    if len(body.password) < 8:
        raise PanelError("Password must be at least 8 characters.", 400)
    row = db.query(FtpUser).filter(FtpUser.id == ftp_id).first()
    if not row:
        raise PanelError("FTP user not found.", 404)
    manager = ftpmgr.FtpManager()
    manager.set_password(row.name, body.password)
    return api_ok({"user": row.name, "changed": True})


@router.post("/{ftp_id}/delete")
def delete_ftp(ftp_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(FtpUser).filter(FtpUser.id == ftp_id).first()
    if not row:
        raise PanelError("FTP user not found.", 404)
    manager = ftpmgr.FtpManager()
    manager.delete_user(row.name)
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.name})
