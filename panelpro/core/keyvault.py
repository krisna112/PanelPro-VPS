"""Machine secret storage and Fernet-based string encryption.

Every PanelPro install owns one random key file (``data/secret.key``,
mode 0600).  It encrypts stored credentials (e.g. database passwords) and
signs the entry-path cookie, so nothing sensitive is kept in plain text.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as _stdlib_secrets

from cryptography.fernet import Fernet, InvalidToken

from panelpro.config import CFG
from panelpro.core.errors import PanelError

_fernet: Fernet | None = None


def machine_key() -> bytes:
    """Load (or lazily create) the per-install secret key."""
    path = CFG.secret_path
    if path.exists():
        key = path.read_bytes().strip()
        if key:
            return key
    key = Fernet.generate_key()
    CFG.data_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(machine_key())
    return _fernet


def encrypt_str(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_str(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        raise PanelError("Stored secret could not be decrypted (key changed?).", 500)


def token_hex(nbytes: int = 32) -> str:
    return _stdlib_secrets.token_hex(nbytes)


def random_password(length: int = 16) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
    return "".join(_stdlib_secrets.choice(alphabet) for _ in range(length))


def sign(value: str) -> str:
    return hmac.new(machine_key(), value.encode(), hashlib.sha256).hexdigest()


def verify_signature(value: str, signature: str) -> bool:
    return hmac.compare_digest(sign(value), signature or "")
