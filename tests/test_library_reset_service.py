# SPDX-License-Identifier: AGPL-3.0-or-later
"""Đặt lại thư viện: backs up, then empties every table of library data -- never a file, never a book's own
metadata, never the online community database."""
from __future__ import annotations

import pytest

from smartdoc.application.backup_service import BackupError, REASON_PRE_RESET
from smartdoc.application.library_reset_service import LibraryResetError
from smartdoc.core.app_context import AppContext
from smartdoc.core.config import ConfigManager
from smartdoc.infrastructure.database import DatabaseManager


@pytest.fixture
def file_context(tmp_path):
    db = DatabaseManager(str(tmp_path / "library.db"))
    context = AppContext(config=ConfigManager(app_data_dir=tmp_path / "appdata"), db=db)
    for n in range(3):
        db.add_or_update_document(f"d{n}", {"title": f"Sách {n}", "author": "A", "file_path": f"{n}.pdf",
                                            "extension": "pdf", "tags": "Tiểu thuyết", "created_at": float(n)})
    db.save_collection("c1", "Bộ sưu tập 1", "[]", "all", 0.0)
    db.connection.execute(
        "INSERT INTO reading_progress (doc_id, last_opened_at, position, total, unit, open_count) "
        "VALUES ('d0', 1.0, 3, 100, 'page', 2)"
    )
    db.connection.execute("INSERT INTO excluded_paths (path_key, path, file_size, excluded_at) VALUES ('k', 'p', 1, 1.0)")
    db.connection.commit()
    yield context
    context.shutdown()


def _rowcount(context, table: str) -> int:
    return context.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_reset_empties_every_library_table(file_context):
    assert _rowcount(file_context, "documents") == 3
    assert _rowcount(file_context, "collections") == 1
    assert _rowcount(file_context, "reading_progress") == 1
    assert _rowcount(file_context, "excluded_paths") == 1

    file_context.library_reset.reset()

    for table in ("documents", "documents_fts", "collections", "collection_documents", "facet_groups",
                  "facet_group_members", "smart_classification", "metadata_history", "reading_progress",
                  "excluded_paths"):
        assert _rowcount(file_context, table) == 0, table


def test_reset_backs_up_the_library_first(file_context):
    assert file_context.backups.list_backups() == []

    file_context.library_reset.reset()

    backups = file_context.backups.list_backups()
    assert len(backups) == 1 and backups[0].reason == REASON_PRE_RESET


def test_a_failed_backup_stops_the_reset_and_touches_nothing(file_context, monkeypatch):
    monkeypatch.setattr(file_context.backups, "create_backup",
                        lambda *a, **k: (_ for _ in ()).throw(BackupError("đĩa đầy")))

    with pytest.raises(LibraryResetError, match="đĩa đầy"):
        file_context.library_reset.reset()

    assert _rowcount(file_context, "documents") == 3  # no backup, no reset


def test_reset_keeps_configuration_by_default(file_context):
    file_context.config.config.theme = "broadsheet"
    file_context.config.config.sidebar_width = 999
    db_path = file_context.config.config.db_path

    file_context.library_reset.reset(keep_config=True)

    assert file_context.config.config.theme == "broadsheet"
    assert file_context.config.config.sidebar_width == 999
    assert file_context.config.config.db_path == db_path


def test_reset_can_also_put_configuration_back_to_defaults(file_context):
    from smartdoc.core.config import AppConfig

    file_context.config.config.sidebar_width = 999
    db_path, cover_dir = file_context.config.config.db_path, file_context.config.config.cover_cache_dir

    file_context.library_reset.reset(keep_config=False)

    assert file_context.config.config.sidebar_width == AppConfig().sidebar_width
    # The two exceptions: nothing else moves the library or the cover cache.
    assert file_context.config.config.db_path == db_path
    assert file_context.config.config.cover_cache_dir == cover_dir


def test_reset_never_touches_the_book_files_on_disk(file_context, tmp_path):
    book = tmp_path / "0.pdf"
    book.write_bytes(b"%PDF-1.4 fake book content")
    before = book.read_bytes()
    file_context.db.add_or_update_document("d0", {"title": "Sách 0", "file_path": str(book), "created_at": 0.0})

    file_context.library_reset.reset()

    assert book.read_bytes() == before  # untouched, even though its library row is gone


def test_reset_publishes_library_updated_and_clears_the_active_filter(file_context):
    from smartdoc.core.event_bus import LibraryUpdatedEvent

    file_context.filters.select("collections", "c1")
    announced = []
    file_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: announced.append(e))

    file_context.library_reset.reset()

    assert announced
    assert file_context.filters.current.collections == ()


def test_reset_skips_the_backup_for_an_in_memory_library(app_context):
    """The in-memory database used by tests/demos has no file to back up -- same exception initialize_tables
    already makes for a schema upgrade (AppContext passes before_migrate=None for it)."""
    app_context.db.add_or_update_document("d1", {"title": "A", "file_path": "a.pdf", "created_at": 0.0})

    app_context.library_reset.reset()  # must not raise

    assert app_context.db.count_documents() == 0
