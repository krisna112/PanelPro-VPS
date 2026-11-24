"""PanelPro command line interface.

    panelpro start [--host H] [--port P] [--dev]
    panelpro menu
    panelpro setup-admin
    panelpro change-credentials [--username NAME]
    panelpro reset-password [--username NAME]
    panelpro set-port PORT
    panelpro set-entry PATH
    panelpro setup-domain DOMAIN --email EMAIL
    panelpro backup-panel
    panelpro doctor
    panelpro version
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import warnings
from datetime import datetime
from getpass import GetPassWarning, getpass

from panelpro.config import CFG
from panelpro.constants import APP_NAME, VERSION


def _open_db():
    from panelpro.core.database import SessionLocal, init_db

    CFG.ensure_dirs()
    init_db()
    return SessionLocal()


def cmd_start(args) -> int:
    import uvicorn

    from panelpro.core import settings_store

    with _open_db():
        settings_store.init_defaults()
    host = args.host or "127.0.0.1"
    port = args.port if args.port is not None else int(settings_store.get_setting("panel_port"))
    ssl_options = {}
    if settings_store.get_setting("panel_ssl"):
        cert = settings_store.get_setting("panel_ssl_cert")
        key = settings_store.get_setting("panel_ssl_key")
        if not cert or not key:
            print("Panel HTTPS requires a configured certificate and private key.", file=sys.stderr)
            return 1
        ssl_options = {"ssl_certfile": cert, "ssl_keyfile": key}
    log_level = "debug" if args.dev else "info"
    uvicorn.run(
        "panelpro.main:app", host=host, port=port, log_level=log_level, workers=1,
        access_log=args.dev, proxy_headers=bool(settings_store.get_setting("trust_proxy")),
        forwarded_allow_ips="127.0.0.1,::1", **ssl_options,
    )
    return 0


def _read_username(label: str, default: str) -> str:
    while True:
        username = input(f"{label} [{default}]: ").strip()
        if not username:
            return default
        if re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", username):
            return username
        print("Use up to 64 letters, digits, dots, underscores, or hyphens.")


def _read_password(prompt: str, *, optional: bool = False) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        while True:
            password = getpass(prompt)
            if not password and optional:
                return ""
            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                print("Use at least 8 characters and at most 72 UTF-8 bytes.")
                continue
            if password == getpass("Confirm password: "):
                return password
            print("Passwords do not match. Try again.")


def cmd_setup_admin(args) -> int:
    """Prompt for the first administrator before the service starts."""
    from sqlalchemy import text

    from panelpro.core.security import hash_password
    from panelpro.models.tables import User

    with _open_db() as db:
        if db.query(User.id).first() is not None:
            print("PanelPro already has login accounts. Use your existing credentials.")
            return 0
        db.rollback()

        try:
            username = _read_username("Administrator username", "admin")
            password = _read_password("Administrator password: ")
        except (EOFError, KeyboardInterrupt, GetPassWarning):
            print("Administrator setup requires an interactive terminal with hidden password input.", file=sys.stderr)
            return 1

        password_hash = hash_password(password)
        db.execute(text("BEGIN IMMEDIATE"))
        if db.query(User.id).first() is not None:
            print("PanelPro already has login accounts. Use your existing credentials.")
            return 0
        db.add(User(username=username, password_hash=password_hash, role="admin"))
        db.commit()

    print(f"Administrator '{username}' created. Use the password you entered to sign in.")
    return 0


def cmd_change_credentials(args) -> int:
    from sqlalchemy import text

    from panelpro.core import security
    from panelpro.models.tables import User

    try:
        with _open_db() as db:
            current = args.username
            if current is None:
                first_admin = db.query(User.username).filter_by(role="admin").order_by(User.id).first()
                default = first_admin.username if first_admin else "admin"
                db.rollback()
                current = input(f"Current username [{default}]: ").strip() or default

            user = security.get_user(db, current)
            if user is None:
                print(f"User '{current}' not found.", file=sys.stderr)
                return 1
            user_id, previous_hash = user.id, user.password_hash
            db.rollback()

            username = _read_username("New username", current)
            password = _read_password("New password (Enter to keep the current one): ", optional=True)
            if username == current and not password:
                print("No changes requested.")
                return 0

            password_hash = security.hash_password(password) if password else None
            db.execute(text("BEGIN IMMEDIATE"))
            user = db.get(User, user_id)
            if user is None or user.username != current or user.password_hash != previous_hash:
                print("The account changed during this session. Run the command again.", file=sys.stderr)
                return 1
            if username != current and security.get_user(db, username) is not None:
                print(f"Username '{username}' is already in use.", file=sys.stderr)
                return 1

            user.username = username
            if password_hash is not None:
                user.password_hash = password_hash
            security.destroy_all_sessions(db, user_id)
    except (EOFError, KeyboardInterrupt, GetPassWarning):
        print("Credential changes require an interactive terminal with hidden password input.", file=sys.stderr)
        return 1

    print(f"Credentials updated. Sign in again as '{username}'.")
    return 0


def cmd_reset_password(args) -> int:
    from panelpro.core import security
    from panelpro.core.keyvault import random_password
    from panelpro.models.tables import User

    db = _open_db()
    try:
        username = args.username or "admin"
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            print(f"User '{username}' not found.", file=sys.stderr)
            return 1
        password = random_password(14)
        user.password_hash = security.hash_password(password)
        db.commit()
        security.destroy_all_sessions(db, user.id)
        print(f"New password for '{username}': {password}")
        print("(All sessions were revoked; save this password now.)")
        return 0
    finally:
        db.close()


def cmd_set_port(args) -> int:
    from panelpro.core import settings_store

    port = int(args.port)
    if not 1024 <= port <= 65535:
        print("Port must be between 1024 and 65535.", file=sys.stderr)
        return 1
    db = _open_db()
    try:
        settings_store.init_defaults()
        settings_store.set_setting("panel_port", port)
        print(f"Panel port set to {port}. Restart the panel to apply.")
        return 0
    finally:
        db.close()


def cmd_set_entry(args) -> int:
    from panelpro.core import settings_store

    path = str(args.path)
    if not settings_store.valid_entry_path(path):
        print("Entry path must be 4-32 chars (letters, digits, -, _) and not reserved.", file=sys.stderr)
        return 1
    db = _open_db()
    try:
        settings_store.init_defaults()
        settings_store.set_setting("entry_path", path)
        print(f"Security entry path set to '/{path}'. Restart the panel to apply.")
        return 0
    finally:
        db.close()


def cmd_setup_domain(args) -> int:
    if sys.platform != "linux" or os.geteuid() != 0:
        print("Run setup-domain as root on the Linux VPS.", file=sys.stderr)
        return 1
    if not CFG.db_path.is_file():
        print("PanelPro must be installed and running on this VPS.", file=sys.stderr)
        return 1

    from panelpro.core.errors import PanelError
    from panelpro.services.panel_access import access_lock, setup_domain

    try:
        with access_lock():
            url = setup_domain(args.domain, args.email)
    except (OSError, PanelError) as exc:
        print(f"Panel domain setup failed: {exc}", file=sys.stderr)
        return 1

    print(f"PanelPro login: {url}")
    return 0


def cmd_backup_panel(args) -> int:
    """Back up the panel's own database + secrets into a tar.gz."""
    import tarfile

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out = CFG.home / f"panelpro-backup-{stamp}.tar.gz"
    CFG.ensure_dirs()
    with tarfile.open(out, "w:gz") as tf:
        if CFG.db_path.exists():
            tf.add(CFG.db_path, arcname="data/panel.db")
        if CFG.secret_path.exists():
            tf.add(CFG.secret_path, arcname="data/secret.key")
        for extra in ("ssl",):
            d = CFG.data_dir / extra
            if d.is_dir():
                tf.add(d, arcname=f"data/{extra}")
    print(f"Panel backup written to {out}")
    return 0


def cmd_doctor(args) -> int:
    tools = ["nginx", "apache2", "mysql", "mysqldump", "psql", "redis-cli",
             "mongosh", "php", "certbot", "docker", "ufw", "firewall-cmd",
             "iptables", "pure-pw", "proftpd", "rclone", "fail2ban-client"]
    print(f"{APP_NAME} {VERSION} environment doctor")
    print(f"  home       : {CFG.home}")
    print(f"  database   : {CFG.db_path} ({'OK' if CFG.db_path.exists() else 'missing'})")
    print(f"  platform   : {sys.platform}")
    print("  tools:")
    for tool in tools:
        path = shutil.which(tool)
        print(f"    {tool:<16} {'OK  ' + path if path else '-'}")
    try:
        import psutil  # noqa: F401

        print("  python deps: psutil OK")
    except ImportError:
        print("  python deps: MISSING — run: pip install -r requirements.txt")
        return 1
    return 0


def cmd_version(args) -> int:
    print(f"{APP_NAME} {VERSION}")
    return 0


def cmd_menu(args) -> int:
    from panelpro.console import menu

    return menu()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="panelpro", description=f"{APP_NAME} control panel CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("menu", help="open the terminal menu on an installed VPS")
    p.set_defaults(fn=cmd_menu)

    p = sub.add_parser("setup-admin", help="set the first administrator's username and password")
    p.set_defaults(fn=cmd_setup_admin)

    p = sub.add_parser("change-credentials", help="change a login username or password interactively")
    p.add_argument("--username", help="existing username to update")
    p.set_defaults(fn=cmd_change_credentials)

    p = sub.add_parser("start", help="start the panel server")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--dev", action="store_true", help="verbose logging")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("reset-password", help="reset a user's password")
    p.add_argument("--username", default="admin")
    p.set_defaults(fn=cmd_reset_password)

    p = sub.add_parser("set-port", help="change the panel port")
    p.add_argument("port")
    p.set_defaults(fn=cmd_set_port)

    p = sub.add_parser("set-entry", help="change the security entry path")
    p.add_argument("path")
    p.set_defaults(fn=cmd_set_entry)

    p = sub.add_parser("setup-domain", help="publish the panel login on a domain with HTTPS")
    p.add_argument("domain")
    p.add_argument("--email", required=True, help="Let's Encrypt account email")
    p.set_defaults(fn=cmd_setup_domain)

    p = sub.add_parser("backup-panel", help="back up panel database + secrets")
    p.set_defaults(fn=cmd_backup_panel)

    p = sub.add_parser("doctor", help="check environment and installed tools")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("version", help="print version")
    p.set_defaults(fn=cmd_version)

    argv = sys.argv[1:] if argv is None else argv
    if not argv and sys.stdin.isatty() and sys.platform == "linux":
        argv = ["menu"]
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
