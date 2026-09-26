# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tìm file trùng, "Danh sách": all files in one searchable, sortable table, handled in bulk -- and every group keeps a copy."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog, suggested_keeper
from smartdoc.presentation.duplicate_list_pane import _C_NOTE, _C_TICK, DuplicateListPane


def _doc(doc_id, title, author="X", path=None, size=1000, created=1.0, **extra):
    return {"id": doc_id, "title": title, "author": author, "file_path": path or f"C:/sach/{doc_id}.pdf", "file_size": size,
            "created_at": created, "extension": "pdf", **extra}


GROUPS = [
    [_doc("a1", "Đắc nhân tâm", "Dale Carnegie", size=5000, cover_path="c.webp", publisher="NXB"),
     _doc("a2", "Đắc nhân tâm (bản sao)", "Dale Carnegie", path="D:/tai ve/dac nhan tam.pdf", size=5000)],
    [_doc("b1", "Nhà giả kim", "Paulo Coelho", size=9000), _doc("b2", "Nha gia kim", "Paulo Coelho", size=9000),
     _doc("b3", "Nhà giả kim - bản scan", "Paulo Coelho", size=30000)],
    [_doc("c1", "Python cơ bản", "Nguyễn Văn A"), _doc("c2", "Python cơ bản", "Nguyễn Văn A", path="E:/usb/python.epub")],
]


def _pane(qapp):
    pane = DuplicateListPane(suggested_keeper)
    pane.resize(900, 500)
    pane.show()
    pane.set_groups(GROUPS)
    return pane


def _tick(pane, doc_id, on=True):
    for row in range(pane.table.rowCount()):
        item = pane.table.item(row, _C_TICK)
        if item.data(Qt.UserRole + 1)["id"] == doc_id:
            item.setCheckState(Qt.Checked if on else Qt.Unchecked)
            return
    raise AssertionError(doc_id)


def _visible_ids(pane):
    return {pane.table.item(r, _C_TICK).data(Qt.UserRole + 1)["id"] for r in range(pane.table.rowCount()) if not pane.table.isRowHidden(r)}


def test_every_file_of_every_group_is_listed_with_nothing_ticked(qapp):
    pane = _pane(qapp)
    assert pane.table.rowCount() == 7 and pane.ticked_docs() == []
    assert pane.count_label.text() == "3/3 nhóm · 7 file"
    assert not pane.remove_button.isEnabled() and not pane.trash_button.isEnabled()
    assert pane.remove_button.text() == "Bỏ 0 file khỏi thư viện"
    pane.deleteLater()


def test_search_ignores_accents_and_case_and_keeps_a_group_whole(qapp):
    pane = _pane(qapp)
    pane.search_edit.setText("DAC nhan")
    assert _visible_ids(pane) == {"a1", "a2"}
    pane.search_edit.setText("gia kim scan")  # matches one file of the group; its two other copies stay to compare against
    assert _visible_ids(pane) == {"b1", "b2", "b3"} and pane.count_label.text() == "1/3 nhóm · 3 file"
    pane.search_edit.setText("usb epub")  # a folder and a format
    assert _visible_ids(pane) == {"c1", "c2"}
    pane.search_edit.setText("paulo dale")  # every word must appear (in one file)
    assert _visible_ids(pane) == set()
    pane.search_edit.setText("")
    assert len(_visible_ids(pane)) == 7
    pane.deleteLater()


def test_ticks_survive_searching_and_sorting(qapp):
    pane = _pane(qapp)
    _tick(pane, "b3")
    pane.search_edit.setText("python")
    pane.search_edit.setText("")
    pane.table.sortByColumn(4, Qt.DescendingOrder)  # by size
    assert [d["id"] for d in pane.ticked_docs()] == ["b3"] and pane.remove_button.text() == "Bỏ 1 file khỏi thư viện"
    sizes = [pane.table.item(r, 4).data(Qt.UserRole + 2) for r in range(pane.table.rowCount())]
    assert sizes == sorted(sizes, reverse=True)  # a number sorts as a number ("30000" after "9000" as text would be wrong)
    pane.deleteLater()


def test_a_group_can_never_be_ticked_out_of_existence(qapp):
    pane = _pane(qapp)
    _tick(pane, "a1")
    _tick(pane, "a2")
    assert pane.groups_left_empty() == [1]
    assert not pane.remove_button.isEnabled() and not pane.trash_button.isEnabled()
    assert "nhóm #1" in pane.guard_label.text() and not pane.guard_label.isHidden()
    _tick(pane, "a1", on=False)
    assert pane.groups_left_empty() == [] and pane.remove_button.isEnabled() and pane.guard_label.isHidden()
    pane.deleteLater()


def test_the_helper_ticks_all_but_the_most_complete_copy_only_where_shown_and_can_be_undone(qapp):
    pane = _pane(qapp)
    pane.search_edit.setText("nha gia")
    pane.rule_button.click()
    assert {d["id"] for d in pane.ticked_docs()} == {"b2", "b3"} or len(pane.ticked_docs()) == 2  # all but one of group 2
    assert all(d["id"].startswith("b") for d in pane.ticked_docs())  # the hidden groups were not touched
    assert pane.groups_left_empty() == []
    pane.clear_button.click()
    assert pane.ticked_docs() == []
    pane.search_edit.setText("")
    pane.rule_button.click()
    assert len(pane.ticked_docs()) == 4  # groups of 2, 3, 2 files: one kept in each
    assert "a1" not in {d["id"] for d in pane.ticked_docs()}  # the one with cover and publisher is the suggested copy
    assert pane.table.item(0, _C_NOTE) is not None
    pane.deleteLater()


def test_the_buttons_report_what_is_ticked(qapp):
    pane = _pane(qapp)
    asked = {"remove": None, "trash": None}
    pane.remove_requested.connect(lambda docs: asked.__setitem__("remove", [d["id"] for d in docs]))
    pane.trash_requested.connect(lambda docs: asked.__setitem__("trash", [d["id"] for d in docs]))
    _tick(pane, "a2")
    _tick(pane, "c2")
    pane.remove_button.click()
    pane.trash_button.click()
    assert asked["remove"] == ["a2", "c2"] and asked["trash"] == ["a2", "c2"]
    pane.deleteLater()


# -- in the dialog ----------------------------------------------------------------------------------------------------------

def _seed(app_context, tmp_path):
    for n, name in enumerate(("a.pdf", "a2.pdf", "b.pdf", "b2.pdf", "c.pdf")):
        (tmp_path / name).write_bytes(b"x" * (10 if n < 2 else 20 if n < 4 else 30))
    rows = [("d1", "Sách A", "a.pdf", "h1"), ("d2", "Sách A (bản sao)", "a2.pdf", "h1"), ("d3", "Sách B", "b.pdf", "h2"),
            ("d4", "Sách B", "b2.pdf", "h2"), ("d5", "Sách lẻ", "c.pdf", "h3")]
    for doc_id, title, name, digest in rows:
        app_context.db.add_or_update_document(doc_id, {"title": title, "author": "X", "file_path": str(tmp_path / name),
                                                       "content_hash": digest, "file_size": (tmp_path / name).stat().st_size, "created_at": 1.0})


def test_the_dialog_switches_between_the_group_view_and_the_list(qapp, app_context, tmp_path):
    _seed(app_context, tmp_path)
    dialog = DuplicateFinderDialog(app_context)
    dialog.wait_for_scan()
    assert dialog.view_stack.currentIndex() == 0 and dialog.groups_view_button.isChecked()
    dialog.list_view_button.click()
    assert dialog.view_stack.currentIndex() == 1 and dialog.list_pane.table.rowCount() == 4
    assert dialog.previous_button.isHidden() and dialog.next_button.isHidden()
    dialog.groups_view_button.click()
    assert dialog.view_stack.currentIndex() == 0 and not dialog.previous_button.isHidden()
    dialog.deleteLater()


def test_the_list_follows_the_mode_buttons(qapp, app_context, tmp_path):
    _seed(app_context, tmp_path)
    dialog = DuplicateFinderDialog(app_context)
    dialog.wait_for_scan()
    dialog.list_view_button.click()
    dialog.fuzzy_button.click()  # the hint list (similar titles), shown in the same table
    assert dialog._mode == "fuzzy" and dialog.list_pane.table.rowCount() == sum(len(g) for g in dialog._groups["fuzzy"])
    dialog.exact_button.click()
    assert dialog.list_pane.table.rowCount() == 4
    dialog.deleteLater()


def test_removing_ticked_files_from_the_list_keeps_the_files_and_the_rest_of_the_list(qapp, app_context, tmp_path):
    _seed(app_context, tmp_path)
    dialog = DuplicateFinderDialog(app_context)
    dialog.wait_for_scan()
    dialog.list_view_button.click()
    pane = dialog.list_pane
    _tick(pane, "d2")
    _tick(pane, "d4")
    pane.remove_button.click()
    remaining = {d["id"] for d in app_context.db.list_all_documents()}
    assert remaining == {"d1", "d3", "d5"} and all((tmp_path / n).exists() for n in ("a.pdf", "a2.pdf", "b.pdf", "b2.pdf"))
    assert app_context.db.is_path_excluded(str(tmp_path / "a2.pdf"))  # dropped on purpose: the watcher will not bring it back
    assert pane.table.rowCount() == 0  # both groups are resolved
    dialog.deleteLater()


def test_trashing_ticked_files_from_the_list_asks_once_and_moves_them(qapp, app_context, tmp_path, monkeypatch):
    _seed(app_context, tmp_path)
    dialog = DuplicateFinderDialog(app_context)
    dialog.wait_for_scan()
    dialog.list_view_button.click()
    _tick(dialog.list_pane, "d1")
    _tick(dialog.list_pane, "d3")
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[1]) or QMessageBox.No)
    dialog.list_pane.trash_button.click()
    assert asked and "2 file" in asked[0] and (tmp_path / "a.pdf").exists()  # declined: nothing moved
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dialog.list_pane.trash_button.click()
    assert not (tmp_path / "a.pdf").exists() and not (tmp_path / "b.pdf").exists() and (tmp_path / "a2.pdf").exists()
    assert {i.original_path for i in app_context.trash.list_items()} == {str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")}
    dialog.deleteLater()
