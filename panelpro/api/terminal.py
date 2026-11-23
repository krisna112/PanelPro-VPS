"""Web terminal: WebSocket bridge to a local SSH session (paramiko)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from panelpro.api.deps import api_ok, require_auth
from panelpro.constants import ENTRY_COOKIE, SESSION_COOKIE
from panelpro.core import keyvault, security
from panelpro.core.database import SessionLocal
from panelpro.core.errors import PanelError
from panelpro.core.ssh import SSHTerminal, start_reader_thread
from panelpro.services import firewall as fw

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


@router.get("/status")
def status(ctx=Depends(require_auth)):
    import shutil

    return api_ok({"sshd_available": shutil.which("sshd") is not None,
                   "ssh_port": fw.ssh_port() if shutil.which("sshd") else None})


def _ws_authorized(ws: WebSocket) -> bool:
    """Validate the entry cookie + panel session directly from the WS scope."""
    cookies = {}
    for raw_key, raw_val in ws.scope.get("headers", []):
        if raw_key.lower() == b"cookie":
            for part in raw_val.decode("latin-1").split(";"):
                k, _, v = part.strip().partition("=")
                cookies[k] = v
    if not keyvault.verify_signature("entry-ok", cookies.get(ENTRY_COOKIE, "")):
        return False
    db = SessionLocal()
    try:
        session = security.get_session(db, cookies.get(SESSION_COOKIE, ""))
        return session is not None
    finally:
        db.close()


@router.websocket("/ws")
async def terminal_ws(ws: WebSocket):
    await ws.accept()
    if not _ws_authorized(ws):
        await ws.close(code=4401)
        return

    terminal = SSHTerminal()

    async def send_to_client(data: bytes) -> None:
        try:
            await ws.send_bytes(data)
        except Exception:
            terminal.alive = False

    try:
        # first message: SSH credentials (typed into the terminal page)
        raw = await ws.receive_text()
        creds = json.loads(raw)
        terminal.connect(
            creds.get("username", "root"),
            creds.get("password", ""),
            cols=int(creds.get("cols") or 120),
            rows=int(creds.get("rows") or 32),
        )
    except PanelError as exc:
        await ws.send_text(json.dumps({"error": exc.message}))
        await ws.close()
        return
    except Exception as exc:
        await ws.send_text(json.dumps({"error": f"SSH failed: {exc}"}))
        await ws.close()
        return

    start_reader_thread(terminal, lambda data: None)
    # Pump SSH -> WS from a dedicated thread using asyncio-safe calls.
    import asyncio
    import threading

    loop = asyncio.get_running_loop()

    def reader():
        channel = terminal.channel
        try:
            while terminal.alive and not channel.closed:
                data = channel.recv(4096)
                if not data:
                    break
                asyncio.run_coroutine_threadsafe(send_to_client(data), loop).result(5)
        except Exception:
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                terminal.write(raw.encode())
                continue
            if "resize" in msg:
                terminal.resize(int(msg["resize"].get("cols", 120)),
                                int(msg["resize"].get("rows", 32)))
            elif "data" in msg:
                terminal.write(msg["data"].encode("utf-8", errors="replace"))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        terminal.close()
