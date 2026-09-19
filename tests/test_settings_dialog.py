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


def test_ereader_folder_field_starts_populated_from_config(qapp, app_context):
    app_context.config.config.ereader_folder_path = r"E:\Kindle\documents"
    dialog = SettingsDialog(app_context)
    assert dialog.ereader_folder_edit.text() == r"E:\Kindle\documents"


def test_choosing_ereader_folder_and_saving_updates_config(qapp, app_context, monkeypatch):
    dialog = SettingsDialog(app_context)
    monkeypatch.setattr(
        "smartdoc.presentation.settings_dialog.QFileDialog.getExistingDirectory",
        lambda *a, **k: r"E:\Kobo\books",
    )

    dialog._on_choose_ereader_folder()
    dialog._on_save()

    assert app_context.config.config.ereader_folder_path == r"E:\Kobo\books"


def test_cancelling_ereader_folder_picker_leaves_config_unchanged(qapp, app_context, monkeypatch):
    app_context.config.config.ereader_folder_path = r"E:\Kindle\documents"
    dialog = SettingsDialog(app_context)
    monkeypatch.setattr(
        "smartdoc.presentation.settings_dialog.QFileDialog.getExistingDirectory", lambda *a, **k: ""
    )

    dialog._on_choose_ereader_folder()
    dialog._on_save()

    assert app_context.config.config.ereader_folder_path == r"E:\Kindle\documents"


def test_theme_change_sets_appearance_changed_flag_no_restart_needed(qapp, app_context):
    assert app_context.config.config.theme == "broadsheet"
    dialog = SettingsDialog(app_context)
    dialog.theme_combo.setCurrentIndex(2)  # "inkynight"

    dialog._on_save()  # must not show any blocking dialog -- nothing to stub out anymore

    assert app_context.config.config.theme == "inkynight"
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


def test_cover_search_tab_starts_unconfigured_by_default(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert dialog.google_image_api_key_edit.text() == ""
    assert dialog.google_image_cx_edit.text() == ""


def test_saving_google_image_search_config_persists(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.google_image_api_key_edit.setText("AIza-fake-key")
    dialog.google_image_cx_edit.setText("012345:abcdef")

    dialog._on_save()

    assert app_context.config.config.google_image_api_key == "AIza-fake-key"
    assert app_context.config.config.google_image_search_cx == "012345:abcdef"


def test_clearing_google_image_key_saves_as_none(qapp, app_context):
    app_context.config.config.google_image_api_key = "existing-key"
    dialog = SettingsDialog(app_context)
    dialog.google_image_api_key_edit.setText("   ")

    dialog._on_save()

    assert app_context.config.config.google_image_api_key is None


def test_ai_provider_guide_updates_when_provider_changes(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert dialog.ai_provider_guide_label.text() == ""  # "(Chưa cấu hình)" has no guide

    index = dialog.ai_provider_combo.findData("gemini")
    dialog.ai_provider_combo.setCurrentIndex(index)
    assert "aistudio.google.com" in dialog.ai_provider_guide_label.text()

    index = dialog.ai_provider_combo.findData("openai")
    dialog.ai_provider_combo.setCurrentIndex(index)
    assert "platform.openai.com" in dialog.ai_provider_guide_label.text()


def test_test_connection_without_provider_shows_message(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_test_connection()
    assert "chọn" in dialog.connection_status_label.text().lower()


def test_test_connection_success_updates_status_label(qapp, app_context, monkeypatch):
    monkeypatch.setattr("smartdoc.presentation.settings_dialog.test_connection", lambda provider, key: None)
    dialog = SettingsDialog(app_context)
    index = dialog.ai_provider_combo.findData("gemini")
    dialog.ai_provider_combo.setCurrentIndex(index)
    dialog.ai_api_key_edit.setText("fake-key")

    dialog._on_connection_test_finished(True, "✅ Kết nối thành công!")

    assert "thành công" in dialog.connection_status_label.text()
    assert dialog.test_connection_button.isEnabled()


def test_test_connection_failure_updates_status_label(qapp, app_context):
    from smartdoc.application.ai_summary import AISummaryError

    dialog = SettingsDialog(app_context)
    dialog._on_connection_test_finished(False, f"❌ {AISummaryError('bad key')}")

    assert "bad key" in dialog.connection_status_label.text()


def test_content_font_tab_defaults_to_no_change(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_save()
    assert dialog.appearance_changed is False
    assert app_context.config.config.content_font_family is None
    assert app_context.config.config.content_text_color is None


def test_content_font_size_change_saved_separately_from_app_font(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.content_font_size_spin.setValue(18)

    dialog._on_save()

    assert app_context.config.config.content_font_size == 18
    assert app_context.config.config.font_size == 10  # app chrome font untouched
    assert dialog.appearance_changed is True


def test_content_text_color_picker_updates_and_saves(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert dialog._content_text_color is None

    from PySide6.QtGui import QColor

    dialog._content_text_color = "#ff0000"
    dialog._update_color_swatch()
    dialog._on_save()

    assert app_context.config.config.content_text_color == "#ff0000"
    assert QColor(dialog.content_color_swatch.styleSheet().split(";")[0].split(":")[1].strip()) == QColor("#ff0000")


def test_reset_content_color_clears_it(qapp, app_context):
    app_context.config.config.content_text_color = "#ff0000"
    dialog = SettingsDialog(app_context)
    assert dialog._content_text_color == "#ff0000"

    dialog._on_reset_content_color()

    assert dialog._content_text_color is None


def test_performance_tab_shows_active_worker_count(qapp, app_context):
    dialog = SettingsDialog(app_context, import_manager=_FakeImportManager())
    assert "3" in dialog.performance_status_label.text()


def test_performance_tab_shows_zero_active_when_no_import_manager(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert "0" in dialog.performance_status_label.text()


def test_cloud_review_tab_starts_unconfigured_and_saves(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert dialog.supabase_url_edit.text() == ""
    assert dialog.supabase_key_edit.text() == ""

    dialog.supabase_url_edit.setText("https://demo.supabase.co/")
    dialog.supabase_key_edit.setText("anon-key-123")
    dialog._on_save()

    # The trailing slash is stripped -- cloud_reviews builds URLs by
    # appending "/rest/v1/...", so leaving it would produce a double slash.
    assert app_context.config.config.supabase_url == "https://demo.supabase.co"
    assert app_context.config.config.supabase_anon_key == "anon-key-123"


def test_cloud_review_tab_preloads_existing_config(qapp, app_context):
    app_context.config.config.supabase_url = "https://saved.supabase.co"
    app_context.config.config.supabase_anon_key = "saved-key"

    dialog = SettingsDialog(app_context)

    assert dialog.supabase_url_edit.text() == "https://saved.supabase.co"
    assert dialog.supabase_key_edit.text() == "saved-key"


def test_supabase_test_result_is_shown_in_the_status_label(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_supabase_test_finished(False, "❌ View 'review_stats' không tồn tại")
    assert "review_stats" in dialog.supabase_test_status_label.text()
    assert "crimson" in dialog.supabase_test_status_label.styleSheet()


def test_cover_test_result_is_shown_in_the_status_label(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_cover_test_finished(True, "✅ Kết nối thành công!")
    assert "thành công" in dialog.cover_test_status_label.text()
    assert "green" in dialog.cover_test_status_label.styleSheet()


def _theme_index(dialog, key):
    from smartdoc.presentation.settings_dialog import THEME_CHOICES

    return list(THEME_CHOICES).index(key)


def test_changing_theme_clears_a_font_saved_earlier(qapp, app_context):
    app_context.config.config.theme = "broadsheet"
    app_context.config.config.font_family = "Arial"
    app_context.config.config.content_font_family = "Arial"
    dialog = SettingsDialog(app_context)

    dialog.theme_combo.setCurrentIndex(_theme_index(dialog, "retro_tech"))
    dialog._on_save()

    assert app_context.config.config.theme == "retro_tech"
    assert app_context.config.config.font_family is None  # so the theme's own font applies
    assert app_context.config.config.content_font_family is None
    assert dialog.appearance_changed is True


def _pick_font(combo, family):
    """Simulates the user choosing `family` in a font picker. The test
    environment has no fonts installed, so a real QFontComboBox can't hold
    any family; this stands in for one that can."""
    from PySide6.QtGui import QFont

    combo.currentFont = lambda: QFont(family)
    combo.currentFontChanged.emit(QFont(family))


def test_font_picked_in_the_same_visit_wins_over_the_theme_font(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.theme_combo.setCurrentIndex(_theme_index(dialog, "retro_tech"))
    _pick_font(dialog.font_combo, "Arial")
    dialog._on_save()

    assert app_context.config.config.font_family == "Arial"
    assert app_context.config.config.content_font_family is None  # only the one that was touched


def test_font_boxes_follow_the_selected_theme_until_the_user_picks_one(qapp, app_context):
    from smartdoc.presentation.theme import THEMES, resolve_font_family

    dialog = SettingsDialog(app_context)
    shown = {"app": [], "content": []}
    dialog.font_combo.setCurrentFont = lambda font: shown["app"].append(font.family())
    dialog.content_font_combo.setCurrentFont = lambda font: shown["content"].append(font.family())

    dialog.theme_combo.setCurrentIndex(_theme_index(dialog, "retro_tech"))
    expected = resolve_font_family(THEMES["retro_tech"])
    assert shown == {"app": [expected], "content": [expected]}
    assert app_context.config.config.font_family is None  # previewing is not saving

    _pick_font(dialog.font_combo, "Arial")  # from here on the app font is the user's
    dialog.theme_combo.setCurrentIndex(_theme_index(dialog, "japandi"))
    assert shown["app"] == [expected]
    assert shown["content"] == [expected, resolve_font_family(THEMES["japandi"])]


def test_saving_without_touching_fonts_keeps_them_unset(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog._on_save()
    assert app_context.config.config.font_family is None
    assert app_context.config.config.content_font_family is None


def test_metadata_write_options_default_off_and_are_saved(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert not dialog.metadata_write_check.isChecked() and dialog.metadata_backup_spin.value() == 3

    dialog.metadata_write_check.setChecked(True)
    dialog.metadata_backup_spin.setValue(7)
    dialog._on_save()

    config = app_context.config.config
    assert config.metadata_write_to_file_default is True and config.metadata_backup_keep == 7
