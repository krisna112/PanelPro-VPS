"""PHP management endpoints: versions, extensions, ini, FPM pools."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.errors import PanelError
from panelpro.services import phpmgr

router = APIRouter(prefix="/api/php", tags=["php"])


class IniBody(BaseModel):
    sapi: str = "fpm"
    content: str


class ExtensionBody(BaseModel):
    extension: str


class PoolBody(BaseModel):
    settings: dict


class InstallBody(BaseModel):
    version: str


@router.get("/versions")
def versions(ctx=Depends(require_auth)):
    return api_ok(phpmgr.list_versions())


@router.get("/versions/{version}/extensions")
def version_extensions(version: str, ctx=Depends(require_auth)):
    return api_ok(phpmgr.extensions(version))


@router.post("/versions/{version}/extensions/install")
def install_extension(version: str, body: ExtensionBody, ctx=Depends(require_role("admin"))):
    return api_ok(phpmgr.install_extension(version, body.extension))


@router.get("/versions/{version}/ini")
def read_ini(version: str, sapi: str = "fpm", ctx=Depends(require_auth)):
    return api_ok(phpmgr.read_ini(version, sapi))


@router.post("/versions/{version}/ini")
def write_ini(version: str, body: IniBody, ctx=Depends(require_role("operator"))):
    return api_ok(phpmgr.write_ini(version, body.sapi, body.content))


@router.post("/versions/{version}/restart")
def restart(version: str, ctx=Depends(require_role("operator"))):
    phpmgr.restart(version)
    return api_ok({"restarted": version})


@router.get("/versions/{version}/pool")
def pool(version: str, ctx=Depends(require_auth)):
    return api_ok({"file": str(phpmgr.pool_file(version) or ""), "settings": phpmgr.pool_settings(version)})


@router.post("/versions/{version}/pool")
def tune_pool(version: str, body: PoolBody, ctx=Depends(require_role("operator"))):
    return api_ok(phpmgr.tune_pool(version, body.settings))


@router.post("/install")
def install_php(body: InstallBody, ctx=Depends(require_role("admin"))):
    """Install a PHP-FPM version through the system package manager."""
    version = body.version.strip()
    if not version.replace(".", "").isdigit():
        raise PanelError(f"Invalid version: {version}", 400)
    if shutil.which("apt-get"):
        cmd = ["apt-get", "install", "-y", f"php{version}-fpm", f"php{version}-mysql",
               f"php{version}-curl", f"php{version}-gd", f"php{version}-xml",
               f"php{version}-mbstring", f"php{version}-zip"]
        env = {"DEBIAN_FRONTEND": "noninteractive"}
    elif shutil.which("yum") or shutil.which("dnf"):
        installer = shutil.which("dnf") or "yum"
        cmd = [installer, "install", "-y", "php-fpm", "php-mysqlnd", "php-gd",
               "php-xml", "php-mbstring"]
        env = {}
    else:
        raise PanelError("No supported package manager found (apt-get/yum/dnf).", 400)
    from panelpro.core.syscmd import run

    res = run(cmd, timeout=900, env=env)
    if res.code != 0:
        raise PanelError(f"PHP install failed: {res.stderr[-400:]}", 500)
    return api_ok({"installed": version, "note": "Check the versions list to confirm."})
