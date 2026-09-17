"""TDD-006: File System Watcher.

Watches configured folders and publishes FileDetectedEvent once a file has
stopped changing (debounced), so an importer never reads a file that the OS
is still writing to (e.g. a browser download or a slow copy).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from smartdoc.core.event_bus import FileDetectedEvent
from smartdoc.domain.models import MetadataNormalizer

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 1.5


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, on_stable, is_extension_allowed) -> None:
        self._on_stable = on_stable
        self._is_extension_allowed = is_extension_allowed
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _is_supported(self, path: str) -> bool:
        extension = Path(path).suffix.lower().lstrip(".")
        return self._is_extension_allowed(extension)

    def _schedule(self, path: str) -> None:
        if not self._is_supported(path):
            return
        with self._lock:
            existing = self._timers.get(path)
            if existing:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, self._fire, args=(path,))
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)
        if Path(path).exists():
            self._on_stable(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.dest_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        pass  # deletions are handled at the application layer (see LibraryWatcher.on_deleted)


class LibraryWatcher:
    def __init__(self, context) -> None:
        self.context = context
        self._observer = Observer()
        self._handler = _DebouncedHandler(
            on_stable=self._handle_stable_file,
            is_extension_allowed=self._is_extension_allowed,
        )
        self._watches: dict[str, object] = {}  # folder_path -> watchdog ObservedWatch

    def _is_extension_allowed(self, extension: str) -> bool:
        # Read live from config (not cached at construction time) so a
        # Settings change takes effect without restarting the app.
        return extension in self.context.config.config.allowed_extensions

    def _handle_stable_file(self, path: str) -> None:
        logger.info("File stable, publishing FileDetectedEvent: %s", path)
        self.context.event_bus.publish(FileDetectedEvent(file_path=path))

    def start(self) -> None:
        for folder in self.context.config.config.watch_folders:
            self._schedule_folder(folder)
        self._observer.start()

    def add_folder(self, folder_path: str) -> None:
        """Start watching an additional folder while the observer is already running."""
        self._schedule_folder(folder_path)

    def remove_folder(self, folder_path: str) -> None:
        """Stop watching a folder that was removed from Settings, without
        restarting the whole observer (and therefore the other folders)."""
        watch = self._watches.pop(folder_path, None)
        if watch is not None:
            self._observer.unschedule(watch)

    def _schedule_folder(self, folder_path: str) -> None:
        if folder_path in self._watches:
            return
        if Path(folder_path).is_dir():
            self._watches[folder_path] = self._observer.schedule(self._handler, folder_path, recursive=True)
        else:
            logger.warning("Watch folder does not exist, skipping: %s", folder_path)

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)


if __name__ == "__main__":
    import sys
    import tempfile
    import time
    from pathlib import Path as _Path

    from smartdoc.core.app_context import AppContext

    watch_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    print(f"Watching {watch_dir} for 10 seconds. Drop a .pdf/.epub file in there.")

    with tempfile.TemporaryDirectory() as app_data:
        context = AppContext.create_in_memory(_Path(app_data))
        context.config.add_watch_folder(watch_dir)
        context.event_bus.subscribe(FileDetectedEvent, lambda e: print("Detected stable file:", e.file_path))

        watcher = LibraryWatcher(context)
        watcher.start()
        time.sleep(10)
        watcher.stop()
        context.shutdown()
