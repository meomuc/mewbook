# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the token for one of the two triage roles, on the project owner's own computer (S1e, E-07/E-08; spec section 5).

The triage agent does not use Supabase's `service_role` key: it uses a JWT whose `role` claim names `triage_reader` or
`triage_writer`, two Postgres roles that can see two filtered views and call one narrow function
(application/sql/003_error_reports.sql). Supabase's Data API accepts a JWT you sign yourself as `Authorization: Bearer <jwt>`,
provided it is signed with a key the project trusts and its `role` is an existing Postgres role (Supabase documentation,
"JWT Signing Keys", read 2026-09-20). Two ways, in the order Supabase recommends:

- **ES256 (or RS256) with an imported private key.** In the dashboard (Project Settings, JWT Signing Keys) import a private key
  you generated; sign here with that key and its `kid`. This is the current mechanism.
- **HS256 with the project's legacy JWT secret.** Still available while the legacy keys exist (Supabase is deprecating them by
  the end of 2026); the secret is read from an environment variable, never from the command line.

The token is printed on stdout and nowhere else: put it in the environment of the computer that runs the agent, never in the
repository, and never in the environment of the Claude Code process. Only the two triage roles can be minted here, so a slip
cannot produce a powerful token, and the lifetime is capped so a leaked one expires.

    python -m tools.triage.mint_token --role triage_reader --alg ES256 --key-file private.pem --kid <the kid> --days 90
    set SUPABASE_JWT_SECRET=...   &   python -m tools.triage.mint_token --role triage_writer --alg HS256 --days 90
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

ALLOWED_ROLES = ("triage_reader", "triage_writer")
MAX_DAYS = 400
ISSUER = "mewbook-triage"


class MintError(Exception):
    """The token cannot be made as asked."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def claims_for(role: str, days: int, *, now: float | None = None) -> dict[str, object]:
    if role not in ALLOWED_ROLES:
        raise MintError(f"only {', '.join(ALLOWED_ROLES)} can be minted here, not {role!r}")
    if not 1 <= days <= MAX_DAYS:
        raise MintError(f"the lifetime must be between 1 and {MAX_DAYS} days")
    issued = int(now if now is not None else time.time())
    return {"role": role, "iss": ISSUER, "iat": issued, "exp": issued + days * 86_400}


def mint_hs256(secret: bytes, claims: dict[str, object], *, kid: str | None = None) -> str:
    if len(secret) < 16:
        raise MintError("that secret is too short to be a JWT secret")
    header = {"alg": "HS256", "typ": "JWT", **({"kid": kid} if kid else {})}
    signing_input = f"{_b64(_json(header))}.{_b64(_json(claims))}"
    signature = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


def mint_es256(private_key_pem: bytes, claims: dict[str, object], *, kid: str) -> str:
    """ES256: an ECDSA P-256 signature, as the raw 64 bytes r||s that JWT specifies."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    if not kid:
        raise MintError("ES256 needs the kid of the signing key you imported")
    try:
        key = serialization.load_pem_private_key(private_key_pem, password=None)
    except (ValueError, TypeError) as exc:
        raise MintError("that is not an unencrypted PEM private key") from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise MintError("ES256 needs a P-256 (prime256v1) key")
    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    signing_input = f"{_b64(_json(header))}.{_b64(_json(claims))}".encode("ascii")
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    return f"{signing_input.decode('ascii')}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint a JWT for the triage_reader or triage_writer role.")
    parser.add_argument("--role", required=True, choices=ALLOWED_ROLES)
    parser.add_argument("--alg", required=True, choices=("ES256", "HS256"))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--key-file", help="PEM private key (ES256)")
    parser.add_argument("--kid", help="the key id shown in the dashboard (ES256; optional for HS256)")
    parser.add_argument("--secret-env", default="SUPABASE_JWT_SECRET", help="environment variable holding the HS256 secret")
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        claims = claims_for(args.role, args.days)
        if args.alg == "ES256":
            if not args.key_file:
                raise MintError("ES256 needs --key-file")
            token = mint_es256(Path(args.key_file).read_bytes(), claims, kid=args.kid or "")
        else:
            secret = env.get(args.secret_env, "")
            if not secret:
                raise MintError(f"set {args.secret_env} to the project's JWT secret")
            token = mint_hs256(secret.encode("utf-8"), claims, kid=args.kid)
    except (MintError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
