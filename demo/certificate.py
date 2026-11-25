"""A certificate made on this laptop, so that phones can open the site over https.

A phone browser lets a page use the microphone only on a secure (https)
connection. On a hotspot there is no real certificate to be had, so the laptop
makes its own. The phone shows a warning the first time; the person accepts it
once, and then recording works.

The files are written to demo/cert/ and are never committed.
"""

import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

VALID_DAYS = 30


def _names(addresses: list[str]):
    from cryptography import x509

    ips = ["127.0.0.1", *addresses]
    return [x509.DNSName("localhost"), *[x509.IPAddress(ipaddress.ip_address(ip)) for ip in dict.fromkeys(ips)]]


def make_certificate(folder: Path, addresses: list[str]) -> None:
    """Writes cert.pem and key.pem for localhost and the laptop's addresses on the hotspot."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    folder.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Rasd demo (this laptop)")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(_names(addresses)), critical=False)
        .sign(key, hashes.SHA256())
    )
    (folder / "cert.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (folder / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
        )
    )


def certificate_covers(folder: Path, addresses: list[str]) -> bool:
    """True when a certificate is already there, is still valid, and names all these addresses."""
    from cryptography import x509

    if not (folder / "cert.pem").exists() or not (folder / "key.pem").exists():
        return False
    certificate = x509.load_pem_x509_certificate((folder / "cert.pem").read_bytes())
    if certificate.not_valid_after_utc <= datetime.now(timezone.utc) + timedelta(hours=12):
        return False
    named = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    have = {str(ip) for ip in named.get_values_for_type(x509.IPAddress)}
    return set(addresses) <= have
