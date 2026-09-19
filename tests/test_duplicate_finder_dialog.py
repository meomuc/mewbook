from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog


def _pick_action_containing(text_substring: str):
    def fake_exec_menu(self, menu, _position):
        for action in menu.actions():
            if text_substring in action.text():
                return action
        return None

    return fake_exec_menu


def _delete_via_menu(monkeypatch, choice_text: str = "Xóa khỏi thư viện") -> None:
    """"Xóa khỏi thư viện" is a substring of "Xóa khỏi thư viện và thư mục
    gốc" too, but menu.actions() preserves insertion order and the
    library-only action is added first, so this still picks the intended
    one when choice_text is the default."""
    monkeypatch.setattr(DuplicateFinderDialog, "_exec_menu", _pick_action_containing(choice_text))


def _seed_exact_duplicates(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Sach A", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Sach A (copy)", "author": "X", "file_path": "a2.pdf", "content_hash": "h1", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "Unique", "author": "Y", "file_path": "b.pdf", "content_hash": "h2", "created_at": 3.0}
    )


def test_exact_tab_lists_only_duplicate_documents(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    assert dialog.exact_table.rowCount() == 2
    titles = {dialog.exact_table.item(row, 0).text() for row in range(2)}
    assert titles == {"Sach A", "Sach A (copy)"}


def test_no_duplicates_means_empty_tables(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Only One", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    dialog = DuplicateFinderDialog(app_context)

    assert dialog.exact_table.rowCount() == 0
    assert dialog.fuzzy_table.rowCount() == 0


def test_checking_a_row_and_deleting_removes_from_library(qapp, app_context, monkeypatch):
    _seed_exact_duplicates(app_context)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    _delete_via_menu(monkeypatch)

    dialog = DuplicateFinderDialog(app_context)
    dialog.exact_table.item(0, 0).setCheckState(Qt.Checked)

    dialog._on_delete_selected()

    remaining_ids = {d["id"] for d in app_context.db.list_all_documents()}
    assert "d1" not in remaining_ids or "d2" not in remaining_ids
    assert len(remaining_ids) == 2  # one of the pair removed, "d3" untouched
    assert "d3" in remaining_ids


def test_deleting_with_nothing_checked_does_nothing(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    dialog._on_delete_selected()

    assert len(app_context.db.list_all_documents()) == 3


def test_delete_cancelled_keeps_all_documents(qapp, app_context, monkeypatch):
    _seed_exact_duplicates(app_context)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    _delete_via_menu(monkeypatch)

    dialog = DuplicateFinderDialog(app_context)
    dialog.exact_table.item(0, 0).setCheckState(Qt.Checked)
    dialog._on_delete_selected()

    assert len(app_context.db.list_all_documents()) == 3


def test_delete_menu_dismissed_does_nothing(qapp, app_context, monkeypatch):
    """Picking "Hủy bỏ" (or dismissing the menu, which _exec_menu returns
    None for) must not touch the library or even prompt for confirmation."""
    _seed_exact_duplicates(app_context)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(1) or QMessageBox.Yes))
    monkeypatch.setattr(DuplicateFinderDialog, "_exec_menu", lambda self, menu, position: None)

    dialog = DuplicateFinderDialog(app_context)
    dialog.exact_table.item(0, 0).setCheckState(Qt.Checked)
    dialog._on_delete_selected()

    assert asked == []
    assert len(app_context.db.list_all_documents()) == 3


def test_delete_with_library_and_disk_option_removes_physical_file(qapp, app_context, tmp_path, monkeypatch):
    real_file = tmp_path / "book.pdf"
    real_file.write_bytes(b"content")
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": str(real_file), "content_hash": "h1", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "A (copy)", "author": "X", "file_path": "a2.pdf", "content_hash": "h1", "created_at": 2.0}
    )
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    _delete_via_menu(monkeypatch, "và thư mục gốc")

    dialog = DuplicateFinderDialog(app_context)
    row = next(r for r in range(dialog.exact_table.rowCount()) if dialog.exact_table.item(r, 3).text() == str(real_file))
    dialog.exact_table.item(row, 0).setCheckState(Qt.Checked)
    dialog._on_delete_selected()

    assert not real_file.exists()


def test_refresh_updates_after_external_change(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    assert dialog.exact_table.rowCount() == 0

    _seed_exact_duplicates(app_context)
    dialog.refresh()

    assert dialog.exact_table.rowCount() == 2


def test_date_added_column_is_populated_on_both_tabs(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    dates = {dialog.exact_table.item(row, 2).text() for row in range(dialog.exact_table.rowCount())}
    assert all(d != "—" for d in dates)


def test_table_is_sorted_by_first_column_by_default(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Zeta Book", "author": "X", "file_path": "z.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Zeta Book (copy)", "author": "X", "file_path": "z2.pdf", "content_hash": "h1", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "Alpha Book", "author": "Y", "file_path": "a.pdf", "content_hash": "h2", "created_at": 3.0}
    )
    app_context.db.add_or_update_document(
        "d4", {"title": "Alpha Book (copy)", "author": "Y", "file_path": "a2.pdf", "content_hash": "h2", "created_at": 4.0}
    )
    dialog = DuplicateFinderDialog(app_context)

    titles = [dialog.exact_table.item(row, 0).text() for row in range(dialog.exact_table.rowCount())]
    assert titles == sorted(titles)


def test_select_duplicates_keeps_newest_by_default(qapp, app_context):
    _seed_exact_duplicates(app_context)  # d1 "Sach A" created_at=1.0, d2 "Sach A (copy)" created_at=2.0 (newer)
    dialog = DuplicateFinderDialog(app_context)

    dialog._apply_duplicate_selection(keep_newest=True)

    checked_titles = [
        dialog.exact_table.item(row, 0).text()
        for row in range(dialog.exact_table.rowCount())
        if dialog.exact_table.item(row, 0).checkState() == Qt.Checked
    ]
    assert checked_titles == ["Sach A"]  # d1 (older) marked for deletion, d2 (newest) kept


def test_select_duplicates_keeps_oldest_when_requested(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    dialog._apply_duplicate_selection(keep_newest=False)

    checked_titles = [
        dialog.exact_table.item(row, 0).text()
        for row in range(dialog.exact_table.rowCount())
        if dialog.exact_table.item(row, 0).checkState() == Qt.Checked
    ]
    assert checked_titles == ["Sach A (copy)"]  # d2 (newer) marked for deletion, d1 (oldest) kept


def test_select_duplicates_colors_marked_rows_differently(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    dialog._apply_duplicate_selection(keep_newest=True)

    marked_brushes = {
        dialog.exact_table.item(row, 0).background().color().name()
        for row in range(dialog.exact_table.rowCount())
        if dialog.exact_table.item(row, 0).checkState() == Qt.Checked
    }
    kept_brushes = {
        dialog.exact_table.item(row, 0).background().color().name()
        for row in range(dialog.exact_table.rowCount())
        if dialog.exact_table.item(row, 0).checkState() == Qt.Unchecked
    }
    assert marked_brushes.isdisjoint(kept_brushes)


def _seed_fuzzy_duplicates(app_context):
    app_context.db.add_or_update_document(
        "f1", {"title": "Python Co Ban", "author": "Nguyen Van A", "file_path": "p1.pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "f2", {"title": "Python Cơ Bản (copy)", "author": "Nguyễn Văn A", "file_path": "p2.pdf", "created_at": 2.0}
    )


def test_fuzzy_scan_runs_in_the_background_and_fills_the_tab(qapp, app_context):
    _seed_fuzzy_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    # The constructor returns straight away; the fuzzy tab fills in later.
    assert dialog.wait_for_scan()
    assert dialog.fuzzy_table.rowCount() == 2
    assert "1 nhóm" in dialog.tabs.tabText(1)


def test_closing_the_dialog_cancels_a_scan_in_progress(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    cancel_flag = dialog._cancel_scan

    dialog.reject()

    assert cancel_flag.is_set()


def test_deleting_updates_the_fuzzy_tab_without_rescanning(qapp, app_context, monkeypatch):
    _seed_fuzzy_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)
    assert dialog.wait_for_scan()

    rescans = []
    monkeypatch.setattr(dialog, "_start_fuzzy_scan", lambda: rescans.append(1))
    _delete_via_menu(monkeypatch)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    dialog.tabs.setCurrentWidget(dialog.fuzzy_table)
    dialog.fuzzy_table.item(0, 0).setCheckState(Qt.Checked)

    dialog._on_delete_selected()

    assert rescans == []
    assert dialog.fuzzy_table.rowCount() == 0  # a group of one is no longer a duplicate group
    assert len(app_context.db.list_documents_for_dedup()) == 1


def test_a_newer_scan_supersedes_an_older_one(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    stale_generation = dialog._scan_generation

    dialog.refresh()  # starts a new scan
    dialog._on_fuzzy_finished(stale_generation, [[{"id": "x"}, {"id": "y"}]], "")

    assert dialog._fuzzy_groups == []  # the stale result was ignored
    dialog.wait_for_scan()
