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
from smartdoc.application.fingerprint_backfill import FingerprintBackfill
from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.application.smart_classifier import AutoClassifyOnImport, SmartClassifyService
from smartdoc.core.app_context import AppContext
from smartdoc.core.config import default_app_data_dir
from smartdoc.core.diagnostics import current_log_path, install_exception_hooks, setup_logging
from smartdoc.infrastructure.schema_migrations import SchemaError
from smartdoc.presentation.dialog_size import DialogSizeGuard
from smartdoc.presentation.eula_dialog import EulaDialog
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.resources import app_icon_path
from smartdoc.presentation.theme import app_stylesheet, apply_theme, theme_font


def _apply_appearance(app: QApplication, context: AppContext) -> None:
    colors = apply_theme(app, context.config.config.theme)
    font_family = context.config.config.font_family
    if font_family:
        font = QFont(font_family)
    else:
        # Default to the theme's own typeface (serif for most, monospace
        # for Retro-Tech, light sans for Japandi -- see
        # ThemeColors.font_families) rather than the bare OS default, while
        # leaving the user's own override in Settings completely intact.
        font = theme_font(colors)
    font.setPointSize(context.config.config.font_size)
    app.setFont(font)
    # Button/tooltip look for themes that restyle them; empty (Qt's own
    # look) for the original themes. Always set, so switching back from
    # such a theme clears it.
    app.setStyleSheet(app_stylesheet(colors))


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


def _show_crash_dialog(summary: str) -> None:
    """At most one crash dialog at a time, and never from inside the failing call.

    An error raised while painting (a delegate, say) repeats on every repaint. Running the
    dialog's modal loop right there made each repaint raise again and open another dialog on
    top of the last, and the window froze ("Not Responding"). Later errors are still logged
    by the hook; they just don't stack more dialogs."""
    global _crash_dialog_open
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
            + (f"Chi tiết đã được ghi vào:\n{log_path}\n\n" if log_path else "")
            + "Nếu lỗi lặp lại, hãy gửi file nhật ký này kèm mô tả thao tác cho nhà phát triển "
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
    install_exception_hooks(show_dialog=_show_crash_dialog)

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
    # The ★ buttons file documents into this built-in collection -- create
    # it up front so it's visible in the sidebar before the first star.
    context.db.ensure_reading_list()

    import_manager = ImportQueueManager(context, num_workers=context.config.config.worker_thread_count)
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
        window = MainWindow(
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

    # Books imported before fingerprints existed get theirs in the background.
    fingerprint_backfill = FingerprintBackfill(context)
    fingerprint_backfill.start()

    # Which books have lost their file (moved, deleted, drive unplugged)? Checked in the background so a big or
    # networked library never delays the window; the status bar shows the answer (S1-04).
    threading.Thread(target=context.relink.check_files, name="missing-files-check", daemon=True).start()
    threading.Thread(target=context.updates.maybe_check_on_startup, name="update-check", daemon=True).start()  # off unless enabled

    exit_code = app.exec()
    fingerprint_backfill.stop()
    auto_classifier.stop()
    smart_classifier.stop()
    context.shutdown()  # only now: the event loop has drained, nothing queries the database any more
    logger.info("Exiting with code %s", exit_code)
    instance_lock.unlock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
