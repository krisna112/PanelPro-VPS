"""System monitor: live snapshot, in-memory ring buffer, SQLite retention.

A daemon thread samples CPU / memory / disk / network every
``MONITOR_SAMPLE_INTERVAL`` seconds, keeps ~24h in memory for instant
charts, and flushes one row per ``MONITOR_FLUSH_INTERVAL`` to the database
for 7-day history.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

import psutil

from panelpro.constants import (
    MONITOR_FLUSH_INTERVAL,
    MONITOR_HISTORY_POINTS,
    MONITOR_RETENTION_DAYS,
    MONITOR_SAMPLE_INTERVAL,
)
from panelpro.core.database import SessionLocal
from panelpro.models.tables import MonitorSample


def _load_average() -> float:
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return 0.0


def top_processes(limit: int = 15) -> dict:
    procs = []
    for p in psutil.process_iter(
        ["pid", "name", "username", "cpu_percent", "memory_percent", "memory_info"]
    ):
        try:
            info = p.info
            mem = info["memory_info"].rss if info.get("memory_info") else 0
            procs.append(
                {
                    "pid": info["pid"],
                    "name": (info["name"] or "?")[:64],
                    "user": (info["username"] or "?")[:64],
                    "cpu": round(info["cpu_percent"] or 0.0, 1),
                    "mem": round(info["memory_percent"] or 0.0, 1),
                    "rss": mem,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: (x["cpu"], x["mem"]), reverse=True)
    by_cpu = procs[:limit]
    by_mem = sorted(procs, key=lambda x: x["mem"], reverse=True)[:limit]
    return {"by_cpu": by_cpu, "by_mem": by_mem}


def disk_usage_all() -> list[dict]:
    result = []
    for part in psutil.disk_partitions(all=False):
        if "loop" in part.device or "snap" in part.device:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        result.append(
            {
                "device": part.device,
                "mount": part.mountpoint,
                "fstype": part.fstype,
                "total": u.total,
                "used": u.used,
                "free": u.free,
                "percent": round(u.used / u.total * 100, 1) if u.total else 0,
            }
        )
    return result


class MonitorCollector:
    """Restart-safe background sampler (owns its own worker thread).

    Never raises, never blocks the event loop.
    """

    def __init__(self) -> None:
        self.samples: deque[dict] = deque(maxlen=MONITOR_HISTORY_POINTS)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_flush = 0.0
        self._last_net: tuple[int, int] | None = None
        self._net_rate_in = 0.0
        self._net_rate_out = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pp-monitor")
        self._thread.start()

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self) -> None:
        self._stop_event.set()

    # -- live snapshot ----------------------------------------------------
    def snapshot(self) -> dict:
        cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        root_usage = disk_usage_all()
        disk = root_usage[0] if root_usage else {"used": 0, "total": 0, "percent": 0}
        net = psutil.net_io_counters()
        self._update_net_rates(net)
        boot = psutil.boot_time()
        return {
            "ts": int(time.time()),
            "cpu": round(sum(cpu_cores) / max(len(cpu_cores), 1), 1),
            "cpu_cores": cpu_cores,
            "load1": round(_load_average(), 2),
            "mem_used": vm.used,
            "mem_total": vm.total,
            "mem_percent": vm.percent,
            "swap_used": sm.used,
            "swap_total": sm.total,
            "disk_used": disk["used"],
            "disk_total": disk["total"],
            "disk_percent": disk["percent"],
            "disks": root_usage,
            "net_in": net.bytes_recv,
            "net_out": net.bytes_sent,
            "net_rate_in": round(self._net_rate_in, 0),
            "net_rate_out": round(self._net_rate_out, 0),
            "uptime": int(time.time() - boot),
            "processes": top_processes(),
        }

    def _update_net_rates(self, net) -> None:
        totals = (net.bytes_recv, net.bytes_sent)
        if self._last_net is not None:
            elapsed = MONITOR_SAMPLE_INTERVAL
            d_in = totals[0] - self._last_net[0]
            d_out = totals[1] - self._last_net[1]
            if elapsed > 0 and d_in >= 0 and d_out >= 0:
                self._net_rate_in = d_in / elapsed
                self._net_rate_out = d_out / elapsed
        self._last_net = totals

    # -- background loop ----------------------------------------------------
    def _collect(self) -> dict:
        snap = self.snapshot()
        return {
            "ts": snap["ts"],
            "cpu": snap["cpu"],
            "mem_used": snap["mem_used"],
            "mem_total": snap["mem_total"],
            "disk_used": snap["disk_used"],
            "disk_total": snap["disk_total"],
            "net_in": snap["net_in"],
            "net_out": snap["net_out"],
            "load1": snap["load1"],
        }

    def flush(self) -> None:
        if not self.samples:
            return
        row = self.samples[-1]
        db = SessionLocal()
        try:
            db.add(MonitorSample(**row))
            cutoff = int(time.time()) - MONITOR_RETENTION_DAYS * 86400
            db.query(MonitorSample).filter(MonitorSample.ts < cutoff).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(MONITOR_SAMPLE_INTERVAL)
            if self._stop_event.is_set():
                break
            try:
                self.samples.append(self._collect())
                if time.time() - self._last_flush >= MONITOR_FLUSH_INTERVAL:
                    self.flush()
                    self._last_flush = time.time()
            except Exception:
                # Monitoring must never take the panel down.
                time.sleep(1)


MONITOR = MonitorCollector()


def history(since_ts: int | None = None) -> list[dict]:
    """Return chart-ready history (memory first, DB as fallback)."""
    cutoff = since_ts or (int(time.time()) - 86400)
    rows = [s for s in MONITOR.samples if s["ts"] >= cutoff]
    if rows:
        return list(rows)
    db = SessionLocal()
    try:
        out = (
            db.query(MonitorSample)
            .filter(MonitorSample.ts >= cutoff)
            .order_by(MonitorSample.ts.asc())
            .limit(2000)
            .all()
        )
        return [
            {
                "ts": r.ts,
                "cpu": r.cpu,
                "mem_used": r.mem_used,
                "mem_total": r.mem_total,
                "disk_used": r.disk_used,
                "disk_total": r.disk_total,
                "net_in": r.net_in,
                "net_out": r.net_out,
                "load1": r.load1,
            }
            for r in out
        ]
    finally:
        db.close()
