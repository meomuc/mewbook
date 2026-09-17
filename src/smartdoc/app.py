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
    apply_theme(app, context.config.config.theme)

    font_family = context.config.config.font_family
    font = QFont(font_family) if font_family else app.font()
    font.setPointSize(context.config.config.font_size)
    app.setFont(font)

    window = MainWindow(context, watcher=watcher, import_manager=import_manager)
    window.show()

    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
