"""PanelPro command line interface.

    panelpro start [--host H] [--port P] [--dev]
    panelpro reset-password [--username NAME]
    panelpro set-port PORT
    panelpro set-entry PATH
    panelpro backup-panel
    panelpro doctor
    panelpro version
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime

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
    if not re.match(r"^[a-zA-Z0-9_-]{4,32}$", path):
        print("Entry path must be 4-32 chars (letters, digits, -, _).", file=sys.stderr)
        return 1
    db = _open_db()
    try:
        settings_store.init_defaults()
        settings_store.set_setting("entry_path", path)
        print(f"Security entry path set to '/{path}'. Restart the panel to apply.")
        return 0
    finally:
        db.close()


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="panelpro", description=f"{APP_NAME} control panel CLI")
    sub = parser.add_subparsers(dest="command", required=True)

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

    p = sub.add_parser("backup-panel", help="back up panel database + secrets")
    p.set_defaults(fn=cmd_backup_panel)

    p = sub.add_parser("doctor", help="check environment and installed tools")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("version", help="print version")
    p.set_defaults(fn=cmd_version)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
