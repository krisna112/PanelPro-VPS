"""User & API key management endpoints (admin)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_role
from panelpro.constants import ROLES
from panelpro.core import security
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import ApiKey, User

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = "operator"


class UpdateUserBody(BaseModel):
    password: str | None = None
    role: str | None = None


class ApiKeyBody(BaseModel):
    name: str
    role: str = "operator"


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise PanelError(f"Unknown role: {role}", 400)
    return role


def _count_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "admin").count()


@router.get("")
def list_users(db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    rows = db.query(User).order_by(User.created_at.asc()).all()
    return api_ok(
        [
            {
                "id": r.id,
                "username": r.username,
                "role": r.role,
                "totp_enabled": r.totp_enabled,
                "last_login_at": r.last_login_at.isoformat() if r.last_login_at else None,
                "last_login_ip": r.last_login_ip,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@router.post("")
def create_user(body: CreateUserBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    if not re.match(r"^[a-zA-Z0-9_.-]{3,32}$", body.username):
        raise PanelError("Username must be 3-32 chars (letters, digits, . _ -).", 400)
    if len(body.password) < 8:
        raise PanelError("Password must be at least 8 characters.", 400)
    _validate_role(body.role)
    if db.query(User).filter(User.username == body.username).first():
        raise PanelError("Username already exists.", 400)
    user = User(
        username=body.username,
        password_hash=security.hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    return api_ok({"id": user.id, "username": user.username, "role": user.role})


@router.post("/{user_id}/update")
def update_user(user_id: int, body: UpdateUserBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise PanelError("User not found.", 404)
    if body.password is not None:
        if len(body.password) < 8:
            raise PanelError("Password must be at least 8 characters.", 400)
        user.password_hash = security.hash_password(body.password)
        security.destroy_all_sessions(db, user.id)
    if body.role is not None:
        _validate_role(body.role)
        if user.role == "admin" and body.role != "admin" and _count_admins(db) <= 1:
            raise PanelError("Cannot demote the last admin.", 400)
        user.role = body.role
    db.commit()
    return api_ok({"updated": user.username})


@router.post("/{user_id}/delete")
def delete_user(user_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise PanelError("User not found.", 404)
    if user.id == ctx.user.id:
        raise PanelError("You cannot delete your own account.", 400)
    if user.role == "admin" and _count_admins(db) <= 1:
        raise PanelError("Cannot delete the last admin.", 400)
    security.destroy_all_sessions(db, user.id)
    db.delete(user)
    db.commit()
    return api_ok({"deleted": user.username})


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


@router.get("/keys")
def list_keys(db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    rows = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return api_ok(
        [
            {
                "id": r.id,
                "name": r.name,
                "role": r.role,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@router.post("/keys")
def create_key(body: ApiKeyBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    _validate_role(body.role)
    raw = security.generate_api_key()
    row = ApiKey(name=body.name[:100], key_hash=security.hash_api_key(raw), role=body.role)
    db.add(row)
    db.commit()
    return api_ok({"id": row.id, "name": row.name, "key": raw,
                   "note": "Copy this key now — it is shown only once."})


@router.post("/keys/{key_id}/delete")
def delete_key(key_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not row:
        raise PanelError("API key not found.", 404)
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.name})
