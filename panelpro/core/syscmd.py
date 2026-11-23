"""Safe subprocess wrappers used by every OS-facing module.

All callers go through :func:`run` (argument-list form, no shell) or
:func:`run_shell` (explicit bash script).  Both capture output, enforce a
timeout, and raise :class:`PanelError` with a readable message on failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from panelpro.core.errors import PanelError


@dataclass
class CmdResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def which(tool: str) -> str | None:
    return shutil.which(tool)


def require(tool: str, hint: str = "") -> str:
    """Return the binary path or raise a user-facing error."""
    path = shutil.which(tool)
    if not path:
        message = f"'{tool}' is not installed on this system."
        if hint:
            message += f" {hint}"
        raise PanelError(message, 400)
    return path


def run(
    args: list[str],
    timeout: int = 60,
    cwd: str | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> CmdResult:
    """Run an argument-list command without involving a shell."""
    merged_env = {**os.environ, **env} if env else None
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=merged_env,
        )
    except FileNotFoundError as exc:
        raise PanelError(f"Command not found: {args[0]}", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise PanelError(f"Command timed out after {timeout}s: {args[0]}", 504) from exc

    result = CmdResult(proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and not result.ok:
        tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise PanelError(
            f"Command failed ({args[0]}): {' | '.join(tail) or 'no output'}", 500
        )
    return result


def run_shell(script: str, timeout: int = 300, cwd: str | None = None) -> CmdResult:
    """Run a bash script (used for user-defined tasks and app installers)."""
    return run(["bash", "-lc", script], timeout=timeout, cwd=cwd)
