"""Filesystem helpers for the file manager.

Paths coming from the browser are always normalised to absolute form with
no ``..`` segments; symlinks are resolved so listings describe real targets.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import stat
import time
from pathlib import Path

from panelpro.config import CFG
from panelpro.core.errors import PanelError

try:  # POSIX only
    import grp  # type: ignore
    import pwd  # type: ignore
    HAS_PWD = True
except ImportError:  # pragma: no cover - Windows dev environment
    HAS_PWD = False


def normalize_path(path: str) -> str:
    """Return an absolute, symlink-free, traversal-free path."""
    if not path or not path.strip():
        raise PanelError("A file path is required.", 400)
    p = Path(path.strip()).expanduser()
    if not p.is_absolute():
        raise PanelError("Only absolute paths are allowed.", 400)
    resolved = Path(os.path.normpath(str(p)))
    if ".." in resolved.parts:
        raise PanelError("Path traversal is not allowed.", 400)
    return str(resolved)


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} EB"


def _owner_names(uid: int | None, gid: int | None) -> tuple[str | None, str | None]:
    if not HAS_PWD or uid is None:
        return None, None
    try:
        owner = pwd.getpwuid(uid).pw_name
    except KeyError:
        owner = str(uid)
    try:
        group = grp.getgrgid(gid).gr_name
    except KeyError:
        group = str(gid)
    return owner, group


def entry_info(full: Path) -> dict:
    try:
        st = full.lstat()
    except (FileNotFoundError, PermissionError):
        return {"name": full.name, "hidden": full.name.startswith("."), "accessible": False}

    is_dir = stat.S_ISDIR(st.st_mode)
    owner, group = _owner_names(st.st_uid, st.st_gid)
    mime = None
    if not is_dir:
        mime, _ = mimetypes.guess_type(full.name)
    return {
        "name": full.name,
        "path": str(full),
        "is_dir": is_dir,
        "is_symlink": stat.S_ISLNK(st.st_mode),
        "size": 0 if is_dir else st.st_size,
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "owner": owner,
        "group": group,
        "mtime": int(st.st_mtime),
        "mime": mime,
        "hidden": full.name.startswith("."),
        "accessible": True,
    }


def list_dir(path: str, show_hidden: bool = True) -> dict:
    path = normalize_path(path)
    target = Path(path)
    if not target.exists():
        raise PanelError(f"Path does not exist: {path}", 404)
    if not target.is_dir():
        raise PanelError(f"Not a directory: {path}", 400)

    entries: list[dict] = []
    for child in target.iterdir():
        if not show_hidden and child.name.startswith("."):
            continue
        entries.append(entry_info(child))
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return {"path": path, "entries": entries}


def read_text(path: str, max_bytes: int | None = None) -> dict:
    from panelpro.constants import MAX_TEXT_EDIT_BYTES

    path = normalize_path(path)
    p = Path(path)
    if not p.exists():
        raise PanelError(f"File does not exist: {path}", 404)
    if p.is_dir():
        raise PanelError("Cannot read a directory as text.", 400)
    limit = max_bytes or MAX_TEXT_EDIT_BYTES
    if p.stat().st_size > limit:
        raise PanelError(
            f"File is larger than the {human_size(limit)} editor limit.", 400
        )
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except PermissionError as exc:
        raise PanelError(f"Permission denied: {path}", 403) from exc
    return {"path": path, "content": content, "size": p.stat().st_size}


def is_text_file(path: str) -> bool:
    p = Path(normalize_path(path))
    if not p.is_file():
        return False
    with open(p, "rb") as fh:
        chunk = fh.read(4096)
    return b"\0" not in chunk


def write_text(path: str, content: str) -> dict:
    path = normalize_path(path)
    p = Path(path)
    if p.is_dir():
        raise PanelError("Target is a directory.", 400)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".pp-tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(p)
    return {"path": path, "size": len(content.encode("utf-8"))}


def mkdir(path: str) -> dict:
    path = normalize_path(path)
    p = Path(path)
    if p.exists():
        raise PanelError("Path already exists.", 400)
    p.mkdir(parents=True, exist_ok=False)
    return {"path": path}


def rename(src: str, dst: str) -> dict:
    src_p = Path(normalize_path(src))
    dst_p = Path(normalize_path(dst))
    if not src_p.exists():
        raise PanelError(f"Source does not exist: {src}", 404)
    if dst_p.exists():
        raise PanelError(f"Target already exists: {dst}", 400)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    src_p.rename(dst_p)
    return {"from": src, "to": dst}


def copy_path(src: str, dst: str) -> dict:
    src_p = Path(normalize_path(src))
    dst_p = Path(normalize_path(dst))
    if not src_p.exists():
        raise PanelError(f"Source does not exist: {src}", 404)
    if dst_p.exists():
        raise PanelError(f"Target already exists: {dst}", 400)
    if src_p.is_dir():
        shutil.copytree(src_p, dst_p)
    else:
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_p, dst_p)
    return {"from": src, "to": dst}


def delete_paths(paths: list[str], use_trash: bool = True) -> dict:
    """Delete (or trash) a list of files/directories."""
    if not paths:
        raise PanelError("Nothing to delete.", 400)
    moved: list[str] = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for raw in paths:
        p = Path(normalize_path(raw))
        if not p.exists():
            continue
        if use_trash:
            target_dir = CFG.trash_dir / stamp
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = target_dir / p.name
            base = dest
            i = 1
            while dest.exists():
                dest = base.with_name(f"{base.name}.{i}")
                i += 1
            shutil.move(str(p), str(dest))
            moved.append(str(dest))
        else:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            moved.append(str(p))
    return {"removed": len(moved), "trash": use_trash, "items": moved}


def chmod_path(path: str, mode: int) -> dict:
    p = Path(normalize_path(path))
    if not p.exists():
        raise PanelError(f"Path does not exist: {path}", 404)
    os.chmod(p, mode)
    return {"path": path, "mode": oct(mode)}


def chown_path(path: str, owner: str | None, group: str | None) -> dict:
    if not HAS_PWD:
        raise PanelError("Ownership changes require a POSIX system.", 400)
    p = Path(normalize_path(path))
    if not p.exists():
        raise PanelError(f"Path does not exist: {path}", 404)
    uid = pwd.getpwnam(owner).pw_uid if owner else -1
    gid = grp.getgrnam(group).gr_gid if group else -1
    os.chown(p, uid, gid)
    return {"path": path, "owner": owner, "group": group}


def compress(paths: list[str], out: str, fmt: str = "zip") -> dict:
    """Compress files/directories into a zip or tar.gz archive."""
    out_p = Path(normalize_path(out))
    if out_p.exists():
        raise PanelError("Archive already exists.", 400)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    sources = [Path(normalize_path(x)) for x in paths]
    for s in sources:
        if not s.exists():
            raise PanelError(f"Path does not exist: {s}", 404)

    if fmt == "zip":
        import zipfile

        with zipfile.ZipFile(out_p, "w", zipfile.ZIP_DEFLATED) as zf:
            for s in sources:
                if s.is_dir():
                    for f in s.rglob("*"):
                        zf.write(f, f.relative_to(s.parent))
                else:
                    zf.write(s, s.name)
    elif fmt in ("tar.gz", "tgz"):
        import tarfile

        with tarfile.open(out_p, "w:gz") as tf:
            for s in sources:
                tf.add(s, arcname=s.name)
    else:
        raise PanelError(f"Unsupported archive format: {fmt}", 400)
    return {"out": str(out_p), "size": out_p.stat().st_size}


def extract(archive: str, dest: str) -> dict:
    """Extract zip/tar archives with path-escape protection."""
    import tarfile
    import zipfile

    arc_p = Path(normalize_path(archive))
    dest_p = Path(normalize_path(dest))
    if not arc_p.exists():
        raise PanelError(f"Archive does not exist: {archive}", 404)
    dest_p.mkdir(parents=True, exist_ok=True)

    dest_root = dest_p.resolve()

    def _safe_tar_members(tf: tarfile.TarFile) -> list[tarfile.TarInfo]:
        safe: list[tarfile.TarInfo] = []
        for m in tf.getmembers():
            candidate = (dest_root / m.name).resolve()
            if not str(candidate).startswith(str(dest_root)):
                raise PanelError(f"Refusing unsafe archive member: {m.name}", 400)
            safe.append(m)
        return safe

    if zipfile.is_zipfile(arc_p):
        with zipfile.ZipFile(arc_p) as zf:
            for info in zf.infolist():
                candidate = (dest_root / info.filename).resolve()
                if not str(candidate).startswith(str(dest_root)):
                    raise PanelError(
                        f"Refusing unsafe archive member: {info.filename}", 400
                    )
            zf.extractall(dest_p)
    elif tarfile.is_tarfile(arc_p):
        with tarfile.open(arc_p) as tf:
            tf.extractall(dest_p, members=_safe_tar_members(tf))
    else:
        raise PanelError("Unsupported archive type.", 400)
    return {"dest": str(dest_p)}


def search_files(root: str, query: str, max_results: int = 500) -> list[dict]:
    root_p = Path(normalize_path(root))
    if not root_p.is_dir():
        raise PanelError("Search root must be a directory.", 400)
    needle = query.lower().strip()
    if not needle:
        return []
    results: list[dict] = []
    for current, dirs, files in os.walk(root_p):
        dirs[:] = [d for d in dirs if not d.startswith(".pp-")]
        for name in files + dirs:
            if needle in name.lower():
                results.append(entry_info(Path(current) / name))
                if len(results) >= max_results:
                    return results
    return results


def disk_usage(path: str) -> dict:
    p = Path(normalize_path(path) if path else str(CFG.home))
    usage = shutil.disk_usage(p)
    return {
        "path": str(p),
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": round(usage.used / usage.total * 100, 1) if usage.total else 0,
    }
