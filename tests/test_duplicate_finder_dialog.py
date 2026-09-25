# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tìm file trùng (stage G7): groups on the left, the files of a group on the right with a "Giữ" choice, and two
clearly different actions -- remove the others from the library (files stay) or delete them from the disk (locked
confirmation)."""
from PySide6.QtWidgets import QDialog

from smartdoc.presentation import duplicate_finder_dialog as module
from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog, default_keeper, note_for


def _seed_exact_duplicates(app_context, tmp_path=None):
    def path(name):
        return str(tmp_path / name) if tmp_path else name

    app_context.db.add_or_update_document(
        "d1", {"title": "Sach A", "author": "X", "file_path": path("a.pdf"), "content_hash": "h1", "created_at": 1.0,
               "file_size": 12_400_000})
    app_context.db.add_or_update_document(
        "d2", {"title": "Sach A (copy)", "author": "X", "file_path": path("a2.pdf"), "content_hash": "h1",
               "created_at": 2.0, "file_size": 12_400_000})
    app_context.db.add_or_update_document(
        "d3", {"title": "Unique", "author": "Y", "file_path": path("b.pdf"), "content_hash": "h2", "created_at": 3.0})


def _dialog(app_context):
    dialog = DuplicateFinderDialog(app_context)
    dialog.wait_for_scan()
    return dialog


def test_exact_groups_list_only_duplicate_books_with_counts_and_sizes(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = _dialog(app_context)

    assert dialog.group_list.count() == 1
    assert "2 file" in dialog.group_list.item(0).text()
    assert dialog.summary_label.text().startswith("1 nhóm · 2 file")
    assert dialog.file_table.rowCount() == 2
    dialog.deleteLater()


def test_no_duplicates_means_an_empty_dialog_with_buttons_off(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Only One", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0})
    dialog = _dialog(app_context)
    assert dialog.group_list.count() == 0 and dialog.file_table.rowCount() == 0
    assert not dialog.remove_button.isEnabled() and not dialog.delete_button.isEnabled()
    dialog.deleteLater()


def test_the_copy_with_most_information_is_offered_as_the_one_to_keep(qapp):
    poor = {"id": "a", "title": "T", "author": "Unknown", "created_at": 1.0}
    rich = {"id": "b", "title": "T", "author": "X", "cover_path": "c.webp", "publisher": "NXB", "created_at": 2.0}
    assert default_keeper([poor, rich])["id"] == "b"
    tie_old = {"id": "c", "title": "T", "created_at": 1.0}
    tie_new = {"id": "d", "title": "T", "created_at": 5.0}
    assert default_keeper([tie_new, tie_old])["id"] == "c"  # equal: the oldest
    assert note_for(poor, rich, "exact") == "Giống hệt từng byte"


def test_choosing_another_keeper_updates_the_buttons_and_the_group_line(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = _dialog(app_context)
    radios = [dialog.file_table.cellWidget(row, 0).findChildren(type(dialog._radio_group.buttons()[0]))[0]
              for row in range(2)]
    checked_before = [r.isChecked() for r in radios]
    assert checked_before.count(True) == 1

    other = radios[checked_before.index(False)]
    other.setChecked(True)

    assert "đã chọn cái giữ" in dialog.group_list.item(0).text()
    assert dialog.remove_button.text() == "Bỏ 1 bản kia khỏi thư viện"
    assert dialog.delete_button.text() == "Xóa 1 file khỏi máy…"
    dialog.deleteLater()


def test_removing_the_others_from_the_library_keeps_every_file(qapp, app_context, tmp_path):
    _seed_exact_duplicates(app_context, tmp_path)
    for name in ("a.pdf", "a2.pdf", "b.pdf"):
        (tmp_path / name).write_bytes(b"x")
    dialog = _dialog(app_context)
    keeper = default_keeper(dialog._exact_groups[0])["id"]

    dialog.remove_button.click()

    remaining = {d["id"] for d in app_context.db.list_all_documents()}
    assert keeper in remaining and len(remaining) == 2  # the keeper and the unrelated book
    assert all((tmp_path / name).exists() for name in ("a.pdf", "a2.pdf", "b.pdf"))  # no file touched
    assert dialog.group_list.count() == 0
    dialog.deleteLater()


def test_deleting_files_needs_the_confirmation_and_removes_only_the_others(qapp, app_context, tmp_path, monkeypatch):
    _seed_exact_duplicates(app_context, tmp_path)
    for name in ("a.pdf", "a2.pdf", "b.pdf"):
        (tmp_path / name).write_bytes(b"x")
    dialog = _dialog(app_context)
    keeper_id = default_keeper(dialog._exact_groups[0])["id"]
    asked = {}

    def fake_confirm(parent, **kwargs):
        asked.update(kwargs)
        return True

    monkeypatch.setattr(module, "confirm_danger", fake_confirm)
    dialog.delete_button.click()

    assert asked["action_text"] == "Xóa 1 file" and "Không bị đụng tới" in asked["safe_text"]
    assert len(asked["items"]) == 1
    remaining_paths = {p.name for p in tmp_path.iterdir() if p.suffix == ".pdf"}
    assert len(remaining_paths) == 2  # one duplicate is gone from the disk
    assert app_context.db.get_document(keeper_id) is not None
    dialog.deleteLater()


def test_declining_the_confirmation_keeps_files_and_library(qapp, app_context, tmp_path, monkeypatch):
    _seed_exact_duplicates(app_context, tmp_path)
    for name in ("a.pdf", "a2.pdf", "b.pdf"):
        (tmp_path / name).write_bytes(b"x")
    dialog = _dialog(app_context)
    monkeypatch.setattr(module, "confirm_danger", lambda parent, **kw: False)

    dialog.delete_button.click()

    assert len([p for p in tmp_path.iterdir() if p.suffix == ".pdf"]) == 3 and len(app_context.db.list_all_documents()) == 3
    dialog.deleteLater()


def test_the_coming_soon_block_is_shown_but_switched_off(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    assert not dialog.soon_toggle.isEnabled()
    dialog.reject()
    dialog.deleteLater()


def test_navigation_buttons_step_through_the_groups(qapp, app_context):
    for i in range(4):
        app_context.db.add_or_update_document(
            f"a{i}", {"title": f"T{i // 2}", "author": "X", "file_path": f"{i}.pdf", "content_hash": f"h{i // 2}",
                      "created_at": float(i)})
    dialog = _dialog(app_context)
    assert dialog.group_list.count() == 2 and dialog.position_label.text() == "Nhóm 1 / 2"
    assert not dialog.previous_button.isEnabled() and dialog.next_button.isEnabled()
    dialog.next_button.click()
    assert dialog.position_label.text() == "Nhóm 2 / 2" and not dialog.next_button.isEnabled()
    dialog.deleteLater()


def test_refresh_updates_after_an_external_change(qapp, app_context):
    dialog = _dialog(app_context)
    assert dialog.group_list.count() == 0
    _seed_exact_duplicates(app_context)
    dialog.refresh()
    assert dialog.group_list.count() == 1
    dialog.wait_for_scan()
    dialog.deleteLater()


# -- the "Gần giống" scan ------------------------------------------------------------------------------------------------


def _seed_fuzzy(app_context):
    app_context.db.add_or_update_document(
        "f1", {"title": "Python Co Ban", "author": "Nguyen Van A", "file_path": "1.pdf", "content_hash": "x1",
               "created_at": 1.0})
    app_context.db.add_or_update_document(
        "f2", {"title": "Python Cơ Bản (copy)", "author": "Nguyễn Văn A", "file_path": "2.pdf",
               "content_hash": "x2", "created_at": 2.0})


def test_fuzzy_scan_runs_in_the_background_and_fills_its_list(qapp, app_context):
    _seed_fuzzy(app_context)
    dialog = DuplicateFinderDialog(app_context)
    assert dialog.wait_for_scan(), "timeout"
    assert len(dialog._fuzzy_groups) == 1 and dialog.fuzzy_button.text() == "Gần giống (1)"
    dialog.fuzzy_button.click()
    assert dialog.group_list.count() == 1
    dialog.deleteLater()


def test_closing_the_dialog_cancels_a_scan_in_progress(qapp, app_context):
    _seed_fuzzy(app_context)
    dialog = DuplicateFinderDialog(app_context)
    cancel = dialog._cancel_scan
    dialog.reject()
    assert cancel.is_set() and not dialog._scan_poll.isActive()
    dialog.deleteLater()


def test_a_newer_scan_supersedes_an_older_one(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    stale_generation = dialog._scan_generation
    dialog.refresh()  # starts a new scan
    dialog._on_fuzzy_finished(stale_generation, [[{"id": "x"}, {"id": "y"}]], "")
    assert dialog._fuzzy_groups == []  # the stale result is ignored
    dialog.wait_for_scan()
    dialog.deleteLater()


def test_dialog_result_codes_are_normal(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    dialog.deleteLater()
