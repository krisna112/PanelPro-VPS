"""PHP multi-version management: detection, extensions, ini editing, FPM."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which

FPM_UNIT_CANDIDATES = "php{v}-fpm", "php{v}-phpfpm", "php-fpm"
INI_PATH_RE = re.compile(r"^/etc/php/([\d.]+)/(cli|fpm|apache2)/php\.ini$")


def detect_versions() -> list[str]:
    """Installed PHP versions (descending), from /etc/php and bin/phpX.Y."""
    versions: set[str] = set()
    etc_php = Path("/etc/php")
    if etc_php.is_dir():
        for child in etc_php.iterdir():
            if child.is_dir() and re.match(r"^\d+\.\d+$", child.name):
                versions.add(child.name)
    for bin_path in Path("/usr/bin").glob("php[0-9]*"):
        m = re.match(r"^php(\d+\.\d+)$", bin_path.name)
        if m:
            versions.add(m.group(1))
    if which("php"):
        res = run(["php", "-r", "echo PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION;"], timeout=10)
        if res.code == 0 and res.stdout.strip():
            versions.add(res.stdout.strip())
    return sorted(versions, reverse=True)


def fpm_unit(version: str) -> str | None:
    from panelpro.core.syscmd import run as _run

    for pattern in FPM_UNIT_CANDIDATES:
        unit = pattern.format(v=version)
        if unit == "php-fpm" and version:
            continue
        res = _run(["systemctl", "list-unit-files", unit + ".service"], timeout=15)
        if res.code == 0 and unit in res.stdout:
            return unit + ".service"
    return None


def list_versions() -> list[dict]:
    from panelpro.services import systemd

    result = []
    for v in detect_versions():
        unit = fpm_unit(v)
        active = False
        if unit and not CFG.is_windows:
            active = systemd.is_active(unit)
        result.append(
            {
                "version": v,
                "cli": str(Path("/usr/bin") / f"php{v}") if which(f"php{v}") else which("php"),
                "fpm_unit": unit,
                "fpm_active": active,
            }
        )
    return result


def require_version(version: str) -> str:
    if version not in detect_versions():
        raise PanelError(f"PHP {version} is not installed.", 404)
    return version


def cli_binary(version: str) -> str:
    require_version(version)
    return f"php{version}" if which(f"php{version}") else "php"


def extensions(version: str) -> list[str]:
    binary = cli_binary(version)
    res = run([binary, "-m"], timeout=30)
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def install_extension(version: str, extension: str) -> dict:
    require_version(version)
    if not re.match(r"^[a-z0-9-]{2,40}$", extension or ""):
        raise PanelError(f"Invalid extension name: {extension}", 400)
    package = f"php{version}-{extension}" if shutil.which("apt-get") else f"php-{extension}"
    installer = "apt-get" if shutil.which("apt-get") else "yum"
    res = run(
        [installer, "install", "-y", package],
        timeout=600,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    if res.code != 0:
        raise PanelError(f"Extension install failed: {res.stderr[-400:]}", 500)
    restart(version)
    return {"version": version, "extension": extension, "package": package}


def ini_paths(version: str) -> dict:
    require_version(version)
    paths: dict = {}
    for ini in Path(f"/etc/php/{version}").rglob("php.ini"):
        sapi = ini.parent.name
        paths[sapi] = str(ini)
    if not paths and which("php"):
        res = run(["php", "--ini"], timeout=10)
        loaded = [
            line.split(":")[1].strip()
            for line in res.stdout.splitlines()
            if line.startswith("Loaded Configuration File")
        ]
        if loaded:
            paths["cli"] = loaded[0]
    return paths


def read_ini(version: str, sapi: str = "fpm") -> dict:
    paths = ini_paths(version)
    path = paths.get(sapi)
    if not path:
        raise PanelError(f"No php.ini for PHP {version} ({sapi}).", 404)
    return {"path": path, "content": Path(path).read_text(encoding="utf-8")}


def write_ini(version: str, sapi: str, content: str) -> dict:
    paths = ini_paths(version)
    path = paths.get(sapi)
    if not path:
        raise PanelError(f"No php.ini for PHP {version} ({sapi}).", 404)
    p = Path(path)
    backup = p.with_suffix(".ini.pp-bak")
    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(content, encoding="utf-8")
    restart(version)
    return {"path": path, "backup": str(backup)}


def restart(version: str) -> None:
    from panelpro.services import systemd

    unit = fpm_unit(version)
    if not unit:
        raise PanelError(f"No PHP-FPM service found for {version}.", 404)
    systemd.action(unit, "restart")


POOL_FILE_CANDIDATES = [
    "/etc/php/{v}/fpm/pool.d/www.conf",
    "/etc/php-fpm.d/www.conf",
    "/etc/php/{v}/fpm/pool.d/panelpro.conf",
]


def pool_file(version: str) -> Path | None:
    for pattern in POOL_FILE_CANDIDATES:
        p = Path(pattern.format(v=version))
        if p.exists():
            return p
    return None


def pool_settings(version: str) -> dict:
    p = pool_file(version)
    if not p:
        return {}
    values: dict = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("["):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return {k: values[k] for k in ("pm", "pm.max_children", "pm.start_servers",
                                    "pm.min_spare_servers", "pm.max_spare_servers",
                                    "pm.max_requests", "user", "group", "listen")
            if k in values}


def tune_pool(version: str, settings: dict) -> dict:
    """Update pool directives in place (with backup) and restart FPM."""
    p = pool_file(version)
    if not p:
        raise PanelError("No PHP-FPM pool file found.", 404)
    allowed = {"pm", "pm.max_children", "pm.start_servers", "pm.min_spare_servers",
               "pm.max_spare_servers", "pm.max_requests"}
    lines = p.read_text(encoding="utf-8").splitlines()
    backup = p.with_suffix(".conf.pp-bak")
    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    out: list[str] = []
    for line in lines:
        replaced = False
        stripped = line.strip()
        for key, value in settings.items():
            if key not in allowed:
                raise PanelError(f"Unknown pool directive: {key}", 400)
            if stripped.startswith(key) and "=" in stripped:
                out.append(f"{key} = {value}")
                replaced = True
                break
        if not replaced:
            out.append(line)
    # append directives that were missing entirely
    existing_keys = {
        line.split("=")[0].strip()
        for line in lines
        if "=" in line and not line.strip().startswith(";")
    }
    for key, value in settings.items():
        if key not in existing_keys:
            out.append(f"{key} = {value}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    restart(version)
    return {"pool": str(p), "backup": str(backup)}
