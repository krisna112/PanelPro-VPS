"""MySQL replication endpoints (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_role
from panelpro.core.database import get_db
from panelpro.services import repl as repl_svc

router = APIRouter(prefix="/api/replication", tags=["replication"])


class SlaveBody(BaseModel):
    master_host: str
    master_port: int = 3306
    repl_user: str
    repl_password: str


@router.get("/status")
def status(db=Depends(get_db), ctx=Depends(require_role("admin"))):
    from panelpro.core import settings_store

    return api_ok({
        "available": repl_svc.available(),
        "master_configured": repl_svc.master_configured() if repl_svc.available() else False,
        "repl_user": repl_svc.REPL_USER if repl_svc.available() else None,
        "has_repl_password": bool(settings_store.get_setting(repl_svc.PASSWORD_KEY, "")),
        "master_status": repl_svc.master_status() if repl_svc.master_configured() else None,
        "slave_status": repl_svc.slave_status() if repl_svc.available() else None,
    })


@router.post("/setup-master")
def setup_master(db=Depends(get_db), ctx=Depends(require_role("admin"))):
    return api_ok(repl_svc.setup_master(db))


@router.post("/setup-slave")
def setup_slave(body: SlaveBody, db=Depends(get_db), ctx=Depends(require_role("admin"))):
    return api_ok(repl_svc.setup_slave(
        body.master_host, body.master_port, body.repl_user, body.repl_password
    ))


@router.post("/stop-slave")
def stop_slave(db=Depends(get_db), ctx=Depends(require_role("admin"))):
    return api_ok(repl_svc.stop_slave())
