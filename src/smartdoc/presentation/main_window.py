"""TDD-010 (with the menu bar + toolbar Milestone D upgrades applied).

3-pane layout: sidebar (virtual collections + faceted filters) on the left,
omnibar + sort/cover-size toolbar + library grid on the right.
"""
from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget

from smartdoc.application.calibre_migrator import CalibreImporter
from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.omnibar import OmnibarSearchBar
from smartdoc.presentation.resources import app_icon_path
from smartdoc.presentation.settings_dialog import SettingsDialog
from smartdoc.presentation.sidebar import LibrarySidebar
from smartdoc.presentation.theme import current_colors
from smartdoc.presentation.toolbar import LibraryToolbar


class MainWindow(QMainWindow):
    def __init__(self, context, watcher=None, import_manager=None, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager

        self.setWindowTitle("SmartDoc Library")
        self.resize(1200, 800)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        colors = current_colors()
        self.setStyleSheet(
            f"QMainWindow {{ background: {colors.background}; color: {colors.text}; }}"
            f" QSplitter::handle {{ background: {colors.border}; }}"
            f" QMenuBar {{ background: {colors.background}; color: {colors.text}; }}"
            f" QMenuBar::item:selected {{ background: {colors.border}; }}"
            f" QMenu {{ background: {colors.surface}; color: {colors.text}; border: 1px solid {colors.border}; }}"
            f" QMenu::item:selected {{ background: {colors.accent}; color: {colors.accent_text}; }}"
        )

        self._build_menu()

        self.sidebar = LibrarySidebar(context)

        self.omnibar = OmnibarSearchBar(context)
        self.toolbar = LibraryToolbar(context)
        self.library_view = LibraryListWidget(context)
        self.library_view.set_view_mode(context.config.config.view_mode)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.addWidget(self.omnibar)
        content_layout.addWidget(self.toolbar)
        content_layout.addWidget(self.library_view)

        splitter = QSplitter()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([240, 960])

        self.setCentralWidget(splitter)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        add_folder_action = QAction("Thêm thư mục...", self)
        add_folder_action.triggered.connect(self._on_add_folder)
        file_menu.addAction(add_folder_action)
        import_calibre_action = QAction("Nhập từ thư viện Calibre...", self)
        import_calibre_action.triggered.connect(self._on_import_from_calibre)
        file_menu.addAction(import_calibre_action)
        file_menu.addSeparator()
        exit_action = QAction("Thoát", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        select_all_action = QAction("Chọn tất cả", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(lambda: self.library_view.list_view.selectAll())
        edit_menu.addAction(select_all_action)

        view_menu = self.menuBar().addMenu("&View")
        grid_action = QAction("Dạng lưới (Grid)", self, checkable=True)
        list_action = QAction("Dạng danh sách (List)", self, checkable=True)
        grid_action.setChecked(self.context.config.config.view_mode != "list")
        list_action.setChecked(self.context.config.config.view_mode == "list")
        grid_action.triggered.connect(lambda: self._set_view_mode("grid"))
        list_action.triggered.connect(lambda: self._set_view_mode("list"))
        for action in (grid_action, list_action):
            view_menu.addAction(action)
        view_menu.addSeparator()
        sidebar_action = QAction("Hiện/Ẩn Sidebar", self, checkable=True)
        sidebar_action.setChecked(True)
        sidebar_action.toggled.connect(lambda checked: self.sidebar.setVisible(checked))
        view_menu.addAction(sidebar_action)

        tools_menu = self.menuBar().addMenu("&Tools")
        duplicates_action = QAction("Dọn dẹp trùng lặp...", self)
        duplicates_action.triggered.connect(self._on_open_duplicate_finder)
        tools_menu.addAction(duplicates_action)
        tools_menu.addSeparator()
        settings_action = QAction("Cài đặt...", self)
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

    def _on_open_duplicate_finder(self) -> None:
        DuplicateFinderDialog(self.context, self).exec()

    def _set_view_mode(self, mode: str) -> None:
        self.context.config.config.view_mode = mode
        self.context.config.save()
        self.library_view.set_view_mode(mode)

    def _on_open_settings(self) -> None:
        SettingsDialog(self.context, self, watcher=self.watcher).exec()

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục để theo dõi")
        if not folder:
            return
        self.context.config.add_watch_folder(folder)
        if self.watcher:
            self.watcher.add_folder(folder)
        if self.import_manager:
            self.import_manager.scan_folder(folder)

    def _on_import_from_calibre(self) -> None:
        if not self.import_manager:
            return
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục thư viện Calibre (chứa metadata.db)")
        if not folder:
            return
        importer = CalibreImporter(self.context, self.import_manager)
        try:
            count = importer.import_library(folder)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Không tìm thấy thư viện Calibre", str(exc))
            return
        QMessageBox.information(
            self, "Nhập từ Calibre", f"Đã đưa {count} sách vào hàng đợi xử lý. Thư viện Calibre gốc không bị thay đổi."
        )

    def closeEvent(self, event) -> None:
        if self.watcher:
            self.watcher.stop()
        if self.import_manager:
            self.import_manager.stop()
        self.context.shutdown()
        event.accept()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "doc1", {"title": "Demo Book", "author": "Someone", "file_path": __file__, "created_at": 0.0}
        )

        app = QApplication(sys.argv)
        from smartdoc.presentation.theme import apply_theme

        apply_theme(app, context.config.config.theme)
        window = MainWindow(context)
        window.show()
        sys.exit(app.exec())
