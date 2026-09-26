# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading history (migration 2, `reading_progress`): a 1.0.0 library upgrades in place without losing anything, and the
"Trang đầu" queries -- what was read last, where, and the author of the month -- answer from it."""
from __future__ import annotations

import sqlite3

import pytest

from smartdoc.infrastructure import schema_migrations as sm
from smartdoc.infrastructure.database import DatabaseManager
from tests.test_schema_migrations import _library_1_0_0

DAY = 86400.0
NOW = 1_800_000_000.0


def _doc(db: DatabaseManager, doc_id: str, author: str = "Tô Hoài", created: float = NOW - 100 * DAY, cover: str | None = None):
    db.add_or_update_document(doc_id, {"title": doc_id, "author": author, "file_path": f"{doc_id}.pdf", "extension": "pdf",
                                       "file_size": 1, "created_at": created, "cover_path": cover})


@pytest.fixture
def db(app_context):
    return app_context.db


def test_a_1_0_0_library_upgrades_in_place_and_keeps_every_book(tmp_path):
    path = tmp_path / "old.db"
    _library_1_0_0(path)
    upgraded = DatabaseManager(str(path))
    upgraded.initialize_tables()
    assert upgraded.schema_version() == len(sm.MIGRATIONS) >= 2
    assert upgraded.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    assert upgraded.connection.execute("SELECT COUNT(*) FROM reading_progress").fetchone()[0] == 0
    assert upgraded.recent_reading() == []  # nothing opened yet, and no error


def test_a_new_library_has_the_same_table_as_an_upgraded_one(tmp_path):
    old = tmp_path / "old.db"
    _library_1_0_0(old)
    DatabaseManager(str(old)).initialize_tables()
    fresh = DatabaseManager(str(tmp_path / "new.db"))
    fresh.initialize_tables()

    def shape(path):
        con = sqlite3.connect(path)
        return [tuple(r[1:3]) for r in con.execute("PRAGMA table_info(reading_progress)")]

    assert shape(old) == shape(tmp_path / "new.db") != []


def test_opening_and_reading_are_remembered(db):
    _doc(db, "a")
    db.record_reading_open("a", unit="page", total=248, now=NOW)
    db.record_reading_position("a", 57, now=NOW + 60)
    progress = db.get_reading_progress("a")
    assert (progress["position"], progress["total"], progress["unit"], progress["open_count"]) == (57, 248, "page", 1)
    assert progress["last_opened_at"] == NOW + 60
    db.record_reading_open("a", unit="page", total=248, now=NOW + 3600)
    again = db.get_reading_progress("a")
    assert again["position"] == 57 and again["open_count"] == 2  # opening again keeps where it was


def test_recent_reading_is_latest_first_and_carries_the_book(db):
    for doc_id, when in (("old", NOW - 5 * DAY), ("mid", NOW - 2 * DAY), ("new", NOW)):
        _doc(db, doc_id)
        db.record_reading_open(doc_id, total=10, now=when)
    rows = db.recent_reading(2)
    assert [r["id"] for r in rows] == ["new", "mid"]
    assert rows[0]["title"] == "new" and rows[0]["total"] == 10


def test_deleting_a_book_forgets_its_reading_progress(db):
    _doc(db, "gone")
    db.record_reading_open("gone", now=NOW)
    db.delete_document("gone")
    assert db.get_reading_progress("gone") is None and db.recent_reading() == []


def test_author_of_the_month_counts_added_and_opened_books_of_the_last_30_days(db):
    _doc(db, "n1", "Nguyễn Nhật Ánh", created=NOW - 3 * DAY, cover="c1.png")
    _doc(db, "n2", "Nguyễn Nhật Ánh", created=NOW - 10 * DAY, cover="c2.png")
    _doc(db, "n3", "Nguyễn Nhật Ánh", created=NOW - 400 * DAY)  # old, but opened lately (below)
    db.record_reading_open("n3", now=NOW - DAY)
    _doc(db, "t1", "Tô Hoài", created=NOW - 2 * DAY)
    _doc(db, "u1", "Unknown", created=NOW - DAY)  # an unknown author never wins
    _doc(db, "u2", "Unknown", created=NOW - DAY)
    _doc(db, "u3", "Unknown", created=NOW - DAY)
    winner = db.author_of_the_month(now=NOW)
    assert winner["author"] == "Nguyễn Nhật Ánh" and winner["active"] == 3 and winner["books"] == 3
    assert winner["cover_paths"] == ["c1.png", "c2.png"]  # newest activity first, only real covers


def test_nobody_is_author_of_the_month_when_nothing_is_recent(db):
    _doc(db, "old", created=NOW - 200 * DAY)
    assert db.author_of_the_month(now=NOW) is None


def test_a_co_authored_book_counts_for_each_author(db):
    _doc(db, "x", "A. Nguyễn & B. Trần", created=NOW - DAY)
    _doc(db, "y", "B. Trần", created=NOW - 2 * DAY)
    assert db.author_of_the_month(now=NOW)["author"] == "B. Trần"
