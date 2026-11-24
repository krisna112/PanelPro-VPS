"""PHP multi-version management: detection, extensions, ini editing, FPM."""

from __future__ import annotations

import re
from pathlib import Path

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which
from panelpro.services import packages

FPM_UNIT_CANDIDATES = "php{v}-fpm", "php{v}-phpfpm", "php-fpm"
VERSION_RE = re.compile(r"[0-9]{1,2}\.[0-9]{1,2}")
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
    if version := _cli_version():
        versions.add(version)
    return sorted(versions, key=lambda version: tuple(map(int, version.split("."))), reverse=True)


def fpm_unit(version: str) -> str | None:
    if CFG.is_windows or not which("systemctl"):
        return None
    for pattern in FPM_UNIT_CANDIDATES:
        unit = pattern.format(v=version)
        if unit == "php-fpm" and version != _cli_version():
            continue
        res = run(["systemctl", "show", "--property=LoadState", "--value", unit + ".service"], timeout=15)
        if res.ok and res.stdout.strip() == "loaded":
            return unit + ".service"
    return None


def _cli_version(binary: str = "php") -> str | None:
    if not which(binary):
        return None
    res = run([binary, "-r", "echo PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION;"], timeout=10)
    version = res.stdout.strip()
    return version if res.ok and VERSION_RE.fullmatch(version) else None


def socket_path(version: str) -> Path:
    if not VERSION_RE.fullmatch(version):
        raise PanelError("Invalid PHP version.", 400)
    default = Path(f"/run/php/php{version}-fpm.sock")
    if default.is_socket():
        return default
    pool = pool_file(version)
    if pool and (pool.parent.parent.name == "fpm" or version == _cli_version()):
        match = re.search(r"^\s*listen\s*=\s*(/[^\s;]+)", pool.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return Path(match[1])
    return default


def install_options() -> list[str]:
    manager = packages.manager()
    if not manager:
        return []
    if manager != "apt-get" or not which("apt-cache"):
        return ["default"]
    result = run(["apt-cache", "pkgnames", "php"], timeout=10)
    names = re.findall(r"^php([0-9]{1,2}\.[0-9]{1,2})-fpm$", result.stdout, re.MULTILINE)
    return ["default", *sorted(set(names), key=lambda v: tuple(map(int, v.split("."))), reverse=True)]


def install_runtime(version: str = "default", *, refresh: bool = True) -> dict:
    version = version.strip()
    if version != "default" and not VERSION_RE.fullmatch(version):
        raise PanelError("Choose the distro default or a PHP version such as 8.3.", 400)
    manager = packages.manager()
    if not manager:
        raise PanelError("PHP installation requires a Linux package manager.", 400)
    with packages.INSTALL_LOCK:
        if refresh:
            packages.refresh()
        if manager == "apt-get":
            if version == "default":
                result = run(["apt-cache", "depends", "php-fpm"], timeout=15, check=True, env={"LC_ALL": "C"})
                match = re.search(r"Depends:\s*php([0-9]{1,2}\.[0-9]{1,2})-fpm\b", result.stdout)
                if not match:
                    raise PanelError("The enabled APT repositories do not offer the default PHP-FPM package.", 400)
                version = match[1]
            if version not in install_options():
                raise PanelError(f"PHP {version} is unavailable in the enabled APT repositories. Choose the distro default.", 400)
            names = [f"php{version}-{ext}" for ext in ("cli", "fpm", "mysql", "curl", "gd", "xml", "mbstring", "zip")]
            packages.install(names)
        else:
            if version != "default":
                raise PanelError("Choose the default version provided by the active PHP package stream.", 400)
            packages.install(["php-cli", "php-fpm", "php-mysqlnd", "php-gd", "php-xml", "php-mbstring"])
            version = _cli_version()
        unit = fpm_unit(version) if version else None
        if not unit:
            raise PanelError("PHP-FPM was installed but its systemd service could not be found.", 500)
        run(["systemctl", "enable", "--now", unit], timeout=90, check=True)
        socket = socket_path(version)
        if not socket.is_socket():
            raise PanelError(f"PHP-FPM started without the Unix socket at {socket}. Check {unit}.", 500)
    return {"installed": version, "unit": unit, "socket": str(socket)}


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
    package = f"php{version}-{extension}" if packages.manager() == "apt-get" else f"php-{extension}"
    with packages.INSTALL_LOCK:
        packages.refresh()
        packages.install([package])
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
