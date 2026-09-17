from smartdoc.presentation.settings_dialog import SettingsDialog


class _FakeWatcher:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self.debounce_seconds: float | None = None

    def add_folder(self, path: str) -> None:
        self.added.append(path)

    def remove_folder(self, path: str) -> None:
        self.removed.append(path)

    def set_debounce_seconds(self, seconds: float) -> None:
        self.debounce_seconds = seconds


class _FakeImportManager:
    def __init__(self) -> None:
        self.restarted_with: int | None = None

    def active_worker_count(self) -> int:
        return 3

    def restart(self, num_workers: int) -> None:
        self.restarted_with = num_workers


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


def test_theme_change_sets_appearance_changed_flag_no_restart_needed(qapp, app_context):
    assert app_context.config.config.theme == "light"
    dialog = SettingsDialog(app_context)
    dialog.theme_combo.setCurrentIndex(1)  # "dark"

    dialog._on_save()  # must not show any blocking dialog -- nothing to stub out anymore

    assert app_context.config.config.theme == "dark"
    assert dialog.appearance_changed is True


def test_no_changes_does_not_set_appearance_changed_flag(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_save()
    assert dialog.appearance_changed is False


def test_worker_thread_count_saved_and_applied_live(qapp, app_context):
    import_manager = _FakeImportManager()
    dialog = SettingsDialog(app_context, import_manager=import_manager)
    dialog.worker_spin.setValue(8)
    dialog._on_save()
    assert app_context.config.config.worker_thread_count == 8
    assert import_manager.restarted_with == 8
    assert dialog.appearance_changed is False  # thread count is a live-apply setting, not an appearance one


def test_worker_thread_count_unchanged_does_not_restart_import_manager(qapp, app_context):
    import_manager = _FakeImportManager()
    dialog = SettingsDialog(app_context, import_manager=import_manager)
    dialog._on_save()
    assert import_manager.restarted_with is None


def test_font_size_change_saved_and_sets_appearance_changed_flag(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.font_size_spin.setValue(14)
    dialog._on_save()
    assert app_context.config.config.font_size == 14
    assert dialog.appearance_changed is True


def test_debounce_seconds_change_saved_and_applied_live(qapp, app_context):
    watcher = _FakeWatcher()
    dialog = SettingsDialog(app_context, watcher=watcher)
    dialog.debounce_spin.setValue(5.0)
    dialog._on_save()
    assert app_context.config.config.watch_debounce_seconds == 5.0
    assert watcher.debounce_seconds == 5.0
    assert dialog.appearance_changed is False


def test_debounce_has_no_meaningfully_low_upper_bound(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.debounce_spin.setValue(3600.0)  # one hour -- must be accepted, not clamped down
    assert dialog.debounce_spin.value() == 3600.0


def test_ai_tab_starts_unconfigured_by_default(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert dialog.ai_provider_combo.currentData() is None
    assert dialog.ai_api_key_edit.text() == ""


def test_ai_tab_preloads_existing_provider_and_key(qapp, app_context):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "existing-key"

    dialog = SettingsDialog(app_context)

    assert dialog.ai_provider_combo.currentData() == "gemini"
    assert dialog.ai_api_key_edit.text() == "existing-key"


def test_saving_ai_provider_and_key_persists_to_config(qapp, app_context):
    dialog = SettingsDialog(app_context)
    index = dialog.ai_provider_combo.findData("openai")
    dialog.ai_provider_combo.setCurrentIndex(index)
    dialog.ai_api_key_edit.setText("sk-new-key")

    dialog._on_save()

    assert app_context.config.config.ai_provider == "openai"
    assert app_context.config.config.ai_api_key == "sk-new-key"


def test_clearing_ai_key_saves_as_none(qapp, app_context):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "existing-key"
    dialog = SettingsDialog(app_context)
    dialog.ai_api_key_edit.setText("   ")

    dialog._on_save()

    assert app_context.config.config.ai_api_key is None


def test_performance_tab_shows_active_worker_count(qapp, app_context):
    dialog = SettingsDialog(app_context, import_manager=_FakeImportManager())
    assert "3" in dialog.performance_status_label.text()


def test_performance_tab_shows_zero_active_when_no_import_manager(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert "0" in dialog.performance_status_label.text()
