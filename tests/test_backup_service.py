# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from smartdoc.application.backup_service import BackupError, BackupService, snapshot
from smartdoc.core.app_context import AppContext
from smartdoc.core.config import ConfigManager
from smartdoc.infrastructure import schema_migrations as sm
from smartdoc.infrastructure.database import DatabaseManager


def _library(tmp_path: Path, books: int = 3) -> DatabaseManager:
    db = DatabaseManager(str(tmp_path / "library.db"))
    db.initialize_tables()
    for n in range(books):
        db.add_or_update_document(f"d{n}", {"title": f"Sách số {n}", "author": "Tác giả", "file_path": f"{n}.pdf", "extension": "pdf", "created_at": float(n)})
    return db


def _next_migration(db_version_sql: str = "ALTER TABLE documents ADD COLUMN note TEXT") -> tuple[sm.Migration, ...]:
    """The shipped migrations plus one more, so a library created by the current code has something pending."""
    shipped = sm.MIGRATIONS
    return shipped + (sm.Migration(len(shipped) + 1, "add note", lambda c: c.execute(db_version_sql)),)


def _titles(db: DatabaseManager) -> set[str]:
    return {r["title"] for r in db.connection.execute("SELECT title FROM documents")}


def test_a_backup_is_a_verified_copy_next_to_the_library(tmp_path):
    db = _library(tmp_path)
    info = BackupService(db).create_backup()

    assert info.path.parent == tmp_path / "backups" and info.path.suffix == ".db"
    assert info.reason == "manual" and info.schema_version == sm.latest_version() and info.size > 0
    copy = sqlite3.connect(info.path)
    assert copy.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    assert copy.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert not list((tmp_path / "backups").glob("*.part"))  # nothing half-written is left behind


def test_backups_are_listed_newest_first_and_pruned_to_the_retention(tmp_path):
    db = _library(tmp_path)
    service = BackupService(db, retention=2)
    made = []
    for _ in range(4):
        made.append(service.create_backup().path)
        time.sleep(0.02)

    listed = service.list_backups()
    assert [b.path for b in listed] == [made[3], made[2]]  # the two newest, newest first
    assert not made[0].exists() and not made[1].exists()


def test_retention_is_clamped_to_a_sane_range(tmp_path):
    db = _library(tmp_path)
    assert BackupService(db, retention=0).retention() == 1
    assert BackupService(db, retention=10_000).retention() == 50
    assert BackupService(db, retention=lambda: 7).retention() == 7


def test_an_in_memory_library_has_nothing_to_back_up():
    db = DatabaseManager(":memory:")
    db.initialize_tables()
    with pytest.raises(BackupError, match="bộ nhớ"):
        BackupService(db).create_backup()


def test_restore_puts_the_backed_up_books_back_and_keeps_the_state_it_replaced(tmp_path):
    db = _library(tmp_path)
    service = BackupService(db)
    backup = service.create_backup()
    db.add_or_update_document("d9", {"title": "Sách thêm sau", "file_path": "9.pdf", "extension": "pdf", "created_at": 9.0})
    db.connection.execute("DELETE FROM documents WHERE id = 'd0'")
    db.connection.commit()

    safety = service.restore(backup.path)

    assert _titles(db) == {"Sách số 0", "Sách số 1", "Sách số 2"}
    assert [d["title"] for d in db.query_documents(fts_query="số")]  # the full-text index came back with it
    assert safety.reason == "pre-restore"
    undo = sqlite3.connect(safety.path)
    assert {r[0] for r in undo.execute("SELECT title FROM documents")} == {"Sách số 1", "Sách số 2", "Sách thêm sau"}


def test_restore_refuses_a_broken_or_foreign_file_and_changes_nothing(tmp_path):
    db = _library(tmp_path)
    junk = tmp_path / "not-a-db.db"
    junk.write_bytes(b"this is not sqlite")
    with pytest.raises(BackupError):
        BackupService(db).restore(junk)
    with pytest.raises(BackupError, match="Không tìm thấy"):
        BackupService(db).restore(tmp_path / "missing.db")
    assert len(_titles(db)) == 3


def test_restore_refuses_a_backup_from_a_newer_release(tmp_path):
    db = _library(tmp_path)
    backup = BackupService(db).create_backup()
    con = sqlite3.connect(backup.path)
    con.execute("PRAGMA user_version = 99")
    con.commit()
    con.close()

    with pytest.raises(sm.SchemaTooNewError):
        BackupService(db).restore(backup.path)
    assert len(_titles(db)) == 3


def test_a_migration_of_an_existing_library_is_preceded_by_a_backup(tmp_path, monkeypatch):
    path = tmp_path / "library.db"
    _library(tmp_path)  # a library with data, at the current schema
    plan = _next_migration()
    monkeypatch.setattr(sm, "MIGRATIONS", plan)

    context = AppContext(config=ConfigManager(app_data_dir=tmp_path / "appdata"), db=DatabaseManager(str(path)))

    backups = context.backups.list_backups()
    old, new = plan[-1].version - 1, plan[-1].version
    assert len(backups) == 1 and backups[0].reason == f"pre-upgrade-v{old}-to-v{new}" and backups[0].schema_version == old
    assert context.db.schema_version() == new
    context.shutdown()


def test_a_migration_that_fails_midway_loses_nothing_and_leaves_the_backup(tmp_path, monkeypatch):
    path = tmp_path / "library.db"
    _library(tmp_path)

    def explode(connection):
        connection.execute("DELETE FROM documents")  # destructive, then...
        raise RuntimeError("boom")

    monkeypatch.setattr(sm, "MIGRATIONS", sm.MIGRATIONS + (sm.Migration(len(sm.MIGRATIONS) + 1, "explodes", explode),))
    before = sm.latest_version() - 1
    db = DatabaseManager(str(path))
    service = BackupService(db)
    with pytest.raises(sm.MigrationError):
        db.initialize_tables(before_migrate=service.before_migration)

    assert len(_titles(db)) == 3 and db.schema_version() == before  # rolled back
    assert len(service.list_backups()) == 1  # and the pre-upgrade backup is there for good measure


def test_no_backup_no_migration(tmp_path, monkeypatch):
    path = tmp_path / "library.db"
    _library(tmp_path)
    monkeypatch.setattr(sm, "MIGRATIONS", _next_migration())
    db = DatabaseManager(str(path))
    current = db.schema_version()
    (tmp_path / "backups").write_text("a file where the folder must go")  # the backup cannot be written

    with pytest.raises(BackupError):
        db.initialize_tables(before_migrate=BackupService(db).before_migration)

    assert db.schema_version() == current


def test_snapshot_reports_a_failure_in_plain_words(tmp_path):
    db = _library(tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("i am a file")
    with pytest.raises(BackupError):
        snapshot(db.connection, blocked / "x.db")


def test_a_backup_stays_a_single_file_even_after_it_is_opened_and_listed(tmp_path):
    db = _library(tmp_path)
    service = BackupService(db)
    service.create_backup()
    service.list_backups()  # opens each backup read-only to read its schema version
    assert sorted(p.suffix for p in (tmp_path / "backups").iterdir()) == [".db"]  # no -wal / -shm / .part beside it
