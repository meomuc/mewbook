"""TDD-014: File Action Engine.

Talks to the OS shell on behalf of the library view (open a document, reveal
it in Explorer, remove it from the index and optionally delete the file).
Never uses shell=True — arguments are passed as argument lists (or, for
Windows Explorer's `/select,"path"` syntax specifically, a single pre-built
string handed straight to CreateProcess with no shell involved) so a file
path containing shell metacharacters cannot inject commands.
"""
from __future__ import annotations

import logging
import os
import shutil
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

    def delete_document(self, doc_id: str, file_path: str | None = None, delete_physical_file: bool = False) -> None:
        self.delete_documents([(doc_id, file_path)], delete_physical_file)

    def delete_documents(self, items: list[tuple[str, str | None]], delete_physical_file: bool = False) -> None:
        """Bulk form of delete_document: one LibraryUpdatedEvent for the
        whole batch instead of one per document."""
        for doc_id, file_path in items:
            self.context.db.delete_document(doc_id)
            if not delete_physical_file and file_path and os.path.isfile(file_path):
                # The file stays where it is, so the folder watcher would find it again: remember it was dropped on purpose.
                self.context.db.exclude_paths([file_path])
            if delete_physical_file and file_path:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Failed to delete physical file: %s", file_path)
        if items:
            self.context.event_bus.publish(LibraryUpdatedEvent())

    def copy_to_ereader(self, file_path: str, target_folder: str) -> str:
        """Copies one file into the e-reader's folder. Returns "" when it worked, otherwise the reason in plain words
        (for the "Gửi sang máy đọc sách" list)."""
        try:
            shutil.copy2(file_path, Path(target_folder) / Path(file_path).name)
        except FileNotFoundError:
            logger.warning("Failed to send file to e-reader (not found): %s", file_path)
            return "Không tìm thấy file trên máy"
        except PermissionError:
            logger.warning("Failed to send file to e-reader (permission): %s", file_path)
            return "File bị khóa bởi chương trình khác"
        except OSError as exc:
            logger.exception("Failed to send file to e-reader: %s", file_path)
            return "Máy đọc sách đã hết chỗ" if getattr(exc, "errno", None) == 28 else "Không chép được file này"
        return ""

    def copy_to_ereader_as(self, file_path: str, target_folder: str, target_name: str) -> str:
        """Task C1: like copy_to_ereader, but the on-device file name is chosen by the caller (a device profile's
        naming rule) and an existing file of that name is never overwritten -- the AC is explicit that a name
        collision must not clobber whatever is already on the device.

        The target folder's own existence is checked *first* and reported as its own reason ("máy đọc sách đã bị
        rút ra"), not left to fall through to shutil.copy2's FileNotFoundError -- that exception is raised for a
        missing *source* file too, and blaming "file not found on my machine" for a destination that disappeared
        (the device unplugged mid-batch) would be misleading."""
        if not Path(target_folder).is_dir():
            return "Máy đọc sách đã bị rút ra"
        target = Path(target_folder) / target_name
        if target.exists():
            return "Đã có file cùng tên trên máy, bỏ qua để không ghi đè"
        try:
            shutil.copy2(file_path, target)
        except FileNotFoundError:
            logger.warning("Failed to send file to e-reader (not found): %s", file_path)
            return "Không tìm thấy file trên máy"
        except PermissionError:
            logger.warning("Failed to send file to e-reader (permission): %s", file_path)
            return "File bị khóa bởi chương trình khác"
        except OSError as exc:
            logger.exception("Failed to send file to e-reader: %s", file_path)
            if getattr(exc, "errno", None) == 28:
                return "Máy đọc sách đã hết chỗ"
            if not Path(target_folder).is_dir():
                return "Máy đọc sách đã bị rút ra"
            return "Không chép được file này"
        return ""

    def send_to_ereader(self, file_paths: list[str], target_folder: str) -> tuple[list[str], list[str]]:
        """Copies files into an e-reader's book folder -- once connected
        over USB an e-reader just mounts as a normal folder on Windows, so
        this is a real `shutil.copy2`, unlike the library's own "never
        copy the user's files" storage model: the whole point here is
        putting a copy on the external device.

        Returns (succeeded, failed) source paths.
        """
        succeeded: list[str] = []
        failed: list[str] = []
        for file_path in file_paths:
            (failed if self.copy_to_ereader(file_path, target_folder) else succeeded).append(file_path)
        return succeeded, failed


if __name__ == "__main__":
    import tempfile
    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        engine = FileActionEngine(context)
        ok = engine.show_in_file_manager(__file__)
        print("show_in_file_manager(this file) ->", ok)
        context.shutdown()
