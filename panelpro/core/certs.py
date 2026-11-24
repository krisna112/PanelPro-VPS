"""Certificate helpers: self-signed generation and PEM parsing."""

from __future__ import annotations

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from panelpro.core.errors import PanelError


def generate_selfsigned(domain: str, days: int = 3650, extra_domains: list[str] | None = None):
    """Return (cert_pem, key_pem) for a self-signed certificate."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    names = [x509.DNSName(domain)]
    for d in extra_domains or []:
        if d and d != domain:
            names.append(x509.DNSName(d))

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, domain),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PanelPro"),
        ]
    )
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


def parse_cert_pem(pem_text: str) -> dict:
    try:
        cert = x509.load_pem_x509_certificate(pem_text.encode())
    except ValueError as exc:
        raise PanelError("Not a valid PEM certificate.", 400) from exc

    def _cn(name: x509.Name) -> str:
        attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME)
        return attrs[0].value if attrs else ""

    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = list(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        dns_names = []

    not_after = cert.not_valid_after_utc.replace(tzinfo=None)
    not_before = cert.not_valid_before_utc.replace(tzinfo=None)
    days_left = (not_after - datetime.datetime.utcnow()).days
    return {
        "subject": _cn(cert.subject),
        "issuer": _cn(cert.issuer),
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_left": days_left,
        "dns_names": dns_names,
        "serial": format(cert.serial_number, "x"),
    }


def parse_cert_file(path: str) -> dict:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_cert_pem(fh.read())


def verify_key_matches(cert_pem: str, key_pem: str) -> bool:
    """True when the private key corresponds to the certificate."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        cert_pub = cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        key_pub = key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return cert_pub == key_pub
    except Exception:
        return False
