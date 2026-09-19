"""Anonymous, registration-free user identity for this installation.

On the first run a random secret token is generated and stored encrypted
(see core.secret_store.SecretStore) in its own file, `identity.dat`, next to
settings.json. It stays the same for as long as the app stays installed;
the Windows uninstaller deletes that one file (see packaging/MewBook.iss), so
uninstalling and reinstalling yields a brand-new identity -- which is the
intended behavior, not data loss: nothing else is keyed to it locally.

Two values come out of it:

- `token` -- the SECRET. Only ever sent over HTTPS to the review server's
  `submit_review` function, which uses it to prove "this is the same
  person who wrote that review / owns that nickname". Never stored
  server-side and never shown in the UI.
- `user_hash` -- sha256(token) in hex. PUBLIC: stored with each review and
  nickname so ownership can be checked (the server recomputes it from the
  token), and so this app can recognize its own reviews in a fetched list.
  Knowing it doesn't let anyone act as this user -- that needs the token.

No personal data is involved at any point: no account, e-mail, hardware
ID or IP-derived fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from pathlib import Path

from smartdoc.core.secret_store import SecretStore

logger = logging.getLogger(__name__)

IDENTITY_FILE_NAME = "identity.dat"
_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class UserIdentity:
    def __init__(self, token: str, created_at: float) -> None:
        self.token = token
        self.created_at = created_at
        self.user_hash = hash_token(token)

    @property
    def short_id(self) -> str:
        """A short, non-secret label (e.g. for About / diagnostics)."""
        return self.user_hash[:8].upper()

    @classmethod
    def load_or_create(cls, app_data_dir: Path, secrets_store: SecretStore) -> "UserIdentity":
        path = Path(app_data_dir) / IDENTITY_FILE_NAME
        if path.exists():
            identity = cls._load(path, secrets_store)
            if identity is not None:
                return identity
            logger.warning("identity.dat unreadable (key changed or file corrupted) -- generating a new identity")
        identity = cls(secrets.token_urlsafe(_TOKEN_BYTES), time.time())
        payload = json.dumps({"token": identity.token, "created_at": identity.created_at})
        path.write_text(secrets_store.encrypt(payload) or "", encoding="ascii")
        return identity

    @classmethod
    def _load(cls, path: Path, secrets_store: SecretStore) -> "UserIdentity | None":
        plain = secrets_store.decrypt_strict(path.read_text(encoding="ascii").strip())
        if not plain:
            return None
        try:
            data = json.loads(plain)
            token = data["token"]
        except (ValueError, KeyError, TypeError):
            return None
        if not isinstance(token, str) or len(token) < 32:
            return None
        return cls(token, float(data.get("created_at") or 0.0))
