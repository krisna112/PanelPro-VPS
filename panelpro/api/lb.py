"""Load balancing endpoints: nginx upstream pools."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import Site, Upstream
from panelpro.services import lb as lb_svc
from panelpro.services import webservers

router = APIRouter(prefix="/api/lb", tags=["lb"])


class UpstreamBody(BaseModel):
    name: str
    servers: list[dict]


def _check_in_use(db: Session, name: str) -> None:
    using = db.query(Site).filter_by(proxy_target=f"upstream:{name}").limit(5).all()
    if using:
        names = ", ".join(site.name for site in using)
        raise PanelError(f"Upstream is still used by site(s): {names}.", 409)


@router.get("")
def list_upstreams(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(Upstream).order_by(Upstream.name.asc()).all()
    return api_ok({"upstreams": [lb_svc.payload(r) for r in rows]})


@router.post("")
@webservers.serialized
def create_upstream(body: UpstreamBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    name = lb_svc.validate_name(body.name)
    servers = lb_svc.validate_servers(body.servers)
    if db.query(Upstream).filter(Upstream.name == name).first():
        raise PanelError(f"Upstream '{name}' already exists.", 400)
    row = Upstream(name=name, servers=servers)
    adapter = webservers.detect_webserver("nginx")
    path = lb_svc.conf_path(name)
    if path.exists() or path.is_symlink():
        raise PanelError(f"Configuration for '{name}' already exists.", 409)
    with webservers.config_transaction(adapter, [path]) as apply:
        db.add(row)
        result = lb_svc.write_upstream(row, path, adapter)
        apply()
        db.commit()
    return api_ok({"upstream": lb_svc.payload(row), **result})


@router.post("/{upstream_id}/update")
@webservers.serialized
def update_upstream(upstream_id: int, body: UpstreamBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(Upstream).filter(Upstream.id == upstream_id).first()
    if not row:
        raise PanelError("Upstream not found.", 404)
    name = lb_svc.validate_name(body.name)
    if name != row.name and db.query(Upstream).filter(Upstream.name == name).first():
        raise PanelError(f"Upstream '{name}' already exists.", 400)
    servers = lb_svc.validate_servers(body.servers)
    adapter = webservers.detect_webserver("nginx")
    old_path, path = lb_svc.conf_path(row.name), lb_svc.conf_path(name)
    if name != row.name:
        _check_in_use(db, row.name)
        if path.exists() or path.is_symlink():
            raise PanelError(f"Configuration for '{name}' already exists.", 409)
    with webservers.config_transaction(adapter, [old_path, path]) as apply:
        if path != old_path:
            old_path.unlink(missing_ok=True)
        row.name = name
        row.servers = servers
        result = lb_svc.write_upstream(row, path, adapter)
        apply()
        db.commit()
    return api_ok({"upstream": lb_svc.payload(row), **result})


@router.post("/{upstream_id}/delete")
@webservers.serialized
def delete_upstream(upstream_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(Upstream).filter(Upstream.id == upstream_id).first()
    if not row:
        raise PanelError("Upstream not found.", 404)
    _check_in_use(db, row.name)
    adapter = webservers.detect_webserver("nginx")
    path = lb_svc.conf_path(row.name)
    with webservers.config_transaction(adapter, [path]) as apply:
        path.unlink(missing_ok=True)
        db.delete(row)
        apply()
        db.commit()
    return api_ok({"deleted": row.name})
