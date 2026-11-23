"""Pytest fixtures for PanelPro.

``PANELPRO_HOME`` is pointed at a throwaway directory *before* the panel
package is imported, so every test runs against an isolated database.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_HOME = Path(tempfile.mkdtemp(prefix="panelpro-tests-"))
os.environ["PANELPRO_HOME"] = str(_TEST_HOME)

import pytest  # noqa: E402


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from panelpro.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_creds(client):
    """Seed a dedicated admin user and return (username, password)."""
    from panelpro.core.database import SessionLocal
    from panelpro.core.security import hash_password
    from panelpro.models.tables import User

    username, password = "admintest", "SuperSecret9"
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first() is None:
            db.add(User(username=username, password_hash=hash_password(password), role="admin"))
            db.commit()
    finally:
        db.close()
    return username, password


@pytest.fixture()
def entry_path():
    from panelpro.core import settings_store

    settings_store.init_defaults()
    return str(settings_store.get_setting("entry_path"))


@pytest.fixture()
def authed_client(client, admin_creds, entry_path):
    """Client that passed the entry gate and logged in as admin."""
    # pass the entry path once to receive the signed entry cookie
    r = client.get(f"/{entry_path}")
    assert r.status_code == 200, r.text
    username, password = admin_creds
    r = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-PP-Request": "1"},
    )
    assert r.status_code == 200, r.text
    return client
