"""WAF endpoints: per-site nginx rules (CC limit, IP/UA blocklists)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.api.sites import _render_site
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import Site, WafProfile
from panelpro.services import waf as waf_svc
from panelpro.services import webservers

router = APIRouter(prefix="/api/waf", tags=["waf"])


class WafBody(BaseModel):
    site_id: int
    enabled: bool = True
    cc_rpm: int = 300
    blocked_ips: list[str] = []
    blocked_uas: list[str] = []


def _apply_profile(db: Session, site: Site, row: WafProfile | None) -> dict:
    if site.server != "nginx":
        raise PanelError("The basic WAF supports nginx sites only.", 400)
    adapter = webservers.detect_webserver("nginx")
    zone, include = waf_svc.zone_conf_path(site.name), waf_svc.site_conf_path(site.name)
    with webservers.config_transaction(adapter, [zone, include, *adapter.config_paths(site.name)]) as apply:
        db.flush()
        result = waf_svc.write_profile(row, site.name, zone, include)
        _render_site(site, db, adapter)
        apply()
        db.commit()
    return result


@router.get("")
def list_profiles(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(WafProfile).all()
    return api_ok({"profiles": [waf_svc.profile_payload(r) for r in rows]})


@router.get("/{site_id}")
def get_profile(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    row = db.query(WafProfile).filter(WafProfile.site_id == site_id).first()
    return api_ok({"profile": waf_svc.profile_payload(row) if row else None})


@router.post("")
@webservers.serialized
def upsert_profile(body: WafBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == body.site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    data = waf_svc.validate_profile_data(body.enabled, body.cc_rpm, body.blocked_ips, body.blocked_uas)
    row = db.query(WafProfile).filter(WafProfile.site_id == body.site_id).first()
    if row is None:
        row = WafProfile(site_id=body.site_id)
        db.add(row)
    row.enabled = data["enabled"]
    row.cc_rpm = data["cc_rpm"]
    row.blocked_ips = data["blocked_ips"]
    row.blocked_uas = data["blocked_uas"]
    row.updated_at = datetime.utcnow()
    result = _apply_profile(db, site, row)
    return api_ok({"profile": waf_svc.profile_payload(row), **result})


@router.post("/{site_id}/delete")
@webservers.serialized
def delete_profile(site_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    row = db.query(WafProfile).filter(WafProfile.site_id == site_id).first()
    if row:
        db.delete(row)
        _apply_profile(db, site, None)
    return api_ok({"deleted": site.name})
