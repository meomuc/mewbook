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
    assert mgr.config.theme == "light"  # falls back to default, legacy key ignored


def test_worker_thread_count_and_theme_round_trip(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    mgr.config.worker_thread_count = 8
    mgr.config.theme = "dark"
    mgr.save()

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.worker_thread_count == 8
    assert reloaded.config.theme == "dark"


def test_ereader_folder_path_defaults_to_none_and_round_trips(tmp_path):
    mgr = ConfigManager(app_data_dir=tmp_path)
    assert mgr.config.ereader_folder_path is None

    mgr.config.ereader_folder_path = r"E:\Kindle\documents"
    mgr.save()

    reloaded = ConfigManager(app_data_dir=tmp_path)
    assert reloaded.config.ereader_folder_path == r"E:\Kindle\documents"
