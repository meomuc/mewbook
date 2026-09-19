import hashlib

from smartdoc.core.secret_store import SecretStore
from smartdoc.core.user_identity import IDENTITY_FILE_NAME, UserIdentity


def test_first_run_creates_an_encrypted_identity(tmp_path):
    identity = UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path))

    stored = (tmp_path / IDENTITY_FILE_NAME).read_text(encoding="ascii")
    assert len(identity.token) >= 32
    assert identity.token not in stored  # encrypted at rest
    assert identity.user_hash == hashlib.sha256(identity.token.encode()).hexdigest()


def test_identity_is_stable_across_launches(tmp_path):
    first = UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path))
    second = UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path))

    assert first.token == second.token
    assert first.user_hash == second.user_hash


def test_reinstall_without_identity_file_gets_a_new_identity(tmp_path):
    first = UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path))
    (tmp_path / IDENTITY_FILE_NAME).unlink()  # what the uninstaller does

    second = UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path))

    assert second.token != first.token


def test_corrupted_identity_file_is_replaced(tmp_path):
    (tmp_path / IDENTITY_FILE_NAME).write_text("garbage", encoding="ascii")

    identity = UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path))

    assert len(identity.token) >= 32
    assert UserIdentity.load_or_create(tmp_path, SecretStore(tmp_path)).token == identity.token


def test_app_context_exposes_the_identity(app_context):
    assert app_context.identity.user_hash
    assert len(app_context.identity.short_id) == 8
