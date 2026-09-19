"""TDD-015: App configuration persisted as JSON under %APPDATA%."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from smartdoc.core.secret_store import SecretStore

# Kept as the original name -- this is only the on-disk %APPDATA% folder
# name, invisible to the user, and renaming it would silently orphan every
# existing install's settings/database/cover cache on upgrade. The
# user-visible product name (MewBook / "Mèo Mực") lives entirely in the UI
# layer (see presentation/main_window.py, presentation/sidebar.py).
APP_DIR_NAME = "SmartDocLibrary"

# Config fields whose on-disk value is encrypted at rest (see
# core.secret_store.SecretStore) -- anything that is an actual bring-your-own
# API key. Kept in-memory as plaintext for the rest of the app to use
# (ai_summary.py, cover_search.py, their dialogs) -- only the JSON file on
# disk is protected.
_ENCRYPTED_FIELDS = ("ai_api_key", "google_image_api_key")

# See presentation/theme.py for the full palette/token definitions.
THEME_CHOICES = ("broadsheet", "woodshelf", "inkynight", "healing", "retro_tech", "japandi", "zen_dark")

# Maps a config value written by a pre-rebrand version of this app (when the
# only choices were generic "light"/"dark") to the closest new named theme,
# so upgrading never crashes on an unknown value or silently resets to a
# theme the user didn't pick. Applied once in ConfigManager._load().
_LEGACY_THEME_MAP = {"light": "broadsheet", "dark": "inkynight"}

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
AI_PROVIDER_CHOICES = ("gemini", "groq", "openrouter", "mistral", "ollama", "openai", "anthropic", "deepseek")
AI_PROVIDER_DISPLAY_NAMES = {
    "gemini": "Google Gemini (có gói miễn phí)",
    "groq": "Groq (miễn phí)",
    "openrouter": "OpenRouter (nhiều model miễn phí)",
    "mistral": "Mistral AI (có gói miễn phí)",
    "ollama": "Ollama - chạy trên máy (miễn phí, không cần key)",
    "openai": "OpenAI (ChatGPT)",
    "anthropic": "Anthropic Claude",
    "deepseek": "DeepSeek",
}


def default_app_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".smartdoc"
    return base / APP_DIR_NAME


@dataclass
class AppConfig:
    watch_folders: list[str] = field(default_factory=list)
    theme: str = "broadsheet"
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
    # Optional list-view columns beyond the mandatory Title (which always
    # includes an inline cover thumbnail) -- see
    # presentation/library_view.py's OPTIONAL_COLUMN_KEYS for the valid keys.
    visible_columns: list[str] = field(default_factory=lambda: ["author", "format", "file_size", "created_at"])
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
    # Sidebar filter sections the user folded away ("tags", "authors", "formats").
    collapsed_filter_sections: list[str] = field(default_factory=list)
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
    # None = the provider's default (application/ai_summary.DEFAULT_MODELS).
    ai_model: str | None = None
    # Only used by Ollama (local server); None = http://localhost:11434.
    ai_base_url: str | None = None
    # Last-used summary options in the AI Summary dialog -- see
    # application/ai_summary.SUMMARY_STYLES / _LENGTHS / _LANGUAGES.
    ai_summary_style: str = "intro"
    ai_summary_length: str = "short"
    ai_summary_language: str = "vi"
    # Google Programmable Search Engine (Custom Search JSON API), restricted
    # to image search -- see application/cover_search.py. Same
    # bring-your-own-key model as the AI provider above: this app never
    # ships or proxies a key of its own.
    google_image_api_key: str | None = None
    google_image_search_cx: str | None = None  # the search engine's "cx" id
    # Cover/metadata sources switched off, by their display names (application/cover_search.SOURCE_*).
    # Off by default (docs/legal/DATA_SOURCES.md): Tiki, an undocumented shop API with no published terms, and
    # Apple Books, whose terms only allow its artwork to promote the store. Users can switch either on.
    disabled_cover_sources: list[str] = field(default_factory=lambda: ["Tiki", "Apple Books"])
    # How many backups of library.db to keep in the "backups" folder next to it (application/backup_service.py).
    backup_retention: int = 5
    # Optional "newer version?" check (application/update_checker.py): off unless the user turns it on; notify-only.
    update_check_enabled: bool = False
    update_last_checked: float = 0.0
    # Whether the user has accepted the EULA/Privacy notice shown on first
    # launch (see presentation/eula_dialog.py). False on every fresh
    # install; never reset automatically once True.
    eula_accepted: bool = False
    # Folder to copy files into for "Send to e-reader" -- an e-reader
    # connected over USB just mounts as a normal folder on Windows, so this
    # is a plain remembered path, not a device-specific integration. None
    # until the user picks one (first Send prompts for it, then remembers).
    ereader_folder_path: str | None = None
    # Metadata lookup (application/metadata_lookup.py). Whether the "write into
    # the book file" box of the suggestion dialog starts ticked (off: the
    # library index is updated, the file is left alone unless the user opts in
    # each time), and how many pre-write backups of a book file to keep.
    metadata_write_to_file_default: bool = False
    metadata_backup_keep: int = 3
    # Smart classification (application/smart_classifier.py). What to do when
    # new documents are added: "ask" pops up a small question after each
    # import, "always" classifies quietly, "never" doesn't offer at all.
    smart_classify_on_import: str = "ask"
    # How many of a book's first words are read for classification (2,000-5,000
    # -- enough for the preface, contents and chapter one without reading
    # whole books).
    smart_classify_max_words: int = 3000
    # Upper bound on classification worker processes. Deliberately small: the
    # job is meant to trickle along in idle time, not to use the whole machine.
    smart_classify_max_workers: int = 2


SMART_CLASSIFY_ON_IMPORT_CHOICES = ("ask", "always", "never")


class ConfigManager:
    def __init__(self, app_data_dir: Path | None = None) -> None:
        self.app_data_dir = app_data_dir or default_app_data_dir()
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.app_data_dir / "settings.json"
        self._secrets = SecretStore(self.app_data_dir)
        self.config: AppConfig = self._load()

    @property
    def secrets(self) -> SecretStore:
        return self._secrets

    def _load(self) -> AppConfig:
        if not self.settings_path.exists():
            config = AppConfig(
                db_path=str(self.app_data_dir / "library.db"),
                cover_cache_dir=str(self.app_data_dir / "covers"),
            )
            self._write(config)
            return config
        # utf-8-sig: a settings.json saved by Notepad or PowerShell 5 starts with a BOM.
        raw = json.loads(self.settings_path.read_text(encoding="utf-8-sig"))
        # Drop keys from an older schema version (e.g. a settings.json
        # written before a field was renamed/removed) instead of letting
        # them reach AppConfig(**defaults) as an unexpected keyword arg.
        known_fields = {f.name for f in fields(AppConfig)}
        defaults = asdict(AppConfig())
        defaults.update({k: v for k, v in raw.items() if k in known_fields})
        config = AppConfig(**defaults)
        if not config.db_path:
            # Without this the library silently lands in the current working directory (AppContext falls
            # back to a relative "library.db").
            config.db_path = str(self.app_data_dir / "library.db")
        if config.theme not in THEME_CHOICES:
            config.theme = _LEGACY_THEME_MAP.get(config.theme, "broadsheet")
        if config.smart_classify_on_import not in SMART_CLASSIFY_ON_IMPORT_CHOICES:
            config.smart_classify_on_import = "ask"  # a hand-edited settings.json must not disable the prompt by typo
        for field_name in _ENCRYPTED_FIELDS:
            setattr(config, field_name, self._secrets.decrypt(getattr(config, field_name)))
        return config

    def _write(self, config: AppConfig) -> None:
        data = asdict(config)
        for field_name in _ENCRYPTED_FIELDS:
            data[field_name] = self._secrets.encrypt(getattr(config, field_name))
        self.settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

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
