"""TDD-015: App configuration persisted as JSON under %APPDATA%."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_DIR_NAME = "SmartDocLibrary"

# "light" and "dark" are implemented (see presentation/theme.py); "cozy" and
# "glassmorphism" from the original spec are not built yet, so they aren't
# offered as real choices anywhere in the UI.
THEME_CHOICES = ("light", "dark")

# Formats an extractor exists for (routed through PdfExtractor or
# EpubExtractor -- see application/import_queue.py). DOCX from the original
# spec's Tab 1 has no extractor at all, so it is deliberately not offered as
# a checkbox anywhere: a checkbox that can never do anything is worse than
# no checkbox.
KNOWN_EXTENSIONS = ("pdf", "epub", "mobi", "azw3")


def default_app_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".smartdoc"
    return base / APP_DIR_NAME


@dataclass
class AppConfig:
    watch_folders: list[str] = field(default_factory=list)
    theme: str = "light"
    view_mode: str = "grid"  # "grid" | "list"
    db_path: str | None = None
    cover_cache_dir: str | None = None
    worker_thread_count: int = 4
    allowed_extensions: list[str] = field(default_factory=lambda: list(KNOWN_EXTENSIONS))
    reviewer_nickname: str = ""
    # Supabase's "anon" key is meant to be public/embedded in client apps --
    # access control lives in the `reviews` table's Row Level Security
    # policies, not in keeping this secret. See application/cloud_reviews.py.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None


class ConfigManager:
    def __init__(self, app_data_dir: Path | None = None) -> None:
        self.app_data_dir = app_data_dir or default_app_data_dir()
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.app_data_dir / "settings.json"
        self.config: AppConfig = self._load()

    def _load(self) -> AppConfig:
        if not self.settings_path.exists():
            config = AppConfig(
                db_path=str(self.app_data_dir / "library.db"),
                cover_cache_dir=str(self.app_data_dir / "covers"),
            )
            self._write(config)
            return config
        raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        # Drop keys from an older schema version (e.g. a settings.json
        # written before a field was renamed/removed) instead of letting
        # them reach AppConfig(**defaults) as an unexpected keyword arg.
        known_fields = {f.name for f in fields(AppConfig)}
        defaults = asdict(AppConfig())
        defaults.update({k: v for k, v in raw.items() if k in known_fields})
        return AppConfig(**defaults)

    def _write(self, config: AppConfig) -> None:
        self.settings_path.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")

    def save(self) -> None:
        self._write(self.config)

    def add_watch_folder(self, folder_path: str) -> None:
        if folder_path not in self.config.watch_folders:
            self.config.watch_folders.append(folder_path)
            self.save()

    def remove_watch_folder(self, folder_path: str) -> None:
        if folder_path in self.config.watch_folders:
            self.config.watch_folders.remove(folder_path)
            self.save()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mgr = ConfigManager(app_data_dir=Path(tmp))
        mgr.add_watch_folder(r"D:\Ebooks")
        mgr.save()

        reloaded = ConfigManager(app_data_dir=Path(tmp))
        print("watch_folders:", reloaded.config.watch_folders)
        assert reloaded.config.watch_folders == [r"D:\Ebooks"]
