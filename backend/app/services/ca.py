"""Minimal internal Certificate Authority for Control Plane <-> Data Plane Agent mTLS.

Cf. docs/architecture/03-database-orchestrator-et-agent.md §"Sécurité de la
communication Control Plane ↔ Agent" and docs/architecture/04-securite-et-isolation.md.

This is a self-signed root suitable for a single-operator platform in development
and early production. It is deliberately simple (no intermediate CA, no CRL/OCSP):
revocation is handled at the application layer (deactivating a Node record makes its
certificate's identity unusable even though the cert itself remains cryptographically
valid until expiry — a real CRL is a Phase 6+/11 hardening item, tracked here rather
than silently skipped).
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.certs import get_cert_settings

_ONE_DAY = dt.timedelta(days=1)


@dataclass(frozen=True)
class IssuedCertificate:
    certificate_pem: str
    serial_number: str


def _certs_dir() -> Path:
    settings = get_cert_settings()
    path = Path(settings.certs_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generate_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_private(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(path, 0o600)


def ensure_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Loads the root CA from disk, generating it on first run."""
    settings = get_cert_settings()
    ca_key_path = _certs_dir() / "ca.key"
    ca_cert_path = _certs_dir() / "ca.crt"

    if ca_key_path.exists() and ca_cert_path.exists():
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        return ca_key, ca_cert

    ca_key = _generate_private_key()
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, settings.ca_common_name)]
    )
    now = dt.datetime.now(dt.UTC)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _ONE_DAY)
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    _write_private(ca_key_path, ca_key)
    ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    return ca_key, ca_cert


def ca_certificate_pem() -> str:
    _, ca_cert = ensure_ca()
    return ca_cert.public_bytes(serialization.Encoding.PEM).decode()


def ensure_control_plane_client_cert() -> tuple[Path, Path, Path]:
    """Generates (once) the Control Plane's own mTLS client identity, used when it
    calls into Data Plane Agents. Returns (key_path, cert_path, ca_cert_path)."""
    settings = get_cert_settings()
    key_path = _certs_dir() / "control-plane.key"
    cert_path = _certs_dir() / "control-plane.crt"
    ca_cert_path = _certs_dir() / "ca.crt"

    ca_key, ca_cert = ensure_ca()

    if key_path.exists() and cert_path.exists():
        return key_path, cert_path, ca_cert_path

    client_key = _generate_private_key()
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, settings.control_plane_common_name)]
    )
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _ONE_DAY)
        .not_valid_after(now + dt.timedelta(days=settings.cert_validity_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True
        )
        .sign(ca_key, hashes.SHA256())
    )

    _write_private(key_path, client_key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path, ca_cert_path


def sign_node_csr(csr_pem: str, common_name: str, ip_address: str | None) -> IssuedCertificate:
    """Signs a node's CSR. The CommonName is dictated by the Control Plane (the
    node's assigned hostname/id), never trusted from the CSR's own subject — a
    node cannot mint itself a different identity by crafting its CSR."""
    ca_key, ca_cert = ensure_ca()
    settings = get_cert_settings()

    csr = x509.load_pem_x509_csr(csr_pem.encode())
    if not csr.is_signature_valid:
        raise ValueError("CSR signature is invalid")

    san_entries: list[x509.GeneralName] = [x509.DNSName(common_name)]
    if ip_address:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_address)))
        except ValueError:
            pass

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _ONE_DAY)
        .not_valid_after(now + dt.timedelta(days=settings.cert_validity_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=True
        )
        .sign(ca_key, hashes.SHA256())
    )

    return IssuedCertificate(
        certificate_pem=cert.public_bytes(serialization.Encoding.PEM).decode(),
        serial_number=format(cert.serial_number, "x"),
    )
