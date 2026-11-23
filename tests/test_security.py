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


# --- Tahap 0 hardening regression tests -----------------------------------

def test_charset_whitelist_rejects_injection():
    from panelpro.core.errors import PanelError
    from panelpro.services.dbmgr import MYSQL_CHARSETS, PG_CHARSETS, validate_charset

    assert validate_charset("utf8mb4", MYSQL_CHARSETS) == "utf8mb4"
    assert validate_charset("UTF8", PG_CHARSETS) == "UTF8"
    for evil in ("utf8mb4; DROP DATABASE mysql; --", "UTF8'); DROP x; --", ""):
        try:
            validate_charset(evil, MYSQL_CHARSETS)
        except PanelError as exc:
            assert exc.status == 400
        else:
            raise AssertionError(f"charset '{evil}' should be rejected")


def test_cron_command_quoting_and_newline_guard():
    import shlex

    from panelpro.core.errors import PanelError
    from panelpro.services import cronsvc

    payload = "http://x.test/cron'; rm -rf / #"
    url_cmd = cronsvc.build_command("url", payload)
    tokens = shlex.split(url_cmd)
    # payload must end up as ONE inert curl argument, not shell syntax
    assert tokens[0] == "curl"
    assert payload in tokens

    script_payload = "/opt/x.sh'; reboot"
    script_cmd = cronsvc.build_command("script", script_payload)
    assert shlex.split(script_cmd)[0] == "bash"
    assert script_payload in shlex.split(script_cmd)

    for evil in ("echo hi\n* * * * * evil", "echo hi\r\nx", ""):
        try:
            cronsvc.build_command("shell", evil)
        except PanelError as exc:
            assert exc.status == 400
        else:
            raise AssertionError("newline/empty command should be rejected")

    try:
        cronsvc.validate_schedule("* * * * * evil\ncurl evil")
    except PanelError:
        pass
    else:
        raise AssertionError("multiline schedule should be rejected")


def test_selfsigned_domain_validation():
    import panelpro.services.sslmgr as sslmgr
    from panelpro.core.errors import PanelError

    assert sslmgr.validate_cert_domain("Example.COM.") == "example.com"
    assert sslmgr.validate_cert_domain("*.example.com") == "*.example.com"
    for evil in ("../../etc", "a/b", "..", "", "x" * 300, "..\\windows"):
        try:
            sslmgr.validate_cert_domain(evil)
        except PanelError as exc:
            assert exc.status == 400
        else:
            raise AssertionError(f"domain '{evil}' should be rejected")


def test_generate_selfsigned_works():
    from panelpro.core.certs import generate_selfsigned, parse_cert_pem

    cert_pem, key_pem = generate_selfsigned("audit.local", days=30)
    info = parse_cert_pem(cert_pem)
    assert info["subject"] == "audit.local"
    assert info["days_left"] >= 28
    from panelpro.core.certs import verify_key_matches

    assert verify_key_matches(cert_pem, key_pem)
