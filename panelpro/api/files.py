"""File manager endpoints: browse, edit, upload/download, archive, perms."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.config import CFG
from panelpro.constants import MAX_UPLOAD_BYTES
from panelpro.core import fsutil
from panelpro.core.errors import PanelError

router = APIRouter(prefix="/api/files", tags=["files"])


class WriteBody(BaseModel):
    path: str
    content: str


class PathsBody(BaseModel):
    paths: list[str]


class MkdirBody(BaseModel):
    path: str


class RenameBody(BaseModel):
    src: str
    dst: str


class CopyBody(BaseModel):
    src: str
    dst: str


class ChmodBody(BaseModel):
    path: str
    mode: str


class ChownBody(BaseModel):
    path: str
    owner: str | None = None
    group: str | None = None


class CompressBody(BaseModel):
    paths: list[str]
    out: str
    fmt: str = "zip"


class ExtractBody(BaseModel):
    path: str
    dest: str


@router.get("/list")
def list_dir(path: str = "/", show_hidden: bool = True, ctx=Depends(require_auth)):
    data = fsutil.list_dir(path, show_hidden=show_hidden)
    data["disk"] = fsutil.disk_usage(path if Path(path).exists() else str(CFG.home))
    return api_ok(data)


@router.get("/read")
def read_file(path: str, ctx=Depends(require_auth)):
    data = fsutil.read_text(path)
    data["is_text"] = fsutil.is_text_file(path)
    return api_ok(data)


@router.post("/write")
def write_file(body: WriteBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.write_text(body.path, body.content))


@router.post("/mkdir")
def mkdir(body: MkdirBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.mkdir(body.path))


@router.post("/rename")
def rename(body: RenameBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.rename(body.src, body.dst))


@router.post("/copy")
def copy_path(body: CopyBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.copy_path(body.src, body.dst))


@router.post("/delete")
def delete(body: PathsBody, trash: bool = True, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.delete_paths(body.paths, use_trash=trash))


@router.post("/chmod")
def chmod(body: ChmodBody, ctx=Depends(require_role("operator"))):
    try:
        mode = int(str(body.mode), 8)
    except ValueError as exc:
        raise PanelError(f"Invalid mode: {body.mode}", 400) from exc
    return api_ok(fsutil.chmod_path(body.path, mode))


@router.post("/chown")
def chown(body: ChownBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.chown_path(body.path, body.owner, body.group))


@router.post("/compress")
def compress(body: CompressBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.compress(body.paths, body.out, body.fmt))


@router.post("/extract")
def extract(body: ExtractBody, ctx=Depends(require_role("operator"))):
    return api_ok(fsutil.extract(body.path, body.dest))


@router.get("/search")
def search(path: str, query: str, ctx=Depends(require_auth)):
    from panelpro.constants import SEARCH_MAX_RESULTS

    return api_ok(fsutil.search_files(path, query, SEARCH_MAX_RESULTS))


@router.get("/download")
def download(path: str, ctx=Depends(require_auth)):
    clean = fsutil.normalize_path(path)
    if not Path(clean).is_file():
        raise PanelError("Not a file.", 400)
    return FileResponse(clean, filename=Path(clean).name)


@router.post("/upload")
async def upload(dest: str, file: UploadFile, ctx=Depends(require_role("operator"))):
    dest_dir = fsutil.normalize_path(dest)
    target = Path(dest_dir) / Path(file.filename or "upload.bin").name
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(target, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise PanelError("Upload exceeds the size limit.", 413)
            out.write(chunk)
    return api_ok({"path": str(target), "size": size})


@router.post("/trash-empty")
def empty_trash(ctx=Depends(require_role("operator"))):
    import shutil

    if CFG.trash_dir.exists():
        shutil.rmtree(CFG.trash_dir, ignore_errors=True)
        CFG.trash_dir.mkdir(parents=True, exist_ok=True)
    return api_ok({"emptied": True})
