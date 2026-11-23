"""Security endpoints: firewall, IP blocks, ping, SSH port, fail2ban."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.errors import PanelError
from panelpro.services import firewall as fw

router = APIRouter(prefix="/api/security", tags=["security"])


class PortBody(BaseModel):
    port: int
    proto: str = "tcp"


class IpBody(BaseModel):
    ip: str


class PingBody(BaseModel):
    blocked: bool


class SshPortBody(BaseModel):
    port: int


@router.get("/status")
def status(ctx=Depends(require_auth)):
    try:
        state = fw.Firewall().status()
    except PanelError as exc:
        state = {"tool": None, "active": False, "rules": [], "message": exc.message}
    return api_ok(
        {
            "firewall": state,
            "ping_blocked": fw.detect_tool() and fw.Firewall().ping_blocked()
            if state.get("tool") else None,
            "fail2ban": fw.fail2ban_status(),
        }
    )


@router.get("/firewall/rules")
def rules(ctx=Depends(require_auth)):
    return api_ok(fw.Firewall().status())


@router.post("/firewall/allow")
def allow_port(body: PortBody, ctx=Depends(require_role("operator"))):
    return api_ok(fw.Firewall().add_port(body.port, body.proto))


@router.post("/firewall/remove")
def remove_port(body: PortBody, ctx=Depends(require_role("operator"))):
    return api_ok(fw.Firewall().remove_port(body.port, body.proto))


@router.post("/firewall/enable")
def enable(ctx=Depends(require_role("admin"))):
    fw.Firewall().enable()
    return api_ok({"enabled": True})


@router.post("/firewall/disable")
def disable(ctx=Depends(require_role("admin"))):
    fw.Firewall().disable()
    return api_ok({"enabled": False})


@router.post("/block")
def block_ip(body: IpBody, ctx=Depends(require_role("operator"))):
    return api_ok(fw.Firewall().block_ip(body.ip))


@router.post("/unblock")
def unblock_ip(body: IpBody, ctx=Depends(require_role("operator"))):
    return api_ok(fw.Firewall().unblock_ip(body.ip))


@router.post("/ping")
def set_ping(body: PingBody, ctx=Depends(require_role("admin"))):
    return api_ok(fw.Firewall().set_ping_block(body.blocked))


@router.post("/ssh-port")
def ssh_port(body: SshPortBody, ctx=Depends(require_role("admin"))):
    return api_ok(fw.Firewall().set_ssh_port(body.port))


@router.get("/ssh-port")
def get_ssh_port(ctx=Depends(require_auth)):
    return api_ok({"port": fw.Firewall().ssh_port()})
