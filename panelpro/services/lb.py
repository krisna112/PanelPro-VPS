"""nginx upstream pools (load balancing).

An upstream is rendered into its own conf.d file (http context) from
``nginx_upstream.conf.j2``.  Sites point at a pool by setting
``proxy_target = "upstream:<name>"`` — the vhost template proxies to the
pool exactly like a plain host:port target.
"""

from __future__ import annotations

import re
from pathlib import Path

from panelpro.core.errors import PanelError
from panelpro.models.tables import Upstream

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,60}$")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")


def validate_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.fullmatch(name):
        raise PanelError(
            "Invalid upstream name (lowercase letters/digits/underscore, "
            "starts with a letter).",
            400,
        )
    return name


def validate_servers(servers: list) -> list[dict]:
    if not servers or not isinstance(servers, list):
        raise PanelError("At least one upstream server is required.", 400)
    cleaned: list[dict] = []
    for item in servers[:32]:
        host = str(item.get("host", "")).strip()
        port = int(item.get("port", 0))
        weight = int(item.get("weight", 1))
        if not HOST_RE.match(host) or ".." in host:
            raise PanelError(f"Invalid upstream host: {host}", 400)
        if not 0 < port < 65536:
            raise PanelError(f"Invalid upstream port: {port}", 400)
        if not 1 <= weight <= 100:
            raise PanelError(f"Invalid upstream weight: {weight}", 400)
        cleaned.append({"host": host, "port": port, "weight": weight})
    return cleaned


def conf_path(name: str) -> Path:
    """Where the rendered upstream conf is written (nginx conf.d)."""
    from panelpro.services import webservers

    adapter = webservers.detect_webserver("nginx")
    return Path(adapter.conf_dir) / f"upstream_{name}.conf"


def parse_proxy_target(target: str) -> str:
    """Validate a site proxy target; supports 'upstream:<name>' pools."""
    target = (target or "").strip()
    if target.startswith("upstream:"):
        name = validate_name(target.split(":", 1)[1])
        return f"upstream:{name}"
    if not re.match(r"^[A-Za-z0-9.:-]{1,120}$", target) or ".." in target:
        raise PanelError(f"Invalid proxy target: {target}", 400)
    return target


def write_upstream(upstream: Upstream, path: Path, adapter) -> dict:
    from panelpro.services import webservers

    content = adapter.render("nginx_upstream.conf.j2", {
        "name": upstream.name,
        "servers": upstream.servers,
    })
    webservers.write_config(path, content.encode("utf-8"))
    return {"conf_path": str(path), "servers": len(upstream.servers)}


def payload(upstream: Upstream) -> dict:
    return {
        "id": upstream.id,
        "name": upstream.name,
        "servers": upstream.servers,
        "created_at": upstream.created_at.isoformat() if upstream.created_at else None,
    }
