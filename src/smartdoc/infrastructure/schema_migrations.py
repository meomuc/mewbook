# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schema versioning for `library.db` (S1-02, docs/handoff/02_ARCHITECTURE.md section 3).

`PRAGMA user_version` holds the schema version. A `library.db` written by 1.0.0 has never set it, so it reads
0 and *is* the baseline: everything that existed then is created by `_SCHEMA` and topped up by
`DatabaseManager._migrate_add_missing_columns`, which keeps its append-only rule. From now on a new table or
column is a `Migration` in `MIGRATIONS` below:

- numbered 1, 2, 3... with no gaps; never edit or renumber one that has been released;
- run once, in order, each in **its own transaction** together with the `user_version` bump, so a migration
  that fails leaves the database exactly as the previous one left it (and the version says so);
- run only after `before` (S1-03: the automatic backup) has been called, and only for a database that
  already held data;
- must be safe on a database that already has the change (a fresh database gets the baseline tables and then
  every migration, so its shape equals an upgraded one).

A database whose `user_version` is *newer* than this build knows (opened by a later release, then this older
one) is refused with `SchemaTooNewError` instead of being half-understood and corrupted.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SchemaError(Exception):
    """Base class for schema/migration problems."""


class SchemaTooNewError(SchemaError):
    def __init__(self, db_version: int, app_version: int) -> None:
        super().__init__(
            f"Thư viện này được tạo bởi một phiên bản MewBook mới hơn (schema {db_version}, bản này chỉ hiểu tới "
            f"{app_version}). Hãy cài bản MewBook mới nhất; dữ liệu của bạn chưa bị thay đổi."
        )
        self.db_version = db_version
        self.app_version = app_version


class MigrationError(SchemaError):
    def __init__(self, migration: "Migration", cause: Exception) -> None:
        super().__init__(
            f"Không nâng cấp được thư viện lên schema {migration.version} ({migration.description}): {cause}. "
            "Dữ liệu vẫn nguyên như trước lần nâng cấp này."
        )
        self.migration = migration


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    apply: Callable[[sqlite3.Connection], None]
    """Runs inside a transaction opened by `migrate`; must not commit or roll back itself."""


def _add_file_status_columns(connection: sqlite3.Connection) -> None:
    """Missing-file detection (S1-04): whether the book's file was found the last time it was checked."""
    existing = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    if "file_status" not in existing:
        connection.execute("ALTER TABLE documents ADD COLUMN file_status TEXT")  # NULL = never checked, 'present', 'missing'
    if "file_checked_at" not in existing:
        connection.execute("ALTER TABLE documents ADD COLUMN file_checked_at REAL")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_file_status ON documents(file_status)")


# 1.0.0 is the baseline (version 0). The device tables (S3) will be the next entries.
MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "documents.file_status / file_checked_at (missing-file detection)", _add_file_status_columns),
)


def _resolve(migrations: Sequence[Migration] | None) -> Sequence[Migration]:
    """The list is looked up at call time (not bound as a default) so tests can swap it."""
    return MIGRATIONS if migrations is None else migrations


def latest_version(migrations: Sequence[Migration] | None = None) -> int:
    migrations = _resolve(migrations)
    return migrations[-1].version if migrations else 0


def get_version(connection: sqlite3.Connection) -> int:
    cursor = connection.execute("PRAGMA user_version")
    try:
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()


def check_not_newer(connection: sqlite3.Connection, migrations: Sequence[Migration] | None = None) -> None:
    """Raise SchemaTooNewError if the database is newer than this build. Call before touching the schema."""
    found, known = get_version(connection), latest_version(migrations)
    if found > known:
        raise SchemaTooNewError(found, known)


def _validate(migrations: Sequence[Migration]) -> None:
    for expected, migration in enumerate(migrations, start=1):
        if migration.version != expected:
            raise ValueError(f"migrations must be numbered 1, 2, 3... without gaps; got {migration.version} at position {expected}")


def pending(connection: sqlite3.Connection, migrations: Sequence[Migration] | None = None) -> list[Migration]:
    current = get_version(connection)
    return [m for m in _resolve(migrations) if m.version > current]


def migrate(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration] | None = None,
    *,
    before: Callable[[int, int], None] | None = None,
) -> list[int]:
    """Bring the database to the latest version; returns the versions that were applied.

    `before(from_version, to_version)` is called once, before the first pending migration, and may raise to
    stop the upgrade (S1-03 uses it to take a backup; no backup, no migration)."""
    migrations = _resolve(migrations)
    _validate(migrations)
    current = get_version(connection)  # read once: it is also what the too-new check and `pending` need
    if current > latest_version(migrations):
        raise SchemaTooNewError(current, latest_version(migrations))
    todo = [m for m in migrations if m.version > current]
    if not todo:
        return []
    target = todo[-1].version
    if before is not None:
        before(current, target)
    if connection.in_transaction:
        connection.commit()
    applied: list[int] = []
    for migration in todo:
        logger.info("Schema %d -> %d: %s", migration.version - 1, migration.version, migration.description)
        connection.execute("BEGIN IMMEDIATE")
        try:
            migration.apply(connection)
            connection.execute(f"PRAGMA user_version = {int(migration.version)}")
            connection.execute("COMMIT")
        except Exception as exc:  # noqa: BLE001 -- any failure must roll the whole step back before it propagates
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            logger.exception("Migration %d failed and was rolled back", migration.version)
            raise MigrationError(migration, exc) from exc
        applied.append(migration.version)
    return applied
