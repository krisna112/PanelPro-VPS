"""Installer login and terminal menu regressions."""

import sys
from argparse import Namespace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from panelpro import cli, console
from panelpro.core.database import SessionLocal
from panelpro.core.security import hash_password, verify_password
from panelpro.models.tables import Base, User


def test_setup_admin_uses_the_entered_credentials_and_preserves_the_account(monkeypatch, capsys):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(cli, "_open_db", session_factory)
    answers = iter(["wrong username", "vps-owner"])
    passwords = iter(["short", "example-setup-password", "different", "example-setup-password", "example-setup-password"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "getpass", lambda _: next(passwords))

    assert cli.cmd_setup_admin(Namespace()) == 0
    assert cli.cmd_setup_admin(Namespace()) == 0
    with session_factory() as db:
        admin = db.query(User).one()
        assert admin.username == "vps-owner"
        assert admin.role == "admin"
        assert verify_password("example-setup-password", admin.password_hash)
    captured = capsys.readouterr()
    assert "example-setup-password" not in captured.out
    assert "example-setup-password" not in captured.err


def test_menu_dispatches_actions_and_exits(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "panel.db"
    db_path.touch()
    monkeypatch.setattr(console, "CFG", SimpleNamespace(db_path=db_path))
    monkeypatch.setattr(console, "os", SimpleNamespace(geteuid=lambda: 0))
    monkeypatch.setattr(console, "sys", SimpleNamespace(platform="linux", stderr=sys.stderr))
    answers = iter(["unknown", "1", "3", "10", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    actions = []
    monkeypatch.setattr(console, "_show_access", lambda: actions.append("access"))
    monkeypatch.setattr(console, "_service_action", actions.append)
    monkeypatch.setattr(cli, "cmd_change_credentials", lambda args: actions.append("credentials"))

    assert console.menu() == 0
    assert actions == ["access", "restart", "credentials"]
    assert "Choose one of the listed options" in capsys.readouterr().out


def test_bad_listener_port_leaves_the_menu_available(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "70000")
    with pytest.raises(console.PanelError, match="between 1024 and 65535"):
        console._change_port()
    assert capsys.readouterr().out == ""


def test_cli_rejects_a_reserved_login_path():
    assert cli.cmd_set_entry(Namespace(path="assets")) == 1


def test_updated_terminal_credentials_can_sign_in_without_restarting(client, entry_path, monkeypatch):
    old_username = "terminal-admin-before"
    new_username = "terminal-admin-after"
    old_password = "initial-example-password"
    new_password = "updated-example-password"
    with SessionLocal() as db:
        user = User(username=old_username, password_hash=hash_password(old_password), role="admin")
        db.add(user)
        db.commit()
        user_id = user.id

    assert client.get(f"/{entry_path}").status_code == 200

    def login(username, password):
        return client.post("/api/auth/login", headers={"X-PP-Request": "1"},
                           json={"username": username, "password": password})

    assert login(old_username, old_password).status_code == 200
    monkeypatch.setattr("builtins.input", lambda _: new_username)
    monkeypatch.setattr(cli, "getpass", lambda _: new_password)

    assert cli.main(["change-credentials", "--username", old_username]) == 0

    assert client.get("/api/auth/me").status_code == 401
    assert login(old_username, old_password).status_code == 401
    assert login(new_username, old_password).status_code == 401
    assert login(new_username, new_password).status_code == 200
    account = client.get("/api/auth/me").json()["data"]
    assert account["username"] == new_username
    assert account["role"] == "admin"
    with SessionLocal() as db:
        assert db.get(User, user_id).username == new_username


def test_duplicate_username_leaves_original_credentials_valid(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(cli, "_open_db", session_factory)
    with session_factory() as db:
        password_hash = hash_password("original-example-password")
        db.add_all([
            User(username="owner", password_hash=password_hash, role="admin"),
            User(username="operator", password_hash=password_hash, role="operator"),
        ])
        db.commit()

    answers = iter(["", "operator"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "getpass", lambda _: "replacement-example-password")

    assert cli.main(["change-credentials"]) == 1
    with session_factory() as db:
        owner = db.query(User).filter_by(username="owner").one()
        assert owner.password_hash == password_hash
