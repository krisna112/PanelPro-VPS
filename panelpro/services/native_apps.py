"""App Store installers for PHP and packages managed by the host."""

from __future__ import annotations

import time
from pathlib import Path

from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run, which
from panelpro.services import packages, phpmgr, webservers

PMA_ROOT = Path("/usr/share/phpmyadmin")
PMA_PORT = 8881
PMA_HEADER = "# Managed by PanelPro for phpMyAdmin\n"


def unavailable(manifest: dict) -> str | None:
    manager = packages.manager()
    if manifest["id"] == "php-fpm" and manager:
        return None
    if manager != "apt-get":
        return "This package installer requires Debian or Ubuntu with APT."
    return None


def install(manifest: dict, params: dict) -> dict:
    if reason := unavailable(manifest):
        raise PanelError(reason, 400)
    app_id = manifest["id"]
    if app_id == "php-fpm":
        runtime = phpmgr.install_runtime(params.get("version", "default"))
        return {"version": runtime["installed"], "status": "running", **runtime}
    if app_id == "phpmyadmin":
        return _install_phpmyadmin()
    with packages.INSTALL_LOCK:
        packages.refresh()
        packages.install(manifest["packages"])
        if unit := manifest.get("unit"):
            run(["systemctl", "enable", "--now", unit], timeout=90, check=True)
    return {"status": "running" if unit else "installed"}


def _install_phpmyadmin() -> dict:
    adapter = webservers.detect_webserver("nginx")
    config = adapter.conf_dir / "panelpro-phpmyadmin.conf"
    if (config.is_symlink() or config.exists()) and not (
        config.is_file() and config.read_text(encoding="utf-8").startswith(PMA_HEADER)
    ):
        raise PanelError(f"An existing Nginx configuration uses {config}.", 409)
    require("debconf-set-selections")
    require("curl")
    with packages.INSTALL_LOCK:
        packages.refresh()
        runtime = phpmgr.install_runtime(refresh=False)
        if not (which("mysqld") or which("mariadbd")):
            packages.install(["mariadb-server"])
            run(["systemctl", "enable", "--now", "mariadb.service"], timeout=90, check=True)
        run(["debconf-set-selections"], check=True, input_text=(
            "phpmyadmin phpmyadmin/reconfigure-webserver multiselect \n"
            "phpmyadmin phpmyadmin/dbconfig-install boolean false\n"
        ))
        packages.install(["phpmyadmin"])
        if not (PMA_ROOT / "index.php").is_file():
            raise PanelError("The phpMyAdmin package did not provide its web files.", 500)

    content = adapter.render("nginx_phpmyadmin.conf.j2", {
        "port": PMA_PORT, "root": str(PMA_ROOT), "socket": runtime["socket"],
    })
    with webservers.config_transaction(adapter, [config]) as apply:
        webservers.write_config(config, content.encode("utf-8"))
        apply()
        for attempt in range(5):
            response = run(["curl", "--noproxy", "*", "-fsS", "--max-time", "3",
                            f"http://127.0.0.1:{PMA_PORT}/"], timeout=5)
            if response.ok and "<html" in response.stdout.lower() and "pma_username" in response.stdout:
                break
            if attempt < 4:
                time.sleep(0.5)
        else:
            raise PanelError(f"phpMyAdmin did not respond on 127.0.0.1:{PMA_PORT}. Check Nginx and PHP-FPM logs.", 502)
    return {"app_home": str(PMA_ROOT), "port": PMA_PORT, "status": "running"}


def remove_phpmyadmin_access() -> None:
    adapter = webservers.detect_webserver("nginx")
    config = adapter.conf_dir / "panelpro-phpmyadmin.conf"
    if not config.exists():
        return
    if not config.read_text(encoding="utf-8").startswith(PMA_HEADER):
        raise PanelError("phpMyAdmin access is managed outside PanelPro.", 409)
    with webservers.config_transaction(adapter, [config]) as apply:
        config.unlink()
        apply()
