"""TDD-014: File Action Engine.

Talks to the OS shell on behalf of the library view (open a document, reveal
it in Explorer, remove it from the index and optionally delete the file).
Never uses shell=True — arguments are passed as argument lists so a file
path containing shell metacharacters cannot inject commands.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from smartdoc.core.event_bus import LibraryUpdatedEvent

logger = logging.getLogger(__name__)


class FileActionEngine:
    def __init__(self, context) -> None:
        self.context = context

    def open_file(self, file_path: str) -> bool:
        try:
            if sys.platform == "win32":
                os.startfile(file_path)  # noqa: S606 - user-initiated open of their own file
            elif sys.platform == "darwin":
                subprocess.run(["open", file_path], check=True)
            else:
                subprocess.run(["xdg-open", file_path], check=True)
            return True
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            logger.exception("Failed to open file: %s", file_path)
            return False

    def show_in_file_manager(self, file_path: str) -> bool:
        try:
            if sys.platform == "win32":
                # explorer.exe frequently returns a non-zero exit code even
                # on success, so this isn't run with check=True.
                subprocess.run(["explorer", f"/select,{file_path}"])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", file_path], check=True)
            else:
                subprocess.run(["xdg-open", str(Path(file_path).parent)], check=True)
            return True
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            logger.exception("Failed to reveal file in file manager: %s", file_path)
            return False

    def delete_document(self, doc_id: str, file_path: str | None = None, delete_physical_file: bool = False) -> None:
        self.delete_documents([(doc_id, file_path)], delete_physical_file)

    def delete_documents(self, items: list[tuple[str, str | None]], delete_physical_file: bool = False) -> None:
        """Bulk form of delete_document: one LibraryUpdatedEvent for the
        whole batch instead of one per document."""
        for doc_id, file_path in items:
            self.context.db.delete_document(doc_id)
            if delete_physical_file and file_path:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Failed to delete physical file: %s", file_path)
        if items:
            self.context.event_bus.publish(LibraryUpdatedEvent())


if __name__ == "__main__":
    import tempfile
    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        engine = FileActionEngine(context)
        ok = engine.show_in_file_manager(__file__)
        print("show_in_file_manager(this file) ->", ok)
        context.shutdown()
