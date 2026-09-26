# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

import pytest

from smartdoc.core.app_context import AppContext
from smartdoc.core.config import ConfigManager
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.database import DatabaseManager
from smartdoc.presentation.backup_panel import BackupPanel, reason_label
from smartdoc.presentation.settings_dialog import SettingsDialog


@pytest.fixture
def file_context(tmp_path):
    db = DatabaseManager(str(tmp_path / "library.db"))
    context = AppContext(config=ConfigManager(app_data_dir=tmp_path / "appdata"), db=db)
    for n in range(3):
        db.add_or_update_document(f"d{n}", {"title": f"Sách {n}", "file_path": f"{n}.pdf", "extension": "pdf", "created_at": float(n)})
    yield context
    context.shutdown()


def _wait(qapp, panel, timeout=10.0):
    deadline = time.time() + timeout
    while panel._busy and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert not panel._busy, "the background task never reported back"


def _titles(context):
    return {r["title"] for r in context.db.connection.execute("SELECT title FROM documents")}


def test_an_in_memory_library_cannot_be_backed_up_and_says_so(qapp, app_context):
    panel = BackupPanel(app_context)
    assert not panel.backup_button.isEnabled() and not panel.restore_button.isEnabled()
    assert "bộ nhớ" in panel.status_label.text()


def test_backup_now_makes_a_backup_and_lists_it(qapp, file_context):
    panel = BackupPanel(file_context)
    assert panel.backup_list.count() == 0 and not panel.restore_button.isEnabled()

    panel.backup_button.click()
    _wait(qapp, panel)

    assert panel.backup_list.count() == 1 and "Thủ công" in panel.backup_list.item(0).text()
    assert "Đã sao lưu" in panel.status_label.text()
    assert panel.restore_button.isEnabled()  # the new backup is selected


def test_restore_asks_first_and_changes_nothing_when_declined(qapp, file_context, monkeypatch):
    panel = BackupPanel(file_context)
    panel.backup_button.click()
    _wait(qapp, panel)
    file_context.db.connection.execute("DELETE FROM documents WHERE id = 'd0'")
    file_context.db.connection.commit()
    monkeypatch.setattr(panel, "_confirm_restore", lambda info: False)

    panel.restore_button.click()

    assert not panel._busy and _titles(file_context) == {"Sách 1", "Sách 2"}


def test_a_confirmed_restore_puts_the_library_back_and_announces_it(qapp, file_context, monkeypatch):
    panel = BackupPanel(file_context)
    panel.backup_button.click()
    _wait(qapp, panel)
    file_context.db.connection.execute("DELETE FROM documents")
    file_context.db.connection.commit()
    monkeypatch.setattr(panel, "_confirm_restore", lambda info: True)
    announced = []
    file_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: announced.append(e))

    panel.restore_button.click()
    _wait(qapp, panel)

    assert _titles(file_context) == {"Sách 0", "Sách 1", "Sách 2"}
    assert announced and "Đã khôi phục" in panel.status_label.text()
    assert any("Trước khi khôi phục" in panel.backup_list.item(i).text() for i in range(panel.backup_list.count()))


def test_a_failure_is_shown_and_the_buttons_come_back(qapp, file_context, monkeypatch):
    from smartdoc.application.backup_service import BackupError

    panel = BackupPanel(file_context)
    monkeypatch.setattr(file_context.backups, "create_backup", lambda reason="manual": (_ for _ in ()).throw(BackupError("đĩa đầy")))

    panel.backup_button.click()
    _wait(qapp, panel)

    assert "đĩa đầy" in panel.status_label.text() and panel.backup_button.isEnabled()


def test_reason_labels_read_naturally():
    assert reason_label("manual") == "Thủ công"
    assert reason_label("pre-upgrade-v0-to-v2") == "Trước khi nâng cấp"
    assert reason_label("pre-restore") == "Trước khi khôi phục"


def test_settings_saves_the_retention_and_can_open_on_the_backup_tab(qapp, app_context):
    dialog = SettingsDialog(app_context, initial_tab="backup")
    assert dialog.findChild(type(dialog.backup_panel)) is dialog.backup_panel
    dialog.backup_panel.retention_spin.setValue(9)

    dialog._on_save()

    assert app_context.config.config.backup_retention == 9


def test_choosing_a_folder_sends_backups_there_and_a_bad_one_is_refused(qapp, file_context, tmp_path):
    panel = BackupPanel(file_context)
    target = tmp_path / "external"
    assert panel._set_folder(str(target)) == "" and file_context.config.config.backup_dir == str(target)
    panel._on_backup_now()
    _wait(qapp, panel)
    assert list(target.glob("library-*.db"))

    blocker = tmp_path / "plain-file"
    blocker.write_text("x")
    assert panel._set_folder(str(blocker / "sub"))  # a reason is returned
    assert file_context.config.config.backup_dir == str(target)  # the previous choice stays
    assert panel.folder_warning.text()

    panel._set_folder("")
    assert file_context.config.config.backup_dir == "" and "mặc định" in panel.folder_label.text()
