from smartdoc.presentation.settings_dialog import SettingsDialog

_STUB = "test-value"  # a non-empty stand-in for tests that need a pre-filled config field


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


def test_ai_tab_preloads_existing_provider_and_credential(qapp, app_context):
    app_context.config.config.ai_provider = "gemini"
    setattr(app_context.config.config, "ai_api_key", _STUB)

    dialog = SettingsDialog(app_context)

    assert dialog.ai_provider_combo.currentData() == "gemini"
    assert dialog.ai_api_key_edit.text() == _STUB


def test_saving_ai_provider_and_key_persists_to_config(qapp, app_context):
    dialog = SettingsDialog(app_context)
    index = dialog.ai_provider_combo.findData("openai")
    dialog.ai_provider_combo.setCurrentIndex(index)
    dialog.ai_api_key_edit.setText("new-fake-key")

    dialog._on_save()

    assert app_context.config.config.ai_provider == "openai"
    assert app_context.config.config.ai_api_key == "new-fake-key"


def test_clearing_ai_credential_saves_as_none(qapp, app_context):
    app_context.config.config.ai_provider = "gemini"
    setattr(app_context.config.config, "ai_api_key", _STUB)
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
    dialog.google_image_api_key_edit.setText("test-gimg-cred")
    dialog.google_image_cx_edit.setText("012345:abcdef")

    dialog._on_save()

    assert app_context.config.config.google_image_api_key == "test-gimg-cred"
    assert app_context.config.config.google_image_search_cx == "012345:abcdef"


def test_clearing_google_image_credential_saves_as_none(qapp, app_context):
    setattr(app_context.config.config, "google_image_api_key", _STUB)
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


def test_ollama_connection_result_is_published_for_the_status_bar(qapp, app_context):
    from smartdoc.core.event_bus import AiConnectionChangedEvent

    seen = []
    app_context.event_bus.subscribe(AiConnectionChangedEvent, seen.append)
    dialog = SettingsDialog(app_context)

    dialog._tested_provider = "ollama"
    dialog._on_connection_test_finished(True, "ok")
    dialog._on_connection_test_finished(False, "down")
    dialog._tested_provider = "gemini"  # key-based providers do not report
    dialog._on_connection_test_finished(True, "ok")

    assert [e.connected for e in seen] == [True, False]


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


def test_cover_test_result_is_shown_in_the_status_label(qapp, app_context):
    from smartdoc.presentation.theme_manager import theme_manager

    dialog = SettingsDialog(app_context)
    dialog._on_cover_test_finished(True, "✅ Kết nối thành công!")
    assert "thành công" in dialog.cover_test_status_label.text()
    # The theme's own "ok" token, not a hardcoded CSS color name -- stays readable on every theme (task A1).
    assert theme_manager().token("ok") in dialog.cover_test_status_label.styleSheet()


def _theme_index(dialog, key):
    from smartdoc.core.config import THEME_CHOICES

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
    assert not dialog.metadata_write_check.isChecked()

    dialog.metadata_write_check.setChecked(True)
    dialog._on_save()

    assert app_context.config.config.metadata_write_to_file_default is True



def test_cover_source_checkboxes_reflect_config_and_unclear_sources_start_off(qapp, app_context):
    dialog = SettingsDialog(app_context)
    boxes = dialog._cover_source_checkboxes
    assert not boxes["Tiki"].isChecked() and not boxes["Apple Books"].isChecked()
    assert boxes["Open Library"].isChecked() and boxes["Google Books"].isChecked()


def test_saving_source_choices_updates_disabled_cover_sources(qapp, app_context):
    app_context.config.config.disabled_cover_sources = ["Tiki", "Google Images"]
    dialog = SettingsDialog(app_context)
    dialog._cover_source_checkboxes["Apple Books"].setChecked(False)
    dialog._cover_source_checkboxes["Tiki"].setChecked(True)

    dialog._on_save()

    # the ticked Tiki is enabled, the unticked Apple Books disabled, and the entry without a checkbox is kept
    assert sorted(app_context.config.config.disabled_cover_sources) == ["Apple Books", "Google Images"]


# --- Cài đặt -> Quản lý file: format chips in a wrapping row; the folder box sized to its content ---


def test_extension_checkboxes_sit_in_one_row_when_there_is_room(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.resize(700, 600)
    dialog.show()
    qapp.processEvents()

    boxes = list(dialog._extension_checkboxes.values())
    assert len({box.geometry().top() for box in boxes}) == 1  # side by side, not a column
    assert len({box.geometry().left() for box in boxes}) == len(boxes)


def test_extension_checkboxes_wrap_inside_the_frame_when_the_window_is_narrow(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.resize(700, 600)
    dialog.show()
    qapp.processEvents()
    flow = dialog.extension_flow
    one_box_width = max(box.sizeHint().width() for box in dialog._extension_checkboxes.values())

    # The dialog cannot shrink below its own minimum width, so squeeze the row itself: room for two chips per line.
    flow.setFixedWidth(one_box_width * 2 + 16)
    qapp.processEvents()

    boxes = list(dialog._extension_checkboxes.values())
    assert len({box.geometry().top() for box in boxes}) > 1  # wrapped onto more lines
    assert all(flow.rect().contains(box.geometry()) for box in boxes)  # none spills out of the frame


def _folder_box_height(qapp, app_context, count):
    app_context.config.config.watch_folders = [rf"D:\Books{i}" for i in range(count)]
    dialog = SettingsDialog(app_context)
    dialog.resize(700, 700)
    dialog.show()
    qapp.processEvents()
    return dialog.folder_list.height(), dialog


def test_folder_box_grows_with_the_number_of_folders_then_stops_and_scrolls(qapp, app_context):
    heights = {n: _folder_box_height(qapp, app_context, n)[0] for n in (1, 3, 5, 9)}

    assert heights[1] < heights[3] < heights[5]  # fits the real count
    assert heights[9] == heights[5]  # capped at five rows
    _, dialog = _folder_box_height(qapp, app_context, 9)
    assert dialog.folder_list.verticalScrollBar().maximum() > 0  # the rest scrolls
    _, few = _folder_box_height(qapp, app_context, 3)
    assert few.folder_list.verticalScrollBar().maximum() == 0  # nothing to scroll


def test_folder_box_follows_added_and_removed_folders(qapp, app_context):
    before, dialog = _folder_box_height(qapp, app_context, 1)
    for i in range(3):
        dialog.folder_list.addItem(rf"E:\More{i}")
        dialog._fit_folder_list()
    qapp.processEvents()
    assert dialog.folder_list.height() > before

    qapp.processEvents()
    grown = dialog.folder_list.height()
    for _ in range(3):  # the list selects one folder at a time
        dialog.folder_list.setCurrentRow(0)
        dialog._on_remove_folder()
    qapp.processEvents()
    assert dialog.folder_list.height() < grown


def test_a_full_folder_box_does_not_push_the_other_settings_off_the_window(qapp, app_context):
    _, few = _folder_box_height(qapp, app_context, 1)
    _, many = _folder_box_height(qapp, app_context, 40)
    # 40 folders may add at most four more rows over the one-folder layout, never 40 rows.
    row = many.folder_list.sizeHintForRow(0)
    assert many.sizeHint().height() - few.sizeHint().height() <= row * 5


# --- the community-review page: on/off, nickname, and what is (not) sent ---


def test_settings_have_nine_pages_in_the_designed_order(qapp, app_context):
    dialog = SettingsDialog(app_context)
    names = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert names == ["Quản lý File", "Giao diện", "Hiệu năng", "Phân loại", "Kết nối & Dịch vụ",
                     "Thông tin sách", "Sao lưu", "Cập nhật & ủng hộ", "Quyền riêng tư"]
    assert dialog.pills.count() == 9 and not hasattr(dialog, "supabase_url_edit")


def test_the_pills_drive_the_pages(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.pills.setCurrentRow(2)
    assert dialog.tabs.currentIndex() == 2
    dialog.tabs.setCurrentIndex(5)
    assert dialog.pills.currentRow() == 5


def test_the_community_page_keeps_the_switch_and_the_nickname(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.community_reviews_check.setChecked(False)
    dialog.reviewer_nickname_edit.setText("Mèo Mực")
    dialog._on_save()
    assert app_context.config.config.community_reviews_enabled is False
    assert app_context.config.config.reviewer_nickname == "Mèo Mực"


def test_changes_are_saved_as_they_are_made(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.worker_spin.setValue(7)
    assert dialog._autosave_timer.isActive()
    dialog._autosave_timer.stop()
    dialog._apply_settings()  # what the timer does when it fires
    assert app_context.config.config.worker_thread_count == 7
    assert dialog.saved_label.text() == "Thay đổi được lưu ngay."


def test_the_performance_page_saves_its_new_options(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.page_size_combo.setCurrentIndex(dialog.page_size_combo.findData(48))
    dialog.reader_windows_combo.setCurrentIndex(dialog.reader_windows_combo.findData(3))
    dialog.content_pages_combo.setCurrentIndex(dialog.content_pages_combo.findData(200))
    dialog.cover_cache_combo.setCurrentIndex(dialog.cover_cache_combo.findData(600))
    dialog._on_save()
    config = app_context.config.config
    assert (config.page_size, config.max_reader_windows, config.content_search_pages, config.cover_cache_mb) == (48, 3, 200, 600)


def test_the_theme_cards_drive_the_theme_and_show_the_current_one(qapp, app_context):
    dialog = SettingsDialog(app_context)
    from smartdoc.presentation.theme_manager import available_themes

    assert len(dialog.theme_cards) == len(available_themes()) >= 7  # one card per theme package
    assert dialog.theme_cards["broadsheet"].is_selected()
    dialog.theme_cards["inkynight"].chosen.emit("inkynight")
    assert dialog.theme_combo.currentData() == "inkynight" and dialog.theme_cards["inkynight"].is_selected()
    assert not dialog.theme_cards["broadsheet"].is_selected()
    dialog._on_save()
    assert app_context.config.config.theme == "inkynight" and dialog.appearance_changed


def test_coming_soon_rows_are_disabled(qapp, app_context):
    """The 3 classify-tab "Sắp có" rows were replaced with real controls; remaining badges (if any)
    must still be disabled -- this test ensures no badge row is accidentally left enabled."""
    from PySide6.QtWidgets import QLabel

    dialog = SettingsDialog(app_context)
    badges = [label for label in dialog.findChildren(QLabel) if label.text() == "Sắp có"]
    assert all(not label.parent().isEnabled() for label in badges)


def test_saving_settings_keeps_an_existing_community_review_connection(qapp, app_context):
    app_context.config.config.supabase_url = "https://saved.supabase.co"
    app_context.config.config.supabase_anon_key = "saved-key"

    dialog = SettingsDialog(app_context)
    dialog._on_save()

    assert app_context.config.config.supabase_url == "https://saved.supabase.co"
    assert app_context.config.config.supabase_anon_key == "saved-key"


def test_auto_cover_on_import_is_saved(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.auto_cover_check.setChecked(True)
    dialog._on_save()
    assert app_context.config.config.auto_cover_on_import is True
    dialog.auto_cover_check.setChecked(False)
    dialog._on_save()
    assert app_context.config.config.auto_cover_on_import is False


def test_community_rating_badge_is_saved(qapp, app_context):
    dialog = SettingsDialog(app_context)
    dialog.community_badge_check.setChecked(False)
    dialog._on_save()
    assert app_context.config.config.show_community_rating_badge is False
    dialog.community_badge_check.setChecked(True)
    dialog._on_save()
    assert app_context.config.config.show_community_rating_badge is True
