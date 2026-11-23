"""Example PanelPro plugin.

A plugin is a folder under ``panelpro/plugins/`` containing:

* ``manifest.json`` — metadata plus the router prefix.
* ``main.py``       — must expose a FastAPI ``router``.

The panel mounts the router at startup under ``manifest.prefix``.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/hello")
def hello():
    return {"ok": True, "message": "Hello from the sample plugin!"}


@router.get("/info")
def info():
    return {
        "ok": True,
        "plugin": "sample_hello",
        "note": "Copy this folder and extend it to build your own plugin.",
    }
