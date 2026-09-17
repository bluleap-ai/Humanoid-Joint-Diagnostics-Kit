#!/usr/bin/env python3
"""Generate unique local credentials. Never prints private keys or passwords."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import secrets
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def generate(directory, header):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(directory, 0o700)
    identity = secrets.token_hex(6)
    hostname = "can-" + identity + ".local"
    ca_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "CAN local CA " + identity)]
    )
    now = dt.datetime.now(dt.timezone.utc)

    def cert(subject, key, ca=False, client=False):
        # No trusted RTC on the device; see security.md for validity limitations.
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(
                x509.BasicConstraints(ca=ca, path_length=0 if ca else None), True
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                False,
            )
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, ca, ca, False, False),
                True,
            )
        )
        if not ca:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage(
                    [
                        ExtendedKeyUsageOID.CLIENT_AUTH
                        if client
                        else ExtendedKeyUsageOID.SERVER_AUTH
                    ]
                ),
                False,
            )
            if not client:
                builder = builder.add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(hostname)]), False
                )
        return builder.sign(ca_key, hashes.SHA256()).public_bytes(
            serialization.Encoding.PEM
        )

    def keybytes(key):
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    ca = cert(name, ca_key, True)
    server_key = ec.generate_private_key(ec.SECP256R1())
    client_key = ec.generate_private_key(ec.SECP256R1())
    server = cert(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]), server_key
    )
    client = cert(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "operator")]),
        client_key,
        client=True,
    )
    profile = {
        "identity": identity,
        "hostname": hostname,
        "ssid": "CAN-" + identity,
        "ap_password": secrets.token_urlsafe(18),
    }
    files = {
        "ca.pem": ca,
        "server.pem": server,
        "server.key": keybytes(server_key),
        "client.pem": client,
        "client.key": keybytes(client_key),
        "profile.json": json.dumps(profile, indent=2).encode(),
    }
    for filename, data in files.items():
        p = directory / filename
        p.write_bytes(data)
        p.chmod(0o600)
    # Do not retain the CA signing key. Rotation is a new provisioning operation.
    header = Path(header)
    header.parent.mkdir(parents=True, exist_ok=True)
    text = "/* Generated per device; do not commit. */\n"
    for label, value in [
        ("device_id", identity),
        ("device_hostname", hostname),
        ("ap_ssid", profile["ssid"]),
        ("ap_password", profile["ap_password"]),
        ("ca_pem", ca.decode()),
        ("server_pem", server.decode()),
        ("server_key_pem", keybytes(server_key).decode()),
    ]:
        text += f"static const char {label}[] = {json.dumps(value)};\n"
    header.write_text(text)
    header.chmod(0o600)
    return identity


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default=".secrets/device")
    p.add_argument("--header", default="firmware/credentials/device_credentials.h")
    a = p.parse_args()
    identity = generate(a.output, a.header)
    print(
        f"Created credentials for {identity}. Read profile.json locally for the hotspot password; keep this directory private."
    )
