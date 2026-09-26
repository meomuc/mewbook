"""Composition root: wires AppContext + background services + the Qt UI together."""
from __future__ import annotations

import logging
import multiprocessing
import sys
import threading

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from smartdoc import APP_DISPLAY_NAME, APP_NAME, APP_PUBLISHER, __version__
from smartdoc.application.file_watcher import LibraryWatcher
from smartdoc.application.content_backfill import ContentBackfill
from smartdoc.application.fingerprint_backfill import FingerprintBackfill
from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.application.smart_classifier import AutoClassifyOnImport, SmartClassifyService
from smartdoc.core.app_context import AppContext
from smartdoc.core.config import default_app_data_dir
from smartdoc.core.diagnostics import current_log_path, install_exception_hooks, setup_logging
from smartdoc.infrastructure.schema_migrations import SchemaError
from smartdoc.presentation.dialog_size import DialogSizeGuard
from smartdoc.presentation.error_report_dialog import ErrorReportPrompt
from smartdoc.presentation.eula_dialog import EulaDialog
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.resources import app_icon_path
from smartdoc.presentation.theme import apply_theme, theme_font
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.window_shapes import window_class_for


def _apply_appearance(app: QApplication, context: AppContext) -> None:
    manager = theme_manager()
    # Palette + base stylesheet + fonts for the saved (layout, theme) pair; also re-run on a switch. A theme the layout
    # cannot use is replaced by the layout's default inside apply(), so the legacy colours follow manager.key.
    manager.show_backdrop = context.config.config.show_backdrop
    manager.apply(app, context.config.config.theme, context.config.config.layout)
    colors = apply_theme(app, manager.key, manager.tokens())
    font_family = context.config.config.font_family
    # The design's own typeface (Be Vietnam Pro) unless the user picked one in Settings; the legacy per-theme font
    # stack (theme_font) is only the fallback if the bundled font failed to load.
    font = QFont(font_family or manager.font_family("ui"))
    if not font_family and font.family() != manager.font_family("ui"):
        font = theme_font(colors)
    font.setPointSize(context.config.config.font_size)
    app.setFont(font)


logger = logging.getLogger(__name__)

_LOCK_FILE_NAME = "mewbook.lock"


def _acquire_single_instance_lock(app_data_dir) -> QLockFile | None:
    """Two copies of the app writing to the same library.db and cover
    cache at once is a recipe for corruption -- only the first one runs.
    QLockFile detects a stale lock left by a crashed run (dead PID) and
    takes it over, so a crash never locks the user out."""
    app_data_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(app_data_dir / _LOCK_FILE_NAME))
    lock.setStaleLockTime(0)
    if lock.tryLock(200):
        return lock
    return None


_crash_dialog_open = False
# The error reporter of the running app (core/app_context.py), set once the context exists; an error before that is
# logged and shown, but there is nothing to report it to yet.
_error_reporter = None


def _report_unhandled_exception(exc_type, exc_value, exc_tb, thread_name: str) -> str | None:
    """The error-report hook of core/diagnostics.py: hands the error to the reporter, which scrubs it and queues it
    (only in a release build and never in the "never" mode). Returns the id of a report that now waits for the user's
    answer -- the report prompt asks about it, so the plain crash dialog is not shown as well."""
    if _error_reporter is None:
        return None
    return _error_reporter.capture_exception(exc_type, exc_value, exc_tb, thread_name=thread_name)


def _show_crash_dialog(summary: str, report_id: str | None = None) -> None:
    """At most one crash dialog at a time, and never from inside the failing call.

    An error raised while painting (a delegate, say) repeats on every repaint. Running the
    dialog's modal loop right there made each repaint raise again and open another dialog on
    top of the last, and the window froze ("Not Responding"). Later errors are still logged
    by the hook; they just don't stack more dialogs.

    With a `report_id` the error became a report that waits for the user's answer: the report prompt
    (presentation/error_report_dialog.py) shows "Mèo gặp lỗi bất ngờ" for it, which says the same thing and asks
    the question, so this plain message is skipped."""
    global _crash_dialog_open
    if report_id is not None:
        return
    if QApplication.instance() is None or _crash_dialog_open:
        return
    _crash_dialog_open = True
    QTimer.singleShot(0, lambda: _run_crash_dialog(summary))


def _run_crash_dialog(summary: str) -> None:
    global _crash_dialog_open
    log_path = current_log_path()
    try:
        QMessageBox.critical(
            None,
            f"{APP_DISPLAY_NAME} gặp lỗi",
            "Đã xảy ra lỗi không mong muốn. Ứng dụng vẫn cố gắng tiếp tục chạy.\n\n"
            f"{summary}\n\n"
            + ("Chi tiết đã được ghi lại trên máy của bạn.\n\n" if log_path else "")
            + "Nếu lỗi lặp lại, hãy gửi nhật ký lỗi kèm mô tả thao tác cho tác giả "
            "(Trợ giúp > Giới thiệu > Sao chép thông tin hỗ trợ).",
        )
    finally:
        _crash_dialog_open = False


def main() -> None:
    # Smart classification runs in child processes ("spawn"). In a frozen build
    # each child is this very executable, and this call is what turns it into a
    # worker instead of a second copy of the app -- so it has to come first.
    multiprocessing.freeze_support()
    app_data_dir = default_app_data_dir()
    setup_logging(app_data_dir)
    install_exception_hooks(show_dialog=_show_crash_dialog, on_exception=_report_unhandled_exception)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_PUBLISHER)

    instance_lock = _acquire_single_instance_lock(app_data_dir)
    if instance_lock is None:
        logger.info("Another instance is already running -- exiting")
        QMessageBox.information(
            None, APP_DISPLAY_NAME, f"{APP_DISPLAY_NAME} đang chạy. Hãy chuyển sang cửa sổ đang mở trên thanh tác vụ."
        )
        sys.exit(0)
    app._instance_lock = instance_lock  # held (and released on exit) by the app object

    try:
        context = AppContext()
    except SchemaError as exc:
        # A library written by a newer MewBook, or an upgrade that failed and was rolled back: say so plainly
        # instead of the generic crash dialog. Nothing has been changed in either case.
        logger.error("Cannot open the library: %s", exc)
        QMessageBox.critical(None, APP_DISPLAY_NAME, str(exc))
        sys.exit(1)
    # From here on an unhandled error can become an error report (asked about, never sent unasked); the prompt
    # is what shows the question, on the GUI thread, one dialog at a time.
    global _error_reporter
    _error_reporter = context.error_reports
    error_report_prompt = ErrorReportPrompt(context)
    app._error_report_prompt = error_report_prompt  # held by the app object for as long as the app runs
    # The ★ buttons file documents into this built-in collection -- create
    # it up front so it's visible in the sidebar before the first star.
    context.db.ensure_reading_list()

    import_manager = ImportQueueManager(context, num_workers=context.config.config.worker_thread_count, use_process_pool=True)
    import_manager.start()

    watcher = LibraryWatcher(context)
    watcher.start()

    # Nothing here loads a model or starts a process: that only happens when a
    # classification job is requested (button, import popup, or the "always"
    # setting for files the folder watcher picks up).
    smart_classifier = SmartClassifyService(context)
    auto_classifier = AutoClassifyOnImport(context, smart_classifier)

    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Keeps every popup (this app's own dialogs *and* Qt's built-in
    # message/file dialogs) inside the screen it opens on -- see
    # presentation/dialog_size.py. Held on the app object so the filter
    # isn't garbage-collected while it's still installed.
    app._dialog_size_guard = DialogSizeGuard()
    app.installEventFilter(app._dialog_size_guard)

    # Gate entry on the EULA/Privacy notice -- asked once per install, not
    # once per launch (see AppConfig.eula_accepted). Closing the dialog any
    # way other than its "Tôi đã đọc và Đồng ý" button does not count as
    # agreeing (see EulaDialog), so this quits instead of ever building the
    # main window.
    if not context.config.config.eula_accepted:
        if EulaDialog().exec() != QDialog.Accepted:
            watcher.stop()
            import_manager.stop()
            context.shutdown()
            sys.exit(0)
        context.config.config.eula_accepted = True
        context.config.save()

    # A plain local variable inside on_appearance_changed would go out of
    # scope (and, with no C++ or Python owner, be garbage-collected out from
    # under the still-visible window) as soon as the callback returns -- this
    # holder keeps whichever window is current alive for as long as the app
    # runs.
    current_window: list[MainWindow] = []

    def build_and_show_window() -> MainWindow:
        _apply_appearance(app, context)
        window = window_class_for(theme_manager().layout.id)(  # the shape of the layout just applied
            context,
            watcher=watcher,
            import_manager=import_manager,
            on_appearance_changed=on_appearance_changed,
            smart_classifier=smart_classifier,
        )
        window.show()
        current_window.append(window)
        return window

    def on_appearance_changed(old_window: MainWindow) -> None:
        # Theme/font can't be live-restyled onto already-built widgets that
        # baked their colors into a stylesheet string at construction time
        # (see settings_dialog.py's module docstring), so instead of asking
        # for a real app restart, rebuild the window in place: same
        # AppContext/watcher/import_manager (no backend state lost), fresh
        # widget tree. Show the new window BEFORE retiring the old one so
        # there's never a moment with zero visible windows (which could
        # trigger QApplication's quitOnLastWindowClosed). hide()+deleteLater()
        # rather than close() -- close() would run MainWindow.closeEvent's
        # full shutdown (stop watcher/import_manager, close the db), which
        # is only correct for the user actually exiting the app.
        build_and_show_window()
        current_window.remove(old_window)
        old_window.hide()
        old_window.deleteLater()

    build_and_show_window()
    # A report an earlier session never got an answer for (the app closed first) is asked about once the window is up,
    # and reports the user approved but that could not be sent then (no network, server off) get another try. Both are
    # cheap when there is nothing to do: a directory listing, and no connection at all.
    QTimer.singleShot(0, error_report_prompt.ask_about_waiting)
    context.error_uploader.kick()

    # Books imported before fingerprints existed get theirs in the background.
    fingerprint_backfill = FingerprintBackfill(context)
    fingerprint_backfill.start()
    content_backfill = ContentBackfill(context)  # e-books imported before their text was read for search: once
    content_backfill.start()

    # Which books have lost their file (moved, deleted, drive unplugged)? Checked in the background so a big or
    # networked library never delays the window; the status bar shows the answer (S1-04).
    def check_then_scan() -> None:
        context.relink.check_files()
        # Files that arrived while MewBook was closed (the watcher only sees changes from now on). After the check, so a
        # book whose file moved meanwhile is already marked missing and is found again instead of imported twice.
        import_manager.catch_up_scan()

    threading.Thread(target=check_then_scan, name="missing-files-check", daemon=True).start()
    threading.Thread(target=context.trash.purge_expired, name="trash-purge", daemon=True).start()  # past-due items only
    threading.Thread(target=context.updates.maybe_check_on_startup, name="update-check", daemon=True).start()  # off unless enabled

    exit_code = app.exec()
    fingerprint_backfill.stop()
    content_backfill.stop()
    auto_classifier.stop()
    smart_classifier.stop()
    context.error_uploader.stop()  # ends a send in progress at its next step and keeps the queue (ERR-A15)
    context.shutdown()  # only now: the event loop has drained, nothing queries the database any more
    logger.info("Exiting with code %s", exit_code)
    instance_lock.unlock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
