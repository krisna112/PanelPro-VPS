"""Cron engine tests (pure parts; no crontab writes)."""

import pytest

from panelpro.core.errors import PanelError
from panelpro.services import cronsvc


def test_valid_schedules():
    for expr in ("* * * * *", "*/10 * * * *", "0 2 * * 1-5", "30 3 1,15 * *"):
        assert cronsvc.validate_schedule(expr) == expr


def test_invalid_schedule():
    with pytest.raises(PanelError):
        cronsvc.validate_schedule("not a cron")
    with pytest.raises(PanelError):
        cronsvc.validate_schedule("61 * * * *")


def test_build_command_shell():
    assert cronsvc.build_command("shell", "echo hi") == "echo hi"


def test_build_command_url():
    cmd = cronsvc.build_command("url", "https://x.test/cron")
    assert cmd.startswith("curl")
    assert "https://x.test/cron" in cmd


def test_build_command_script_quotes_path():
    import shlex

    cmd = cronsvc.build_command("script", "/opt/run.sh")
    # the script path must remain a single argv token after shlex quoting
    assert shlex.split(cmd)[0] == "bash"
    assert "/opt/run.sh" in shlex.split(cmd)


def test_build_command_url_injection_is_inert():
    import shlex

    payload = "http://x.test/cron'; rm -rf / #"
    cmd = cronsvc.build_command("url", payload)
    tokens = shlex.split(cmd)
    # payload must be one inert curl argument, not shell syntax
    assert tokens[0] == "curl"
    assert payload in tokens


def test_build_command_rejects_unknown():
    with pytest.raises(PanelError):
        cronsvc.build_command("carrier-pigeon", "x")


def test_entry_block_disabled_comments_out():
    block = cronsvc._entry_block(7, "0 2 * * *", "echo hi", enabled=False)
    assert block[0] == "# pp:7"
    assert block[1].startswith("0 2 * * * # echo hi")


def test_entry_block_enabled():
    block = cronsvc._entry_block(7, "0 2 * * *", "echo hi", enabled=True)
    assert block[1] == "0 2 * * * echo hi"


def test_next_run_returns_datetime():
    from datetime import datetime

    assert isinstance(cronsvc.next_run("*/5 * * * *"), datetime)
