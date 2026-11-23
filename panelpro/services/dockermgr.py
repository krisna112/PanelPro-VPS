"""Docker management wrapper (docker CLI with JSON formatting)."""

from __future__ import annotations

import json
import re

from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run, which


def available() -> bool:
    return which("docker") is not None


def _docker(*args: str, timeout: int = 120) -> str:
    require("docker", "Install Docker first (see Apps page or docs/INSTALL.md).")
    res = run(["docker", *args], timeout=timeout)
    if res.code != 0:
        raise PanelError(f"docker error: {(res.stderr or res.stdout)[-400:]}", 500)
    return res.stdout


def _safe_name(name: str) -> str:
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", name or ""):
        raise PanelError(f"Invalid docker resource name: {name}", 400)
    return name


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


def containers(all_ps: bool = True) -> list[dict]:
    out = _docker("ps", "-a" if all_ps else "", "--format", "{{json .}}")
    items = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except ValueError:
            continue
    return items


def container_action(name: str, action: str) -> dict:
    _safe_name(name)
    if action not in ("start", "stop", "restart", "pause", "unpause", "kill", "remove"):
        raise PanelError(f"Unsupported container action: {action}", 400)
    args = ["container", action, name]
    if action == "remove":
        args.append("--force")
    _docker(*args, timeout=60)
    return {"container": name, "action": action}


def container_logs(name: str, tail: int = 200) -> str:
    _safe_name(name)
    return _docker("logs", "--tail", str(max(1, min(tail, 5000))), name, timeout=60)


def container_stats() -> list[dict]:
    out = _docker("stats", "--no-stream", "--format", "{{json .}}", timeout=90)
    items = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    return items


def container_exec(name: str, command: str) -> str:
    _safe_name(name)
    if not command or len(command) > 2000:
        raise PanelError("Invalid exec command.", 400)
    return _docker("exec", name, "sh", "-lc", command, timeout=120)


# ---------------------------------------------------------------------------
# Images / volumes / networks
# ---------------------------------------------------------------------------


def images() -> list[dict]:
    out = _docker("images", "--format", "{{json .}}")
    items = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    return items


def pull(image: str) -> dict:
    if not re.match(r"^[A-Za-z0-9_./:@-]+$", image or ""):
        raise PanelError(f"Invalid image reference: {image}", 400)
    out = _docker("pull", image, timeout=600)
    return {"image": image, "output": out[-400:]}


def remove_image(image: str) -> dict:
    if not re.match(r"^[A-Za-z0-9_./:@-]+$", image or ""):
        raise PanelError(f"Invalid image reference: {image}", 400)
    _docker("rmi", "-f", image, timeout=120)
    return {"image": image}


def prune_images() -> dict:
    out = _docker("image", "prune", "-af", timeout=300)
    return {"output": out[-400:]}


def volumes() -> list[dict]:
    out = _docker("volume", "ls", "--format", "{{json .}}")
    items = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    return items


def networks() -> list[dict]:
    out = _docker("network", "ls", "--format", "{{json .}}")
    items = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    return items


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


def compose_up(project_dir: str) -> dict:
    res = run(
        ["docker", "compose", "-f", f"{project_dir}/docker-compose.yml", "up", "-d"],
        timeout=600,
    )
    if res.code != 0:
        raise PanelError(f"compose up failed: {(res.stderr or res.stdout)[-400:]}", 500)
    return {"dir": project_dir, "output": res.stdout[-400:]}


def compose_down(project_dir: str) -> dict:
    res = run(
        ["docker", "compose", "-f", f"{project_dir}/docker-compose.yml", "down"],
        timeout=300,
    )
    if res.code != 0:
        raise PanelError(f"compose down failed: {(res.stderr or res.stdout)[-400:]}", 500)
    return {"dir": project_dir, "output": res.stdout[-400:]}
