"""Runtime configuration and filesystem layout for PanelPro.

The panel root is resolved once at import time:

1. ``PANELPRO_HOME`` environment variable, if set (used by tests and CI).
2. ``/usr/local/panelpro`` — the production install root (Linux).
3. ``<project>/runtime`` — a development fallback next to the source tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from panelpro.constants import DEFAULT_WWW_ROOT


def _resolve_home() -> Path:
    env = os.environ.get("PANELPRO_HOME")
    if env:
        return Path(env).expanduser().resolve()

    candidate = Path("/usr/local/panelpro")
    if candidate.is_dir() and os.access(candidate, os.W_OK):
        return candidate

    # Development fallback: keep runtime data next to the source tree.
    return Path(__file__).resolve().parent.parent / "runtime"


class PanelConfig:
    """Aggregated paths and environment flags used across the panel."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.package_dir = Path(__file__).resolve().parent
        self.templates_dir = self.package_dir / "templates"
        self.plugins_dir = self.package_dir / "plugins"
        self.web_dir = self.package_dir.parent / "web"

        self.data_dir = home / "data"
        self.logs_dir = home / "logs"
        self.backup_dir = home / "backup"
        self.trash_dir = home / "trash"
        self.apps_dir = home / "apps"
        self.ssl_dir = home / "data" / "ssl"
        self.cron_log_dir = home / "logs" / "cron"

        self.db_path = self.data_dir / "panel.db"
        self.secret_path = self.data_dir / "secret.key"
        self.credentials_path = self.data_dir / "admin_credentials.txt"

        self.is_windows = sys.platform.startswith("win")
        # Web roots only make sense on a Linux server; dev runs still need a
        # writable default so the sites/files modules can be exercised.
        www_root = os.environ.get("PANELPRO_WWW_ROOT")
        self.www_root = (Path(www_root).expanduser().resolve() if www_root else
                         home / "www" if self.is_windows else Path(DEFAULT_WWW_ROOT))
        self.tmp_dir = home / "tmp"

    def ensure_dirs(self) -> None:
        for d in (
            self.home, self.data_dir, self.logs_dir, self.backup_dir,
            self.trash_dir, self.apps_dir, self.ssl_dir, self.cron_log_dir,
            self.www_root, self.tmp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


CFG = PanelConfig(_resolve_home())
