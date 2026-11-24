"""Install trusted distribution packages using the VPS package manager."""

from threading import RLock

from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which

INSTALL_LOCK = RLock()


def manager() -> str | None:
    return next((name for name in ("apt-get", "dnf", "yum") if which(name)), None)


def refresh() -> None:
    if manager() == "apt-get":
        run(["apt-get", "update"], timeout=300, check=True)


def install(names: list[str]) -> None:
    tool = manager()
    if not tool:
        raise PanelError("Install software from a Linux VPS with APT, DNF or YUM.", 400)
    options = ["-o", "DPkg::Lock::Timeout=120", "--no-install-recommends"] if tool == "apt-get" else []
    run([tool, *options, "install", "-y", *names], timeout=900, check=True,
        env={"DEBIAN_FRONTEND": "noninteractive"})
