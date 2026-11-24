"""Fleet client: talk to other PanelPro instances over their REST API.

Each node is authenticated with a scoped API key (Bearer) plus the node's
secret entry path.  A per-node ``httpx.Client`` keeps the entry cookie
after the first visit, so subsequent calls go straight through.
"""

from __future__ import annotations

import atexit
import time
from datetime import datetime
from urllib.parse import urlparse

import httpx

from panelpro.core import keyvault
from panelpro.core.errors import PanelError
from panelpro.models.tables import RemoteServer

CLIENT_TIMEOUT = 12.0
_clients: dict[int, httpx.Client] = {}


def validate_base_url(base_url: str) -> str:
    parsed = urlparse((base_url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PanelError(
            "Invalid base URL (expected https://host:port or http://host:port).", 400
        )
    if parsed.path not in ("", "/"):
        raise PanelError("Base URL must not contain a path.", 400)
    return f"{parsed.scheme}://{parsed.netloc}"


def _client(server: RemoteServer) -> httpx.Client:
    client = _clients.get(server.id)
    if client is None:
        client = httpx.Client(
            base_url=server.base_url.rstrip("/"),
            timeout=CLIENT_TIMEOUT,
            follow_redirects=True,
        )
        _clients[server.id] = client
        atexit.register(client.close)
    return client


def _session_for(server: RemoteServer) -> httpx.Client:
    """Return a client that holds the node's entry cookie."""
    client = _client(server)
    # The entry gate only needs the signed cookie; fetch it once per process.
    if not client.cookies.get("pp_entry"):
        response = client.get(f"/{server.entry_path}")
        response.raise_for_status()
    return client


def call(server: RemoteServer, method: str, path: str, **kwargs) -> dict:
    """Call one API endpoint on a remote panel; returns parsed payload data."""
    import json as _json

    from panelpro.constants import API_KEY_PREFIX

    client = _session_for(server)
    api_key = keyvault.decrypt_str(server.api_key_enc or "")
    if not api_key.startswith(API_KEY_PREFIX):
        raise PanelError(f"Server '{server.name}' has no stored API key.", 400)
    headers = {"Authorization": f"Bearer {api_key}"}
    if method.upper() not in ("GET", "HEAD"):
        headers["X-PP-Request"] = "1"
        if "json" in kwargs:
            kwargs["content"] = _json.dumps(kwargs.pop("json"))
            headers.setdefault("Content-Type", "application/json")
    res = client.request(method.upper(), path, headers=headers, **kwargs)
    try:
        payload = res.json()
    except ValueError as exc:
        raise PanelError(f"Server '{server.name}' returned non-JSON ({res.status_code}).", 502) from exc
    if res.status_code == 401:
        raise PanelError(f"Server '{server.name}' rejected the API key.", 401)
    if not payload.get("ok"):
        raise PanelError(payload.get("message") or f"HTTP {res.status_code}", res.status_code or 502)
    return payload.get("data")


def _mark_seen(db, server: RemoteServer, version: str | None) -> None:
    server.last_seen_at = datetime.utcnow()
    server.version = version
    db.commit()


def test_server(db, server: RemoteServer) -> dict:
    started = time.time()
    health = call(server, "GET", "/api/health")
    latency_ms = int((time.time() - started) * 1000)
    _mark_seen(db, server, health.get("version"))
    return {"ok": True, "version": health.get("version"), "latency_ms": latency_ms}


def overview(db) -> dict:
    """Aggregate health + basic stats for every enabled node."""
    nodes = []
    for server in db.query(RemoteServer).filter(RemoteServer.enabled.is_(True)).all():
        entry = {
            "id": server.id,
            "name": server.name,
            "base_url": server.base_url,
            "state": "down",
            "version": server.version,
            "last_seen_at": server.last_seen_at.isoformat() if server.last_seen_at else None,
        }
        try:
            health = call(server, "GET", "/api/health")
            entry["state"] = "up"
            entry["version"] = health.get("version")
            try:
                entry["monitor"] = call(server, "GET", "/api/monitor/realtime")
            except PanelError:
                pass
            try:
                entry["summary"] = call(server, "GET", "/api/dashboard/summary")
            except PanelError:
                pass
            _mark_seen(db, server, health.get("version"))
        except Exception as exc:
            entry["error"] = str(exc)[:200]
        nodes.append(entry)
    return {"nodes": nodes}


def payload(server: RemoteServer) -> dict:
    return {
        "id": server.id,
        "name": server.name,
        "base_url": server.base_url,
        "entry_path": server.entry_path,
        "enabled": server.enabled,
        "has_key": bool(server.api_key_enc),
        "last_seen_at": server.last_seen_at.isoformat() if server.last_seen_at else None,
        "version": server.version,
    }
