"""Local-only encryption for API keys stored in settings.json.

The encryption key lives in its own file next to settings.json, generated
once on first run. This keeps a plugged-in API key from showing up as plain
text if someone browses %APPDATA%, opens the file in an editor, or it ends
up in a folder backup/sync -- without ever sending the key anywhere, which
matches the existing promise in application/ai_summary.py that keys never
leave this machine except straight to the provider the user picked.

This is not protection against an attacker with full access to this
machine (they can read the keyfile too) -- it is protection against the
much more common case of casual/incidental exposure of the settings file
alone.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_KEY_FILE_NAME = ".secret.key"


class SecretStore:
    def __init__(self, app_data_dir: Path) -> None:
        key_path = app_data_dir / _KEY_FILE_NAME
        if key_path.exists():
            key = key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
        self._fernet = Fernet(key)

    def encrypt(self, plain: str | None) -> str | None:
        if not plain:
            return None
        return self._fernet.encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt_strict(self, token: str | None) -> str | None:
        """Like decrypt(), but returns None for anything that isn't a valid
        token under this key -- for data that must never be read back as
        plaintext (see core.user_identity)."""
        if not token:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return None

    def decrypt(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            # Not a Fernet token -- either a plaintext key saved by a
            # pre-encryption version of this app, or unrelated corruption.
            # Treat it as already-plaintext so upgrading never silently
            # wipes out a key the user already configured; it gets
            # encrypted for real on the next save().
            return token
