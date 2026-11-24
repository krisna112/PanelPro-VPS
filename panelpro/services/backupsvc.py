"""Backup service: site archives + database dumps, retention, remote copy."""

from __future__ import annotations

import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which
from panelpro.models.tables import BackupJob, BackupRun


def _dump_mysql(database: str, dest: Path) -> None:
    if not which("mysqldump"):
        raise PanelError("mysqldump is not installed.", 400)
    import gzip
    import os
    import subprocess

    from panelpro.core import keyvault, settings_store

    env = {}
    enc = settings_store.get_setting("mysql_root_password_enc", "")
    if enc:
        env["MYSQL_PWD"] = keyvault.decrypt_str(enc)
    proc = subprocess.run(
        ["mysqldump", "--single-transaction", "--quick", database],
        capture_output=True,
        timeout=1800,
        env={**os.environ, **env},
    )
    if proc.returncode != 0:
        raise PanelError(f"mysqldump failed: {proc.stderr[-300:]}", 500)
    with gzip.open(dest, "wb") as fh:
        fh.write(proc.stdout)


def _dump_postgres(database: str, dest: Path) -> None:
    if not which("pg_dump"):
        raise PanelError("pg_dump is not installed.", 400)
    res = run(
        ["runuser", "-u", "postgres", "--", "pg_dump", database],
        timeout=1800,
    )
    if res.code != 0:
        res = run(["sudo", "-u", "postgres", "pg_dump", database], timeout=1800)
    if res.code != 0:
        raise PanelError(f"pg_dump failed: {res.stderr[-300:]}", 500)
    import gzip

    with gzip.open(dest, "wb") as fh:
        fh.write(res.stdout.encode())


def run_backup_job(job: BackupJob) -> BackupRun:
    """Execute one backup job; returns the persisted BackupRun row."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.name)
    final_path = CFG.backup_dir / f"{safe_name}_{stamp}.tar.gz"
    CFG.backup_dir.mkdir(parents=True, exist_ok=True)

    run_row = BackupRun(job_id=job.id, filename=final_path.name, status="running")
    with tempfile.TemporaryDirectory(prefix="pp-backup-") as tmp:
        tmp_path = Path(tmp)

        for database in job.databases or []:
            db_type, _, db_name = str(database).partition(":")
            db_name = db_name or db_type
            try:
                if db_type == "mysql":
                    _dump_mysql(db_name, tmp_path / f"db_{db_name}.sql.gz")
                elif db_type == "postgres":
                    _dump_postgres(db_name, tmp_path / f"db_{db_name}.sql.gz")
            except PanelError as exc:
                run_row.status = "failed"
                run_row.message = str(exc)
                return run_row

        try:
            with tarfile.open(final_path, "w:gz") as tf:
                for site_root in job.sites or []:
                    p = Path(str(site_root))
                    if p.exists():
                        tf.add(p, arcname=p.name)
                for dump in sorted(tmp_path.iterdir()):
                    tf.add(dump, arcname=dump.name)
        except OSError as exc:
            run_row.status = "failed"
            run_row.message = f"Archive failed: {exc}"
            return run_row

    # retention for this job's archives
    try:
        archives = sorted(
            CFG.backup_dir.glob(f"{safe_name}_*.tar.gz"), key=lambda p: p.stat().st_mtime
        )
        for old in archives[:-max(1, job.keep)]:
            old.unlink(missing_ok=True)
    except OSError:
        pass

    # remote copy targets
    message = ""
    try:
        if job.target == "sftp":
            message = _copy_sftp(final_path, job.target_config or {})
        elif job.target.startswith("rclone"):
            message = _copy_rclone(final_path, job.target.split(":", 1)[-1])
    except (PanelError, Exception) as exc:  # noqa: BLE001 - report, keep local copy
        message = f"Remote copy failed: {exc}"

    run_row.status = "done"
    run_row.size_bytes = final_path.stat().st_size
    run_row.message = message
    return run_row


def _copy_sftp(archive: Path, cfg: dict) -> str:
    import paramiko

    host = cfg.get("host")
    if not host:
        raise PanelError("SFTP target needs a host.", 400)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=int(cfg.get("port", 22)),
        username=cfg.get("username", "root"),
        password=cfg.get("password", ""),
        key_filename=cfg.get("key_path") or None,
        timeout=20,
    )
    sftp = client.open_sftp()
    remote = f"{cfg.get('remote_dir', '/backups')}/{archive.name}"
    sftp.put(str(archive), remote)
    sftp.close()
    client.close()
    return f"copied to sftp {host}:{remote}"


def _copy_rclone(archive: Path, remote: str) -> str:
    if not which("rclone"):
        raise PanelError("rclone is not installed.", 400)
    res = run(["rclone", "copy", str(archive), remote], timeout=3600)
    if res.code != 0:
        raise PanelError(f"rclone failed: {res.stderr[-300:]}", 500)
    return f"copied to rclone {remote}"


def restore_site(archive_path: str, member: str, dest: str) -> dict:
    """Restore one directory member from a panel archive into dest."""
    arc = Path(archive_path)
    if not arc.exists():
        raise PanelError(f"Archive not found: {archive_path}", 404)
    dest_path = Path(dest)
    dest_path.mkdir(parents=True, exist_ok=True)
    root = dest_path.resolve()
    with tarfile.open(arc, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.name == member or m.name.startswith(member + "/")]
        if not members:
            raise PanelError(f"Member not found in archive: {member}", 404)
        for m in members:
            candidate = (root / Path(m.name).relative_to(member)).resolve()
            if not str(candidate).startswith(str(root) + __import__("os").sep) and candidate != root:
                raise PanelError("Unsafe archive member detected.", 400)
        tf.extractall(dest_path, members=members)
    return {"restored": member, "dest": str(dest_path)}


def import_sql_dump(db_type: str, database: str, dump_path: Path) -> None:
    """Import a gzipped SQL dump produced by export_bundle into the engine."""
    import gzip
    import shutil as _shutil

    # decompress to a plain .sql file so the CLI tools can read it from disk
    # (mysql -e "source …" / psql -f) without needing stdin plumbing
    sql_path = dump_path.with_suffix("")
    with gzip.open(dump_path, "rb") as src, open(sql_path, "wb") as dst:
        _shutil.copyfileobj(src, dst)
    try:
        if db_type == "mysql":
            from panelpro.services.dbmgr import _mysql_client_args

            args, env = _mysql_client_args()
            res = run([*args, database, "-e", f"source {sql_path}"], timeout=1800, env=env)
            if res.code != 0:
                raise PanelError(f"mysql import failed: {res.stderr[-300:]}", 500)
            return
        if db_type == "postgres":
            from panelpro.services.dbmgr import _psql_file_args

            for args in _psql_file_args(database, str(sql_path)):
                res = run(args, timeout=1800)
                if res.code == 0:
                    return
            raise PanelError(f"postgres import failed: {res.stderr[-300:]}", 500)
        raise PanelError(f"Unsupported dump engine: {db_type}", 400)
    finally:
        try:
            sql_path.unlink()
        except OSError:
            pass


def backup_due_check_job() -> None:
    """Scheduler job: run every enabled backup job whose cron is due."""
    from croniter import croniter

    from panelpro.core.database import SessionLocal
    from panelpro.core.notify import notify_event

    db = SessionLocal()
    try:
        jobs = db.query(BackupJob).filter(BackupJob.enabled.is_(True)).all()
        now = datetime.now()
        for job in jobs:
            try:
                next_ts = croniter(job.schedule, job.last_run_at or now - __import__("datetime").timedelta(days=365)).get_next(datetime)
            except Exception:
                continue
            if next_ts > now:
                continue
            run_row = run_backup_job(job)
            job.last_run_at = datetime.utcnow()
            job.last_status = run_row.status
            db.add(run_row)
            db.commit()
            if run_row.status == "done":
                notify_event(
                    "backup_done", "Backup finished",
                    f"{job.name}: {run_row.filename} ({run_row.size_bytes} bytes)",
                )
            else:
                notify_event("backup_failed", "Backup failed", f"{job.name}: {run_row.message}")
    finally:
        db.close()
