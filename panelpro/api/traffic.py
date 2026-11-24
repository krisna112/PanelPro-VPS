"""Traffic statistics endpoints (per-site access-log analytics)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth
from panelpro.core.database import get_db
from panelpro.services import traffic as traffic_svc

router = APIRouter(prefix="/api/traffic", tags=["traffic"])


@router.get("")
def get_traffic(
    site_id: int | None = None,
    days: int = 7,
    db: Session = Depends(get_db),
    ctx=Depends(require_auth),
):
    return api_ok(traffic_svc.series(db, site_id, days))


@router.post("/collect")
def collect_now(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    """Run one collection pass immediately (also runs every 5 minutes)."""
    traffic_svc.traffic_collect_job()
    return api_ok({"collected": True})
