"""Unit tests for auth primitives (pure Python, run on any OS)."""

from panelpro.core import security


def test_password_hash_roundtrip():
    hashed = security.hash_password("S3cret-pass!")
    assert hashed != "S3cret-pass!"
    assert security.verify_password("S3cret-pass!", hashed)
    assert not security.verify_password("wrong", hashed)


def test_password_hash_unique_salts():
    a = security.hash_password("same-password")
    b = security.hash_password("same-password")
    assert a != b


def test_api_key_roundtrip():
    raw = security.generate_api_key()
    assert raw.startswith("ppk_")
    assert security.hash_api_key(raw) == security.hash_api_key(raw)
    assert security.hash_api_key(raw) != security.hash_api_key(raw + "x")


def test_totp_roundtrip():
    secret = security.new_totp_secret()
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert security.verify_totp(secret, code)
    assert not security.verify_totp(secret, "000000")  # may flake once a decade
    assert not security.verify_totp(None, code)


def test_totp_uri_contains_issuer():
    uri = security.totp_uri(security.new_totp_secret(), "admin")
    assert uri.startswith("otpauth://totp/")
    assert "PanelPro" in uri
