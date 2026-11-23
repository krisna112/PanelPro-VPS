"""Authentication primitives: passwords, sessions, API keys, TOTP.

Sessions are opaque random tokens stored server-side in SQLite and sent to
the browser as an HttpOnly cookie.  API keys are stored only as SHA-256
hashes.  Two-factor authentication uses TOTP (RFC 6238) via pyotp.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import bcrypt
import pyotp

from panelpro.constants import SESSION_TTL_HOURS
from panelpro.core.keyvault import token_hex
from panelpro.models.tables import ApiKey, LoginAttempt, SessionRow, User

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(db, user_id: int, ip: str, user_agent: str) -> tuple[str, datetime]:
    token = token_hex(32)
    expires = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
    db.add(
        SessionRow(
            token=token,
            user_id=user_id,
            ip=ip[:64],
            user_agent=user_agent[:255],
            expires_at=expires,
        )
    )
    db.commit()
    return token, expires


def get_session(db, token: str) -> SessionRow | None:
    if not token:
        return None
    row = db.query(SessionRow).filter(SessionRow.token == token).first()
    if row is None or row.expires_at < datetime.utcnow():
        return None
    return row


def destroy_session(db, token: str) -> None:
    db.query(SessionRow).filter(SessionRow.token == token).delete()
    db.commit()


def destroy_all_sessions(db, user_id: int, except_token: str | None = None) -> None:
    q = db.query(SessionRow).filter(SessionRow.user_id == user_id)
    if except_token:
        q = q.filter(SessionRow.token != except_token)
    q.delete(synchronize_session=False)
    db.commit()


def purge_expired_sessions(db) -> int:
    removed = (
        db.query(SessionRow).filter(SessionRow.expires_at < datetime.utcnow()).delete()
    )
    db.commit()
    return removed


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def generate_api_key() -> str:
    from panelpro.constants import API_KEY_PREFIX

    return API_KEY_PREFIX + token_hex(24)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(db, raw_key: str) -> ApiKey | None:
    if not raw_key:
        return None
    row = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(raw_key)).first()
    if row is not None:
        row.last_used_at = datetime.utcnow()
        db.commit()
    return row


# ---------------------------------------------------------------------------
# TOTP (two-factor authentication)
# ---------------------------------------------------------------------------


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str, issuer: str = "PanelPro") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------


def recent_failed_logins(db, ip: str, minutes: int) -> int:
    since = datetime.utcnow() - timedelta(minutes=minutes)
    return (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.ip == ip,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= since,
        )
        .count()
    )


def record_login_attempt(db, ip: str, username: str, success: bool) -> None:
    db.add(LoginAttempt(ip=ip[:64], username=username[:64], success=success))
    db.commit()


def get_user(db, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()
