"""Composition root: wires AppContext + background services + the Qt UI together."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from smartdoc.application.file_watcher import LibraryWatcher
from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.core.app_context import AppContext
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.resources import app_icon_path
from smartdoc.presentation.theme import apply_theme


def _apply_appearance(app: QApplication, context: AppContext) -> None:
    apply_theme(app, context.config.config.theme)
    font_family = context.config.config.font_family
    font = QFont(font_family) if font_family else app.font()
    font.setPointSize(context.config.config.font_size)
    app.setFont(font)


def main() -> None:
    context = AppContext()

    import_manager = ImportQueueManager(context, num_workers=context.config.config.worker_thread_count)
    import_manager.start()

    watcher = LibraryWatcher(context)
    watcher.start()

    app = QApplication(sys.argv)
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # A plain local variable inside on_appearance_changed would go out of
    # scope (and, with no C++ or Python owner, be garbage-collected out from
    # under the still-visible window) as soon as the callback returns -- this
    # holder keeps whichever window is current alive for as long as the app
    # runs.
    current_window: list[MainWindow] = []

    def build_and_show_window() -> MainWindow:
        _apply_appearance(app, context)
        window = MainWindow(
            context, watcher=watcher, import_manager=import_manager, on_appearance_changed=on_appearance_changed
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

    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
