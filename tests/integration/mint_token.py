"""Development-only EdDSA JWT minting for integration tests.

Not part of the public datorium_client runtime API.
Matches DatoriumDB fixture __auth.json + signing key material
(claim ``datoriumdb.kind`` = ``client``, active key ``kid`` in JWT header).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def mint_client_token(
    *,
    private_key_pem: bytes,
    issuer: str,
    audience: str,
    kid: str,
    subject: str = "integration-test",
    ttl_seconds: int = 3600,
) -> str:
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("expected Ed25519 private key")
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + ttl_seconds,
        "datoriumdb.kind": "client",
    }
    return jwt.encode(payload, key, algorithm="EdDSA", headers={"kid": kid})


def mint_from_auth_fixture(
    auth_json_path: Path,
    private_key_path: Path,
    *,
    subject: str = "integration-test",
) -> str:
    auth_root = json.loads(auth_json_path.read_text())
    auth = auth_root.get("auth", auth_root)
    kid = ""
    for key in auth.get("keys", []):
        if key.get("status") == "active":
            kid = str(key.get("kid", ""))
            break
    if not kid:
        raise ValueError(f"no active key in {auth_json_path}")
    ttl = int(auth.get("tokenLifetimeSeconds", {}).get("client", 3600) or 3600)
    return mint_client_token(
        private_key_pem=private_key_path.read_bytes(),
        issuer=str(auth.get("issuer", "datoriumdb")),
        audience=str(auth.get("audience", "datoriumdb")),
        kid=kid,
        subject=subject,
        ttl_seconds=ttl,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint a DatoriumDB client JWT for tests")
    parser.add_argument("--auth", required=True, type=Path, help="path to __auth.json")
    parser.add_argument("--key", required=True, type=Path, help="path to Ed25519 PKCS8 PEM")
    parser.add_argument("--subject", default="todo-integration")
    args = parser.parse_args(argv)
    print(mint_from_auth_fixture(args.auth, args.key, subject=args.subject))
    return 0


if __name__ == "__main__":
    sys.exit(main())
