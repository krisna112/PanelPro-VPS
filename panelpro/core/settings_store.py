"""Key/value panel settings stored in SQLite with an in-process cache.

The cache avoids a database hit on every request (entry-path gate, rate
limits, etc.).  All writes go through :func:`set_setting` which keeps the
cache coherent within the single uvicorn process.
"""

from __future__ import annotations

import threading

from panelpro.constants import DEFAULT_PANEL_PORT
from panelpro.core.database import SessionLocal
from panelpro.core.keyvault import token_hex
from panelpro.models.tables import Setting

DEFAULTS: dict = {
    "entry_path": "",
    "panel_port": DEFAULT_PANEL_PORT,
    "language": "id",
    "theme": "dark",
    "api_enabled": True,
    "ip_allowlist": [],
    "trust_proxy": False,
    "panel_domain": "",
    "panel_ssl": False,
    "panel_ssl_cert": "",
    "panel_ssl_key": "",
    "threshold_disk": 90,
    "threshold_cpu": 85,
    "mysql_root_password_enc": "",
    "backup_dir": "",
}

_lock = threading.Lock()
_cache: dict | None = None


def _load_cache() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            db = SessionLocal()
            try:
                rows = db.query(Setting).all()
                _cache = {r.key: r.value for r in rows}
            finally:
                db.close()
    return _cache


def get_setting(key: str, default=None):
    cache = _load_cache()
    if key in cache and cache[key] not in (None, ""):
        return cache[key]
    return DEFAULTS.get(key, default)


def set_setting(key: str, value) -> None:
    cache = _load_cache()
    with _lock:
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == key).first()
            if row is None:
                db.add(Setting(key=key, value=value))
            else:
                row.value = value
            db.commit()
        finally:
            db.close()
        cache[key] = value


def all_settings() -> dict:
    cache = _load_cache()
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in cache.items() if v not in (None, "")})
    return merged


def init_defaults() -> None:
    """Insert missing defaults (incl. a random security entry path)."""
    cache = _load_cache()
    for key, value in DEFAULTS.items():
        if key not in cache:
            if key == "entry_path":
                value = token_hex(4)  # e.g. "a1b2c3d4" — 8 hex chars
            set_setting(key, value)
