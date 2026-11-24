"""Migration endpoints: export/import a server bundle (async, status polled)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.config import CFG
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.services import migration as migration_svc

router = APIRouter(prefix="/api/migration", tags=["migration"])


class ExportBody(BaseModel):
    include_db: bool = True
    include_ssl: bool = True
    site_ids: list[int] | None = None


@router.post("/export")
def export(body: ExportBody, db=Depends(get_db), ctx=Depends(require_role("operator"))):
    migration_svc.start_export(db, body.include_db, body.include_ssl, body.site_ids)
    return api_ok({"started": True})


@router.get("/status")
def status(ctx=Depends(require_auth)):
    return api_ok(migration_svc.status())


@router.get("/download")
def download(ctx=Depends(require_role("operator"))):
    state = migration_svc.status()
    message = state.get("message", "")
    if state.get("state") != "done" or not message:
        raise PanelError("No finished bundle to download yet.", 404)
    path = Path(message)
    if not path.is_file():
        raise PanelError("Bundle file is gone.", 404)
    return FileResponse(path, filename=path.name, media_type="application/gzip")


@router.post("/import")
def import_bundle(file: UploadFile, db=Depends(get_db), ctx=Depends(require_role("admin"))):
    """Upload a migration bundle and restore it on this server (async)."""
    import threading
    from datetime import datetime

    data = file.file.read()
    if len(data) > 8 * 1024 * 1024 * 1024:
        raise PanelError("Bundle exceeds the 8 GB import limit.", 400)
    inbox = CFG.backup_dir / migration_svc.EXPORT_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "bundle.tar.gz").name
    dest = inbox / f"import-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{safe_name}"
    dest.write_bytes(data)

    if migration_svc.status().get("state") == "running":
        raise PanelError("Another migration operation is already running.", 409)

    def _worker() -> None:
        from panelpro.core.database import SessionLocal
        from panelpro.core.notify import notify_event

        own_db = SessionLocal()
        migration_svc._set_status("running", 10, "importing bundle")
        try:
            result = migration_svc.import_bundle(own_db, str(dest))
            migration_svc._set_status("done", 100, f"imported: {result}")
            notify_event("migration_done", "Migration import",
                         f"sites: {len(result.get('sites', []))}, db: {len(result.get('databases', []))}")
        except Exception as exc:
            migration_svc._set_status("failed", 100, str(exc))
            notify_event("migration_failed", "Migration import failed", str(exc)[:200])
        finally:
            own_db.close()

    threading.Thread(daemon=True, target=_worker).start()
    return api_ok({"started": True, "filename": dest.name})
