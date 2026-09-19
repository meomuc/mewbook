import time
from pathlib import Path

from smartdoc.application.file_watcher import LibraryWatcher
from smartdoc.core.event_bus import FileDetectedEvent


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _write_until(predicate, path: Path, attempts: int = 3, window: float = 3.0) -> bool:
    """Write `path`, and write it again if nothing was reported within `window` seconds.

    watchdog arms the watch of a folder added at run time on its own thread, so on a starved machine (a
    2-core CI runner) the file can be created *before* the watch exists, and that event is gone for good.
    `window` must stay longer than the debounce (1.5 s) or every rewrite would restart the timer."""
    for attempt in range(attempts):
        path.write_bytes(b"fake pdf bytes %d" % attempt)
        if _wait_until(predicate, timeout=window):
            return True
    return predicate()


def test_watcher_detects_new_supported_file_after_debounce(tmp_path, app_context):
    watch_dir = tmp_path / "library"
    watch_dir.mkdir()
    app_context.config.add_watch_folder(str(watch_dir))

    detected: list[str] = []
    app_context.event_bus.subscribe(FileDetectedEvent, lambda e: detected.append(e.file_path))

    watcher = LibraryWatcher(app_context)
    watcher.start()
    try:
        (watch_dir / "book.pdf").write_bytes(b"fake pdf bytes")
        assert _wait_until(lambda: len(detected) == 1, timeout=4.0)
        assert Path(detected[0]).name == "book.pdf"
    finally:
        watcher.stop()


def test_watcher_ignores_unsupported_extensions(tmp_path, app_context):
    watch_dir = tmp_path / "library"
    watch_dir.mkdir()
    app_context.config.add_watch_folder(str(watch_dir))

    detected: list[str] = []
    app_context.event_bus.subscribe(FileDetectedEvent, lambda e: detected.append(e.file_path))

    watcher = LibraryWatcher(app_context)
    watcher.start()
    try:
        (watch_dir / "notes.txt").write_text("ignored")
        time.sleep(2.0)
        assert detected == []
    finally:
        watcher.stop()


def test_add_folder_starts_watching_a_new_directory_after_start(tmp_path, app_context):
    watch_dir = tmp_path / "added_later"
    watch_dir.mkdir()

    detected: list[str] = []
    app_context.event_bus.subscribe(FileDetectedEvent, lambda e: detected.append(e.file_path))

    watcher = LibraryWatcher(app_context)
    watcher.start()
    try:
        watcher.add_folder(str(watch_dir))
        assert _write_until(lambda: len(detected) >= 1, watch_dir / "late.pdf")
        assert {Path(p).name for p in detected} == {"late.pdf"}
    finally:
        watcher.stop()


def test_remove_folder_stops_detecting_new_files_there(tmp_path, app_context):
    keep_dir = tmp_path / "keep"
    remove_dir = tmp_path / "remove"
    keep_dir.mkdir()
    remove_dir.mkdir()
    app_context.config.add_watch_folder(str(keep_dir))
    app_context.config.add_watch_folder(str(remove_dir))

    detected: list[str] = []
    app_context.event_bus.subscribe(FileDetectedEvent, lambda e: detected.append(e.file_path))

    watcher = LibraryWatcher(app_context)
    watcher.start()
    try:
        watcher.remove_folder(str(remove_dir))
        (remove_dir / "ignored.pdf").write_bytes(b"fake pdf bytes")
        (keep_dir / "seen.pdf").write_bytes(b"fake pdf bytes")

        assert _wait_until(lambda: len(detected) == 1, timeout=4.0)
        assert Path(detected[0]).name == "seen.pdf"
    finally:
        watcher.stop()


def test_extension_allowlist_is_read_live_from_config(tmp_path, app_context):
    watch_dir = tmp_path / "library"
    watch_dir.mkdir()
    app_context.config.add_watch_folder(str(watch_dir))
    app_context.config.config.allowed_extensions = ["pdf"]  # epub disabled

    detected: list[str] = []
    app_context.event_bus.subscribe(FileDetectedEvent, lambda e: detected.append(e.file_path))

    watcher = LibraryWatcher(app_context)
    watcher.start()
    try:
        (watch_dir / "book.epub").write_bytes(b"fake epub bytes")
        time.sleep(2.0)
        assert detected == []  # epub disabled in config

        app_context.config.config.allowed_extensions = ["pdf", "epub"]
        (watch_dir / "book2.epub").write_bytes(b"fake epub bytes")
        assert _wait_until(lambda: len(detected) == 1, timeout=4.0)
    finally:
        watcher.stop()


def test_a_change_mewbook_made_itself_is_not_reported_as_a_new_file(app_context):
    from smartdoc.application.file_watcher import LibraryWatcher
    from smartdoc.core.event_bus import FileDetectedEvent

    detected = []
    app_context.event_bus.subscribe(FileDetectedEvent, lambda e: detected.append(e.file_path))
    watcher = LibraryWatcher(app_context)

    app_context.self_writes.mark("C:/Books/mine.epub")
    watcher._handle_stable_file("C:/Books/mine.epub")  # MewBook just wrote metadata into it
    watcher._handle_stable_file("C:/Books/other.epub")  # a genuine change elsewhere

    assert detected == ["C:/Books/other.epub"]


def test_self_write_registry_forgets_after_its_window():
    from smartdoc.core.self_writes import SelfWriteRegistry

    now = [100.0]
    registry = SelfWriteRegistry(clock=lambda: now[0])
    registry.mark("a.epub", seconds=30)
    assert registry.is_recent("a.epub") and not registry.is_recent("b.epub")
    now[0] = 131.0
    assert not registry.is_recent("a.epub")
