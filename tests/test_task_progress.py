# SPDX-License-Identifier: AGPL-3.0-or-later
"""Long work runs behind a "please wait" window instead of freezing the app; an old library is upgraded behind one at start-up."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from smartdoc.infrastructure import schema_migrations as sm
from smartdoc.presentation.task_progress_dialog import TaskProgressDialog, run_with_progress

_BASELINE = Path(__file__).parent / "data" / "schema_1_0_0.sql"


def _old_library(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(_BASELINE.read_text(encoding="utf-8"))
    con.execute("INSERT INTO documents (id, title, author, file_path, extension, tags, content, created_at) VALUES ('d0','Truyện Kiều','Nguyễn Du','0.epub','epub','','nội dung',1.0)")
    con.commit()
    con.close()


# -- needs_upgrade -----------------------------------------------------------------------------------------------------------

def test_only_an_existing_library_behind_this_build_needs_the_upgrade_window(tmp_path):
    assert not sm.needs_upgrade(tmp_path / "none.db")  # nothing there yet: a new library, quick
    (tmp_path / "empty.db").write_bytes(b"")
    assert not sm.needs_upgrade(tmp_path / "empty.db")
    assert not sm.needs_upgrade(":memory:")
    old = tmp_path / "old.db"
    _old_library(old)
    assert sm.needs_upgrade(old)
    from smartdoc.infrastructure.database import DatabaseManager

    db = DatabaseManager(str(old))
    db.initialize_tables()
    db.close()
    assert not sm.needs_upgrade(old)  # now current


def test_a_file_that_is_not_a_database_is_left_to_the_normal_open(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not sqlite" * 50)
    assert sm.needs_upgrade(junk) is False


# -- the dialog --------------------------------------------------------------------------------------------------------------

def test_the_work_runs_off_the_gui_thread_and_its_result_comes_back(qapp):
    seen = {}

    def work(progress):
        seen["thread"] = threading.current_thread().name
        progress(3, 10, "đang làm")
        return 42

    result, error = run_with_progress(None, title="t", message="m", work=work)
    assert (result, error) == (42, "") and seen["thread"] != threading.main_thread().name


def test_an_error_is_reported_not_swallowed_and_does_not_hang(qapp):
    def work(progress):
        raise ValueError("ổ đĩa đầy")

    result, error = run_with_progress(None, title="t", message="m", work=work)
    assert result is None and error == "ổ đĩa đầy"


def test_the_bar_is_busy_until_a_total_is_known_then_counts(qapp):
    dialog = TaskProgressDialog(None, title="t", message="m", work=lambda progress: None, hint="Xin đừng tắt máy.")
    assert dialog.bar.maximum() == 0  # the sliding "busy" bar
    dialog._on_progress(120, 1200, "Đang chuyển…")
    assert dialog.bar.maximum() == 1200 and dialog.bar.value() == 120 and dialog.bar.format() == "120 / 1.200"
    assert dialog.note_label.text() == "Đang chuyển…" and dialog.hint_label.text() == "Xin đừng tắt máy."
    assert dialog.hint_label.isVisibleTo(dialog)
    dialog.deleteLater()


def test_the_window_cannot_be_dismissed_while_the_work_runs_but_a_cancellable_one_can_ask_to_stop(qapp):
    dialog = TaskProgressDialog(None, title="t", message="m", work=lambda progress: None, cancellable=True)
    dialog.reject()  # ignored: closing would not stop the work
    assert not dialog._finished
    assert dialog.cancel_button.isVisibleTo(dialog)  # only a cancellable window shows "Dừng"
    dialog.cancel_button.click()
    assert dialog.cancelled.is_set() and not dialog.cancel_button.isEnabled()
    dialog.deleteLater()


# -- start-up ----------------------------------------------------------------------------------------------------------------

def test_an_old_library_is_upgraded_behind_the_window_and_backed_up_first(qapp, tmp_path, monkeypatch):
    from smartdoc import app as app_module
    from smartdoc.core.config import ConfigManager

    data = tmp_path / "appdata"
    config = ConfigManager(app_data_dir=data)
    _old_library(Path(config.config.db_path))
    monkeypatch.setattr(app_module, "ConfigManager", lambda: config)
    shown = []
    real = app_module.run_with_progress
    monkeypatch.setattr(app_module, "run_with_progress", lambda *a, **k: shown.append(k["message"]) or real(*a, **k))

    context = app_module._open_library()
    try:
        assert shown and "nâng cấp" in shown[0]
        assert context.db.schema_version() == sm.latest_version()
        assert list((Path(config.config.db_path).parent / "backups").glob("*pre-upgrade*")), "the library was backed up first"
        assert context.db.get_document("d0")["title"] == "Truyện Kiều"
    finally:
        context.shutdown()


def test_a_current_library_opens_without_the_window(qapp, tmp_path, monkeypatch):
    from smartdoc import app as app_module
    from smartdoc.core.config import ConfigManager

    config = ConfigManager(app_data_dir=tmp_path / "appdata")
    monkeypatch.setattr(app_module, "ConfigManager", lambda: config)
    monkeypatch.setattr(app_module, "run_with_progress", lambda *a, **k: pytest.fail("no upgrade window for a current library"))
    context = app_module._open_library()  # a new library: created current
    context.shutdown()
    context = app_module._open_library()  # and again: nothing to upgrade
    context.shutdown()
