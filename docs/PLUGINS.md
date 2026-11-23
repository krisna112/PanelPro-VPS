# Writing PanelPro Plugins

A plugin is a folder under `panelpro/plugins/<name>/`:

```
panelpro/plugins/my_plugin/
├── manifest.json
└── main.py
```

## manifest.json

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "What it does",
  "author": "you",
  "prefix": "/api/plugins/my_plugin"
}
```

## main.py

Export a FastAPI `router`; you may import anything from the panel package
(`panelpro.api.deps`, `panelpro.core.*`) to reuse auth and utilities.

```python
from fastapi import APIRouter, Depends

from panelpro.api.deps import api_ok, require_auth

router = APIRouter()

@router.get("/ping")
def ping(ctx=Depends(require_auth)):
    return api_ok({"pong": True, "user": ctx.username})
```

## Loading

* Routers are mounted at startup under `manifest.prefix`
  (`panelpro/main.py` scans `plugins/*/manifest.json`).
* A failing plugin logs a warning and never blocks panel startup.
* After adding a plugin, restart the panel service.

The bundled `sample_hello` plugin exposes `GET /api/plugins/hello/hello`
and is the shortest possible starting point.
