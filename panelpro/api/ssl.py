"""SSL certificate endpoints: Let's Encrypt, self-signed, custom, deploy."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_auth, require_role
from panelpro.api.sites import _attach_certificate, _get_site
from panelpro.core import certs as cert_util
from panelpro.core import keyvault
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import DnsAccount, Site, SslCert
from panelpro.services import sslmgr, webservers

router = APIRouter(prefix="/api/ssl", tags=["ssl"])


class LetsEncryptBody(BaseModel):
    domain: str
    aliases: list[str] = []
    webroot: str = ""
    email: str = ""
    site_id: int | None = None
    auto_renew: bool = True
    dns_account_id: int | None = None  # set => DNS-01 (wildcard) challenge


class DnsAccountBody(BaseModel):
    name: str
    provider: str
    config: dict = {}


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


@router.get("/dns-accounts")
def list_dns_accounts(db: Session = Depends(get_db), ctx=Depends(require_auth)):
    rows = db.query(DnsAccount).order_by(DnsAccount.created_at.desc()).all()
    return api_ok({
        "accounts": [
            {"id": r.id, "name": r.name, "provider": r.provider,
             "config": {"***": "***"},  # never returned in plaintext
             "created_at": r.created_at.isoformat()}
            for r in rows
        ],
        "providers": sslmgr.dns_provider_list(),
    })


@router.post("/dns-accounts")
def create_dns_account(body: DnsAccountBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    import json as _json

    if body.provider not in sslmgr.dns_provider_list():
        raise PanelError(
            f"Unsupported DNS provider '{body.provider}'. "
            f"Available: {', '.join(sslmgr.dns_provider_list())}.",
            400,
        )
    # validate required fields early (also gives a clear error before encrypting)
    sslmgr._dns_credentials_body(body.provider, body.config)
    row = DnsAccount(
        name=body.name[:100],
        provider=body.provider,
        config_enc=keyvault.encrypt_str(_json.dumps(body.config)),
    )
    db.add(row)
    db.commit()
    return api_ok({"id": row.id, "name": row.name, "provider": row.provider})


@router.post("/dns-accounts/{account_id}/delete")
def delete_dns_account(account_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(DnsAccount).filter(DnsAccount.id == account_id).first()
    if not row:
        raise PanelError("DNS account not found.", 404)
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.name})


@router.post("/letsencrypt")
def letsencrypt(body: LetsEncryptBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    import json as _json

    domain = sslmgr.validate_cert_domain(body.domain)
    aliases = [sslmgr.validate_cert_domain(alias) for alias in body.aliases if alias.strip()]
    site = _get_site(db, body.site_id) if body.site_id is not None else None
    if body.dns_account_id:
        account = db.query(DnsAccount).filter(DnsAccount.id == body.dns_account_id).first()
        if not account:
            raise PanelError("DNS account not found.", 404)
        config = _json.loads(keyvault.decrypt_str(account.config_enc))
        result = sslmgr.issue_letsencrypt_dns(
            domain, aliases, account.provider, config, body.email
        )
        source = "letsencrypt-dns"
    else:
        webroot = site.root if site else body.webroot
        if not webroot:
            raise PanelError("webroot is required for the HTTP-01 challenge.", 400)
        if site and (not site.enabled or any(d not in [site.name, *(site.aliases or [])]
                                             for d in [domain, *aliases])):
            raise PanelError("HTTP-01 requires an enabled website that serves all requested domains.", 400)
        result = sslmgr.issue_letsencrypt(domain, aliases, webroot, body.email)
        source = "letsencrypt"
    info = result["info"]
    with webservers.CONFIG_LOCK:
        row = db.query(SslCert).filter_by(cert_path=result["cert_path"]).first()
        if row is None:
            row = SslCert(name=f"LE-{domain}", domain=domain, cert_path=result["cert_path"])
            db.add(row)
        row.issuer = info["issuer"] or "Let's Encrypt"
        row.not_before = datetime.fromisoformat(info["not_before"])
        row.not_after = datetime.fromisoformat(info["not_after"])
        row.key_path = result["key_path"]
        row.source = source
        row.auto_renew = body.auto_renew
        db.commit()
        deployed = None
        warning = None
        if body.site_id is not None:
            try:
                deployed = _attach_certificate(db, body.site_id, row).name
            except PanelError as exc:
                warning = f"Certificate saved. Website deployment failed: {exc.message}"
        return api_ok({"cert": _cert_payload(row), "deployed": deployed, "warning": warning})


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
@webservers.serialized
def deploy(cert_id: int, body: DeployBody, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    cert = db.query(SslCert).filter(SslCert.id == cert_id).first()
    if not cert:
        raise PanelError("Certificate not found.", 404)
    site = _attach_certificate(db, body.site_id, cert)
    return api_ok({"deployed_to": site.name})


@router.post("/{cert_id}/delete")
@webservers.serialized
def delete_cert(cert_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("operator"))):
    row = db.query(SslCert).filter(SslCert.id == cert_id).first()
    if not row:
        raise PanelError("Certificate not found.", 404)
    if db.query(Site).filter_by(ssl_cert_id=cert_id).first():
        raise PanelError("Remove or replace this certificate on its websites before deleting it.", 409)
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.name})


@router.post("/renew")
def renew(ctx=Depends(require_role("operator"))):
    result = sslmgr.renew_all()
    if not result["ok"]:
        raise PanelError(f"Certificate renewal failed: {result['output']}", 502)
    return api_ok(result)


@router.post("/{cert_id}/verify")
def verify(cert_id: int, db: Session = Depends(get_db), ctx=Depends(require_auth)):
    row = db.query(SslCert).filter(SslCert.id == cert_id).first()
    if not row:
        raise PanelError("Certificate not found.", 404)
    return api_ok(cert_util.parse_cert_file(row.cert_path))
