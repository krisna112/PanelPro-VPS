"""Process guard endpoints: CRUD daemon tasks + run-now check."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import DaemonTask
from panelpro.services import procd

router = APIRouter(prefix="/api/daemon", tags=["daemon"])


class DaemonBody(BaseModel):
    name: str
    kind: str = "systemd"
    target: str
    restart_cmd: str | None = None
    check_interval: int = 60
    enabled: bool = True


@router.get("")
def list_tasks(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(DaemonTask).order_by(DaemonTask.created_at.desc()).all()
    return api_ok({"tasks": [procd.task_payload(r) for r in rows],
                   "kinds": list(procd.KINDS)})


@router.post("")
def create_task(body: DaemonBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    target = procd.validate_target(body.kind, body.target)
    row = DaemonTask(
        name=body.name[:100],
        kind=body.kind,
        target=target,
        restart_cmd=(body.restart_cmd or "")[:255] or None,
        check_interval=max(int(body.check_interval or 60), 10),
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    return api_ok(procd.task_payload(row))


@router.post("/{task_id}/update")
def update_task(task_id: int, body: DaemonBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(DaemonTask).filter(DaemonTask.id == task_id).first()
    if not row:
        raise PanelError("Task not found.", 404)
    row.name = body.name[:100]
    row.kind = body.kind
    row.target = procd.validate_target(body.kind, body.target)
    row.restart_cmd = (body.restart_cmd or "")[:255] or None
    row.check_interval = max(int(body.check_interval or 60), 10)
    row.enabled = body.enabled
    db.commit()
    return api_ok(procd.task_payload(row))


@router.post("/{task_id}/toggle")
def toggle_task(task_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(DaemonTask).filter(DaemonTask.id == task_id).first()
    if not row:
        raise PanelError("Task not found.", 404)
    row.enabled = not row.enabled
    db.commit()
    return api_ok({"id": row.id, "enabled": row.enabled})


@router.post("/{task_id}/delete")
def delete_task(task_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(DaemonTask).filter(DaemonTask.id == task_id).first()
    if not row:
        raise PanelError("Task not found.", 404)
    name = row.name
    db.delete(row)
    db.commit()
    return api_ok({"deleted": name})


@router.post("/{task_id}/run-now")
def run_now(task_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(DaemonTask).filter(DaemonTask.id == task_id).first()
    if not row:
        raise PanelError("Task not found.", 404)
    procd.check_one(db, row)
    return api_ok(procd.task_payload(row))
