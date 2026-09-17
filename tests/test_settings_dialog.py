from PySide6.QtWidgets import QMessageBox

from smartdoc.presentation.settings_dialog import SettingsDialog


class _FakeWatcher:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []

    def add_folder(self, path: str) -> None:
        self.added.append(path)

    def remove_folder(self, path: str) -> None:
        self.removed.append(path)


def test_extension_checkboxes_reflect_current_config(qapp, app_context):
    app_context.config.config.allowed_extensions = ["pdf"]
    dialog = SettingsDialog(app_context)
    assert dialog._extension_checkboxes["pdf"].isChecked()
    assert not dialog._extension_checkboxes["epub"].isChecked()


def test_saving_unchecked_extension_removes_it_from_config(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._extension_checkboxes["epub"].setChecked(False)

    dialog._on_save()

    assert "epub" not in app_context.config.config.allowed_extensions
    assert "pdf" in app_context.config.config.allowed_extensions


def test_folder_list_starts_populated_from_config(qapp, app_context):
    app_context.config.add_watch_folder(r"D:\Ebooks")
    dialog = SettingsDialog(app_context)
    assert dialog.folder_list.count() == 1
    assert dialog.folder_list.item(0).text() == r"D:\Ebooks"


def test_removing_folder_in_dialog_and_saving_updates_config_and_watcher(qapp, app_context):
    app_context.config.add_watch_folder(r"D:\Ebooks")
    watcher = _FakeWatcher()
    dialog = SettingsDialog(app_context, watcher=watcher)

    dialog.folder_list.takeItem(0)
    dialog._on_save()

    assert app_context.config.config.watch_folders == []
    assert watcher.removed == [r"D:\Ebooks"]
    assert watcher.added == []


def test_theme_change_sets_restart_flag(qapp, app_context, monkeypatch):
    # QMessageBox.information() is modal and would hang the offscreen test
    # platform forever waiting for a click that never comes, so it's
    # stubbed out the same way QMessageBox.question() is in the context
    # menu tests.
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    assert app_context.config.config.theme == "light"
    dialog = SettingsDialog(app_context)
    dialog.theme_combo.setCurrentIndex(1)  # "dark"

    dialog._on_save()

    assert app_context.config.config.theme == "dark"
    assert dialog._restart_needed is True


def test_no_changes_does_not_set_restart_flag(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_save()
    assert dialog._restart_needed is False


def test_worker_thread_count_saved(qapp, app_context, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    dialog = SettingsDialog(app_context)
    dialog.worker_spin.setValue(8)
    dialog._on_save()
    assert app_context.config.config.worker_thread_count == 8


def test_font_size_change_saved_and_sets_restart_flag(qapp, app_context, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    dialog = SettingsDialog(app_context)
    dialog.font_size_spin.setValue(14)
    dialog._on_save()
    assert app_context.config.config.font_size == 14
    assert dialog._restart_needed is True


def test_debounce_seconds_change_saved(qapp, app_context, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    dialog = SettingsDialog(app_context)
    dialog.debounce_spin.setValue(5.0)
    dialog._on_save()
    assert app_context.config.config.watch_debounce_seconds == 5.0
    assert dialog._restart_needed is True


class _FakeImportManager:
    def active_worker_count(self) -> int:
        return 3


def test_performance_tab_shows_active_worker_count(qapp, app_context):
    dialog = SettingsDialog(app_context, import_manager=_FakeImportManager())
    assert "3" in dialog.performance_status_label.text()


def test_performance_tab_shows_zero_active_when_no_import_manager(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert "0" in dialog.performance_status_label.text()
