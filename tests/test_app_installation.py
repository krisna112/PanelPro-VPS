"""Install PHP from the distro and keep phpMyAdmin behind loopback."""

from pathlib import Path

import pytest

from panelpro.core.errors import PanelError
from panelpro.core.syscmd import CmdResult
from panelpro.services import native_apps, phpmgr, webservers


def test_default_php_uses_the_repository_version_and_starts_fpm(monkeypatch):
    calls = []
    monkeypatch.setattr(phpmgr.packages, "manager", lambda: "apt-get")
    monkeypatch.setattr(phpmgr.packages, "refresh", lambda: calls.append("refresh"))
    monkeypatch.setattr(phpmgr.packages, "install", calls.append)
    monkeypatch.setattr(phpmgr, "install_options", lambda: ["default", "8.4"])
    monkeypatch.setattr(phpmgr, "fpm_unit", lambda version: f"php{version}-fpm.service")
    monkeypatch.setattr(Path, "is_socket", lambda self: self.as_posix().endswith("/php8.4-fpm.sock"))

    def run(args, **kwargs):
        calls.append(args)
        return CmdResult(0, "Depends: php8.4-fpm\n", "")

    monkeypatch.setattr(phpmgr, "run", run)
    result = phpmgr.install_runtime()
    assert result["installed"] == "8.4"
    assert calls[0] == "refresh"
    assert "php8.4-fpm" in calls[2]
    assert calls[-1] == ["systemctl", "enable", "--now", "php8.4-fpm.service"]
    with pytest.raises(PanelError, match="unavailable"):
        phpmgr.install_runtime("8.1")


def test_phpmyadmin_reloads_nginx_and_checks_the_local_login_page(monkeypatch, tmp_path):
    adapter = webservers.NginxAdapter()
    adapter.conf_dir = tmp_path
    reloads = []
    monkeypatch.setattr(adapter, "test_config", lambda: None)
    monkeypatch.setattr(adapter, "reload", lambda: reloads.append(True))
    monkeypatch.setattr(webservers, "detect_webserver", lambda name: adapter)
    monkeypatch.setattr(native_apps, "PMA_ROOT", tmp_path)
    (tmp_path / "index.php").touch()
    monkeypatch.setattr(native_apps, "require", lambda *args: None)
    monkeypatch.setattr(native_apps, "which", lambda name: None)
    monkeypatch.setattr(native_apps.packages, "manager", lambda: "apt-get")
    monkeypatch.setattr(native_apps.packages, "refresh", lambda: None)
    monkeypatch.setattr(native_apps.phpmgr, "install_runtime", lambda **kwargs: {"socket": "/run/php/php8.3-fpm.sock"})
    installed = []
    monkeypatch.setattr(native_apps.packages, "install", installed.append)
    monkeypatch.setattr(native_apps, "run", lambda *args, **kwargs: CmdResult(0, '<html><input name="pma_username">', ""))

    result = native_apps.install({"id": "phpmyadmin"}, {})
    assert installed == [["mariadb-server"], ["phpmyadmin"]]
    conf = (tmp_path / "panelpro-phpmyadmin.conf").read_text(encoding="utf-8")
    assert "listen 127.0.0.1:8881;" in conf
    assert "fastcgi_pass unix:/run/php/php8.3-fpm.sock;" in conf
    assert result["port"] == 8881
    assert reloads == [True]


def test_app_store_installs_php_with_the_same_runtime_service(authed_client, monkeypatch):
    versions = []

    def install_runtime(version):
        versions.append(version)
        return {"installed": "8.4", "unit": "php8.4-fpm.service", "socket": "/test/fpm.sock"}

    monkeypatch.setattr(phpmgr.packages, "manager", lambda: "apt-get")
    monkeypatch.setattr(phpmgr, "install_runtime", install_runtime)
    response = authed_client.post("/api/apps/install", headers={"X-PP-Request": "1"},
                                  json={"app_id": "php-fpm", "params": {}})
    assert response.status_code == 200, response.text
    assert versions == ["default"]
    installed = authed_client.get("/api/apps").json()["data"]["installed"]
    assert any(row["app_id"] == "php-fpm" and row["version"] == "8.4" for row in installed)
