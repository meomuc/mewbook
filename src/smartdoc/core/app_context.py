"""AppContext: single dependency-injection root for the whole app.

Every module accepts `context: AppContext` in its constructor and reaches
its dependencies through it (context.db, context.config, context.event_bus)
instead of importing/constructing collaborators itself. This is the
integration rule every TDD module in this project must follow.
"""
from __future__ import annotations

from pathlib import Path

from smartdoc.application.backup_service import BackupService
from smartdoc.application.error_reporter import ErrorReporter
from smartdoc.application.error_uploader import ErrorUploader
from smartdoc.application.facet_counter import FacetCounter
from smartdoc.application.gather_service import GatherService
from smartdoc.application.info_refresh import InfoRefresh
from smartdoc.application.relink_service import RelinkService
from smartdoc.application.trash_service import TrashService
from smartdoc.application.update_checker import UpdateChecker
from smartdoc.core.config import ConfigManager
from smartdoc.core.event_bus import EventBus
from smartdoc.core.filter_service import FilterService
from smartdoc.core.self_writes import SelfWriteRegistry
from smartdoc.core.user_identity import UserIdentity
from smartdoc.infrastructure.database import DatabaseManager


class AppContext:
    def __init__(self, config: ConfigManager | None = None, event_bus: EventBus | None = None,
                 db: DatabaseManager | None = None) -> None:
        self.config = config or ConfigManager()
        self.event_bus = event_bus or EventBus()
        self.db = db or DatabaseManager(self.config.config.db_path or "library.db")
        # An existing library is backed up before its schema is upgraded (S1-03); a failing backup stops the upgrade.
        self.backups = BackupService(self.db, retention=lambda: self.config.config.backup_retention,
                                     folder=lambda: self.config.config.backup_dir)
        self.db.initialize_tables(before_migrate=None if self.db.db_path == ":memory:" else self.backups.before_migration)
        # Missing-file detection and relinking (S1-04).
        self.relink = RelinkService(self.db, self.event_bus)
        # MewBook's own trash: files removed as duplicates wait here before they are deleted for good.
        self.trash = TrashService(self)
        # "Gom sách về một thư mục": copy or move the library's files into one folder.
        self.gather = GatherService(self)
        # "Cập nhật ngay": re-read what the files say (size, hash, pages) on demand, next to the background work.
        self.info_refresh = InfoRefresh(self)
        # Optional, off-by-default, notify-only check for a newer release (S1-05).
        self.updates = UpdateChecker(self.config, self.event_bus)
        # What the library is filtered by (search text + sidebar selection) --
        # one owner, one event; see core/filter_service.py.
        self.filters = FilterService(self.event_bus)
        # Live counts for the sidebar / "Đang lọc" bar, cached until the library changes.
        self.facets = FacetCounter(self)
        # Files MewBook is rewriting itself, which the folder watcher must not re-import.
        self.self_writes = SelfWriteRegistry()
        # Anonymous per-install identity (see core/user_identity.py) --
        # used to own reviews/nicknames without any sign-up.
        self.identity = UserIdentity.load_or_create(self.config.app_data_dir, self.config.secrets)
        # Voluntary, anonymous, previewed error reports (S1e). Collects nothing until an error happens, and only in a
        # release build; sending is a separate, opt-in step (application/error_uploader.py).
        self.error_reports = ErrorReporter(self.config, self.event_bus, self.identity, self.db)
        # Sends what the user approved, on a background thread; makes no connection unless something was approved.
        self.error_uploader = ErrorUploader(self.config, self.event_bus, self.error_reports)

    @classmethod
    def create_in_memory(cls, app_data_dir: Path) -> "AppContext":
        """Convenience factory for tests: isolated config dir + in-memory DB."""
        config = ConfigManager(app_data_dir=app_data_dir)
        db = DatabaseManager(":memory:")
        return cls(config=config, db=db)

    def shutdown(self) -> None:
        self.db.close()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "doc1",
            {"title": "Demo Book", "author": "Someone", "file_path": "demo.pdf", "created_at": 0.0},
            extracted_text="demo content",
        )
        print("search:", context.db.search("demo*"))
        context.shutdown()
