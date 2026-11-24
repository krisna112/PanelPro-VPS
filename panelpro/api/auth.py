"""Authentication endpoints: login, sessions, password, 2FA."""

from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, client_ip, require_auth
from panelpro.constants import (
    LOGIN_LOCK_MINUTES,
    LOGIN_MAX_ATTEMPTS,
    SESSION_COOKIE,
    SESSION_TTL_HOURS,
)
from panelpro.core import notify, security
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str
    otp: str | None = None


class PasswordBody(BaseModel):
    current: str
    new: str


class OtpBody(BaseModel):
    code: str


@router.post("/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if security.recent_failed_logins(db, ip, LOGIN_LOCK_MINUTES) >= LOGIN_MAX_ATTEMPTS:
        raise PanelError("Too many failed attempts. Try again in a few minutes.", 429)

    user = security.get_user(db, body.username.strip())
    if user is None or not security.verify_password(body.password, user.password_hash):
        security.record_login_attempt(db, ip, body.username, False)
        notify.notify_event(
            "login_failed", "Failed login attempt",
            f"IP {ip} tried to log in as '{body.username[:32]}'.",
        )
        raise PanelError("Invalid username or password.", 401)

    if user.totp_enabled:
        if not security.verify_totp(user.totp_secret, body.otp or ""):
            raise PanelError("A valid 2FA code is required.", 401)

    token, expires = security.create_session(
        db, user.id, ip, request.headers.get("user-agent", "")
    )
    security.record_login_attempt(db, ip, body.username, True)
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = ip
    db.commit()
    notify.notify_event(
        "login_success", "Panel login", f"'{user.username}' logged in from {ip}."
    )

    secure = request.url.scheme == "https"
    resp = JSONResponse(api_ok({"username": user.username, "role": user.role}))
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return resp


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        security.destroy_session(db, token)
    resp = JSONResponse(api_ok({"logged_out": True}))
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/me")
def me(ctx=Depends(require_auth)):
    user = ctx.user
    return api_ok(
        {
            "username": user.username if user else ctx.username,
            "role": ctx.role,
            "totp_enabled": bool(user.totp_enabled) if user else False,
        }
    )


@router.get("/sessions")
def list_sessions(request: Request, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    from panelpro.models.tables import SessionRow

    rows = (
        db.query(SessionRow)
        .filter(SessionRow.user_id == ctx.user.id)
        .order_by(SessionRow.created_at.desc())
        .all()
    )
    current = request.cookies.get(SESSION_COOKIE, "")
    return api_ok(
        [
            {
                "id": r.id,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat(),
                "expires_at": r.expires_at.isoformat(),
                "current": r.token == current,
            }
            for r in rows
        ]
    )


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    from panelpro.models.tables import SessionRow

    row = db.query(SessionRow).filter(
        SessionRow.id == session_id, SessionRow.user_id == ctx.user.id
    ).first()
    if row is None:
        raise PanelError("Session not found.", 404)
    db.delete(row)
    db.commit()
    return api_ok({"revoked": session_id})


@router.post("/sessions/revoke-others")
def revoke_others(request: Request, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    security.destroy_all_sessions(db, ctx.user.id, except_token=request.cookies.get(SESSION_COOKIE))
    return api_ok({"revoked": "others"})


@router.post("/password")
def change_password(body: PasswordBody, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    if not security.verify_password(body.current, ctx.user.password_hash):
        raise PanelError("Current password is incorrect.", 401)
    if len(body.new) < 8:
        raise PanelError("New password must be at least 8 characters.", 400)
    ctx.user.password_hash = security.hash_password(body.new)
    db.commit()
    security.destroy_all_sessions(db, ctx.user.id)
    return api_ok({"changed": True, "note": "All sessions were revoked; log in again."})


@router.post("/2fa/setup")
def twofa_setup(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    if ctx.user.totp_enabled:
        raise PanelError("2FA is already enabled.", 400)
    secret = security.new_totp_secret()
    ctx.user.totp_secret = secret
    db.commit()
    uri = security.totp_uri(secret, ctx.user.username)
    qr_svg = None
    try:
        import qrcode
        import qrcode.image.svg

        img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        qr_svg = buf.getvalue().decode()
    except Exception:
        qr_svg = None
    return api_ok({"secret": secret, "uri": uri, "qr_svg": qr_svg})


@router.post("/2fa/enable")
def twofa_enable(body: OtpBody, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    if not ctx.user.totp_secret:
        raise PanelError("Run setup first.", 400)
    if not security.verify_totp(ctx.user.totp_secret, body.code):
        raise PanelError("Invalid code.", 400)
    ctx.user.totp_enabled = True
    db.commit()
    return api_ok({"enabled": True})


@router.post("/2fa/disable")
def twofa_disable(body: OtpBody, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    if not ctx.user.totp_enabled:
        raise PanelError("2FA is not enabled.", 400)
    if not security.verify_totp(ctx.user.totp_secret, body.code):
        raise PanelError("Invalid code.", 400)
    ctx.user.totp_enabled = False
    ctx.user.totp_secret = None
    db.commit()
    return api_ok({"enabled": False})
