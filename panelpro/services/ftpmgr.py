"""FTP account management: pure-ftpd virtual users or proftpd system users.

The panel database (``ftp_users`` table) is the source of truth; this
module performs the matching OS-level operations.  A dedicated unprivileged
system account (``panelpro_ftp``) owns pure-ftpd virtual users.
"""

from __future__ import annotations

from panelpro.core.errors import PanelError
from panelpro.core.syscmd import require, run, run_shell, which


def detect_backend() -> str | None:
    if which("pure-pw"):
        return "pureftpd"
    if which("proftpd"):
        return "proftpd"
    return None


FTP_SYS_USER = "panelpro_ftp"


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _ensure_pureftpd_sys_user() -> None:
    res = run(["id", FTP_SYS_USER], check=False)
    if res.code != 0:
        shell = which("nologin") or "/bin/false"
        run(
            ["useradd", "-r", "-M", "-s", shell, FTP_SYS_USER],
            check=True,
        )


class FtpManager:
    def __init__(self) -> None:
        self.backend = detect_backend()
        if not self.backend:
            raise PanelError(
                "No FTP server found (install pure-ftpd or proftpd).", 400
            )

    def add_user(self, name: str, password: str, directory: str) -> None:
        require("mkdir")
        run(["mkdir", "-p", directory], check=True)
        if self.backend == "pureftpd":
            _ensure_pureftpd_sys_user()
            script = (
                f"printf '%s\\n%s\\n' {_shell_quote(password)} {_shell_quote(password)} "
                f"| pure-pw useradd {_shell_quote(name)} "
                f"-u {FTP_SYS_USER} -d {_shell_quote(directory)} -m"
            )
            res = run_shell(script, timeout=30)
            if res.code != 0:
                raise PanelError(f"pure-pw failed: {res.stderr[-300:]}", 500)
        else:
            shell = which("nologin") or "/bin/false"
            res = run(
                ["useradd", "-M", "-d", directory, "-s", shell, name], check=False
            )
            if res.code != 0 and "already exists" not in res.stderr:
                raise PanelError(f"useradd failed: {res.stderr[-300:]}", 500)
            script = f"printf '%s' {_shell_quote(name + ':' + password)} | chpasswd"
            res = run_shell(script, timeout=15)
            if res.code != 0:
                raise PanelError(f"chpasswd failed: {res.stderr[-300:]}", 500)

    def set_password(self, name: str, password: str) -> None:
        if self.backend == "pureftpd":
            script = (
                f"printf '%s\\n%s\\n' {_shell_quote(password)} {_shell_quote(password)} "
                f"| pure-pw passwd {_shell_quote(name)} -m"
            )
            res = run_shell(script, timeout=30)
            if res.code != 0:
                raise PanelError(f"pure-pw failed: {res.stderr[-300:]}", 500)
        else:
            script = f"printf '%s' {_shell_quote(name + ':' + password)} | chpasswd"
            res = run_shell(script, timeout=15, check=True)

    def delete_user(self, name: str) -> None:
        if self.backend == "pureftpd":
            run(["pure-pw", "userdel", name, "-m"], check=False)
        else:
            run(["userdel", "-r", name], check=False)

    def list_backends_users(self) -> list[str]:
        if self.backend == "pureftpd":
            res = run(["pure-pw", "list"], timeout=15)
            return [line.split()[0] for line in res.stdout.splitlines() if line.strip()]
        return []

    def reload(self) -> None:
        if self.backend == "pureftpd":
            run(["pure-pw", "mkdb"], check=False)
        run(
            ["systemctl", "restart",
             "pure-ftpd" if self.backend == "pureftpd" else "proftpd"],
            check=False,
        )
