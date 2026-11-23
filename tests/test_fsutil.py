"""Filesystem utility tests (cross-platform)."""

import os
import zipfile

import pytest

from panelpro.core import fsutil
from panelpro.core.errors import PanelError

ABS_PATH = "/tmp/a/b" if os.name == "posix" else "C:/tmp/a/b"


def test_normalize_rejects_traversal():
    with pytest.raises(PanelError):
        fsutil.normalize_path("../etc/passwd")
    with pytest.raises(PanelError):
        fsutil.normalize_path("relative/path")
    assert fsutil.normalize_path(ABS_PATH)


def test_write_read_roundtrip(tmp_path):
    target = tmp_path / "note.txt"
    fsutil.write_text(str(target), "hello panel")
    data = fsutil.read_text(str(target))
    assert data["content"] == "hello panel"
    assert data["size"] == 11


def test_mkdir_rename(tmp_path):
    d = tmp_path / "newdir"
    fsutil.mkdir(str(d))
    assert d.is_dir()
    fsutil.rename(str(d), str(tmp_path / "renamed"))
    assert (tmp_path / "renamed").is_dir()


def test_list_dir(tmp_path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "a.txt").write_text("x")
    data = fsutil.list_dir(str(tmp_path))
    names = {e["name"] for e in data["entries"]}
    assert {"folder", "a.txt"} <= names
    by_name = {e["name"]: e for e in data["entries"]}
    assert by_name["folder"]["is_dir"] is True
    assert by_name["a.txt"]["is_dir"] is False


def test_compress_extract_zip_roundtrip(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "f.txt").write_text("payload")
    (src / "sub" / "g.txt").write_text("nested")

    archive = tmp_path / "out.zip"
    fsutil.compress([str(src)], str(archive), "zip")
    assert archive.exists()

    dest = tmp_path / "out"
    fsutil.extract(str(archive), str(dest))
    assert (dest / "src" / "f.txt").read_text() == "payload"
    assert (dest / "src" / "sub" / "g.txt").exists()


def test_extract_rejects_path_escape(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        info = zipfile.ZipInfo("../escape.txt")
        zf.writestr(info, "nope")
    with pytest.raises(PanelError):
        fsutil.extract(str(evil), str(tmp_path / "dest"))


def test_search(tmp_path):
    (tmp_path / "report-2026.txt").write_text("x")
    (tmp_path / "other.log").write_text("x")
    found = fsutil.search_files(str(tmp_path), "report")
    assert len(found) == 1
    assert found[0]["name"] == "report-2026.txt"


def test_human_size():
    assert fsutil.human_size(0) == "0 B"
    assert fsutil.human_size(2048).endswith("KB")
