import codecs
import json

from smartdoc.core.config import AppConfig, ConfigManager, KNOWN_EXTENSIONS


def test_first_load_creates_defaults_with_real_paths(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.db_path is not None
    assert mgr.config.cover_cache_dir is not None
    assert mgr.config.allowed_extensions == list(KNOWN_EXTENSIONS)
    assert (tmp_path / "settings.json").exists()


def test_add_and_remove_watch_folder_persists(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    mgr.add_watch_folder(r"D:\Ebooks")
    assert r"D:\Ebooks" in mgr.config.watch_folders

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert r"D:\Ebooks" in reloaded.config.watch_folders

    reloaded.remove_watch_folder(r"D:\Ebooks")
    assert reloaded.config.watch_folders == []

    reloaded_again = ConfigManager(app_data_dir=tmp_path)
    assert reloaded_again.config.watch_folders == []


def test_add_watch_folder_does_not_duplicate(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    mgr.add_watch_folder(r"D:\Ebooks")
    mgr.add_watch_folder(r"D:\Ebooks")
    assert mgr.config.watch_folders == [r"D:\Ebooks"]


def test_loading_settings_with_unknown_legacy_keys_does_not_crash(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"watch_folders": ["C:/Books"], "dark_mode": True, "some_removed_field": "x"}),
        encoding="utf-8",
    )
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.watch_folders == ["C:/Books"]
    assert mgr.config.theme == "broadsheet"  # falls back to default, legacy key ignored


def test_worker_thread_count_and_theme_round_trip(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    mgr.config.worker_thread_count = 8
    mgr.config.theme = "inkynight"
    mgr.save()

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.worker_thread_count == 8
    assert reloaded.config.theme == "inkynight"


def test_legacy_light_dark_theme_migrates_to_new_names(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)  # creates settings.json
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    raw["theme"] = "light"
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.theme == "broadsheet"

    raw["theme"] = "dark"
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    reloaded_dark = ConfigManager(app_data_dir=tmp_path)
    assert reloaded_dark.config.theme == "inkynight"

    # A value that cannot be a theme id is reset; a well-formed id is kept (it may be a theme package added later --
    # the core layer cannot see the packages), and ThemeManager falls back to the default look if it is gone.
    raw["theme"] = "Not A Theme!"
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    assert ConfigManager(app_data_dir=tmp_path).config.theme == "broadsheet"

    raw["theme"] = "some-removed-theme"
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    assert ConfigManager(app_data_dir=tmp_path).config.theme == "some-removed-theme"


def test_ereader_folder_path_defaults_to_none_and_round_trips(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.ereader_folder_path is None

    mgr.config.ereader_folder_path = r"E:\Kindle\documents"
    mgr.save()

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.ereader_folder_path == r"E:\Kindle\documents"


def test_api_keys_are_encrypted_on_disk_but_plaintext_in_memory(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    mgr.config.ai_api_key = "sk-super-secret"
    mgr.config.google_image_api_key = "AIza-also-secret"
    mgr.save()

    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "sk-super-secret" not in raw["ai_api_key"]
    assert "AIza-also-secret" not in raw["google_image_api_key"]

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.ai_api_key == "sk-super-secret"
    assert reloaded.config.google_image_api_key == "AIza-also-secret"


def test_legacy_plaintext_api_key_still_loads(tmp_path):
    """A settings.json written by a pre-encryption version of this app has
    the key stored as plain text -- upgrading must not treat that as
    garbage and silently drop it."""
    mgr = ConfigManager(app_data_dir=tmp_path)  # creates settings.json + the secret keyfile
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    raw["ai_api_key"] = "plain-legacy-key"
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.ai_api_key == "plain-legacy-key"


def test_eula_not_accepted_by_default(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.eula_accepted is False

    mgr.config.eula_accepted = True
    mgr.save()

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.eula_accepted is True


def test_smart_classify_settings_default_and_round_trip(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.smart_classify_on_import == "ask"
    assert 2000 <= mgr.config.smart_classify_max_words <= 5000
    mgr.config.smart_classify_on_import = "always"
    mgr.config.smart_classify_max_words = 4000
    mgr.save()
    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.smart_classify_on_import == "always"
    assert reloaded.config.smart_classify_max_words == 4000


def test_a_mistyped_smart_classify_choice_falls_back_to_asking(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"smart_classify_on_import": "alwayz"}), encoding="utf-8")
    assert ConfigManager(app_data_dir=tmp_path).config.smart_classify_on_import == "ask"


def test_a_settings_file_saved_with_a_bom_still_loads(tmp_path):
    # Notepad and Windows PowerShell 5 write "UTF-8 with BOM"; that used to crash startup.
    (tmp_path / "settings.json").write_bytes(codecs.BOM_UTF8 + b'{"theme": "broadsheet", "eula_accepted": true}')
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.eula_accepted is True


def test_a_settings_file_without_db_path_gets_the_default_location(tmp_path):
    # Without a db_path the library used to be created in the current working directory.
    (tmp_path / "settings.json").write_text('{"eula_accepted": true}', encoding="utf-8")
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.db_path == str(tmp_path / "library.db")


def test_sources_with_unclear_terms_are_disabled_by_default_and_the_choice_persists(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.disabled_cover_sources == ["Tiki", "Apple Books"]

    mgr.config.disabled_cover_sources = ["Tiki"]
    mgr.save()
    assert ConfigManager(app_data_dir=tmp_path).config.disabled_cover_sources == ["Tiki"]


def test_error_reports_are_off_until_asked_for_and_the_choice_persists(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert (mgr.config.error_report_mode, mgr.config.error_report_consent_version, mgr.config.error_report_install_id) == ("ask", 0, "")

    mgr.config.error_report_mode = "never"
    mgr.save()
    assert ConfigManager(app_data_dir=tmp_path).config.error_report_mode == "never"


def test_a_mistyped_error_report_mode_falls_back_to_asking_never_to_always(tmp_path):
    (tmp_path / "settings.json").write_text('{"error_report_mode": "alwayz"}', encoding="utf-8")
    assert ConfigManager(app_data_dir=tmp_path).config.error_report_mode == "ask"


def test_a_fresh_install_keeps_one_backup_per_book_but_a_saved_number_is_respected(tmp_path):
    assert ConfigManager(app_data_dir=tmp_path / "new").config.metadata_backup_keep == 1

    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "settings.json").write_text(json.dumps({"metadata_backup_keep": 3}), encoding="utf-8")
    assert ConfigManager(app_data_dir=tmp_path / "old").config.metadata_backup_keep == 3  # an existing choice stays
