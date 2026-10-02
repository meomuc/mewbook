# SPDX-License-Identifier: AGPL-3.0-or-later
"""Clean-up of stub files and of entries whose file is gone: the filter group, the service and the dialog."""
from __future__ import annotations

from pathlib import Path

from smartdoc.application.library_cleanup import LibraryCleanupService
from smartdoc.application.facet_counter import FacetCounter
from smartdoc.domain.filter_collections import rules_from_filter
from smartdoc.domain.library_filter import STATUS_MISSING, STATUS_TINY, STATUSES, TINY_FILE_BYTES, LibraryFilter
from smartdoc.presentation.library_cleanup_dialog import LibraryCleanupDialog


def _add(app_context, folder: Path, name: str, size: int, *, create: bool = True, doc_id: str | None = None) -> str:
    path = folder / name
    if create:
        path.write_bytes(b"x" * size)
    doc_id = doc_id or f"id-{name}"
    app_context.db.add_or_update_document(
        doc_id, {"title": name, "author": "A", "file_path": str(path), "file_size": size,
                 "extension": path.suffix.lstrip("."), "created_at": 1.0})
    return doc_id


def _library(app_context, tmp_path):
    return {
        "tiny": _add(app_context, tmp_path, "tiny.epub", 900),
        "ok": _add(app_context, tmp_path, "ok.epub", TINY_FILE_BYTES + 5000),
        "gone": _add(app_context, tmp_path, "gone.epub", 80000, create=False),
    }


def test_the_status_filter_shows_missing_and_tiny_books_only(app_context, tmp_path):
    ids = _library(app_context, tmp_path)
    app_context.db.record_file_status([ids["tiny"], ids["ok"]], [ids["gone"]])
    db = app_context.db

    def shown(flt: LibraryFilter) -> set[str]:
        where, params = db.filter_where(flt)
        return set(db.list_document_ids_matching(where_sql=where, params=params))

    assert shown(LibraryFilter(statuses=(STATUS_MISSING,))) == {ids["gone"]}
    assert shown(LibraryFilter(statuses=(STATUS_TINY,))) == {ids["tiny"]}
    assert shown(LibraryFilter(statuses=(STATUS_MISSING, STATUS_TINY))) == {ids["gone"], ids["tiny"]}  # OR inside the group
    assert db.count_file_statuses() == {STATUS_MISSING: 1, STATUS_TINY: 1}


def test_a_status_is_a_real_filter_group_not_a_saved_collection_rule(app_context, tmp_path):
    flt = LibraryFilter(statuses=(STATUS_MISSING,))
    assert not flt.is_empty() and flt.active_groups() == (STATUSES,)
    assert rules_from_filter(flt) is None  # a collection cannot follow "the file is gone"
    assert rules_from_filter(LibraryFilter(formats=("epub",), statuses=(STATUS_MISSING,))) is None  # and must not drop it silently


def test_facet_counts_follow_the_status_filter(app_context, tmp_path):
    ids = _library(app_context, tmp_path)
    app_context.db.record_file_status([ids["tiny"], ids["ok"]], [ids["gone"]])
    total = FacetCounter(app_context).total(LibraryFilter(statuses=(STATUS_MISSING,)))
    assert total == 1


def test_tiny_files_go_to_the_trash_and_a_file_that_grew_is_left_alone(app_context, tmp_path):
    ids = _library(app_context, tmp_path)
    service = LibraryCleanupService(app_context)
    assert [d["id"] for d in service.tiny()] == [ids["tiny"]]
    (tmp_path / "ok.epub").write_bytes(b"x" * 100)  # the list is stale: this one is now tiny too -- but was not chosen
    (tmp_path / "tiny.epub").write_bytes(b"x" * (TINY_FILE_BYTES + 1))  # ...and this chosen one grew
    result = service.trash_tiny([ids["tiny"]])
    assert (result.done, result.skipped) == (0, 1) and (tmp_path / "tiny.epub").exists()  # not moved on an old list
    (tmp_path / "tiny.epub").write_bytes(b"x" * 900)
    result = service.trash_tiny([ids["tiny"]])
    assert result.done == 1 and not (tmp_path / "tiny.epub").exists() and app_context.db.get_document(ids["tiny"]) is None
    assert len(app_context.trash.list_items()) == 1  # restorable, not deleted for good


def test_a_missing_entry_is_removed_only_while_its_file_is_still_missing(app_context, tmp_path):
    ids = _library(app_context, tmp_path)
    app_context.db.record_file_status([ids["tiny"], ids["ok"]], [ids["gone"]])
    service = LibraryCleanupService(app_context)
    (tmp_path / "gone.epub").write_bytes(b"x" * 80000)  # the drive came back
    result = service.forget_missing([ids["gone"]])
    assert (result.done, result.skipped) == (0, 1) and app_context.db.get_document(ids["gone"]) is not None
    assert app_context.db.count_missing() == 0  # and it is marked present again
    (tmp_path / "gone.epub").unlink()
    app_context.db.record_file_status([], [ids["gone"]])
    assert service.forget_missing([ids["gone"]]).done == 1 and app_context.db.get_document(ids["gone"]) is None


def test_the_dialog_lists_both_kinds_and_each_button_works_on_its_own_kind(qapp, app_context, tmp_path, monkeypatch):
    ids = _library(app_context, tmp_path)
    app_context.db.record_file_status([ids["tiny"], ids["ok"]], [ids["gone"]])
    dialog = LibraryCleanupDialog(app_context, None)
    try:
        assert dialog.tree.topLevelItemCount() == 2
        leaves = {leaf.data(0, 0x0100 + 1): leaf for top in (dialog.tree.topLevelItem(i) for i in range(2)) for leaf in (top.child(j) for j in range(top.childCount()))}
        assert set(leaves) == {ids["tiny"], ids["gone"]}
        assert not dialog.trash_button.isEnabled() and not dialog.forget_button.isEnabled()
        leaves[ids["tiny"]].setSelected(True)
        assert dialog.trash_button.isEnabled() and not dialog.forget_button.isEnabled()
        leaves[ids["gone"]].setSelected(True)  # a mixed selection is not guessed at
        assert not dialog.trash_button.isEnabled() and not dialog.forget_button.isEnabled()
        dialog.tree.clearSelection()
        leaves[ids["gone"]].setSelected(True)
        assert dialog.forget_button.isEnabled() and not dialog.trash_button.isEnabled()
        monkeypatch.setattr("smartdoc.presentation.library_cleanup_dialog.QMessageBox.question", lambda *a, **k: 16384)  # Yes
        dialog._on_forget()
        assert app_context.db.get_document(ids["gone"]) is None
        dialog._on_show()
        assert app_context.filters.current.statuses == (STATUS_TINY,)
    finally:
        dialog.deleteLater()
