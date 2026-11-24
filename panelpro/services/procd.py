"""Process guard: keeps services, pidfiles, ports and commands alive.

Tasks are checked on a scheduler job; a dead target is restarted via
``systemctl restart`` (systemd kind) or the task's own restart command,
then a notification is emitted with a per-task cooldown.
"""

from __future__ import annotations

import socket
import time
from datetime import datetime

import psutil

from panelpro.core.errors import PanelError
from panelpro.core.notify import notify_event
from panelpro.core.syscmd import run, run_shell
from panelpro.models.tables import DaemonTask

KINDS = ("systemd", "pidfile", "port", "command")

# Re-alert the same task at most once per 30 minutes.
ALERT_COOLDOWN = 30 * 60
_last_alert: dict[int, float] = {}


def validate_target(kind: str, target: str) -> str:
    target = (target or "").strip()
    if not target:
        raise PanelError("Target is required.", 400)
    if kind == "systemd":
        from panelpro.services.systemd import _validate_unit

        _validate_unit(target if target.endswith(".service") else target + ".service")
    elif kind == "pidfile":
        if len(target) > 255 or ".." in target:
            raise PanelError("Invalid pid file path.", 400)
    elif kind == "port":
        host, _, port = target.rpartition(":")
        try:
            if not 0 < int(port) < 65536:
                raise ValueError
        except ValueError as exc:
            raise PanelError(
                f"Invalid port target '{target}' (expected host:port).", 400
            ) from exc
    elif kind == "command":
        if "\n" in target or "\r" in target or len(target) > 255:
            raise PanelError("Invalid command target.", 400)
    else:
        raise PanelError(f"Unknown guard kind: {kind}", 400)
    return target


def check_alive(task: DaemonTask) -> bool:
    """Return True when the guarded target is currently alive."""
    kind, target = task.kind, task.target
    try:
        if kind == "systemd":
            unit = target if target.endswith(".service") else target + ".service"
            from panelpro.services.systemd import is_active

            return is_active(unit)
        if kind == "pidfile":
            try:
                with open(target, encoding="utf-8") as fh:
                    pid = int(fh.read().strip())
            except (OSError, ValueError):
                return False
            return psutil.pid_exists(pid)
        if kind == "port":
            host, _, port = target.rpartition(":")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                return sock.connect_ex((host or "127.0.0.1", int(port))) == 0
        if kind == "command":
            import shlex

            res = run(shlex.split(target), timeout=15, check=False)
            return res.code == 0
    except Exception:
        return False
    return False


def restart(task: DaemonTask) -> None:
    kind = task.kind
    if kind == "systemd":
        unit = task.target if task.target.endswith(".service") else task.target + ".service"
        run(["systemctl", "restart", unit], timeout=60, check=True)
        return
    if task.restart_cmd:
        run_shell(task.restart_cmd, timeout=120)
        return
    raise PanelError(
        f"Task '{task.name}' is down but no restart command is configured.", 400
    )


def _notify_cooldown(task_id: int) -> bool:
    now = time.time()
    if now - _last_alert.get(task_id, 0) < ALERT_COOLDOWN:
        return False
    _last_alert[task_id] = now
    return True


def check_one(db, task: DaemonTask) -> DaemonTask:
    alive = check_alive(task)
    task.last_check_at = datetime.utcnow()
    if alive:
        task.last_status = "up"
        db.commit()
        return task
    task.last_status = "down"
    try:
        restart(task)
        task.last_status = "restarted"
        task.restart_count = (task.restart_count or 0) + 1
        if _notify_cooldown(task.id):
            notify_event(
                "daemon_restarted",
                "Process guard",
                f"'{task.name}' ({task.kind}: {task.target}) was down and has been restarted.",
            )
    except Exception as exc:
        task.last_status = "down"
        if _notify_cooldown(task.id):
            notify_event(
                "daemon_down",
                "Process guard",
                f"'{task.name}' ({task.kind}: {task.target}) is down: {str(exc)[:160]}",
            )
    db.commit()
    return task


def daemon_check_job() -> None:
    """Scheduler entry: check every due task once."""
    from panelpro.core.database import SessionLocal

    db = SessionLocal()
    try:
        now = time.time()
        for task in db.query(DaemonTask).filter(DaemonTask.enabled.is_(True)).all():
            last = task.last_check_at.timestamp() if task.last_check_at else 0
            if now - last >= max(int(task.check_interval or 60), 10):
                check_one(db, task)
    finally:
        db.close()


def task_payload(task: DaemonTask) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "kind": task.kind,
        "target": task.target,
        "restart_cmd": task.restart_cmd,
        "check_interval": task.check_interval,
        "enabled": task.enabled,
        "last_status": task.last_status,
        "last_check_at": task.last_check_at.isoformat() if task.last_check_at else None,
        "restart_count": task.restart_count,
    }
