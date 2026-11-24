"""Interactive administration for an installed PanelPro service."""

from __future__ import annotations

import os
import sys
from argparse import Namespace

from panelpro import cli
from panelpro.config import CFG
from panelpro.core import settings_store
from panelpro.core.database import SessionLocal
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run
from panelpro.models.tables import User
from panelpro.services import panel_access


def _show_access() -> None:
    status = run(["systemctl", "is-active", "panelpro"]).stdout.strip()
    print(f"Service status: {status or 'unknown'}")
    with SessionLocal() as db:
        usernames = db.query(User.username).filter_by(role="admin").order_by(User.username).all()
    if usernames:
        print("Administrators: " + ", ".join(username for (username,) in usernames))

    domain = settings_store.get_setting("panel_domain")
    entry = settings_store.get_setting("entry_path")
    port = settings_store.get_setting("panel_port")
    if domain:
        print(f"Panel login: https://{domain}/{entry}")
    else:
        host = panel_access.listener_host()
        print(f"Panel login: {panel_access.local_url(port, host)}/{entry}")
        if host == "127.0.0.1":
            print(f"SSH tunnel: ssh -N -L {port}:127.0.0.1:{port} user@server")
    print(f"Backend port: {port}")
    if CFG.credentials_path.is_file():
        print(f"Initial credentials file: {CFG.credentials_path}")


def _service_action(action: str) -> None:
    run(["systemctl", action, "panelpro"], check=True)
    status = run(["systemctl", "is-active", "panelpro"]).stdout.strip()
    print(f"Service status: {status or 'unknown'}")


def _change_port() -> None:
    try:
        port = int(input("New backend port: ").strip())
    except ValueError:
        port = 0
    if not 1024 <= port <= 65535:
        raise PanelError("Port must be between 1024 and 65535.", 400)

    panel_access.change_port(port)
    _show_access()


def _change_entry() -> None:
    path = input("New login path without the leading slash: ").strip()
    if cli.cmd_set_entry(Namespace(path=path)) == 0:
        _service_action("restart")
        _show_access()


def _set_domain() -> None:
    domain = input("Panel hostname: ").strip()
    email = input("Email for Let's Encrypt: ").strip()
    cli.cmd_setup_domain(Namespace(domain=domain, email=email))


def _recent_logs() -> None:
    result = run(["journalctl", "--no-pager", "-u", "panelpro", "-n", "40"], check=True)
    print(result.stdout.rstrip())


def menu() -> int:
    if sys.platform != "linux" or os.geteuid() != 0:
        print("Open the menu as root on the Linux VPS with sudo panelpro menu.", file=sys.stderr)
        return 1
    if not CFG.db_path.is_file():
        print("Install PanelPro before opening the terminal menu.", file=sys.stderr)
        return 1

    actions = {
        "1": ("Show service status and login URL", _show_access),
        "2": ("Start panel service", lambda: _service_action("start")),
        "3": ("Restart panel service", lambda: _service_action("restart")),
        "4": ("Stop panel service", lambda: _service_action("stop")),
        "5": ("Change backend port and restart the panel", _change_port),
        "6": ("Change the login path and restart the panel", _change_entry),
        "7": ("Reset a login password", lambda: cli.cmd_reset_password(
            Namespace(username=input("Username [admin]: ").strip() or "admin"))),
        "8": ("Configure the HTTPS domain", _set_domain),
        "9": ("Show recent panel logs", _recent_logs),
        "10": ("Change a login username or password", lambda: cli.cmd_change_credentials(Namespace(username=None))),
    }
    while True:
        print("\nPanelPro terminal menu")
        for key, (label, _) in actions.items():
            print(f"{key}) {label}")
        print("0) Exit")
        try:
            choice = input("Choose an option: ").strip()
            if choice == "0":
                return 0
            if choice not in actions:
                print("Choose one of the listed options.")
                continue
            actions[choice][1]()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        except (OSError, PanelError) as exc:
            print(f"Unable to apply the action: {exc}", file=sys.stderr)
