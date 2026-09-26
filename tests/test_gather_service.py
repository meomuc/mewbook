# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gom sách về một thư mục: a plan first, then copy (originals stay) or move (library follows), never overwriting."""
from __future__ import annotations

import pytest

from smartdoc.application.gather_service import MODE_COPY, MODE_MOVE, STATUS_MISSING, STATUS_THERE, GatherError


@pytest.fixture
def books(app_context, tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    paths = {"d1": src / "a.pdf", "d2": src / "sub" / "a.pdf", "d3": src / "gone.pdf"}  # d1/d2 share a file name
    for doc_id, path in paths.items():
        if doc_id != "d3":
            path.write_bytes(doc_id.encode() * 10)
        app_context.db.add_or_update_document(doc_id, {"title": f"Sách {doc_id}", "file_path": str(path), "extension": "pdf",
                                                       "file_size": 20, "created_at": 1.0})
    return paths


def test_the_plan_writes_nothing_and_names_clashes_apart(app_context, books, tmp_path):
    target = tmp_path / "all"
    plan = app_context.gather.plan(str(target), MODE_COPY)
    assert not target.exists()
    names = sorted(__import__("pathlib").Path(i.destination).name for i in plan.ready)
    assert names == ["a (2).pdf", "a.pdf"]  # two books with one file name do not overwrite each other
    assert [i.status for i in plan.items if i.doc_id == "d3"] == [STATUS_MISSING]
    assert plan.total_bytes == 40 and plan.enough_space


def test_copy_leaves_the_originals_and_the_library_alone(app_context, books, tmp_path):
    plan = app_context.gather.plan(str(tmp_path / "all"), MODE_COPY)
    result = app_context.gather.run(plan)
    assert result.done == 2 and result.skipped == 1 and not result.failed
    assert len(list((tmp_path / "all").iterdir())) == 2
    assert all(p.exists() for k, p in books.items() if k != "d3")
    assert app_context.db.get_document("d1")["file_path"] == str(books["d1"])


def test_move_relocates_the_files_and_the_library_paths(app_context, books, tmp_path):
    plan = app_context.gather.plan(str(tmp_path / "all"), MODE_MOVE)
    result = app_context.gather.run(plan)
    assert result.done == 2
    assert not books["d1"].exists() and not books["d2"].exists()
    for doc_id in ("d1", "d2"):
        row = app_context.db.get_document(doc_id)
        assert row["file_path"].startswith(str(tmp_path / "all")) and __import__("pathlib").Path(row["file_path"]).is_file()
    assert app_context.db.get_document("d3")["file_path"] == str(books["d3"])  # missing one: untouched


def test_a_book_already_in_the_folder_is_left_out(app_context, books):
    plan = app_context.gather.plan(str(books["d1"].parent), MODE_MOVE)
    assert [i.status for i in plan.items if i.doc_id == "d1"] == [STATUS_THERE]


def test_a_failing_file_is_reported_and_stays_put(app_context, books, tmp_path, monkeypatch):
    real_copy = __import__("shutil").copy2

    def flaky(src, dst, **kw):
        if str(src).endswith("a.pdf") and "sub" in str(src):
            raise PermissionError(13, "locked")
        return real_copy(src, dst, **kw)

    monkeypatch.setattr("smartdoc.application.gather_service.shutil.copy2", flaky)
    result = app_context.gather.run(app_context.gather.plan(str(tmp_path / "all"), MODE_MOVE))
    assert result.done == 1 and len(result.failed) == 1 and result.failed[0][0] == "Sách d2"
    assert books["d2"].exists() and app_context.db.get_document("d2")["file_path"] == str(books["d2"])


def test_a_copy_that_comes_out_short_is_removed_and_the_original_kept(app_context, books, tmp_path, monkeypatch):
    def short(src, dst, **kw):
        __import__("pathlib").Path(dst).write_bytes(b"x")
        return dst

    monkeypatch.setattr("smartdoc.application.gather_service.shutil.copy2", short)
    result = app_context.gather.run(app_context.gather.plan(str(tmp_path / "all"), MODE_MOVE))
    assert result.done == 0 and len(result.failed) == 2
    assert not list((tmp_path / "all").iterdir()) and books["d1"].exists()


def test_bad_targets_are_refused_and_a_watched_folder_is_warned_about(app_context, books, tmp_path):
    with pytest.raises(GatherError):
        app_context.gather.plan("", MODE_COPY)
    with pytest.raises(GatherError):
        app_context.gather.plan(str(books["d1"]), MODE_COPY)  # a file, not a folder
    app_context.config.config.watch_folders = [str(tmp_path / "src")]
    assert "theo dõi" in app_context.gather.watched_folder_warning(str(tmp_path / "src" / "new"))
    assert app_context.gather.watched_folder_warning(str(tmp_path / "elsewhere")) == ""


def test_the_dialog_previews_then_runs_and_moving_asks_first(qapp, app_context, books, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QMessageBox

    from smartdoc.presentation.gather_dialog import GatherDialog

    dialog = GatherDialog(app_context)
    assert not dialog.start_button.isEnabled() and "Chưa có gì bị thay đổi" in dialog.summary_label.text()
    dialog.folder_edit.setText(str(tmp_path / "all"))
    assert "2 sách" in dialog.summary_label.text() and "1 sách không thấy file" in dialog.summary_label.text()
    assert not (tmp_path / "all").exists() and dialog.start_button.isEnabled()

    dialog.move_radio.setChecked(True)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[1]) or QMessageBox.No)
    dialog.start_button.click()
    assert asked and books["d1"].exists() and not dialog._busy  # declined: nothing moved

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dialog.start_button.click()
    deadline = time.time() + 10
    while dialog._busy and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert "Xong: 2 sách" in dialog.result_label.text() and not books["d1"].exists()
    dialog.deleteLater()
