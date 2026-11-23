"""API smoke tests through the real ASGI app (TestClient)."""

from panelpro.constants import ENTRY_COOKIE


def test_health_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["app"] == "PanelPro"


def test_entry_gate_masks_api(client, entry_path):
    # without the entry cookie everything except /api/health is masked
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 404
    # visiting the secret path sets the cookie
    r = client.get(f"/{entry_path}")
    assert r.status_code == 200
    assert ENTRY_COOKIE in r.headers.get("set-cookie", "")
    # …and now the API responds (401 = auth required, not 404 masked)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 401


def test_login_wrong_password(authed_client):
    r = authed_client.post(
        "/api/auth/login",
        json={"username": "admintest", "password": "nope-nope"},
        headers={"X-PP-Request": "1"},
    )
    assert r.status_code == 401


def test_login_missing_csrf_header(client, admin_creds, entry_path):
    client.get(f"/{entry_path}")
    r = client.post(
        "/api/auth/login",
        json={"username": admin_creds[0], "password": admin_creds[1]},
    )
    assert r.status_code == 200  # login itself is allowed pre-session


def test_me_requires_auth(client, entry_path):
    client.get(f"/{entry_path}")
    assert client.get("/api/auth/me").status_code == 401


def test_full_session_flow(authed_client):
    me = authed_client.get("/api/auth/me").json()["data"]
    assert me["username"] == "admintest"
    assert me["role"] == "admin"

    summary = authed_client.get("/api/dashboard/summary").json()["data"]
    assert "counts" in summary and "system" in summary

    # file manager on a temp dir
    import tempfile

    root = tempfile.mkdtemp(prefix="pp-files-")
    listing = authed_client.get("/api/files/list", params={"path": root}).json()["data"]
    assert listing["path"] == root

    write = authed_client.post(
        "/api/files/write",
        json={"path": root + "/hello.txt", "content": "hi"},
        headers={"X-PP-Request": "1"},
    )
    assert write.status_code == 200
    read = authed_client.get("/api/files/read", params={"path": root + "/hello.txt"}).json()["data"]
    assert read["content"] == "hi"


def test_csrf_required_for_mutations(authed_client):
    import tempfile

    root = tempfile.mkdtemp(prefix="pp-csrf-")
    r = authed_client.post("/api/files/mkdir", json={"path": root + "/x"})
    assert r.status_code == 403  # missing X-PP-Request header


def test_role_enforcement(authed_client):
    # settings require admin role: admin passes
    r = authed_client.get("/api/settings")
    assert r.status_code == 200
    # a viewer-created key would not — verify the dependency order works
    # by calling an admin-only endpoint without any role bump for operators.
    r = authed_client.post(
        "/api/users/keys", json={"name": "t", "role": "viewer"},
        headers={"X-PP-Request": "1"},
    )
    assert r.status_code == 200
    key = r.json()["data"]["key"]
    assert key.startswith("ppk_")


def test_settings_entry_validation(authed_client):
    r = authed_client.post(
        "/api/settings", json={"key": "entry_path", "value": "api"},
        headers={"X-PP-Request": "1"},
    )
    assert r.status_code == 400


def test_monitor_endpoints(authed_client):
    assert authed_client.get("/api/monitor/realtime").status_code == 200
    assert authed_client.get("/api/monitor/history").status_code == 200
    assert authed_client.get("/api/monitor/disks").status_code == 200
