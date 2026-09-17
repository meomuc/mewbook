"""AppContext: single dependency-injection root for the whole app.

Every module accepts `context: AppContext` in its constructor and reaches
its dependencies through it (context.db, context.config, context.event_bus)
instead of importing/constructing collaborators itself. This is the
integration rule every TDD module in this project must follow.
"""
from __future__ import annotations

from pathlib import Path

from smartdoc.core.config import ConfigManager
from smartdoc.core.event_bus import EventBus
from smartdoc.infrastructure.database import DatabaseManager


class AppContext:
    def __init__(self, config: ConfigManager | None = None, event_bus: EventBus | None = None,
                 db: DatabaseManager | None = None) -> None:
        self.config = config or ConfigManager()
        self.event_bus = event_bus or EventBus()
        self.db = db or DatabaseManager(self.config.config.db_path or "library.db")
        self.db.initialize_tables()

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
