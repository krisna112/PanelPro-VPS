"""Website tamper protection: baseline hashes, scheduled scans, restore.

A watch stores a SHA-256 baseline of every file below the site root
(bounded in size/count).  A scan compares the tree against the baseline
and reports added / modified / deleted files; with ``auto_restore`` the
panel restores modified files from its snapshot copy (files added by an
attacker are left in place and only reported).
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.notify import notify_event
from panelpro.models.tables import Site, TamperWatch

MAX_FILES = 20000
MAX_FILE_BYTES = 5 * 1024 * 1024
SKIP_DIRS = {"logs", "cache", "tmp", ".git", "node_modules"}
ALERT_COOLDOWN = 30 * 60
_last_alert: dict[int, float] = {}


def snapshot_dir(site_id: int) -> Path:
    return CFG.data_dir / "tamper" / str(site_id)


def _hash_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 512), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def site_root(site: Site) -> Path:
    return Path(site.root)


def build_baseline(db, watch: TamperWatch) -> dict:
    site = db.query(Site).filter(Site.id == watch.site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    root = site_root(site)
    if not root.is_dir():
        raise PanelError(f"Site root does not exist: {root}", 400)
    baseline: dict[str, str] = {}
    count = 0
    snap_dir = snapshot_dir(site.id)
    if snap_dir.exists():
        shutil.rmtree(snap_dir)
    snap_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(root.rglob("*")):
        if count >= MAX_FILES:
            raise PanelError(
                f"Site has more than {MAX_FILES} files — tamper watch not supported.",
                400,
            )
        rel = path.relative_to(root).as_posix()
        if not path.is_file() or rel.split("/")[0] in SKIP_DIRS:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        digest = _hash_file(path)
        if digest:
            baseline[rel] = digest
            count += 1
            snapshot_copy = snap_dir / rel
            snapshot_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, snapshot_copy)
    watch.baseline = baseline
    watch.baseline_at = datetime.utcnow()
    watch.last_changes = []
    db.commit()
    return {"files": count, "built_at": watch.baseline_at.isoformat()}


def scan(db, watch: TamperWatch) -> dict:
    site = db.query(Site).filter(Site.id == watch.site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    if not watch.baseline:
        raise PanelError("No baseline built yet — build one first.", 400)
    root = site_root(site)
    current: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if not path.is_file() or rel.split("/")[0] in SKIP_DIRS:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        digest = _hash_file(path)
        if digest:
            current[rel] = digest

    modified = sorted(k for k, v in watch.baseline.items() if k in current and current[k] != v)
    added = sorted(k for k in current if k not in watch.baseline)
    deleted = sorted(k for k in watch.baseline if k not in current)

    restored = 0
    if watch.mode == "auto_restore" and modified:
        snap_dir = snapshot_dir(site.id)
        for rel in modified:
            snap_file = snap_dir / rel
            if snap_file.is_file():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snap_file, target)
                restored += 1

    watch.last_scan_at = datetime.utcnow()
    watch.last_changes = {"modified": modified, "added": added, "deleted": deleted}
    db.commit()

    if modified or added or deleted:
        now = datetime.utcnow().timestamp()
        if now - _last_alert.get(watch.id, 0) > ALERT_COOLDOWN:
            _last_alert[watch.id] = now
            notify_event(
                "tamper_detected",
                "Tamper protection",
                f"'{site.name}': {len(modified)} modified, {len(added)} added, "
                f"{len(deleted)} deleted files"
                + (f", {restored} restored" if restored else ""),
            )
    return {
        "modified": modified,
        "added": added,
        "deleted": deleted,
        "restored": restored,
        "scanned_at": watch.last_scan_at.isoformat(),
    }


def tamper_scan_job() -> None:
    """Scheduler entry: scan every enabled watch."""
    from panelpro.core.database import SessionLocal

    db = SessionLocal()
    try:
        for watch in db.query(TamperWatch).filter(TamperWatch.enabled.is_(True)).all():
            try:
                scan(db, watch)
            except Exception:
                continue
    finally:
        db.close()


def watch_payload(watch: TamperWatch) -> dict:
    return {
        "id": watch.id,
        "site_id": watch.site_id,
        "enabled": watch.enabled,
        "mode": watch.mode,
        "baseline_files": len(watch.baseline or {}),
        "baseline_at": watch.baseline_at.isoformat() if watch.baseline_at else None,
        "last_scan_at": watch.last_scan_at.isoformat() if watch.last_scan_at else None,
        "last_changes": watch.last_changes or {},
    }
