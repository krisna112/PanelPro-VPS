"""PanelPro application factory: FastAPI app, lifespan, routing, entry gate.

Run with the ``panelpro`` CLI (panelpro.cli) or directly:

    uvicorn panelpro.main:app --host 0.0.0.0 --port 21000
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from panelpro.config import CFG
from panelpro.constants import APP_NAME, VERSION
from panelpro.core import settings_store
from panelpro.core.database import SessionLocal, init_db
from panelpro.core.errors import PanelError
from panelpro.core.middleware import (
    AuditMiddleware,
    EntryGateMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from panelpro.core.monitor import MONITOR
from panelpro.core.scheduler import SCHEDULER
from panelpro.models.tables import User

log = logging.getLogger("panelpro")


def _seed_admin(db) -> None:
    """Create the first admin account on a fresh install."""
    if db.query(User).count() > 0:
        return
    from panelpro.core.keyvault import random_password
    from panelpro.core.security import hash_password

    username = os.environ.get("PANELPRO_ADMIN_USER", "admin")
    password = random_password(14)
    db.add(User(username=username, password_hash=hash_password(password), role="admin"))
    db.commit()
    try:
        CFG.credentials_path.write_text(
            f"PanelPro admin credentials\n"
            f"URL:      http://<server>:{settings_store.get_setting('panel_port')}/"
            f"{settings_store.get_setting('entry_path')}\n"
            f"Username: {username}\n"
            f"Password: {password}\n"
            f"Created:  {__import__('datetime').datetime.utcnow().isoformat()}Z\n"
            f"(Delete this file after saving the password.)\n",
            encoding="utf-8",
        )
        CFG.credentials_path.chmod(0o600)
    except OSError:
        pass
    print(f"[PanelPro] Admin account created -> {username} / {password}")
    print(f"[PanelPro] Credentials file: {CFG.credentials_path}")


def _register_background_jobs() -> None:
    from panelpro.constants import (
        MONITOR_FLUSH_INTERVAL,
    )
    from panelpro.core import monitor as monitor_mod
    from panelpro.core import notify as notify_mod
    from panelpro.core import security
    from panelpro.services import backupsvc, sslmgr

    SCHEDULER.register("monitor-flush", monitor_mod.MONITOR.flush, MONITOR_FLUSH_INTERVAL)
    SCHEDULER.register("notify-thresholds", notify_mod.check_thresholds, 300)
    SCHEDULER.register("ssl-expiry-check", sslmgr.check_ssl_expiry_job, 6 * 3600)
    SCHEDULER.register("backup-due-check", backupsvc.backup_due_check_job, 60)

    def purge_sessions() -> None:
        db = SessionLocal()
        try:
            security.purge_expired_sessions(db)
        finally:
            db.close()

    SCHEDULER.register("session-purge", purge_sessions, 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    CFG.ensure_dirs()
    init_db()
    settings_store.init_defaults()
    if not settings_store.get_setting("entry_path"):
        settings_store.set_setting("entry_path", secrets.token_hex(4))
    db = SessionLocal()
    try:
        _seed_admin(db)
    finally:
        db.close()
    if not MONITOR.is_alive:
        MONITOR.start()
    _register_background_jobs()
    SCHEDULER.start()
    log.info("PanelPro %s started (home=%s)", VERSION, CFG.home)
    yield
    SCHEDULER.stop()
    MONITOR.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_NAME,
        version=VERSION,
        description="Open-source Linux server control panel.",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # Middlewares (outermost first: headers -> entry gate -> rate -> audit)
    # ------------------------------------------------------------------ #
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(EntryGateMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # ------------------------------------------------------------------ #
    # Error handling
    # ------------------------------------------------------------------ #

    @app.exception_handler(PanelError)
    async def panel_error_handler(request, exc: PanelError):
        return JSONResponse(
            {"ok": False, "message": exc.message}, status_code=exc.status
        )

    # ------------------------------------------------------------------ #
    # Public endpoints
    # ------------------------------------------------------------------ #

    @app.get("/api/health")
    def health():
        return {"ok": True, "app": APP_NAME, "version": VERSION}

    # ------------------------------------------------------------------ #
    # API routers
    # ------------------------------------------------------------------ #
    from panelpro.api import (
        apps as api_apps,
    )
    from panelpro.api import (
        auth as api_auth,
    )
    from panelpro.api import (
        backup as api_backup,
    )
    from panelpro.api import (
        cron as api_cron,
    )
    from panelpro.api import (
        dashboard as api_dashboard,
    )
    from panelpro.api import (
        databases as api_databases,
    )
    from panelpro.api import (
        docker as api_docker,
    )
    from panelpro.api import (
        files as api_files,
    )
    from panelpro.api import (
        ftp as api_ftp,
    )
    from panelpro.api import (
        logs as api_logs,
    )
    from panelpro.api import (
        monitor_api,
    )
    from panelpro.api import (
        notifications as api_notifications,
    )
    from panelpro.api import (
        php as api_php,
    )
    from panelpro.api import (
        plugins as api_plugins,
    )
    from panelpro.api import (
        security as api_security,
    )
    from panelpro.api import (
        settings as api_settings,
    )
    from panelpro.api import (
        sites as api_sites,
    )
    from panelpro.api import (
        ssl as api_ssl,
    )
    from panelpro.api import (
        system as api_system,
    )
    from panelpro.api import (
        terminal as api_terminal,
    )
    from panelpro.api import (
        users as api_users,
    )

    app.include_router(api_auth.router)
    app.include_router(api_dashboard.router)
    app.include_router(api_system.router)
    app.include_router(api_files.router)
    app.include_router(api_sites.router)
    app.include_router(api_databases.router)
    app.include_router(api_php.router)
    app.include_router(api_ftp.router)
    app.include_router(api_ssl.router)
    app.include_router(api_security.router)
    app.include_router(api_cron.router)
    app.include_router(monitor_api.router)
    app.include_router(api_logs.router)
    app.include_router(api_apps.router)
    app.include_router(api_docker.router)
    app.include_router(api_backup.router)
    app.include_router(api_terminal.router)
    app.include_router(api_settings.router)
    app.include_router(api_users.router)
    app.include_router(api_notifications.router)
    app.include_router(api_plugins.router)

    # ------------------------------------------------------------------ #
    # Dynamic plugins (panelpro/plugins/*/main.py exposing `router`)
    # ------------------------------------------------------------------ #
    for manifest_path in sorted(CFG.plugins_dir.glob("*/manifest.json")):
        try:
            manifest = __import__("json").loads(
                manifest_path.read_text(encoding="utf-8")
            )
            plugin_pkg = f"panelpro.plugins.{manifest_path.parent.name}.main"
            module = __import__(plugin_pkg, fromlist=["router"])
            prefix = manifest.get("prefix") or f"/api/plugins/{manifest.get('id', manifest_path.parent.name)}"
            app.include_router(module.router, prefix=prefix)
            log.info("Loaded plugin: %s (%s)", manifest.get("name"), prefix)
        except Exception as exc:  # plugin bugs must not break the panel
            log.warning("Plugin %s failed to load: %s", manifest_path.parent.name, exc)

    # ------------------------------------------------------------------ #
    # Frontend static assets + SPA fallback
    # ------------------------------------------------------------------ #
    assets_dir = CFG.web_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    index_file = CFG.web_dir / "index.html"
    favicon = CFG.web_dir / "favicon.svg"

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon_route():
        if favicon.exists():
            return FileResponse(favicon, media_type="image/svg+xml")
        raise PanelError("Not found", 404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # The EntryGate middleware already verified the visitor knows the
        # secret entry path; serve the SPA shell for any UI route.
        if full_path.startswith(("api/", "assets/", "docs", "openapi.json")):
            raise PanelError("Not found", 404)
        if index_file.exists():
            return FileResponse(index_file, media_type="text/html")
        raise PanelError("Frontend files are missing (web/index.html).", 404)

    return app


app = create_app()
