"""Scheduled task engine: manages root crontab entries with markers.

Panel-managed lines carry the marker ``# pp:<id>`` so they can be listed,
updated and toggled without touching unrelated crontab content.
"""

from __future__ import annotations

from datetime import datetime

from croniter import croniter

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, run_shell

MARKER = "# pp:{id}"
ENABLED_MARKER = "# pp-enabled"


def validate_schedule(expr: str) -> str:
    expr = (expr or "").strip()
    if not croniter.is_valid(expr):
        raise PanelError(f"Invalid cron expression: {expr}", 400)
    return expr


def next_run(expr: str) -> datetime:
    validate_schedule(expr)
    return croniter(expr, datetime.now()).get_next(datetime)


def build_command(job_type: str, command: str) -> str:
    if job_type == "shell":
        return command
    if job_type == "url":
        return f"curl -sS --max-time 300 '{command}' > /dev/null"
    if job_type == "script":
        return f"bash '{command}' >> '{CFG.cron_log_dir}/script-last.log' 2>&1"
    raise PanelError(f"Unknown task type: {job_type}", 400)


def read_crontab() -> list[str]:
    res = run(["crontab", "-l"], timeout=15, check=False)
    if res.code != 0:
        return []
    return res.stdout.splitlines()


def write_crontab(lines: list[str]) -> None:
    """Write the full crontab from stdin (crontab reads '-' as stdin)."""
    import subprocess

    content = "\n".join(lines).rstrip("\n") + "\n" if lines else ""
    proc = subprocess.run(
        ["crontab", "-"],
        input=content,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise PanelError(f"Failed to write crontab: {proc.stderr[-300:]}", 500)


def _entry_block(job_id: int, schedule: str, command: str, enabled: bool) -> list[str]:
    if not enabled:
        command_line = "# " + command
    else:
        command_line = command
    return [MARKER.format(id=job_id), f"{schedule} {command_line}"]


def upsert_entry(job_id: int, schedule: str, command: str, enabled: bool) -> None:
    validate_schedule(schedule)
    lines = read_crontab()
    out: list[str] = []
    marker = MARKER.format(id=job_id)
    skip_next = False
    for line in lines:
        if line.strip() == marker:
            skip_next = True
            out.append(marker)
            continue
        if skip_next:
            skip_next = False
            continue  # drop the old command line
        out.append(line)
    out.extend(_entry_block(job_id, schedule, command, enabled))
    write_crontab(out)


def remove_entry(job_id: int) -> None:
    lines = read_crontab()
    marker = MARKER.format(id=job_id)
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == marker:
            skipping = True
            continue
        if skipping:
            skipping = False
            continue
        out.append(line)
    write_crontab(out)


def run_job(job_id: int, job_type: str, command: str, name: str = "job") -> dict:
    """Execute a task now and store the log."""
    CFG.cron_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = CFG.cron_log_dir / f"{job_id}.log"
    cmd = build_command(job_type, command)
    started = datetime.utcnow()
    res = run_shell(cmd, timeout=1800)
    finished = datetime.utcnow()
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(
            f"\n===== {started.isoformat()} | {name} =====\n"
            f"$ {cmd}\n{res.stdout}{res.stderr}"
        )
        if not res.ok:
            fh.write(f"EXIT CODE: {res.code}\n")
    return {
        "ok": res.ok,
        "log_path": str(log_path),
        "elapsed_s": int((finished - started).total_seconds()),
    }


def job_log(job_id: int, lines: int = 200) -> str:
    log_path = CFG.cron_log_dir / f"{job_id}.log"
    if not log_path.exists():
        return ""
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        return "".join(fh.readlines()[-lines:])
