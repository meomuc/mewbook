# SPDX-License-Identifier: AGPL-3.0-or-later
"""The folder watcher and the library agree: a book dropped on purpose stays dropped, a renamed file is the same book, files
that arrived while MewBook was closed are found, and duplicates are found although import hashes lazily."""
from __future__ import annotations

import os
import time

import pytest

from smartdoc.application.file_watcher import LibraryWatcher
from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.core.event_bus import FileDetectedEvent
from smartdoc.presentation.file_actions import FileActionEngine
from tests.test_import_queue import _make_pdf, _wait_until


@pytest.fixture
def manager(app_context):
    m = ImportQueueManager(app_context, num_workers=2)
    m.start()
    yield m
    m.stop()


def _import(app_context, manager, path, title):
    path.parent.mkdir(parents=True, exist_ok=True)
    _make_pdf(path, title, "Tác giả", "nội dung " + title)
    manager.add_files([str(path)])
    assert _wait_until(lambda: app_context.db.find_id_by_path(str(path)) is not None)
    return app_context.db.find_id_by_path(str(path))


def test_a_book_dropped_from_the_library_is_not_imported_again_by_the_watcher(tmp_path, app_context, manager):
    path = tmp_path / "a.pdf"
    doc_id = _import(app_context, manager, path, "Sách bỏ")
    FileActionEngine(app_context).delete_documents([(doc_id, str(path))], delete_physical_file=False)
    assert app_context.db.get_document(doc_id) is None and app_context.db.is_path_excluded(str(path))

    app_context.event_bus.publish(FileDetectedEvent(file_path=str(path)))  # the file was touched (antivirus, sync client)
    time.sleep(1.0)
    assert app_context.db.get_document(doc_id) is None and app_context.db.find_id_by_path(str(path)) is None


def test_adding_the_file_by_hand_lifts_the_exclusion(tmp_path, app_context, manager):
    path = tmp_path / "a.pdf"
    doc_id = _import(app_context, manager, path, "Sách bỏ")
    FileActionEngine(app_context).delete_documents([(doc_id, str(path))], delete_physical_file=False)
    manager.add_files([str(path)])
    assert _wait_until(lambda: app_context.db.get_document(doc_id) is not None)
    assert not app_context.db.is_path_excluded(str(path))


def test_deleting_the_file_too_leaves_no_exclusion_behind(tmp_path, app_context, manager):
    path = tmp_path / "a.pdf"
    doc_id = _import(app_context, manager, path, "Sách xóa")
    FileActionEngine(app_context).delete_documents([(doc_id, str(path))], delete_physical_file=True)
    assert not app_context.db.is_path_excluded(str(path)) and not path.exists()


def test_exclusion_compares_paths_the_windows_way(app_context, tmp_path):
    app_context.db.exclude_paths([str(tmp_path / "Sách.PDF")])
    assert app_context.db.is_path_excluded(str(tmp_path / "sách.pdf"))
    app_context.db.unexclude_paths([str(tmp_path / "SÁCH.pdf")])
    assert not app_context.db.list_excluded_paths()


def test_a_renamed_file_is_the_same_book_not_a_new_one(tmp_path, app_context, manager):
    old = tmp_path / "old name.pdf"
    doc_id = _import(app_context, manager, old, "Sách đổi tên")
    app_context.db.update_document_fields(doc_id, {"tags": "yêu,thích"})
    watcher = LibraryWatcher(app_context)
    new = tmp_path / "new name.pdf"
    old.rename(new)
    assert watcher._handle_moved(str(old), str(new)) is True
    row = app_context.db.get_document(doc_id)
    assert row["file_path"] == str(new) and row["tags"] == "yêu,thích"  # same id: hashtags, collections, progress stay
    assert len(app_context.db.list_all_documents()) == 1


def test_a_move_the_library_did_not_know_about_is_left_to_the_normal_import(tmp_path, app_context):
    watcher = LibraryWatcher(app_context)
    assert watcher._handle_moved(str(tmp_path / "unknown.pdf"), str(tmp_path / "x.pdf")) is False


def test_mewbooks_own_moves_are_not_treated_as_news(tmp_path, app_context):
    watcher = LibraryWatcher(app_context)
    app_context.self_writes.mark(str(tmp_path / "dest.pdf"))
    assert watcher._handle_moved(str(tmp_path / "src.pdf"), str(tmp_path / "dest.pdf")) is True


def test_catch_up_scan_imports_only_files_that_arrived_while_closed(tmp_path, app_context, manager):
    folder = tmp_path / "watched"
    folder.mkdir()
    app_context.config.config.watch_folders = [str(folder)]
    known_id = _import(app_context, manager, folder / "known.pdf", "Đã có")
    dropped = folder / "dropped.pdf"
    _make_pdf(dropped, "Đã bỏ", "x", "y")
    app_context.db.exclude_paths([str(dropped)])
    (folder / "sub").mkdir()
    _make_pdf(folder / "sub" / "new.pdf", "Mới", "x", "y")
    (folder / "notes.txt").write_text("not a book")

    assert manager.catch_up_scan() == 1
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 2)
    assert {d["title"] for d in app_context.db.list_all_documents()} == {"Đã có", "Mới"}
    assert app_context.db.get_document(known_id) is not None
    assert manager.catch_up_scan() == 0  # a second scan finds nothing new


def test_catch_up_scan_finds_a_book_that_moved_while_closed_instead_of_importing_it_twice(tmp_path, app_context, manager):
    folder = tmp_path / "watched"
    app_context.config.config.watch_folders = [str(folder)]
    path = folder / "old" / "book.pdf"
    doc_id = _import(app_context, manager, path, "Sách chuyển")
    (folder / "new").mkdir()
    moved = folder / "new" / "book.pdf"
    os.replace(path, moved)
    app_context.relink.check_files()  # what start-up does first: the old path is now missing
    assert manager.catch_up_scan() == 0
    row = app_context.db.get_document(doc_id)
    assert row["file_path"] == str(moved) and len(app_context.db.list_all_documents()) == 1


def test_duplicates_are_found_although_import_hashes_lazily(tmp_path, app_context, manager):
    from smartdoc.application.duplicate_finder import DuplicateEngine

    a = tmp_path / "a.pdf"
    _import(app_context, manager, a, "Bản gốc")
    (tmp_path / "b.pdf").write_bytes(a.read_bytes())
    _import(app_context, manager, tmp_path / "c.pdf", "Sách khác hẳn để dung lượng khác " * 20)
    manager.add_files([str(tmp_path / "b.pdf")])
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 3)
    engine = DuplicateEngine(app_context)
    engine.hash_pending()
    groups = engine.find_exact_duplicates()
    assert len(groups) == 1 and {d["file_path"] for d in groups[0]} == {str(a), str(tmp_path / "b.pdf")}
    assert engine.pending_hash_count() == 0


def test_the_duplicate_dialog_hashes_pending_files_in_the_background_and_then_lists_them(qapp, app_context, tmp_path):
    from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog

    for name in ("a.bin", "b.bin"):
        (tmp_path / name).write_bytes(b"identical bytes")
    for n, name in enumerate(("a.bin", "b.bin")):
        app_context.db.add_or_update_document(f"d{n}", {"title": f"T{n}", "file_path": str(tmp_path / name), "file_size": 15, "created_at": 1.0})
    assert app_context.db.get_document("d0")["content_hash"] is None
    dialog = DuplicateFinderDialog(app_context)
    def pumped():
        qapp.processEvents()  # the dialog's timers need the event loop
        return dialog.group_list.count() == 1

    assert _wait_until(pumped, timeout=10)
    assert app_context.db.get_document("d0")["content_hash"] == app_context.db.get_document("d1")["content_hash"]
    dialog.deleteLater()
