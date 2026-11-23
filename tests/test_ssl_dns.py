"""DNS-01 helper tests (pure parts, any OS)."""

import pytest

from panelpro.core.errors import PanelError
from panelpro.services import sslmgr


def test_dns_credentials_body_cloudflare():
    body = sslmgr._dns_credentials_body("cloudflare", {"api_token": "tok123"})
    assert body == "dns_cloudflare_api_token = tok123\n"


def test_dns_credentials_body_dnspod_two_keys():
    body = sslmgr._dns_credentials_body("dnspod", {"id": "12345", "token": "abc"})
    assert "dns_dnspod_id = 12345" in body
    assert "dns_dnspod_token = abc" in body


def test_dns_credentials_body_missing_field():
    with pytest.raises(PanelError) as exc:
        sslmgr._dns_credentials_body("cloudflare", {})
    assert exc.value.status == 400
    assert "api_token" in exc.value.message


def test_dns_credentials_body_unknown_provider():
    with pytest.raises(PanelError) as exc:
        sslmgr._dns_credentials_body("nope", {"x": "y"})
    assert exc.value.status == 400


def test_domain_validator_accepts_wildcard_and_casing():
    assert sslmgr.validate_cert_domain("*.Example.com") == "*.example.com"
    assert sslmgr.validate_cert_domain("sub.Example.com") == "sub.example.com"
