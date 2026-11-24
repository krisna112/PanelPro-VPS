"""App store service: manifest-driven one-click installers.

Manifests live in ``panelpro/templates/apps/*.json``.  A manifest declares
parameters, an install script (Jinja2/bash) and an uninstall script; docker
apps additionally carry a compose template.  Scripts are rendered per
install and executed with bash.
"""

from __future__ import annotations

import json
import re
import shlex
from threading import RLock

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.keyvault import random_password, token_hex
from panelpro.core.syscmd import run, which
from panelpro.models.tables import InstalledApp
from panelpro.services import native_apps, phpmgr, webservers

APP_LOCK = RLock()

_env = Environment(
    loader=FileSystemLoader(str(CFG.templates_dir / "apps")),
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def list_manifests() -> list[dict]:
    """All available app manifests (without raw scripts)."""
    apps = []
    docker_ready = _docker_ready()
    for path in sorted((CFG.templates_dir / "apps").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        app_type = data.get("type", "script")
        reason = native_apps.unavailable(data) if app_type == "native" else None
        if app_type == "docker" and not docker_ready:
            reason = "Docker Engine and the Docker Compose plugin are required."
        params = [dict(p) for p in data.get("params", [])]
        if data.get("id") == "php-fpm" and params:
            params[0]["choices"] = phpmgr.install_options()
        apps.append(
            {
                "id": data.get("id", path.stem),
                "name": data.get("name", path.stem),
                "category": data.get("category", "apps"),
                "description": data.get("description", ""),
                "version": data.get("version", ""),
                "type": app_type,
                "unavailable": reason,
                "port": data.get("port"),
                "docs_url": data.get("docs_url", ""),
                "params": params,
            }
        )
    return apps


def load_manifest(app_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", app_id):
        raise PanelError("Invalid app ID.", 400)
    path = CFG.templates_dir / "apps" / f"{app_id}.json"
    if not path.exists():
        raise PanelError(f"Unknown app: {app_id}", 404)
    return json.loads(path.read_text(encoding="utf-8"))


def _render(template: str, params: dict) -> str:
    return _env.from_string(template).render(**params)


def _docker_ready() -> bool:
    if not which("docker"):
        return False
    try:
        return run(["docker", "compose", "version"], timeout=5).ok
    except PanelError:
        return False


def _install_params(manifest: dict, params: dict) -> dict:
    result = {}
    for field in manifest.get("params", []):
        name = field["name"]
        value = params.get(name, field.get("default", ""))
        if not isinstance(value, (str, int)):
            raise PanelError(f"Invalid value for {field.get('label', name)}.", 400)
        value = str(value)
        if field.get("required") and not value:
            raise PanelError(f"{field.get('label', name)} is required.", 400)
        if name == "domain":
            value = webservers.validate_domain(value)
            if value.startswith("*."):
                raise PanelError("Use a single domain for this application.", 400)
        elif name == "http_port" and (not re.fullmatch(r"[0-9]{1,5}", value) or not 1 <= int(value) <= 65535):
            raise PanelError("Port must be between 1 and 65535.", 400)
        elif name in {"db_name", "db_user"} and not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", value):
            raise PanelError(f"Invalid {field.get('label', name)}.", 400)
        elif name == "redis_host" and not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", value):
            raise PanelError("Use a Redis hostname or IPv4 address.", 400)
        result[name] = value
    return result


def install_app(db, manifest: dict, params: dict) -> tuple[InstalledApp, dict]:
    values = _install_params(manifest, params)
    with APP_LOCK:
        app_type = manifest.get("type", "script")
        row = db.query(InstalledApp).filter_by(app_id=manifest["id"], type=app_type).first()
        if row and app_type != "native":
            raise PanelError(f"{manifest['name']} is already installed.", 409)
        result = install(manifest, values)
        if row is None:
            row = InstalledApp(app_id=manifest["id"], name=manifest["name"], type=app_type)
            db.add(row)
        row.version = result.get("version", manifest.get("version", ""))
        row.install_path = result.get("app_home", "")
        row.port = result.get("port", int(values["http_port"]) if "http_port" in values else manifest.get("port"))
        row.domain = values.get("domain")
        row.status = result.get("status", "installed")
        db.commit()
    return row, result


def install(manifest: dict, params: dict) -> dict:
    """Render + run the install script; docker apps go through compose."""
    app_id = manifest["id"]
    if manifest.get("type") == "native":
        return native_apps.install(manifest, params)
    if manifest.get("type") == "docker" and not _docker_ready():
        raise PanelError("Docker Engine and the Docker Compose plugin are required.", 400)
    app_home = CFG.apps_dir / app_id
    app_home.mkdir(parents=True, exist_ok=True)

    ctx = dict(params)
    ctx.update(app_home=shlex.quote(str(app_home)), www_root=str(CFG.www_root),
               random_password=random_password(), secret=token_hex(16))
    if app_id == "wordpress":
        password = ctx["db_pass"]
        if any(char in password for char in "\r\n\0"):
            raise PanelError("The database password cannot contain newlines or null bytes.", 400)
        php = password.replace("\\", "\\\\").replace("'", "\\'")
        sed = php.replace("\\", "\\\\").replace("/", "\\/").replace("&", "\\&")
        ctx["db_pass"] = re.sub(r'[\\"$`]', lambda match: "\\" + match[0], sed)

    if manifest.get("type") == "docker":
        compose_text = _render(manifest.get("compose", ""), ctx)
        (app_home / "docker-compose.yml").write_text(compose_text, encoding="utf-8")
        script = _render(
            manifest.get("install_script", "cd {{ app_home }} && docker compose up -d"),
            ctx,
        )
        script_path = app_home / "install.sh"
        script_path.write_text(script, encoding="utf-8")
        res = run(["bash", str(script_path)], timeout=1800)
        if res.code != 0:
            raise PanelError(f"Install failed: {(res.stderr or res.stdout)[-500:]}", 500)
        return {"app_home": str(app_home), "log": res.stdout[-1000:]}

    script = _render(manifest.get("install_script", "echo nothing to do"), ctx)
    script_path = app_home / "install.sh"
    webservers.write_config(script_path, script.encode("utf-8"), 0o600)
    res = run(["bash", str(script_path)], timeout=3600)
    if res.code != 0:
        raise PanelError(f"Install failed: {(res.stderr or res.stdout)[-500:]}", 500)
    return {"app_home": str(app_home), "log": res.stdout[-1000:]}


def uninstall(manifest: dict, install_path: str) -> dict:
    app_id = manifest["id"]
    if manifest.get("type") == "native":
        if app_id != "phpmyadmin":
            raise PanelError("Use the system package manager to remove shared packages.", 400)
        native_apps.remove_phpmyadmin_access()
        return {"removed": app_id}
    if manifest.get("type") == "docker":
        compose_dir = install_path or str(CFG.apps_dir / app_id)
        from panelpro.services import dockermgr

        dockermgr.compose_down(compose_dir)
        return {"removed": compose_dir}

    script = _render(manifest.get("uninstall_script", "echo nothing to remove"), {})
    app_home = CFG.apps_dir / app_id
    script_path = app_home / "uninstall.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    res = run(["bash", str(script_path)], timeout=600, check=True)
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
    if installed.get("type") == "native":
        return installed.get("status", "installed")
    return "unknown"
