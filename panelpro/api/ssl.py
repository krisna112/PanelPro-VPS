"""SSL certificate endpoints: Let's Encrypt, self-signed, custom, deploy."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.core import certs as cert_util
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import Site, SslCert
from panelpro.services import sslmgr, webservers

router = APIRouter(prefix="/api/ssl", tags=["ssl"])


class LetsEncryptBody(BaseModel):
    domain: str
    aliases: list[str] = []
    webroot: str
    email: str = ""
    site_id: int | None = None
    auto_renew: bool = True


class SelfSignedBody(BaseModel):
    domain: str
    aliases: list[str] = []
    days: int = 3650
    site_id: int | None = None


class CustomCertBody(BaseModel):
    name: str
    cert: str
    key: str
    site_id: int | None = None


class DeployBody(BaseModel):
    site_id: int


def _cert_payload(row: SslCert) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "domain": row.domain,
        "issuer": row.issuer,
        "not_before": row.not_before.isoformat() if row.not_before else None,
        "not_after": row.not_after.isoformat() if row.not_after else None,
        "days_left": (row.not_after - datetime.utcnow()).days if row.not_after else None,
        "source": row.source,
        "auto_renew": row.auto_renew,
        "cert_path": row.cert_path,
    }


@router.get("")
def list_certs(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(SslCert).order_by(SslCert.created_at.desc()).all()
    return api_ok(
        {"certs": [_cert_payload(r) for r in rows],
         "certbot_available": sslmgr.certbot_available()}
    )


@router.post("/letsencrypt")
def letsencrypt(body: LetsEncryptBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    domain = webservers.validate_domain(body.domain)
    result = sslmgr.issue_letsencrypt(domain, body.aliases, body.webroot, body.email)
    info = result["info"]
    row = SslCert(
        name=f"LE-{domain}",
        domain=domain,
        issuer=info["issuer"] or "Let's Encrypt",
        not_before=datetime.fromisoformat(info["not_before"]),
        not_after=datetime.fromisoformat(info["not_after"]),
        cert_path=result["cert_path"],
        key_path=result["key_path"],
        source="letsencrypt",
        auto_renew=body.auto_renew,
    )
    db.add(row)
    db.commit()
    deployed = None
    if body.site_id:
        site = db.query(Site).filter(Site.id == body.site_id).first()
        if site:
            site.ssl_cert_id = row.id
            db.commit()
            from panelpro.api.sites import _render_site

            _render_site(site, db)
            webservers.detect_webserver(site.server).reload()
            deployed = site.name
    return api_ok({"cert": _cert_payload(row), "deployed": deployed})


@router.post("/selfsigned")
def selfsigned(body: SelfSignedBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    result = sslmgr.issue_selfsigned(body.domain, body.aliases, body.days)
    info = result["info"]
    row = SslCert(
        name=f"self-{body.domain}",
        domain=body.domain,
        issuer=info["issuer"],
        not_before=datetime.fromisoformat(info["not_before"]),
        not_after=datetime.fromisoformat(info["not_after"]),
        cert_path=result["cert_path"],
        key_path=result["key_path"],
        source="selfsigned",
    )
    db.add(row)
    db.commit()
    return api_ok({"cert": _cert_payload(row)})


@router.post("/custom")
def custom(body: CustomCertBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    result = sslmgr.import_custom(body.name, body.cert, body.key)
    info = result["info"]
    row = SslCert(
        name=body.name,
        domain=info["subject"],
        issuer=info["issuer"],
        not_before=datetime.fromisoformat(info["not_before"]),
        not_after=datetime.fromisoformat(info["not_after"]),
        cert_path=result["cert_path"],
        key_path=result["key_path"],
        source="custom",
    )
    db.add(row)
    db.commit()
    return api_ok({"cert": _cert_payload(row)})


@router.post("/{cert_id}/deploy")
def deploy(cert_id: int, body: DeployBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    cert = db.query(SslCert).filter(SslCert.id == cert_id).first()
    if not cert:
        raise PanelError("Certificate not found.", 404)
    site = db.query(Site).filter(Site.id == body.site_id).first()
    if not site:
        raise PanelError("Site not found.", 404)
    site.ssl_cert_id = cert.id
    db.commit()
    from panelpro.api.sites import _render_site

    _render_site(site, db)
    webservers.detect_webserver(site.server).reload()
    return api_ok({"deployed_to": site.name})


@router.post("/{cert_id}/delete")
def delete_cert(cert_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(SslCert).filter(SslCert.id == cert_id).first()
    if not row:
        raise PanelError("Certificate not found.", 404)
    # detach from any site using it
    for site in db.query(Site).filter(Site.ssl_cert_id == cert_id).all():
        site.ssl_cert_id = None
        db.commit()
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.name})


@router.post("/renew")
def renew(ctx=Depends(require_role("operator"))):
    return api_ok(sslmgr.renew_all())


@router.post("/{cert_id}/verify")
def verify(cert_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    row = db.query(SslCert).filter(SslCert.id == cert_id).first()
    if not row:
        raise PanelError("Certificate not found.", 404)
    return api_ok(cert_util.parse_cert_file(row.cert_path))
