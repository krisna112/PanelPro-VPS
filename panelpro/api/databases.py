"""Database management endpoints (MySQL/MariaDB, PostgreSQL, Redis, MongoDB)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core import keyvault, settings_store
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import DatabaseRow, DbUser
from panelpro.services import dbmgr

router = APIRouter(prefix="/api/databases", tags=["databases"])


class CreateDbBody(BaseModel):
    type: str = "mysql"
    name: str
    charset: str = "utf8mb4"
    with_user: bool = True
    user: str | None = None
    password: str | None = None


class CreateUserBody(BaseModel):
    type: str = "mysql"
    user: str
    host: str = "localhost"
    password: str
    database: str | None = None


class DbUserKeyBody(BaseModel):
    type: str = "mysql"
    user: str
    host: str = "localhost"


class GrantBody(DbUserKeyBody):
    database: str


class PasswordBody(DbUserKeyBody):
    password: str


class RootPasswordBody(BaseModel):
    password: str


class RedisPasswordBody(BaseModel):
    password: str


@router.get("/engines")
def engines(ctx=Depends(require_auth)):
    return api_ok(dbmgr.available_engines())


@router.get("")
def list_databases(type: str = "mysql", db: Session = Depends(get_db), ctx=Depends(require_auth)):
    manager = dbmgr.get_manager(type)
    live = manager.list_databases() if manager.available() else []
    rows = {r.name: r for r in db.query(DatabaseRow).filter(DatabaseRow.type == type).all()}
    out = []
    for item in live:
        row = rows.pop(item["name"], None)
        out.append(
            {
                "name": item["name"],
                "type": type,
                "charset": item.get("charset", ""),
                "owner_user": row.owner_user if row else None,
                "created_at": row.created_at.isoformat() if row else None,
                "size": manager.db_size(item["name"]) if hasattr(manager, "db_size") else None,
            }
        )
    return api_ok(out)


@router.post("")
def create_database(body: CreateDbBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    manager = dbmgr.get_manager(body.type)
    name = dbmgr.validate_ident(body.name, "database name")
    manager.create_database(name, body.charset or "utf8mb4")
    info = {"database": name}
    if body.with_user:
        user_name = dbmgr.validate_ident(body.user or f"{name[:32]}_u", "database user")
        password = body.password or keyvault.random_password(16)
        manager.create_user(user_name, "localhost", password)
        manager.grant(user_name, "localhost", name)
        db.add(DbUser(name=user_name, host="localhost", type=body.type,
                      password_enc=keyvault.encrypt_str(password)))
        info.update({"user": user_name, "password": password})
    db.add(DatabaseRow(name=name, type=body.type))
    db.commit()
    return api_ok(info)


@router.post("/{name}/delete")
def delete_database(name: str, type: str = "mysql", db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    manager = dbmgr.get_manager(type)
    manager.delete_database(dbmgr.validate_ident(name, "database name"))
    db.query(DatabaseRow).filter(DatabaseRow.name == name, DatabaseRow.type == type).delete()
    db.commit()
    return api_ok({"deleted": name})


@router.get("/users")
def list_users(type: str = "mysql", ctx=Depends(require_auth)):
    manager = dbmgr.get_manager(type)
    if not manager.available():
        return api_ok([])
    return api_ok(manager.list_users())


@router.post("/users")
def create_user(body: CreateUserBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    manager = dbmgr.get_manager(body.type)
    user_name = dbmgr.validate_ident(body.user, "database user")
    manager.create_user(user_name, body.host, body.password)
    if body.database:
        manager.grant(user_name, body.host, dbmgr.validate_ident(body.database, "database name"))
    db.add(DbUser(name=user_name, host=body.host, type=body.type,
                  password_enc=keyvault.encrypt_str(body.password)))
    db.commit()
    return api_ok({"user": user_name})


@router.post("/users/password")
def set_user_password(body: PasswordBody, ctx=Depends(require_role("operator"))):
    manager = dbmgr.get_manager(body.type)
    manager.set_password(dbmgr.validate_ident(body.user, "database user"), body.host, body.password)
    return api_ok({"user": body.user, "changed": True})


@router.post("/users/grant")
def grant_user(body: GrantBody, ctx=Depends(require_role("operator"))):
    manager = dbmgr.get_manager(body.type)
    manager.grant(dbmgr.validate_ident(body.user, "database user"), body.host,
                  dbmgr.validate_ident(body.database, "database name"))
    return api_ok({"granted": body.database, "user": body.user})


@router.post("/users/delete")
def delete_user(body: DbUserKeyBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    manager = dbmgr.get_manager(body.type)
    manager.delete_user(dbmgr.validate_ident(body.user, "database user"), body.host)
    db.query(DbUser).filter(DbUser.name == body.user, DbUser.type == body.type).delete()
    db.commit()
    return api_ok({"deleted": body.user})


@router.get("/redis/info")
def redis_info(ctx=Depends(require_auth)):
    manager = dbmgr.get_manager("redis")
    if not manager.available():
        raise PanelError("redis-cli is not installed.", 400)
    return api_ok(manager.info())


@router.post("/redis/password")
def redis_password(body: RedisPasswordBody, ctx=Depends(require_role("admin"))):
    manager = dbmgr.get_manager("redis")
    manager.set_password(body.password)
    return api_ok({"changed": True})


@router.post("/root-password")
def mysql_root_password(body: RootPasswordBody, ctx=Depends(require_role("admin"))):
    """Verify and store the MySQL root password (encrypted) for future ops."""
    import os
    import subprocess

    proc = subprocess.run(
        ["mysql", "-uroot", "-e", "SELECT 1;"],
        capture_output=True,
        timeout=20,
        env={**os.environ, "MYSQL_PWD": body.password},
    )
    if proc.returncode != 0:
        raise PanelError("MySQL rejected this password.", 400)
    settings_store.set_setting(
        "mysql_root_password_enc", keyvault.encrypt_str(body.password)
    )
    return api_ok({"stored": True})
