"""App store service: manifest-driven one-click installers.

Manifests live in ``panelpro/templates/apps/*.json``.  A manifest declares
parameters, an install script (Jinja2/bash) and an uninstall script; docker
apps additionally carry a compose template.  Scripts are rendered per
install and executed with bash.
"""

from __future__ import annotations

import json

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.keyvault import random_password, token_hex
from panelpro.core.syscmd import run_shell

_env = Environment(
    loader=FileSystemLoader(str(CFG.templates_dir / "apps")),
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def list_manifests() -> list[dict]:
    """All available app manifests (without raw scripts)."""
    apps = []
    for path in sorted((CFG.templates_dir / "apps").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        apps.append(
            {
                "id": data.get("id", path.stem),
                "name": data.get("name", path.stem),
                "category": data.get("category", "apps"),
                "description": data.get("description", ""),
                "version": data.get("version", ""),
                "type": data.get("type", "script"),
                "port": data.get("port"),
                "docs_url": data.get("docs_url", ""),
                "params": [
                    {"name": p["name"], "label": p.get("label", p["name"]),
                     "default": p.get("default", ""), "required": p.get("required", False)}
                    for p in data.get("params", [])
                ],
            }
        )
    return apps


def load_manifest(app_id: str) -> dict:
    path = CFG.templates_dir / "apps" / f"{app_id}.json"
    if not path.exists():
        raise PanelError(f"Unknown app: {app_id}", 404)
    return json.loads(path.read_text(encoding="utf-8"))


def _render(template: str, params: dict) -> str:
    return _env.from_string(template).render(**params)


def install(manifest: dict, params: dict) -> dict:
    """Render + run the install script; docker apps go through compose."""
    app_id = manifest["id"]
    app_home = CFG.apps_dir / app_id
    app_home.mkdir(parents=True, exist_ok=True)

    ctx = dict(params)
    ctx.setdefault("app_home", str(app_home))
    ctx.setdefault("www_root", str(CFG.www_root))
    ctx.setdefault("random_password", random_password())
    ctx.setdefault("secret", token_hex(16))

    if manifest.get("type") == "docker":
        compose_text = _render(manifest.get("compose", ""), ctx)
        (app_home / "docker-compose.yml").write_text(compose_text, encoding="utf-8")
        script = _render(
            manifest.get("install_script", "cd {{ app_home }} && docker compose up -d"),
            ctx,
        )
        (app_home / "install.sh").write_text(script, encoding="utf-8")
        res = run_shell(f"bash '{app_home}/install.sh'", timeout=1800)
        if res.code != 0:
            raise PanelError(f"Install failed: {(res.stderr or res.stdout)[-500:]}", 500)
        return {"app_home": str(app_home), "log": res.stdout[-1000:]}

    script = _render(manifest.get("install_script", "echo nothing to do"), ctx)
    script_path = app_home / "install.sh"
    script_path.write_text(script, encoding="utf-8")
    res = run_shell(f"bash '{script_path}'", timeout=3600)
    if res.code != 0:
        raise PanelError(f"Install failed: {(res.stderr or res.stdout)[-500:]}", 500)
    return {"app_home": str(app_home), "log": res.stdout[-1000:]}


def uninstall(manifest: dict, install_path: str) -> dict:
    app_id = manifest["id"]
    if manifest.get("type") == "docker":
        compose_dir = install_path or str(CFG.apps_dir / app_id)
        try:
            from panelpro.services import dockermgr

            dockermgr.compose_down(compose_dir)
        except PanelError:
            pass  # docker may already be gone
        return {"removed": compose_dir}

    script = _render(manifest.get("uninstall_script", "echo nothing to remove"), {})
    app_home = CFG.apps_dir / app_id
    script_path = app_home / "uninstall.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    res = run_shell(f"bash '{script_path}'", timeout=600)
    return {"removed": app_id, "output": (res.stdout + res.stderr)[-500:]}


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def app_status(installed: dict) -> str:
    if installed.get("type") == "docker" and installed.get("app_id"):
        try:
            from panelpro.services import dockermgr

            for c in dockermgr.containers(all_ps=True):
                names = (c.get("Names") or c.get("names") or "")
                if installed["app_id"] in names:
                    return c.get("State") or "unknown"
        except PanelError:
            return "docker-missing"
    if installed.get("port"):
        return "running" if port_open(int(installed["port"])) else "stopped"
    return "unknown"
