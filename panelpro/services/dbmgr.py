"""Database engine managers: MySQL/MariaDB, PostgreSQL, Redis, MongoDB.

Each manager wraps the engine's CLI tool.  Credentials the panel stores
(database root password, Redis password) are encrypted at rest via
``core.keyvault``.
"""

from __future__ import annotations

import re

from panelpro.core import keyvault, settings_store
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run, which

IDENT_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")

# Charsets are interpolated into CREATE DATABASE statements, so only a fixed
# whitelist is accepted — never trust API-supplied charset strings.
MYSQL_CHARSETS = {"utf8mb4", "utf8", "latin1", "binary", "ascii"}
PG_CHARSETS = {"UTF8", "LATIN1", "SQL_ASCII"}


def validate_ident(name: str, what: str = "identifier") -> str:
    if not IDENT_RE.match(name or ""):
        raise PanelError(f"Invalid {what}: {name}", 400)
    return name


def validate_charset(charset: str, allowed: set[str]) -> str:
    if charset not in allowed:
        raise PanelError(
            f"Unsupported charset '{charset}'. Allowed: {', '.join(sorted(allowed))}.",
            400,
        )
    return charset


def _sql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


# ---------------------------------------------------------------------------
# MySQL / MariaDB
# ---------------------------------------------------------------------------


def _mysql_client_args() -> list[str]:
    require("mysql", "Install MySQL or MariaDB first.")
    args = ["mysql", "-uroot"]
    env = {}
    enc = settings_store.get_setting("mysql_root_password_enc", "")
    if enc:
        env["MYSQL_PWD"] = keyvault.decrypt_str(enc)
    return args, env


class MySQLManager:
    type = "mysql"

    def available(self) -> bool:
        return which("mysql") is not None

    def _query(self, sql: str) -> str:
        args, env = _mysql_client_args()
        res = run([*args, "-B", "-N", "-e", sql], timeout=60, env=env)
        if res.code != 0:
            raise PanelError(f"MySQL error: {res.stderr.strip()[-300:]}", 500)
        return res.stdout

    def list_databases(self) -> list[dict]:
        out = self._query(
            "SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA "
            "WHERE SCHEMA_NAME NOT IN ('information_schema','performance_schema','sys','mysql');"
        )
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if parts and parts[0]:
                rows.append(
                    {"name": parts[0], "charset": parts[1] if len(parts) > 1 else ""}
                )
        return rows

    def create_database(self, name: str, charset: str = "utf8mb4") -> None:
        validate_ident(name, "database name")
        charset = validate_charset(charset, MYSQL_CHARSETS)
        self._query(
            f"CREATE DATABASE `{name}` CHARACTER SET {charset} "
            f"COLLATE {charset}_unicode_ci;"
        )

    def delete_database(self, name: str) -> None:
        validate_ident(name, "database name")
        self._query(f"DROP DATABASE IF EXISTS `{name}`;")

    def db_size(self, name: str) -> int:
        validate_ident(name, "database name")
        out = self._query(
            f"SELECT COALESCE(SUM(data_length+index_length),0) FROM information_schema.TABLES "
            f"WHERE table_schema='{_sql_escape(name)}';"
        ).strip()
        try:
            return int(out.split("\t")[-1])
        except ValueError:
            return 0

    def list_users(self) -> list[dict]:
        out = self._query(
            "SELECT user, host FROM mysql.user WHERE user NOT IN "
            "('mysql.sys','mysql.session','mysql.infoschema','debian-sys-maint','healthchecker');"
        )
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 2:
                rows.append({"user": parts[0], "host": parts[1]})
        return rows

    def create_user(self, user: str, host: str, password: str) -> None:
        validate_ident(user, "database user")
        self._query(
            f"CREATE USER '{_sql_escape(user)}'@'{_sql_escape(host)}' "
            f"IDENTIFIED BY '{_sql_escape(password)}';"
        )

    def set_password(self, user: str, host: str, password: str) -> None:
        validate_ident(user, "database user")
        self._query(
            f"ALTER USER '{_sql_escape(user)}'@'{_sql_escape(host)}' "
            f"IDENTIFIED BY '{_sql_escape(password)}';"
        )

    def delete_user(self, user: str, host: str) -> None:
        validate_ident(user, "database user")
        self._query(f"DROP USER IF EXISTS '{_sql_escape(user)}'@'{_sql_escape(host)}';")

    def grant(self, user: str, host: str, database: str) -> None:
        validate_ident(database, "database name")
        self._query(
            f"GRANT ALL PRIVILEGES ON `{database}`.* "
            f"TO '{_sql_escape(user)}'@'{_sql_escape(host)}'; FLUSH PRIVILEGES;"
        )


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------


class PostgresManager:
    type = "postgres"

    def available(self) -> bool:
        return which("psql") is not None

    def _psql(self, sql: str) -> str:
        res = run(
            ["runuser", "-u", "postgres", "--", "psql", "-tAc", sql], timeout=60
        )
        if res.code != 0:
            res = run(["sudo", "-u", "postgres", "psql", "-tAc", sql], timeout=60)
        if res.code != 0:
            raise PanelError(f"PostgreSQL error: {res.stderr.strip()[-300:]}", 500)
        return res.stdout


def _psql_prefixes() -> list[list[str]]:
    """Candidate argv prefixes for running psql as the postgres user."""
    return [
        ["runuser", "-u", "postgres", "--"],
        ["sudo", "-u", "postgres"],
    ]


def _psql_file_args(database: str, sql_file: str) -> list[list[str]]:
    """Full argv candidates to run a SQL file inside one database."""
    return [
        [*prefix, "psql", "-v", "ON_ERROR_STOP=1", "-d", database, "-f", sql_file]
        for prefix in _psql_prefixes()
    ]

    def list_databases(self) -> list[dict]:
        out = self._psql(
            "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname != 'postgres';"
        )
        return [{"name": line.strip(), "charset": ""} for line in out.splitlines() if line.strip()]

    def create_database(self, name: str, charset: str = "UTF8") -> None:
        validate_ident(name, "database name")
        charset = validate_charset(charset, PG_CHARSETS)
        self._psql(f"CREATE DATABASE {name} ENCODING '{charset}';")

    def delete_database(self, name: str) -> None:
        validate_ident(name, "database name")
        self._psql(f"DROP DATABASE IF EXISTS {name};")

    def list_users(self) -> list[dict]:
        out = self._psql(
            "SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%';"
        )
        return [{"user": line.strip(), "host": ""} for line in out.splitlines() if line.strip()]

    def create_user(self, user: str, host: str, password: str) -> None:
        validate_ident(user, "database user")
        self._psql(
            f"CREATE USER {user} WITH PASSWORD '{_sql_escape(password)}';"
        )

    def set_password(self, user: str, host: str, password: str) -> None:
        validate_ident(user, "database user")
        self._psql(f"ALTER USER {user} WITH PASSWORD '{_sql_escape(password)}';")

    def delete_user(self, user: str, host: str) -> None:
        validate_ident(user, "database user")
        self._psql(f"DROP USER IF EXISTS {user};")

    def grant(self, user: str, host: str, database: str) -> None:
        validate_ident(database, "database name")
        self._psql(f"GRANT ALL PRIVILEGES ON DATABASE {database} TO {user};")


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


class RedisManager:
    type = "redis"

    def available(self) -> bool:
        return which("redis-cli") is not None

    def _cli(self, *args: str) -> str:
        cmd = ["redis-cli"]
        enc = settings_store.get_setting("redis_password_enc", "")
        if enc:
            cmd += ["-a", keyvault.decrypt_str(enc), "--no-auth-warning"]
        res = run([*cmd, *args], timeout=30)
        if res.code != 0:
            raise PanelError(f"Redis error: {res.stderr.strip()[-300:]}", 500)
        return res.stdout

    def info(self, section: str = "default") -> dict:
        out = self._cli("INFO", section)
        info: dict = {}
        for line in out.splitlines():
            if ":" in line and not line.startswith("#"):
                key, _, value = line.partition(":")
                info[key.strip()] = value.strip()
        return info

    def list_databases(self) -> list[dict]:
        info = self.info("keyspace")
        return [
            {"name": key, "charset": f"{value.split(',')[0]} keys"}
            for key, value in sorted(info.items())
        ]

    def set_password(self, password: str) -> None:
        require("redis-cli")
        self._cli("CONFIG", "SET", "requirepass", password)
        self._cli("CONFIG", "REWRITE")
        settings_store.set_setting(
            "redis_password_enc", keyvault.encrypt_str(password)
        )

    def flush_database(self, db: str = "0") -> None:
        self._cli("-n", db, "FLUSHDB")


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------


class MongoManager:
    type = "mongo"

    def available(self) -> bool:
        return which("mongosh") is not None or which("mongo") is not None

    def _shell(self, js: str) -> str:
        tool = which("mongosh") or which("mongo")
        res = run([tool, "--quiet", "--eval", js], timeout=60)
        if res.code != 0:
            raise PanelError(f"MongoDB error: {res.stderr.strip()[-300:]}", 500)
        return res.stdout.strip()

    def list_databases(self) -> list[dict]:
        out = self._shell(
            "JSON.stringify(db.adminCommand({listDatabases:1}).databases"
            ".map(function(d){return {name:d.name, size:d.sizeOnDisk}}))"
        )
        import json

        try:
            return json.loads(out)
        except ValueError:
            return []

    def create_database(self, name: str, charset: str = "") -> None:
        validate_ident(name, "database name")
        self._shell(f"db.getSiblingDB('{_sql_escape(name)}').createCollection('_init')")

    def delete_database(self, name: str) -> None:
        validate_ident(name, "database name")
        self._shell(f"db.getSiblingDB('{_sql_escape(name)}').dropDatabase()")

    def list_users(self) -> list[dict]:
        out = self._shell(
            "JSON.stringify(db.getSiblingDB('admin').getUsers().users"
            ".map(function(u){return {user:u.user, host:''}}))"
        )
        import json

        try:
            return json.loads(out)
        except ValueError:
            return []

    def create_user(self, user: str, host: str, password: str, database: str = "admin") -> None:
        validate_ident(user, "database user")
        self._shell(
            f"db.getSiblingDB('{_sql_escape(database)}').createUser("
            f"{{user:'{_sql_escape(user)}', pwd:'{_sql_escape(password)}', "
            f"roles:[{{role:'readWrite', db:'{_sql_escape(database)}'}}]}})"
        )

    def set_password(self, user: str, host: str, password: str, database: str = "admin") -> None:
        validate_ident(user, "database user")
        self._shell(
            f"db.getSiblingDB('{_sql_escape(database)}').updateUser("
            f"'{_sql_escape(user)}', {{pwd:'{_sql_escape(password)}'}})"
        )

    def delete_user(self, user: str, host: str, database: str = "admin") -> None:
        validate_ident(user, "database user")
        self._shell(
            f"db.getSiblingDB('{_sql_escape(database)}').dropUser('{_sql_escape(user)}')"
        )

    def grant(self, user: str, host: str, database: str) -> None:
        self._shell(
            f"db.getSiblingDB('admin').grantRolesToUser('{_sql_escape(user)}', "
            f"[{{role:'readWrite', db:'{_sql_escape(database)}'}}])"
        )


MANAGERS = {
    "mysql": MySQLManager,
    "postgres": PostgresManager,
    "redis": RedisManager,
    "mongo": MongoManager,
}


def get_manager(dbtype: str):
    cls = MANAGERS.get(dbtype)
    if not cls:
        raise PanelError(f"Unsupported database type: {dbtype}", 400)
    return cls()


def available_engines() -> dict:
    return {key: get_manager(key).available() for key in MANAGERS}
