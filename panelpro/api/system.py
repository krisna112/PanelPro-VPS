"""System endpoints: info, service manager, processes, panel update."""

from __future__ import annotations

import os
import platform
import shutil

import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_role
from panelpro.config import CFG
from panelpro.constants import KNOWN_SERVICES, VERSION
from panelpro.core.errors import PanelError
from panelpro.core.monitor import top_processes

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/info")
def info(ctx=Depends(require_role("viewer"))):
    uname = platform.uname()
    cpu_model = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "model name" in line:
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        cpu_model = uname.processor or ""
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage(CFG.www_root if CFG.www_root.exists() else "/")
    return api_ok(
        {
            "hostname": uname.node,
            "os": f"{uname.system} {uname.release}",
            "arch": uname.machine,
            "kernel": uname.version,
            "python": platform.python_version(),
            "panel_version": VERSION,
            "uptime": int(psutil.boot_time() and __import__("time").time() - psutil.boot_time()),
            "cpu_model": cpu_model,
            "cpu_cores": os.cpu_count() or 1,
            "mem_total": mem.total,
            "disk_total": disk.total,
            "www_root": str(CFG.www_root),
        }
    )


@router.get("/services")
def services(ctx=Depends(require_role("viewer"))):
    try:
        from panelpro.services import systemd
    except Exception:
        systemd = None
    if systemd and not CFG.is_windows:
        try:
            units = systemd.list_units(patterns=KNOWN_SERVICES + ["panelpro"])
            return api_ok({"available": True, "units": units})
        except PanelError as exc:
            return api_ok({"available": False, "units": [], "message": str(exc.message)})
    return api_ok(
        {"available": False, "units": [],
         "message": "Service management requires a Linux server with systemd."}
    )


@router.post("/services/{unit}/{action}")
def service_action(unit: str, action: str, ctx=Depends(require_role("admin"))):
    from panelpro.services import systemd

    return api_ok(systemd.action(unit, action))


@router.get("/services/{unit}/journal")
def service_journal(unit: str, lines: int = 100, ctx=Depends(require_role("operator"))):
    from panelpro.services import systemd

    return api_ok({"unit": unit, "log": systemd.journal(unit, lines)})


class KillBody(BaseModel):
    pid: int


@router.get("/processes")
def processes(ctx=Depends(require_role("viewer"))):
    return api_ok(top_processes(50))


@router.post("/processes/kill")
def kill_process(body: KillBody, ctx=Depends(require_role("admin"))):
    if body.pid <= 1 or body.pid == os.getpid():
        raise PanelError("Refusing to kill this process.", 400)
    try:
        proc = psutil.Process(body.pid)
        proc.kill()
        return api_ok({"killed": body.pid, "name": proc.name()})
    except psutil.NoSuchProcess as exc:
        raise PanelError(f"Process {body.pid} does not exist.", 404) from exc


@router.post("/panel/update")
def panel_update(ctx=Depends(require_role("admin"))):
    script = CFG.home / "update.sh"
    src = CFG.package_dir.parent / "scripts" / "update.sh"
    if src.exists():
        res = __import__("subprocess").run(
            ["bash", str(src)], capture_output=True, text=True, timeout=600
        )
        return api_ok(
            {"updated": res.returncode == 0,
             "output": ((res.stdout or "") + (res.stderr or ""))[-1000:]}
        )
    if script.exists():
        res = __import__("subprocess").run(
            ["bash", str(script)], capture_output=True, text=True, timeout=600
        )
        return api_ok(
            {"updated": res.returncode == 0,
             "output": ((res.stdout or "") + (res.stderr or ""))[-1000:]}
        )
    raise PanelError("update.sh not found — update manually via git pull + pip install.", 400)
