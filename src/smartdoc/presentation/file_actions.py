"""TDD-014: File Action Engine.

Talks to the OS shell on behalf of the library view (open a document, reveal
it in Explorer, copy it to an e-reader). Removing a book from the library is not done here: see application/removal.py.
Never uses shell=True — arguments are passed as argument lists (or, for
Windows Explorer's `/select,"path"` syntax specifically, a single pre-built
string handed straight to CreateProcess with no shell involved) so a file
path containing shell metacharacters cannot inject commands.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

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
                path = Path(file_path)
                if not path.exists():
                    # explorer /select silently falls back to its default
                    # folder (Documents/Quick access) when the target is
                    # missing, which looks like "it opened the wrong
                    # folder" -- open the parent folder explicitly instead
                    # so the failure is legible.
                    parent = path.parent
                    if parent.exists():
                        os.startfile(str(parent))  # noqa: S606
                        return True
                    return False
                # Passed as one pre-built string, not a list: subprocess's
                # automatic list2cmdline quoting would wrap the *whole*
                # "/select,<path>" token in quotes whenever the path
                # contains a space, which explorer.exe doesn't parse as a
                # valid /select argument -- it then silently falls back to
                # its default folder instead of erroring. Quoting only the
                # path (explorer's own documented syntax) avoids that.
                subprocess.run(f'explorer /select,"{path.resolve()}"')
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", file_path], check=True)
            else:
                subprocess.run(["xdg-open", str(Path(file_path).parent)], check=True)
            return True
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            logger.exception("Failed to reveal file in file manager: %s", file_path)
            return False


if __name__ == "__main__":
    import tempfile
    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        engine = FileActionEngine(context)
        ok = engine.show_in_file_manager(__file__)
        print("show_in_file_manager(this file) ->", ok)
        context.shutdown()
