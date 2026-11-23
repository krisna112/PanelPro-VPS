"""Shared FastAPI dependencies: authentication, roles, response helpers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from panelpro.constants import CSRF_HEADER, ROLES, SESSION_COOKIE
from panelpro.core import security, settings_store
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import ApiKey, User

MUTATING = ("POST", "PUT", "DELETE", "PATCH")


@dataclass
class AuthCtx:
    user: User | None
    key: ApiKey | None
    role: str

    @property
    def username(self) -> str:
        if self.user is not None:
            return self.user.username
        if self.key is not None:
            return f"apikey:{self.key.name}"
        return ""


def client_ip(request: Request) -> str:
    if settings_store.get_setting("trust_proxy"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def authenticate(db: Session, request: Request) -> AuthCtx | None:
    """Resolve the caller from the session cookie or an API key."""
    token = request.cookies.get(SESSION_COOKIE, "")
    session = security.get_session(db, token)
    if session is not None:
        user = security.get_user_by_id(db, session.user_id)
        if user is not None:
            return AuthCtx(user=user, key=None, role=user.role)

    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        key = security.verify_api_key(db, header[7:].strip())
        if key is not None:
            if not settings_store.get_setting("api_enabled", True):
                raise PanelError("API access is disabled in settings.", 403)
            return AuthCtx(user=None, key=key, role=key.role)
    return None


def require_auth(request: Request, db: Session = Depends(get_db)) -> AuthCtx:
    ctx = authenticate(db, request)
    if ctx is None:
        raise PanelError("Not authenticated.", 401)
    # CSRF defence for cookie-based sessions: browsers cannot set custom
    # headers cross-site without a preflight we never allow.
    if request.method in MUTATING and ctx.key is None:
        if request.headers.get(CSRF_HEADER) != "1":
            raise PanelError("Missing CSRF protection header.", 403)
    request.scope["pp_user"] = ctx.username
    return ctx


def require_role(minimum: str):
    """Dependency factory: viewer < operator < admin."""
    min_rank = ROLES.get(minimum, 0)

    def checker(ctx: AuthCtx = Depends(require_auth)) -> AuthCtx:
        if ROLES.get(ctx.role, -1) < min_rank:
            raise PanelError("Insufficient permissions for this action.", 403)
        return ctx

    return checker


def api_ok(data=None, **extra) -> dict:
    return {"ok": True, "data": data, **extra}
