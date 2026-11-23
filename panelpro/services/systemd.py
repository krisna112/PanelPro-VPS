"""systemd service management via systemctl (Linux servers only)."""

from __future__ import annotations

import re

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run

ALLOWED_ACTIONS = {"start", "stop", "restart", "reload", "enable", "disable"}
UNIT_RE = re.compile(r"^[A-Za-z0-9_.@:\\-]+\.(service|socket|timer)$")


def _require_linux() -> None:
    if CFG.is_windows:
        raise PanelError("systemd operations require a Linux server.", 400)


def _validate_unit(unit: str) -> str:
    if not UNIT_RE.match(unit):
        raise PanelError(f"Invalid unit name: {unit}", 400)
    return unit


def list_units(patterns: list[str] | None = None) -> list[dict]:
    _require_linux()
    res = run(
        ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"],
        timeout=25,
    )
    units: list[dict] = []
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        name, load, active = parts[0], parts[1], parts[2]
        description = " ".join(parts[4:]) if len(parts) > 4 else ""
        if not name.endswith(".service"):
            continue
        if patterns and not any(p in name or p in description.lower() for p in patterns):
            continue
        units.append(
            {"unit": name, "active": active, "load": load, "description": description}
        )
    return units


def action(unit: str, act: str) -> dict:
    _require_linux()
    _validate_unit(unit)
    if act not in ALLOWED_ACTIONS:
        raise PanelError(f"Unsupported service action: {act}", 400)
    res = run(["systemctl", act, unit], timeout=60, check=True)
    return {"unit": unit, "action": act, "output": res.stdout.strip()[-400:]}


def is_active(unit: str) -> bool:
    _require_linux()
    _validate_unit(unit)
    return run(["systemctl", "is-active", "--quiet", unit], timeout=15).code == 0


def journal(unit: str, lines: int = 100) -> str:
    _require_linux()
    _validate_unit(unit)
    lines = max(1, min(int(lines), 1000))
    res = run(
        ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"], timeout=30
    )
    return res.stdout[-64_000:]
