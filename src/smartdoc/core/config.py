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

# AI providers with a well-known, well-documented REST API a user can plug
# their own key into (see application/ai_summary.py). Kept to a fixed,
# vetted list rather than a free-text "custom endpoint" field -- matches
# the request for "phổ biến hiện có" (the popular ones that already exist)
# rather than a generic (and much harder to get right/secure) integration.
AI_PROVIDER_CHOICES = ("gemini", "openai", "anthropic")
AI_PROVIDER_DISPLAY_NAMES = {
    "gemini": "Google Gemini",
    "openai": "OpenAI (ChatGPT)",
    "anthropic": "Anthropic Claude",
}


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
    # Optional list-view columns beyond the mandatory Title -- see
    # presentation/library_view.py's OPTIONAL_COLUMNS for the valid keys.
    visible_columns: list[str] = field(default_factory=lambda: ["author", "created_at"])
    # Application font -- the app's own chrome (menus, buttons, dialogs,
    # generic labels). Kept separate from the "content" font below per
    # explicit request: "tách cấu hình ... của nội dung và cấu hình của
    # ứng dụng riêng ra" (separate the content styling from the app's own
    # configuration) -- one governs how the app looks, the other how
    # documents' text is displayed.
    font_family: str | None = None  # None = Qt/OS default
    font_size: int = 10
    # Content font -- applied to document-related text specifically: the
    # library grid/list's title/author, and the Document Detail Panel's
    # title/author/tags. None family/color = fall back to the app font /
    # current theme's text color.
    content_font_family: str | None = None
    content_font_size: int = 13
    content_text_color: str | None = None  # hex, e.g. "#1a1a1a"; None = theme default
    show_detail_panel: bool = False
    # Last folder the user picked in any "choose a file/folder" dialog, so
    # the next dialog opens there instead of always starting at the OS
    # default location.
    last_used_directory: str | None = None
    # Debounce window before the file watcher reacts to a newly
    # created/modified file (TDD-007) -- lets a still-copying file finish
    # writing before it's read. Exposed in Settings beyond its default.
    watch_debounce_seconds: float = 1.5
    # AI-generated non-spoiler summaries (application/ai_summary.py) run
    # against the *user's own* account/key -- never a key this app ships
    # with -- so this is stored the same way as the Calibre/Supabase
    # settings: plain config, no separate secrets vault.
    ai_provider: str | None = None  # one of core.config.AI_PROVIDER_CHOICES
    ai_api_key: str | None = None
    # Folder to copy files into for "Send to e-reader" -- an e-reader
    # connected over USB just mounts as a normal folder on Windows, so this
    # is a plain remembered path, not a device-specific integration. None
    # until the user picks one (first Send prompts for it, then remembers).
    ereader_folder_path: str | None = None


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
