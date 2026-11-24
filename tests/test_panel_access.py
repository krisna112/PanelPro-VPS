"""Regression tests for publishing a panel hostname and recovering on failure."""

import pytest

from panelpro.core.errors import PanelError
from panelpro.services import panel_access, webservers


@pytest.fixture
def panel_domain(monkeypatch, tmp_path):
    adapter = webservers.NginxAdapter()
    adapter.conf_dir = tmp_path
    path = tmp_path / "panelpro-panel.conf"
    settings = {"panel_port": 24500, "entry_path": "demo-entry", "panel_ssl": False,
                "panel_domain": "", "trust_proxy": False}
    monkeypatch.setattr(panel_access, "ACME_ROOT", tmp_path / "acme")
    monkeypatch.setattr(panel_access, "_check_domain_available", lambda domain: None)
    monkeypatch.setattr(panel_access, "require", lambda *args: None)
    monkeypatch.setattr(panel_access, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(webservers, "detect_webserver", lambda name: adapter)
    monkeypatch.setattr(adapter, "test_config", lambda: None)
    monkeypatch.setattr(adapter, "reload", lambda: None)
    monkeypatch.setattr(panel_access.settings_store, "get_setting", settings.get)
    monkeypatch.setattr(panel_access.settings_store, "set_setting", settings.__setitem__)
    return path, settings


def test_publish_waits_for_tls_and_reuses_existing_challenge_route(monkeypatch, panel_domain):
    path, settings = panel_domain
    probes = []

    def probe(args, expected, error):
        probes.append(args[-1])

    def issue(*args, **kwargs):
        config = path.read_text()
        assert "location ^~ /.well-known/acme-challenge/" in config
        assert kwargs["deploy_hook"] == "systemctl reload nginx"
        return {"cert_path": "/test/fullchain.pem", "key_path": "/test/privkey.pem"}

    monkeypatch.setattr(panel_access, "_probe", probe)
    monkeypatch.setattr(panel_access.sslmgr, "issue_letsencrypt", issue)

    for _ in range(2):
        assert panel_access.setup_domain("Panel.Example", "owner@example.com") == "https://panel.example/demo-entry"
        config = path.read_text()
        assert "return 301 https://panel.example$request_uri;" in config
        assert "proxy_pass http://127.0.0.1:24500;" in config
        assert probes[-1] == "https://panel.example/api/health"
    assert settings["trust_proxy"] is True
    assert settings["panel_domain"] == "panel.example"


@pytest.mark.parametrize("failure", ["certbot", "https"])
def test_failed_setup_restores_nginx_config_and_settings(monkeypatch, panel_domain, failure):
    path, settings = panel_domain
    previous = panel_access.MANAGED_HEADER + "    server_name old.example;\n"
    path.write_text(previous, encoding="utf-8")
    settings["panel_domain"] = "old.example"

    def probe(args, expected, error):
        if failure == "https" and args[-1].startswith("https://"):
            raise PanelError("TLS health check failed", 502)

    def issue(*args, **kwargs):
        if failure == "certbot":
            assert "proxy_pass" not in path.read_text()
            raise PanelError("Domain validation failed", 502)
        return {"cert_path": "/test/fullchain.pem", "key_path": "/test/privkey.pem"}

    monkeypatch.setattr(panel_access, "_probe", probe)
    monkeypatch.setattr(panel_access.sslmgr, "issue_letsencrypt", issue)

    with pytest.raises(PanelError, match="failed"):
        panel_access.setup_domain("panel.example", "owner@example.com")
    assert path.read_text(encoding="utf-8") == previous
    assert settings["panel_domain"] == "old.example"
    assert settings["trust_proxy"] is False
