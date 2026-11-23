"""Web-terminal bridge: WebSocket <-> local SSH channel (paramiko).

The browser opens the panel WebSocket, authenticates by typing the SSH
password once, and then gets an interactive xterm shell on the server.
"""

from __future__ import annotations

import threading

import paramiko

from panelpro.core.errors import PanelError


class SSHTerminal:
    """One interactive SSH session; call :meth:`close` when the WS drops."""

    def __init__(self) -> None:
        self.client: paramiko.SSHClient | None = None
        self.channel: paramiko.Channel | None = None
        self.alive = False

    def connect(
        self,
        username: str,
        password: str,
        host: str = "127.0.0.1",
        port: int = 22,
        cols: int = 120,
        rows: int = 32,
    ) -> None:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.client.connect(
                host,
                port=port,
                username=username,
                password=password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False,
            )
        except Exception as exc:
            self.client = None
            raise PanelError(f"SSH login failed: {exc}", 401) from exc

        self.channel = self.client.invoke_shell(
            term="xterm-256color", width=cols, height=rows
        )
        self.alive = True

    def read_loop(self, on_data) -> None:
        """Blocking reader; call from a thread, push bytes via callback."""
        channel = self.channel
        assert channel is not None
        try:
            while self.alive and not channel.closed:
                data = channel.recv(4096)
                if not data:
                    break
                on_data(data)
        except Exception:
            pass
        finally:
            self.alive = False

    def write(self, data: bytes) -> None:
        if self.channel and self.alive:
            try:
                self.channel.sendall(data)
            except Exception:
                self.alive = False

    def resize(self, cols: int, rows: int) -> None:
        if self.channel and self.alive:
            try:
                self.channel.resize_pty(width=max(20, cols), height=max(10, rows))
            except Exception:
                pass

    def close(self) -> None:
        self.alive = False
        try:
            if self.channel:
                self.channel.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass


def start_reader_thread(terminal: SSHTerminal, on_data) -> threading.Thread:
    t = threading.Thread(target=terminal.read_loop, args=(on_data,), daemon=True)
    t.start()
    return t
