"""Backup endpoints: jobs, runs, archive download, restore."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from croniter import croniter
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.config import CFG
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.core.notify import notify_event
from panelpro.models.tables import BackupJob, BackupRun
from panelpro.services import backupsvc

router = APIRouter(prefix="/api/backup", tags=["backup"])


class JobBody(BaseModel):
    name: str
    sites: list[str] = []
    databases: list[str] = []
    schedule: str = "0 2 * * *"
    target: str = "local"
    target_config: dict = {}
    keep: int = 7
    enabled: bool = True


@router.get("/jobs")
def jobs(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(BackupJob).order_by(BackupJob.created_at.desc()).all()
    return api_ok(
        [
            {
                "id": r.id,
                "name": r.name,
                "sites": r.sites,
                "databases": r.databases,
                "schedule": r.schedule,
                "target": r.target,
                "keep": r.keep,
                "enabled": r.enabled,
                "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
                "last_status": r.last_status,
                "next_run": (
                    croniter(r.schedule, r.last_run_at or datetime.utcnow()).get_next(datetime).isoformat()
                    if r.enabled else None
                ),
            }
            for r in rows
        ]
    )


@router.post("/jobs")
def create_job(body: JobBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    from panelpro.services.cronsvc import validate_schedule

    job = BackupJob(
        name=body.name[:255],
        sites=body.sites,
        databases=body.databases,
        schedule=validate_schedule(body.schedule),
        target=body.target,
        target_config=body.target_config,
        keep=max(1, body.keep),
        enabled=body.enabled,
    )
    db.add(job)
    db.commit()
    return api_ok({"id": job.id, "name": job.name})


@router.post("/jobs/{job_id}/update")
def update_job(job_id: int, body: JobBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    from panelpro.services.cronsvc import validate_schedule

    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise PanelError("Backup job not found.", 404)
    job.name = body.name[:255]
    job.sites = body.sites
    job.databases = body.databases
    job.schedule = validate_schedule(body.schedule)
    job.target = body.target
    job.target_config = body.target_config
    job.keep = max(1, body.keep)
    job.enabled = body.enabled
    db.commit()
    return api_ok({"updated": job.id})


@router.post("/jobs/{job_id}/delete")
def delete_job(job_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise PanelError("Backup job not found.", 404)
    db.delete(job)
    db.commit()
    return api_ok({"deleted": job_id})


@router.post("/jobs/{job_id}/toggle")
def toggle_job(job_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise PanelError("Backup job not found.", 404)
    job.enabled = not job.enabled
    db.commit()
    return api_ok({"enabled": job.enabled})


@router.post("/jobs/{job_id}/run")
def run_job(job_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise PanelError("Backup job not found.", 404)
    run_row = backupsvc.run_backup_job(job)
    job.last_run_at = datetime.utcnow()
    job.last_status = run_row.status
    db.add(run_row)
    db.commit()
    if run_row.status == "done":
        notify_event("backup_done", "Backup finished",
                     f"{job.name}: {run_row.filename} ({run_row.size_bytes} bytes)")
    else:
        notify_event("backup_failed", "Backup failed", f"{job.name}: {run_row.message}")
    return api_ok({"status": run_row.status, "filename": run_row.filename,
                   "size": run_row.size_bytes, "message": run_row.message})


@router.get("/runs")
def runs(job_id: int | None = None, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    q = db.query(BackupRun).order_by(BackupRun.created_at.desc())
    if job_id:
        q = q.filter(BackupRun.job_id == job_id)
    rows = q.limit(100).all()
    return api_ok(
        [
            {
                "id": r.id,
                "job_id": r.job_id,
                "filename": r.filename,
                "size": r.size_bytes,
                "status": r.status,
                "message": r.message,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@router.get("/files")
def files(ctx=Depends(require_auth)):
    CFG.backup_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(CFG.backup_dir.glob("*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True):
        out.append({"name": p.name, "size": p.stat().st_size,
                    "mtime": int(p.stat().st_mtime)})
    return api_ok(out)


@router.get("/download")
def download(name: str, ctx=Depends(require_auth)):
    p = CFG.backup_dir / Path(name).name  # basename only
    if not p.exists():
        raise PanelError("Archive not found.", 404)
    return FileResponse(str(p), filename=p.name, media_type="application/gzip")


@router.post("/restore")
def restore(archive: str, member: str, dest: str, ctx=Depends(require_role("operator"))):
    p = CFG.backup_dir / Path(archive).name
    return api_ok(backupsvc.restore_site(str(p), member, dest))


@router.get("/archive-members")
def archive_members(name: str, ctx=Depends(require_auth)):
    import tarfile

    p = CFG.backup_dir / Path(name).name
    if not p.exists():
        raise PanelError("Archive not found.", 404)
    with tarfile.open(p, "r:gz") as tf:
        names = sorted({m.name.split("/")[0] for m in tf.getmembers()[:500]})
    return api_ok(names)
