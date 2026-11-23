"""Docker management endpoints (thin wrapper over the CLI service)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.services import dockermgr

router = APIRouter(prefix="/api/docker", tags=["docker"])


class PullBody(BaseModel):
    image: str


class ImageBody(BaseModel):
    image: str


class ExecBody(BaseModel):
    command: str


@router.get("/status")
def status(ctx=Depends(require_auth)):
    return api_ok({"available": dockermgr.available()})


@router.get("/containers")
def containers(all_ps: bool = True, ctx=Depends(require_auth)):
    return api_ok(dockermgr.containers(all_ps))


@router.post("/containers/{name}/{action}")
def container_action(name: str, action: str, ctx=Depends(require_role("operator"))):
    return api_ok(dockermgr.container_action(name, action))


@router.get("/containers/{name}/logs")
def container_logs(name: str, tail: int = 200, ctx=Depends(require_auth)):
    return api_ok({"log": dockermgr.container_logs(name, tail)})


@router.post("/containers/{name}/exec")
def container_exec(name: str, body: ExecBody, ctx=Depends(require_role("operator"))):
    return api_ok({"output": dockermgr.container_exec(name, body.command)[-512_000:]})


@router.get("/stats")
def stats(ctx=Depends(require_auth)):
    return api_ok(dockermgr.container_stats())


@router.get("/images")
def images(ctx=Depends(require_auth)):
    return api_ok(dockermgr.images())


@router.post("/images/pull")
def pull(body: PullBody, ctx=Depends(require_role("operator"))):
    return api_ok(dockermgr.pull(body.image))


@router.post("/images/remove")
def remove_image(body: ImageBody, ctx=Depends(require_role("operator"))):
    return api_ok(dockermgr.remove_image(body.image))


@router.post("/images/prune")
def prune(ctx=Depends(require_role("operator"))):
    return api_ok(dockermgr.prune_images())


@router.get("/volumes")
def volumes(ctx=Depends(require_auth)):
    return api_ok(dockermgr.volumes())


@router.get("/networks")
def networks(ctx=Depends(require_auth)):
    return api_ok(dockermgr.networks())
