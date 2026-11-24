"""MySQL master/slave replication manager.

Setup writes the replication configuration into MySQL via the CLI client
(the panel never edits my.cnf automatically — the pre-req notes are
returned to the UI), creates a dedicated replication user on the master
and issues CHANGE MASTER on the slave.  The replication password is
stored encrypted via core.keyvault.
"""

from __future__ import annotations

from panelpro.core import keyvault, settings_store
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import which
from panelpro.services.dbmgr import MySQLManager, validate_ident

REPL_USER = "panelpro_repl"
PASSWORD_KEY = "mysql_repl_password_enc"
ROOT_PASSWORD_KEY = "mysql_root_password_enc"


def available() -> bool:
    return which("mysql") is not None


def _query(sql: str, timeout: int = 60) -> str:
    mgr = MySQLManager()
    enc = settings_store.get_setting(ROOT_PASSWORD_KEY, "")
    if not enc:
        raise PanelError(
            "Set the MySQL root password in Database settings first.", 400
        )
    return mgr._query(sql)  # noqa: SLF001 — shared client plumbing


def master_configured() -> bool:
    try:
        out = _query("SELECT @@global.log_bin;")
    except PanelError:
        return False
    return out.strip() == "1"


def slave_status() -> dict | None:
    if not available():
        return None
    out = _query("SHOW SLAVE STATUS\\G", timeout=30)
    fields: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    if not fields:
        return None
    return {
        "running": (
            fields.get("Slave_IO_Running") == "Yes"
            and fields.get("Slave_SQL_Running") == "Yes"
        ),
        "io_running": fields.get("Slave_IO_Running"),
        "sql_running": fields.get("Slave_SQL_Running"),
        "seconds_behind": fields.get("Seconds_Behind_Master"),
        "master_host": fields.get("Master_Host"),
        "last_error": fields.get("Last_Error", "")[:300],
    }


def master_status() -> dict:
    out = _query("SHOW MASTER STATUS\\G", timeout=30)
    fields: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return {
        "file": fields.get("File"),
        "position": fields.get("Position"),
        "binlog_do_db": fields.get("Binlog_Do_DB"),
    }


def setup_master(db) -> dict:
    """Enable binlog requirements check + create the replication user."""
    if not available():
        raise PanelError("MySQL/MariaDB is not installed.", 400)
    if not master_configured():
        raise PanelError(
            "Binary logging is disabled. Add to my.cnf [mysqld]: "
            "server-id=1, log_bin=mysql-bin, then restart MySQL, and try again.",
            400,
        )
    password = keyvault.random_password(20)
    safe = password.replace("\\", "\\\\").replace("'", "\\'")
    _query(
        f"CREATE USER IF NOT EXISTS '{REPL_USER}'@'%' "
        f"IDENTIFIED BY '{safe}';"
    )
    _query(f"GRANT REPLICATION SLAVE ON *.* TO '{REPL_USER}'@'%'; FLUSH PRIVILEGES;")
    settings_store.set_setting(PASSWORD_KEY, keyvault.encrypt_str(password))
    status = master_status()
    return {
        "repl_user": REPL_USER,
        "repl_password": password,  # shown once to the operator
        "master_file": status.get("file"),
        "master_position": status.get("position"),
    }


def setup_slave(master_host: str, master_port: int, repl_user: str, repl_password: str) -> dict:
    if not available():
        raise PanelError("MySQL/MariaDB is not installed.", 400)
    import re as _re

    if not _re.match(r"^[A-Za-z0-9.:-]{1,120}$", master_host) or ".." in master_host:
        raise PanelError(f"Invalid master host: {master_host}", 400)
    if not 0 < int(master_port) < 65536:
        raise PanelError(f"Invalid master port: {master_port}", 400)
    validate_ident(repl_user, "replication user")
    safe_pass = repl_password.replace("\\", "\\\\").replace("'", "\\'")
    _query("STOP SLAVE;")
    _query(
        f"CHANGE MASTER TO MASTER_HOST='{master_host}', MASTER_PORT={int(master_port)}, "
        f"MASTER_USER='{_query_escape(repl_user)}', MASTER_PASSWORD='{safe_pass}', "
        f"MASTER_AUTO_POSITION=1;"
    )
    _query("START SLAVE;")
    return {"status": slave_status()}


def _query_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def stop_slave() -> dict:
    _query("STOP SLAVE;")
    return {"status": slave_status()}
