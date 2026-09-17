"""TDD-022: Calibre / External Library Migrator.

Reads an existing Calibre library's metadata.db (itself a SQLite database)
read-only, resolves each book's file on disk, and hands those paths to the
normal import pipeline (ImportQueueManager) -- rather than hand-mapping
Calibre's cached metadata fields into our schema, this lets our own
PDF/EPUB extractors pull real metadata, a cover and full text straight from
the files themselves, none of which metadata.db has. Never touches the
Calibre library's files: Single Source of Truth applies here too, so this
is an index-only import exactly like scanning any other folder.

Known limitation: Calibre's own tags/ratings are not carried over. Doing so
would mean writing to a document's DB row before it's guaranteed to exist
yet (the import queue processes files asynchronously on worker threads,
after this module hands off the file paths), which needs its own event
coordination this pass didn't build.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Calibre stores "format" values uppercase (PDF, EPUB, MOBI, AZW3). A book
# can have more than one format on disk; this is the preference order when
# choosing which one to index.
_FORMAT_PREFERENCE = ("PDF", "EPUB", "MOBI", "AZW3")


class CalibreImporter:
    def __init__(self, context, import_manager) -> None:
        self.context = context
        self.import_manager = import_manager

    def scan_library(self, calibre_library_path: str) -> list[str]:
        """Resolve every importable book's file path in a Calibre library.
        Opens metadata.db read-only (uri mode=ro) -- this never writes
        anything into the Calibre library.
        """
        metadata_db_path = Path(calibre_library_path) / "metadata.db"
        if not metadata_db_path.exists():
            raise FileNotFoundError(f"Not a Calibre library (no metadata.db found): {calibre_library_path}")

        uri = f"file:{metadata_db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            books = conn.execute("SELECT id, path FROM books").fetchall()
            file_paths: list[str] = []
            for book in books:
                formats = conn.execute("SELECT format, name FROM data WHERE book = ?", (book["id"],)).fetchall()
                chosen = self._choose_format(formats)
                if chosen is None:
                    logger.info("Calibre book id=%s has no supported format, skipping", book["id"])
                    continue
                format_name, file_name = chosen
                file_path = Path(calibre_library_path) / book["path"] / f"{file_name}.{format_name.lower()}"
                if file_path.exists():
                    file_paths.append(str(file_path))
                else:
                    logger.warning("Calibre metadata.db references a missing file: %s", file_path)
            return file_paths
        finally:
            conn.close()

    @staticmethod
    def _choose_format(formats: list[sqlite3.Row]) -> tuple[str, str] | None:
        by_format = {row["format"].upper(): row["name"] for row in formats}
        for preferred in _FORMAT_PREFERENCE:
            if preferred in by_format:
                return preferred, by_format[preferred]
        return None

    def import_library(self, calibre_library_path: str) -> int:
        """Scan + enqueue every book into the normal import pipeline.
        Returns how many files were enqueued."""
        file_paths = self.scan_library(calibre_library_path)
        for path in file_paths:
            self.import_manager.add_file(path)
        return len(file_paths)


if __name__ == "__main__":
    import sys
    import tempfile

    from smartdoc.application.import_queue import ImportQueueManager
    from smartdoc.core.app_context import AppContext

    if len(sys.argv) < 2:
        print("Usage: python calibre_migrator.py <path-to-calibre-library>")
        sys.exit(0)

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        import_manager = ImportQueueManager(context)
        import_manager.start()

        importer = CalibreImporter(context, import_manager)
        count = importer.import_library(sys.argv[1])
        print(f"Enqueued {count} files from Calibre library")

        import_manager.stop()
        context.shutdown()
