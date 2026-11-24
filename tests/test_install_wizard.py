"""Exercise the installer questions without running system commands."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

if os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "bash.exe"
    BASH = str(candidate) if candidate.is_file() else None
else:
    BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(not BASH, reason="requires Bash")


def prompt(answers: str, domain: str = "", stack: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, "-c", '''
set -euo pipefail
source scripts/install.sh
PANEL_HOST=127.0.0.1
PANEL_DOMAIN="$1"
PANEL_EMAIL=""
STACK="$2"
prompt_install_options true
printf '%s|%s|%s\n' "$PANEL_DOMAIN" "$PANEL_EMAIL" "$STACK"
''', "panelpro-wizard", domain, stack],
        cwd=Path(__file__).resolve().parents[1], input=answers,
        capture_output=True, text=True, timeout=15,
    )


def test_https_inputs_retry_before_installing():
    result = prompt("https://panel.example.com\n panel.example.com. \nwrong\nowner@example.com\n9\n2\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "panel.example.com|owner@example.com|php"
    assert "without https://" in result.stderr
    assert "valid email" in result.stderr
    assert "web stacks listed above" in result.stderr


def test_local_access_defaults_to_nginx_without_asking_for_email():
    result = prompt("\n\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "||nginx"
    assert "Email for Let's Encrypt" not in result.stderr


def test_preset_domain_and_stack_require_only_email():
    result = prompt("owner@example.com\n", domain="panel.example.com", stack="none")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "panel.example.com|owner@example.com|none"


def test_closed_input_cancels_setup():
    result = prompt("panel.example.com\n")
    assert result.returncode != 0
    assert "Installation cancelled" in result.stderr
