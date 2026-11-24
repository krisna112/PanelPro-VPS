"""Server migration: export sites/DBs/certs to one bundle, import on another.

The bundle is a plain tar.gz containing:

* ``manifest.json``            — site/database/cert metadata + panel version
* ``www/<domain>/...``         — site document roots
* ``db/<engine>/<name>.sql.gz``— mysqldump / pg_dump snapshots
* ``ssl/<cert_name>/...``      — certificate + key pairs

Import restores the file trees, recreates Site/Db rows, registers the
certificates as custom certs, renders vhosts and reloads the webserver.
No user passwords or API keys are migrated — those are set fresh on the
target server by design.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import threading
from pathlib import Path

from panelpro.config import CFG
from panelpro.constants import VERSION
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import which
from panelpro.models.tables import DatabaseRow, DbUser, Site, SslCert

STATUS_KEY = "migration_status"
EXPORT_DIR = "migration"

_STATUS: dict = {"state": "idle", "progress": 0, "message": ""}


def status() -> dict:
    return dict(_STATUS)


def _set_status(state: str, progress: int = 0, message: str = "") -> None:
    _STATUS.update({"state": state, "progress": max(0, min(progress, 100)), "message": message[:400]})


def _manifest_sites(db) -> list[dict]:
    return [
        {
            "name": s.name,
            "server": s.server,
            "root": s.root,
            "aliases": s.aliases or [],
            "php_version": s.php_version,
            "proxy_target": s.proxy_target,
            "force_https": s.force_https,
            "enabled": s.enabled,
            "cert_domain": (db.query(SslCert).filter(SslCert.id == s.ssl_cert_id).first().domain
                            if s.ssl_cert_id else None),
        }
        for s in db.query(Site).order_by(Site.id.asc()).all()
    ]


def _manifest_databases(db) -> list[dict]:
    out = []
    for row in db.query(DatabaseRow).order_by(DatabaseRow.id.asc()).all():
        users = [
            {"name": u.name, "host": u.host}
            for u in db.query(DbUser).filter(DbUser.type == row.type, DbUser.name == row.owner_user).all()
        ]
        out.append({"name": row.name, "type": row.type, "charset": row.charset, "users": users})
    return out


def _manifest_certs(db) -> list[dict]:
    return [
        {
            "name": c.name,
            "domain": c.domain,
            "source": c.source,
            "cert_file": f"ssl/{c.id}/cert.pem",
            "key_file": f"ssl/{c.id}/key.pem",
        }
        for c in db.query(SslCert).order_by(SslCert.id.asc()).all()
        if c.source in ("selfsigned", "custom")
    ]


def export_bundle(db, include_db: bool = True, include_ssl: bool = True, site_ids: list[int] | None = None) -> Path:
    """Build a migration tar.gz; returns the archive path."""
    from panelpro.services import backupsvc

    sites = db.query(Site).order_by(Site.id.asc()).all()
    if site_ids:
        sites = [s for s in sites if s.id in site_ids]
    if not sites:
        raise PanelError("No sites to export.", 400)

    out_dir = CFG.backup_dir / EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime_stamp()
    archive_path = out_dir / f"panelpro-migration-{stamp}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as tar:
        manifest = {
            "panelpro_version": VERSION,
            "created_at": datetime_iso(),
            "sites": [m for m in _manifest_sites(db) if
                      next((s for s in sites if s.name == m["name"]), None)],
            "databases": _manifest_databases(db) if include_db else [],
            "certs": _manifest_certs(db) if include_ssl else [],
        }
        manifest["sites"] = [
            {**m, "root": f"/www/wwwroot/{m['name']}"} for m in manifest["sites"]
        ]
        _add_text(tar, archive_path, "manifest.json", json.dumps(manifest, indent=2))

        for site in sites:
            root = Path(site.root)
            if not root.is_dir():
                continue
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.stat().st_size > 512 * 1024 * 1024:
                    continue
                arcname = f"www/{site.name}/{file_path.relative_to(root).as_posix()}"
                tar.add(file_path, arcname=arcname)

        if include_db:
            tmp = CFG.tmp_dir / "migration-db"
            tmp.mkdir(parents=True, exist_ok=True)
            for row in db.query(DatabaseRow).all():
                try:
                    if row.type == "mysql" and which("mysqldump"):
                        dest = tmp / f"{row.name}.sql.gz"
                        backupsvc._dump_mysql(row.name, dest)
                        tar.add(dest, arcname=f"db/mysql/{row.name}.sql.gz")
                    elif row.type == "postgres" and which("pg_dump"):
                        dest = tmp / f"{row.name}.sql.gz"
                        backupsvc._dump_postgres(row.name, dest)
                        tar.add(dest, arcname=f"db/postgres/{row.name}.sql.gz")
                except Exception:
                    continue  # a failed dump is reported in the manifest note
        if include_ssl:
            for cert in db.query(SslCert).filter(SslCert.source.in_(("selfsigned", "custom"))).all():
                cert_file = Path(cert.cert_path)
                key_file = Path(cert.key_path or "")
                if cert_file.is_file():
                    tar.add(cert_file, arcname=f"ssl/{cert.id}/cert.pem")
                if key_file.is_file():
                    tar.add(key_file, arcname=f"ssl/{cert.id}/key.pem")
    return archive_path


def datetime_stamp() -> str:
    from datetime import datetime as _dt

    return _dt.utcnow().strftime("%Y%m%d-%H%M%S")


def datetime_iso() -> str:
    from datetime import datetime as _dt

    return _dt.utcnow().isoformat()


def _add_text(tar: tarfile.TarFile, _archive: Path, arcname: str, content: str) -> None:
    import io

    data = content.encode("utf-8")
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def import_bundle(db, archive_path: str, progress_cb=None) -> dict:
    """Restore sites/DBs/certs from a migration bundle."""
    from panelpro.api.sites import _apply_site, _check_domains, _proxy_target
    from panelpro.core import fsutil
    from panelpro.services import backupsvc, webservers

    archive = Path(archive_path)
    if not archive.is_file():
        raise PanelError("Migration archive not found.", 404)
    work = CFG.tmp_dir / f"migration-import-{datetime_stamp()}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        fsutil.extract(str(archive), str(work))
    except (tarfile.TarError, PanelError) as exc:
        raise PanelError(f"Invalid migration archive: {exc}", 400) from exc

    manifest_file = work / "manifest.json"
    if not manifest_file.is_file():
        raise PanelError("Archive has no manifest.json — not a PanelPro bundle.", 400)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    created_sites = []
    created_dbs = []
    created_certs = []
    site_errors = {}

    for db_meta in manifest.get("databases", []):
        name, db_type = db_meta["name"], db_meta.get("type", "mysql")
        engine = db.query(DatabaseRow).filter(DatabaseRow.name == name).first()
        if engine is not None:
            continue
        try:
            if db_type == "mysql":
                from panelpro.services.dbmgr import MySQLManager

                MySQLManager().create_database(name, db_meta.get("charset") or "utf8mb4")
            elif db_type == "postgres":
                from panelpro.services.dbmgr import PostgresManager

                PostgresManager().create_database(name, db_meta.get("charset") or "UTF8")
            else:
                continue
            dump = work / "db" / db_type / f"{name}.sql.gz"
            if dump.is_file():
                backupsvc.import_sql_dump(db_type, name, dump)
            row = DatabaseRow(name=name, type=db_type, charset=db_meta.get("charset") or "")
            db.add(row)
            db.commit()
            created_dbs.append(name)
        except Exception:
            continue

    for cert_meta in manifest.get("certs", []):
        cert_file = (work / cert_meta["cert_file"]).resolve()
        key_file = (work / cert_meta["key_file"]).resolve()
        if not all(path.is_relative_to(work.resolve()) for path in (cert_file, key_file)):
            continue
        if not (cert_file.is_file() and key_file.is_file()):
            continue
        existing = db.query(SslCert).filter(SslCert.domain == cert_meta["domain"]).first()
        if existing is not None:
            continue
        try:
            from panelpro.services import sslmgr

            result = sslmgr.import_custom(
                cert_meta["name"], cert_file.read_text(encoding="utf-8"),
                key_file.read_text(encoding="utf-8"),
            )
            info = result["info"]
            row = SslCert(
                name=cert_meta["name"],
                domain=info["subject"],
                issuer=info["issuer"],
                not_before=datetime_from_iso(info["not_before"]),
                not_after=datetime_from_iso(info["not_after"]),
                cert_path=result["cert_path"],
                key_path=result["key_path"],
                source="custom",
            )
            db.add(row)
            db.commit()
            created_certs.append(cert_meta["domain"])
        except Exception:
            continue

    site_entries = manifest.get("sites", [])
    for idx, metadata in enumerate(site_entries, start=1):
        name = str(metadata.get("name", ""))
        try:
            name = webservers.validate_domain(name)
            aliases = [webservers.validate_domain(alias) for alias in metadata.get("aliases", [])]
            with webservers.CONFIG_LOCK:
                _check_domains(db, [name, *aliases])
                adapter = webservers.detect_webserver(metadata.get("server") or "nginx")
                if any(path.exists() or path.is_symlink() for path in adapter.config_paths(name)):
                    raise PanelError("A webserver configuration already exists.", 409)
                proxy = _proxy_target(db, metadata.get("proxy_target"), adapter.name)
                source = work / "www" / name
                root = CFG.www_root / name
                if root.is_symlink() or (root.exists() and not root.is_dir()):
                    raise PanelError("Site root must be a regular directory.", 409)
                if not root.exists():
                    if source.is_dir():
                        shutil.copytree(source, root)
                    else:
                        root.mkdir()
                cert = db.query(SslCert).filter_by(domain=metadata["cert_domain"]).first() if metadata.get("cert_domain") else None
                site = Site(name=name, server=adapter.name, root=str(root), aliases=aliases,
                            php_version=metadata.get("php_version"), proxy_target=proxy,
                            ssl_cert_id=cert.id if cert else None, force_https=bool(cert and metadata.get("force_https")),
                            enabled=bool(metadata.get("enabled", True)))
                db.add(site)
                _apply_site(site, db, adapter)
                created_sites.append(name)
        except (OSError, PanelError) as exc:
            db.rollback()
            site_errors[name] = str(exc)
        if progress_cb:
            progress_cb(int(idx / len(site_entries) * 100))
    shutil.rmtree(work, ignore_errors=True)
    return {
        "sites": created_sites,
        "site_errors": site_errors,
        "databases": created_dbs,
        "certs": created_certs,
        "manifest_version": manifest.get("panelpro_version"),
    }


def datetime_from_iso(value: str):
    from datetime import datetime as _dt

    return _dt.fromisoformat(value)


def start_export(db, include_db: bool, include_ssl: bool, site_ids: list[int] | None) -> None:
    """Kick off the export in a background thread (status via settings)."""
    from panelpro.core.database import SessionLocal

    if _STATUS.get("state") == "running":
        raise PanelError("A migration export is already running.", 409)

    def _worker() -> None:
        own_db = SessionLocal()
        _set_status("running", 5, "building archive")
        try:
            archive = export_bundle(own_db, include_db, include_ssl, site_ids)
            from panelpro.core.notify import notify_event

            _set_status("done", 100, str(archive))
            notify_event("migration_done", "Migration export", f"Bundle ready: {archive.name}")
        except Exception as exc:
            from panelpro.core.notify import notify_event

            _set_status("failed", 100, str(exc))
            notify_event("migration_failed", "Migration export failed", str(exc)[:200])
        finally:
            own_db.close()

    threading.Thread(daemon=True, target=_worker).start()
