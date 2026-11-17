"""Self-signed certificate for serving the call page over HTTPS on the LAN.

Phones only grant microphone access on a secure origin, so ``--tls`` is what
makes ``https://<your-ip>:8443`` usable from another device. The certificate is
generated once, stored in ``certs/`` and reused; browsers will warn about it once
until you accept it.
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import socket
from pathlib import Path

CERT_DIR = Path(__file__).resolve().parent.parent / "certs"


def _lan_ips() -> list[str]:
    """Best-effort list of this machine's non-loopback IPv4 addresses."""
    found: set[str] = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        found.add(probe.getsockname()[0])
        probe.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except Exception:
        pass
    return sorted(ip for ip in found if not ip.startswith("127."))


def ensure_certificate(directory: Path | None = None, days: int = 825) -> tuple[Path, Path]:
    """Return ``(cert_path, key_path)``, creating a self-signed pair if needed."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    folder = Path(directory or CERT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    cert_path = folder / "indicvoice-cert.pem"
    key_path = folder / "indicvoice-key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IndicVoice local")])
    sans: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for ip in _lan_ips():
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue

    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=5))
        .not_valid_after(now + _dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
