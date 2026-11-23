"""Scheduled task endpoints backed by the crontab marker engine."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import CronJob
from panelpro.services import cronsvc

router = APIRouter(prefix="/api/cron", tags=["cron"])


class CronBody(BaseModel):
    name: str
    type: str = "shell"  # shell | url | script
    schedule: str
    command: str
    enabled: bool = True


def _job_payload(job: CronJob) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "type": job.type,
        "schedule": job.schedule,
        "command": job.command,
        "enabled": job.enabled,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "last_status": job.last_status,
        "next_run": cronsvc.next_run(job.schedule).isoformat() if job.enabled else None,
    }


@router.get("")
def list_cron(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(CronJob).order_by(CronJob.created_at.desc()).all()
    return api_ok([_job_payload(r) for r in rows])


@router.post("")
def create_cron(body: CronBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    if body.type not in ("shell", "url", "script"):
        raise PanelError(f"Unknown task type: {body.type}", 400)
    schedule = cronsvc.validate_schedule(body.schedule)
    command = cronsvc.build_command(body.type, body.command)
    job = CronJob(name=body.name[:255], type=body.type, schedule=schedule,
                  command=body.command, enabled=body.enabled)
    db.add(job)
    db.commit()
    cronsvc.upsert_entry(job.id, schedule, command, job.enabled)
    return api_ok(_job_payload(job))


@router.post("/{job_id}/update")
def update_cron(job_id: int, body: CronBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(CronJob).filter(CronJob.id == job_id).first()
    if not job:
        raise PanelError("Task not found.", 404)
    job.name = body.name[:255]
    job.type = body.type
    job.schedule = cronsvc.validate_schedule(body.schedule)
    job.command = body.command
    job.enabled = body.enabled
    db.commit()
    cronsvc.upsert_entry(job.id, job.schedule,
                         cronsvc.build_command(job.type, job.command), job.enabled)
    return api_ok(_job_payload(job))


@router.post("/{job_id}/toggle")
def toggle_cron(job_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(CronJob).filter(CronJob.id == job_id).first()
    if not job:
        raise PanelError("Task not found.", 404)
    job.enabled = not job.enabled
    db.commit()
    cronsvc.upsert_entry(job.id, job.schedule,
                         cronsvc.build_command(job.type, job.command), job.enabled)
    return api_ok({"enabled": job.enabled})


@router.post("/{job_id}/delete")
def delete_cron(job_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(CronJob).filter(CronJob.id == job_id).first()
    if not job:
        raise PanelError("Task not found.", 404)
    cronsvc.remove_entry(job.id)
    db.delete(job)
    db.commit()
    return api_ok({"deleted": job_id})


@router.post("/{job_id}/run")
def run_now(job_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(CronJob).filter(CronJob.id == job_id).first()
    if not job:
        raise PanelError("Task not found.", 404)
    result = cronsvc.run_job(job.id, job.type, job.command, job.name)
    job.last_run_at = datetime.utcnow()
    job.last_status = "done" if result["ok"] else "failed"
    db.commit()
    return api_ok(result)


@router.get("/{job_id}/log")
def job_log(job_id: int, lines: int = 200, ctx=Depends(require_auth)):
    return api_ok({"log": cronsvc.job_log(job_id, lines)})
