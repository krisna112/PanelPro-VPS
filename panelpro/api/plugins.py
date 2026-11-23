"""Plugin registry: discovery, metadata, enable/disable hooks.

Plugins live in ``panelpro/plugins/<name>/`` with a ``manifest.json`` and a
``main.py`` exposing a FastAPI ``router``.  Routers are mounted at startup
(see main.py); this endpoint lists what is loaded.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from panelpro.api.deps import api_ok, require_role
from panelpro.config import CFG

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def discover_plugins() -> list[dict]:
    """Scan the plugins directory for valid manifests."""
    plugins = []
    if not CFG.plugins_dir.is_dir():
        return plugins
    for manifest_path in sorted(CFG.plugins_dir.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        plugins.append(
            {
                "id": data.get("id", manifest_path.parent.name),
                "name": data.get("name", manifest_path.parent.name),
                "version": data.get("version", ""),
                "description": data.get("description", ""),
                "author": data.get("author", ""),
                "prefix": data.get("prefix", ""),
                "path": str(manifest_path.parent),
            }
        )
    return plugins


@router.get("")
def list_plugins(ctx=Depends(require_role("admin"))):
    return api_ok(discover_plugins())


@router.post("/reload-hint")
def reload_hint(ctx=Depends(require_role("admin"))):
    return api_ok({"note": "Plugin routers mount at startup. Restart the panel to load new plugins."})
