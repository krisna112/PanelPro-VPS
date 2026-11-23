"""Log viewer endpoints: panel audit, system logs, webserver site logs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth
from panelpro.config import CFG
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import Site
from panelpro.services import webservers

router = APIRouter(prefix="/api/logs", tags=["logs"])

MAX_TAIL_BYTES = 2_000_000


def _tail_file(path: str, lines: int) -> str:
    p = Path(path)
    if not p.exists():
        raise PanelError(f"Log file not found: {path}", 404)
    with open(p, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - MAX_TAIL_BYTES))
        content = fh.read().decode("utf-8", errors="replace")
    selected = content.splitlines()[-lines:]
    return "\n".join(selected)


def _resolve_source(source: str, db: Session) -> dict:
    """Map a source id onto {kind: file|journal|db, target}."""
    if source == "panel-audit":
        return {"kind": "db"}
    if source == "panel-log":
        return {"kind": "file", "target": str(CFG.logs_dir / "panel.log")}
    if source == "auth":
        return {"kind": "file", "target": "/var/log/auth.log"}
    if source == "syslog":
        return {"kind": "file", "target": "/var/log/syslog"}
    if source == "secure":
        return {"kind": "file", "target": "/var/log/secure"}
    if source == "messages":
        return {"kind": "file", "target": "/var/log/messages"}
    if source.startswith("site-access:"):
        domain = source.split(":", 1)[1]
        return {"kind": "file", "target": webservers.detect_webserver().log_paths(domain)[0]}
    if source.startswith("site-error:"):
        domain = source.split(":", 1)[1]
        return {"kind": "file", "target": webservers.detect_webserver().log_paths(domain)[1]}
    if source.startswith("journal:"):
        return {"kind": "journal", "target": source.split(":", 1)[1]}
    raise PanelError(f"Unknown log source: {source}", 400)


@router.get("/sources")
def sources(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    items = [
        {"id": "panel-audit", "name": "Panel audit log"},
        {"id": "panel-log", "name": "Panel application log"},
        {"id": "auth", "name": "SSH / auth log"},
        {"id": "syslog", "name": "System log (syslog)"},
        {"id": "secure", "name": "Security log (/var/log/secure)"},
        {"id": "messages", "name": "Kernel messages"},
        {"id": "journal:sshd", "name": "journal: sshd"},
        {"id": "journal:nginx", "name": "journal: nginx"},
        {"id": "journal:mysql", "name": "journal: mysql"},
    ]
    for site in db.query(Site).all():
        items.append({"id": f"site-access:{site.name}", "name": f"Site access: {site.name}"})
        items.append({"id": f"site-error:{site.name}", "name": f"Site error: {site.name}"})
    return api_ok(items)


@router.get("/tail")
def tail(source: str, lines: int = 200, query: str = "", db: Session = Depends(get_db), ctx=Depends(require_auth)):
    lines = max(1, min(lines, 2000))
    spec = _resolve_source(source, db)
    if spec["kind"] == "db":
        from panelpro.models.tables import AuditLog

        rows = (
            db.query(AuditLog)
            .order_by(AuditLog.ts.desc())
            .limit(lines)
            .all()
        )
        lines_out = [
            f"{r.ts.isoformat()} {r.username or '-'}@{r.ip} {r.method} {r.path} -> {r.status}"
            for r in reversed(rows)
        ]
        text = "\n".join(lines_out)
    elif spec["kind"] == "journal":
        res = subprocess.run(
            ["journalctl", "-u", spec["target"], "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = res.stdout or res.stderr
    else:
        text = _tail_file(spec["target"], lines)

    if query:
        text = "\n".join(line for line in text.splitlines() if query.lower() in line.lower())
    return api_ok({"source": source, "log": text[-512_000:]})


@router.get("/download")
def download(source: str, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    spec = _resolve_source(source, db)
    if spec["kind"] != "file":
        raise PanelError("Only file-based logs can be downloaded.", 400)
    p = Path(spec["target"])
    if not p.exists():
        raise PanelError(f"Log file not found: {spec['target']}", 404)
    return Response(
        content=p.read_bytes()[:20_000_000],
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{p.name}"'},
    )
