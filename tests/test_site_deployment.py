"""Regression coverage for provisioning and applying website changes."""

from pathlib import Path

import pytest

from panelpro.config import CFG
from panelpro.core.database import SessionLocal
from panelpro.core.errors import PanelError
from panelpro.models.tables import DatabaseRow, DbUser
from panelpro.services import webservers

WRITE = {"X-PP-Request": "1"}


@pytest.fixture
def nginx(monkeypatch, tmp_path):
    adapter = webservers.NginxAdapter()
    adapter.conf_dir = tmp_path / "nginx"
    adapter.conf_dir.mkdir()
    adapter.log_dir = tmp_path
    monkeypatch.setattr(CFG, "www_root", tmp_path / "www")
    CFG.www_root.mkdir(exist_ok=True)
    monkeypatch.setattr(webservers, "detect_webserver", lambda server=None: adapter)
    monkeypatch.setattr(adapter, "test_config", lambda: None)
    monkeypatch.setattr(adapter, "reload", lambda: None)
    return adapter


def post(client, path, body=None):
    return client.post(f"/api/{path}", json=body, headers=WRITE)


def listed(client, domain):
    return next((site for site in client.get("/api/sites").json()["data"] if site["name"] == domain), None)


def test_website_create_reserves_aliases_and_preserves_uploads(authed_client, nginx):
    client = authed_client
    root = CFG.www_root / "project.example"
    root.mkdir()
    index = root / "index.html"
    index.write_text("Existing project", encoding="utf-8")

    response = post(client, "sites", {
        "domain": "Project.Example.",
        "aliases": ["www.Project.Example", "www.project.example"],
    })
    assert response.status_code == 200, response.text
    site = listed(client, "project.example")
    assert site["aliases"] == ["www.project.example"]
    assert index.read_text(encoding="utf-8") == "Existing project"
    assert "server_name project.example www.project.example;" in nginx.conf_path(site["name"]).read_text()
    assert post(client, "sites", {"domain": "www.project.example"}).status_code == 409


def test_webserver_rejection_restores_site_and_disk(authed_client, nginx, monkeypatch):
    client = authed_client
    domain = "rollback.example"
    assert post(client, "sites", {"domain": domain}).status_code == 200
    site = listed(client, domain)
    path = nginx.conf_path(domain)
    original = path.read_bytes()
    reloads = []

    def fail_first_reload():
        reloads.append(path.read_bytes())
        if len(reloads) == 1:
            raise PanelError("Fake nginx reload failure", 500)

    monkeypatch.setattr(nginx, "reload", fail_first_reload)
    failed = post(client, f"sites/{site['id']}/proxy", {"target": "http://127.0.0.1:3000"})
    assert failed.status_code == 500
    assert b"proxy_pass" in reloads[0]
    assert reloads[1] == original
    assert listed(client, domain)["proxy_target"] is None
    assert path.read_bytes() == original


def test_rejected_create_can_retry_without_orphaned_files_or_rows(authed_client, nginx, monkeypatch):
    client = authed_client
    domain = "retry.example"
    body = {"domain": domain, "proxy_target": "http://127.0.0.1:8000"}

    def fail_test():
        raise PanelError("Fake nginx configuration failure", 500)

    with monkeypatch.context() as failure:
        failure.setattr(nginx, "test_config", fail_test)
        assert post(client, "sites", body).status_code == 500

    assert listed(client, domain) is None
    assert not nginx.conf_path(domain).exists()
    assert not (CFG.www_root / domain).exists()

    assert post(client, "sites", body).status_code == 200
    assert listed(client, domain)["proxy_target"] == body["proxy_target"]
    assert "proxy_pass" in nginx.conf_path(domain).read_text()


def test_disabled_site_stays_disabled_after_edit(authed_client, nginx):
    client = authed_client
    domain = "parked.example"
    created = post(client, "sites", {"domain": domain})
    site_id = created.json()["data"]["site"]["id"]
    assert post(client, f"sites/{site_id}/toggle").json()["data"]["enabled"] is False
    assert not nginx.conf_path(domain).exists()
    paused = nginx.inactive_path(domain)

    assert post(client, f"sites/{site_id}/domains", {"domain": "www.parked.example"}).status_code == 200
    assert not nginx.conf_path(domain).exists()
    assert "www.parked.example" in paused.read_text()
    assert post(client, f"sites/{site_id}/toggle").json()["data"]["enabled"] is True
    assert not paused.exists()
    assert "www.parked.example" in nginx.conf_path(domain).read_text()


def test_database_compensates_when_provisioning_fails(authed_client, nginx, monkeypatch):
    from panelpro.services import dbmgr

    calls = []

    class Manager:
        def create_database(self, name):
            calls.append(("create_database", name))

        def create_user(self, user, host, password):
            calls.append(("create_user", user))

        def grant(self, user, host, name):
            raise PanelError("Database grant failed", 500)

        def delete_user(self, user, host):
            calls.append(("delete_user", user))

        def delete_database(self, name):
            calls.append(("delete_database", name))

    monkeypatch.setattr(dbmgr, "get_manager", lambda db_type: Manager())
    body = {"domain": "database.example", "create_db": {"name": "exampledb", "user": "exampleuser"}}
    assert post(authed_client, "sites", body).status_code == 500
    assert calls == [
        ("create_database", "exampledb"), ("create_user", "exampleuser"),
        ("delete_user", "exampleuser"), ("delete_database", "exampledb"),
    ]
    assert listed(authed_client, body["domain"]) is None
    assert not Path(CFG.www_root / body["domain"]).exists()
    with SessionLocal() as db:
        assert db.query(DatabaseRow).filter_by(name="exampledb").first() is None
        assert db.query(DbUser).filter_by(name="exampleuser").first() is None


def test_waf_update_and_delete_switch_vhost_include(authed_client, nginx):
    client = authed_client
    domain = "waf.example"
    site_id = post(client, "sites", {"domain": domain}).json()["data"]["site"]["id"]
    path = nginx.conf_path(domain)
    result = post(client, "waf", {"site_id": site_id, "blocked_ips": ["192.0.2.22"]})
    assert result.status_code == 200, result.text
    include = Path(result.json()["data"]["site_conf"])
    assert include.as_posix().endswith("site_waf.example.conf")
    assert "site_waf.example.conf" in path.read_text()
    assert "deny 192.0.2.22;" in include.read_text()
    assert post(client, f"waf/{site_id}/delete").status_code == 200
    assert not include.exists()
    assert "site_waf.example.conf" not in path.read_text()


def test_upstream_in_use_can_neither_be_renamed_nor_deleted(authed_client, nginx):
    client = authed_client
    servers = [{"host": "127.0.0.1", "port": 8000}]
    result = post(client, "lb", {"name": "backend", "servers": servers})
    assert result.status_code == 200, result.text
    pool_id = result.json()["data"]["upstream"]["id"]
    site = post(client, "sites", {"domain": "pool.example", "proxy_target": "upstream:backend"})
    assert site.status_code == 200, site.text
    assert post(client, f"lb/{pool_id}/update", {"name": "renamed", "servers": servers}).status_code == 409
    assert post(client, f"lb/{pool_id}/delete").status_code == 409
    assert (nginx.conf_dir / "upstream_backend.conf").exists()


def test_ssl_serves_https_before_redirect_and_can_be_detached(authed_client, nginx):
    client = authed_client
    domain = "tls.example"
    site_id = post(client, "sites", {"domain": domain}).json()["data"]["site"]["id"]
    conf = nginx.conf_path(domain)
    assert post(client, f"sites/{site_id}/https", {"force": True}).status_code == 400
    cert = post(client, "ssl/selfsigned", {"domain": domain})
    assert cert.status_code == 200, cert.text
    cert_id = cert.json()["data"]["cert"]["id"]

    assert post(client, f"ssl/{cert_id}/deploy", {"site_id": site_id}).status_code == 200
    assert "listen 443 ssl;" in conf.read_text(encoding="utf-8")
    assert "return 301" not in conf.read_text(encoding="utf-8")
    assert post(client, f"sites/{site_id}/https", {"force": True}).status_code == 200
    assert "return 301 https://$host$request_uri;" in conf.read_text(encoding="utf-8")
    assert post(client, f"ssl/{cert_id}/delete").status_code == 409
    assert post(client, f"sites/{site_id}/ssl/remove").status_code == 200
    assert "listen 443 ssl;" not in conf.read_text(encoding="utf-8")
    assert post(client, f"ssl/{cert_id}/delete").status_code == 200
