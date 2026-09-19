# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from smartdoc.infrastructure import schema_migrations as sm
from smartdoc.infrastructure.database import DatabaseManager

_BASELINE = Path(__file__).parent / "data" / "schema_1_0_0.sql"


def _library_1_0_0(path: Path) -> None:
    """A library.db exactly as 1.0.0 leaves it: the frozen schema, user_version 0, a few books and a collection."""
    con = sqlite3.connect(path)
    con.executescript(_BASELINE.read_text(encoding="utf-8"))
    for n, (title, author, tags) in enumerate(
        [("Truyện Kiều", "Nguyễn Du", "thơ,cổ điển"), ("Dế Mèn phiêu lưu ký", "Tô Hoài", "thiếu nhi"), ("Python Cookbook", "Beazley", "lập trình")]
    ):
        con.execute(
            "INSERT INTO documents (id, title, author, file_path, extension, tags, content, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (f"d{n}", title, author, f"{n}.epub", "epub", tags, f"nội dung {title}", float(n)),
        )
    con.execute("INSERT INTO collections (id, name, rules_json, created_at) VALUES ('c1', 'Đọc dở', '[]', 1.0)")
    con.execute("INSERT INTO collection_documents VALUES ('c1', 'd0')")
    con.commit()
    assert con.execute("PRAGMA user_version").fetchone()[0] == 0
    con.close()


def _add_note_table(con):
    con.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, body TEXT)")


def _add_note_column(con):
    con.execute("ALTER TABLE documents ADD COLUMN note TEXT")


def _boom(con):
    con.execute("CREATE TABLE half_done (x)")  # runs, then...
    raise RuntimeError("disk on fire")


MIGRATIONS = (
    sm.Migration(1, "notes table", _add_note_table),
    sm.Migration(2, "documents.note", _add_note_column),
)


def test_a_1_0_0_library_upgrades_in_place_and_keeps_every_book(tmp_path):
    path = tmp_path / "library.db"
    _library_1_0_0(path)

    db = DatabaseManager(str(path))
    db.initialize_tables()

    titles = {r["title"] for r in db.connection.execute("SELECT title FROM documents")}
    assert titles == {"Truyện Kiều", "Dế Mèn phiêu lưu ký", "Python Cookbook"}
    assert [d["title"] for d in db.query_documents(fts_query="Kiều")] == ["Truyện Kiều"]  # full-text index still answers
    assert db.schema_version() == sm.latest_version()
    assert db.connection.execute("SELECT COUNT(*) FROM collection_documents").fetchone()[0] == 1


def test_a_fresh_database_and_an_upgraded_one_end_up_with_the_same_schema(tmp_path):
    old = tmp_path / "old.db"
    _library_1_0_0(old)
    upgraded = DatabaseManager(str(old))
    upgraded.initialize_tables()
    fresh = DatabaseManager(str(tmp_path / "fresh.db"))
    fresh.initialize_tables()

    def shape(db):
        rows = db.connection.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        columns = {r["name"] for r in db.connection.execute("PRAGMA table_info(documents)")}
        return sorted((r[0], r[1]) for r in rows), columns

    assert shape(upgraded) == shape(fresh)


def test_pending_migrations_run_once_in_order_and_set_the_version(tmp_path):
    con = sqlite3.connect(tmp_path / "a.db")
    con.execute("CREATE TABLE documents (id TEXT)")

    assert sm.migrate(con, MIGRATIONS) == [1, 2]
    assert sm.get_version(con) == 2
    assert {r[1] for r in con.execute("PRAGMA table_info(documents)")} == {"id", "note"}
    assert sm.migrate(con, MIGRATIONS) == []  # nothing left to do, nothing re-run


def test_a_failing_migration_rolls_back_only_itself(tmp_path):
    con = sqlite3.connect(tmp_path / "a.db")
    con.execute("CREATE TABLE documents (id TEXT)")
    con.execute("INSERT INTO documents VALUES ('keep me')")
    con.commit()
    plan = (MIGRATIONS[0], sm.Migration(2, "explodes", _boom))

    with pytest.raises(sm.MigrationError, match="schema 2"):
        sm.migrate(con, plan)

    assert sm.get_version(con) == 1  # migration 1 stayed, migration 2 left no trace
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "notes" in tables and "half_done" not in tables
    assert con.execute("SELECT id FROM documents").fetchall() == [("keep me",)]
    assert not con.in_transaction


def test_a_library_from_a_newer_release_is_refused_and_left_alone(tmp_path):
    path = tmp_path / "library.db"
    _library_1_0_0(path)
    con = sqlite3.connect(path)
    con.execute("PRAGMA user_version = 99")
    con.commit()
    con.close()

    db = DatabaseManager(str(path))
    with pytest.raises(sm.SchemaTooNewError) as caught:
        db.initialize_tables()

    assert caught.value.db_version == 99 and "mới hơn" in str(caught.value)
    assert db.schema_version() == 99
    assert db.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3  # untouched


def test_the_before_hook_runs_once_for_an_existing_library_but_not_for_a_new_one(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "MIGRATIONS", MIGRATIONS)
    calls: list[tuple[int, int]] = []

    existing = tmp_path / "old.db"
    _library_1_0_0(existing)
    DatabaseManager(str(existing)).initialize_tables(before_migrate=lambda a, b: calls.append((a, b)))
    assert calls == [(0, 2)]

    calls.clear()
    DatabaseManager(str(tmp_path / "new.db")).initialize_tables(before_migrate=lambda a, b: calls.append((a, b)))
    assert calls == []  # a brand-new library has nothing to back up


def test_a_failing_before_hook_stops_the_upgrade(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "MIGRATIONS", MIGRATIONS)
    path = tmp_path / "old.db"
    _library_1_0_0(path)

    def no_backup(_from, _to):
        raise OSError("disk full")

    db = DatabaseManager(str(path))
    with pytest.raises(OSError):
        db.initialize_tables(before_migrate=no_backup)

    assert db.schema_version() == 0  # no backup, no migration
    assert "notes" not in {r[0] for r in db.connection.execute("SELECT name FROM sqlite_master")}


def test_migrations_must_be_numbered_without_gaps(tmp_path):
    con = sqlite3.connect(tmp_path / "a.db")
    with pytest.raises(ValueError, match="without gaps"):
        sm.migrate(con, (sm.Migration(2, "skips one", lambda c: None),))


def test_the_shipped_migration_list_is_consistent():
    versions = [m.version for m in sm.MIGRATIONS]
    assert versions == list(range(1, len(versions) + 1))
