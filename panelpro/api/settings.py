"""Panel settings endpoints (admin only for most operations)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from panelpro.api.deps import api_ok, require_role
from panelpro.config import CFG
from panelpro.core import settings_store
from panelpro.core.errors import PanelError

router = APIRouter(prefix="/api/settings", tags=["settings"])

EDITABLE_KEYS = {
    "panel_port", "entry_path", "language", "theme", "api_enabled",
    "ip_allowlist", "trust_proxy", "panel_ssl", "threshold_disk",
    "threshold_cpu", "backup_dir",
}

class SettingBody(BaseModel):
    key: str
    value: object


class PanelSslBody(BaseModel):
    cert: str
    key: str


@router.get("")
def get_settings(ctx=Depends(require_role("admin"))):
    data = settings_store.all_settings()
    data.pop("mysql_root_password_enc", None)
    data["password"] = None  # never expose secrets
    return api_ok(data)


@router.post("")
def set_setting(body: SettingBody, ctx=Depends(require_role("admin"))):
    if body.key not in EDITABLE_KEYS:
        raise PanelError(f"Setting '{body.key}' is not editable via the API.", 400)
    value = body.value
    if body.key == "panel_port":
        try:
            port = int(value)
        except (TypeError, ValueError) as exc:
            raise PanelError("panel_port must be an integer.", 400) from exc
        if not (1024 <= port <= 65535):
            raise PanelError("panel_port must be between 1024 and 65535.", 400)
        value = port
        settings_store.set_setting("panel_port", port)
        return api_ok({"key": "panel_port", "value": port,
                       "note": "Restart the panel service to apply."})
    if body.key == "entry_path":
        entry = str(value)
        if not settings_store.valid_entry_path(entry):
            raise PanelError(
                "Entry path must be 4-32 chars (letters/digits/-/_) and not reserved.", 400
            )
        settings_store.set_setting("entry_path", entry)
        return api_ok({"key": "entry_path", "value": entry,
                       "note": "New login URL: /" + entry})
    if body.key == "ip_allowlist":
        if not isinstance(value, list):
            raise PanelError("ip_allowlist must be a list of IPs/CIDRs.", 400)
    settings_store.set_setting(body.key, value)
    return api_ok({"key": body.key, "value": value})


@router.post("/panel-ssl")
def panel_ssl(body: PanelSslBody, ctx=Depends(require_role("admin"))):
    from panelpro.core import certs as cert_util

    if not cert_util.verify_key_matches(body.cert, body.key):
        raise PanelError("Certificate and key do not match.", 400)
    out_dir = CFG.ssl_dir / "panel"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cert.pem").write_text(body.cert, encoding="utf-8")
    key_file = out_dir / "key.pem"
    key_file.write_text(body.key, encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    settings_store.set_setting("panel_ssl_cert", str(out_dir / "cert.pem"))
    settings_store.set_setting("panel_ssl_key", str(out_dir / "key.pem"))
    settings_store.set_setting("panel_ssl", True)
    return api_ok({"enabled": True,
                   "note": "Restart the panel service to apply HTTPS."})
