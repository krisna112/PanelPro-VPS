"""Dashboard summary endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth
from panelpro.core import monitor as monitor_mod
from panelpro.core.database import get_db
from panelpro.models.tables import AuditLog, BackupJob, CronJob, DatabaseRow, InstalledApp, Site, SslCert

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    snap = monitor_mod.MONITOR.snapshot()
    ssl_rows = db.query(SslCert).all()
    expiring = [
        {
            "name": row.name,
            "domain": row.domain,
            "not_after": row.not_after.isoformat() if row.not_after else None,
            "days_left": (row.not_after - datetime.utcnow()).days if row.not_after else None,
        }
        for row in ssl_rows
        if row.not_after and (row.not_after - datetime.utcnow()).days <= 30
    ]
    audit = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(10).all()
    return api_ok(
        {
            "counts": {
                "sites": db.query(Site).count(),
                "databases": db.query(DatabaseRow).count(),
                "crons": db.query(CronJob).filter(CronJob.enabled.is_(True)).count(),
                "apps": db.query(InstalledApp).count(),
                "backup_jobs": db.query(BackupJob).filter(BackupJob.enabled.is_(True)).count(),
                "certs": len(ssl_rows),
            },
            "system": {
                "cpu": snap["cpu"],
                "load1": snap["load1"],
                "mem_percent": snap["mem_percent"],
                "mem_used": snap["mem_used"],
                "mem_total": snap["mem_total"],
                "disk_percent": snap["disk_percent"],
                "disk_used": snap["disk_used"],
                "disk_total": snap["disk_total"],
                "net_rate_in": snap["net_rate_in"],
                "net_rate_out": snap["net_rate_out"],
                "uptime": snap["uptime"],
            },
            "ssl_expiring": expiring,
            "recent_audit": [
                {
                    "ts": a.ts.isoformat(),
                    "username": a.username,
                    "method": a.method,
                    "path": a.path,
                    "status": a.status,
                }
                for a in audit
            ],
        }
    )
