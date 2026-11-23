"""Monitor endpoints: realtime snapshot, history, disks, processes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from panelpro.api.deps import api_ok, require_auth
from panelpro.core import monitor as monitor_mod

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/realtime")
def realtime(ctx=Depends(require_auth)):
    return api_ok(monitor_mod.MONITOR.snapshot())


@router.get("/history")
def history(hours: int = 24, ctx=Depends(require_auth)):
    since = int(time.time()) - max(1, min(hours, 168)) * 3600
    rows = monitor_mod.history(since)
    # convert cumulative network counters into per-point rates
    out = []
    prev = None
    for row in rows:
        item = dict(row)
        if prev is not None and row["ts"] > prev["ts"]:
            elapsed = row["ts"] - prev["ts"]
            item["net_in_rate"] = max(0, (row["net_in"] - prev["net_in"]) / elapsed)
            item["net_out_rate"] = max(0, (row["net_out"] - prev["net_out"]) / elapsed)
        else:
            item["net_in_rate"] = 0
            item["net_out_rate"] = 0
        out.append(item)
        prev = row
    return api_ok(out)


@router.get("/disks")
def disks(ctx=Depends(require_auth)):
    return api_ok(monitor_mod.disk_usage_all())


@router.get("/processes")
def processes(ctx=Depends(require_auth)):
    return api_ok(monitor_mod.top_processes(50))
