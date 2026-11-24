"""Installer login and terminal menu regressions."""

import sys
from argparse import Namespace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from panelpro import cli, console
from panelpro.core.security import verify_password
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
    answers = iter(["unknown", "1", "3", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    actions = []
    monkeypatch.setattr(console, "_show_access", lambda: actions.append("access"))
    monkeypatch.setattr(console, "_service_action", actions.append)

    assert console.menu() == 0
    assert actions == ["access", "restart"]
    assert "Choose one of the listed options" in capsys.readouterr().out


def test_bad_listener_port_leaves_the_menu_available(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "70000")
    with pytest.raises(console.PanelError, match="between 1024 and 65535"):
        console._change_port()
    assert capsys.readouterr().out == ""


def test_cli_rejects_a_reserved_login_path():
    assert cli.cmd_set_entry(Namespace(path="assets")) == 1
