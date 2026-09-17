"""TDD-010 (with the menu bar + toolbar Milestone D upgrades applied).

4-pane layout: sidebar (virtual collections + faceted filters) on the left,
omnibar + sort/cover-size toolbar + library grid in the center, and a
collapsible document detail panel on the right.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget

from smartdoc.application.calibre_migrator import CalibreImporter
from smartdoc.core.config import KNOWN_EXTENSIONS
from smartdoc.core.event_bus import ImportBatchCompletedEvent
from smartdoc.presentation.detail_panel import DocumentDetailPanel
from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.omnibar import OmnibarSearchBar
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.resources import app_icon_path
from smartdoc.presentation.settings_dialog import SettingsDialog
from smartdoc.presentation.sidebar import LibrarySidebar
from smartdoc.presentation.status_bar_panel import StatusBarPanel
from smartdoc.presentation.theme import current_colors
from smartdoc.presentation.toolbar import LibraryToolbar


class MainWindow(QMainWindow):
    def __init__(self, context, watcher=None, import_manager=None, parent=None, on_appearance_changed=None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager
        # Called (with this window) after Settings closes if the user
        # changed theme/font -- see app.py's on_appearance_changed, which
        # rebuilds the window in place rather than requiring a real app
        # restart (theme.py can't live-restyle already-built stylesheets).
        self._on_appearance_changed = on_appearance_changed

        self.setWindowTitle("SmartDoc Library")
        self.resize(1400, 800)
        self.setAcceptDrops(True)
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

        self.detail_panel = DocumentDetailPanel(context)

        # Inner splitter: library view | detail panel
        library_container = QWidget()
        library_layout = QVBoxLayout(library_container)
        library_layout.setContentsMargins(12, 12, 12, 12)
        library_layout.addWidget(self.omnibar)
        library_layout.addWidget(self.toolbar)
        library_layout.addWidget(self.library_view)

        self._content_splitter = QSplitter(Qt.Horizontal)
        self._content_splitter.addWidget(library_container)
        self._content_splitter.addWidget(self.detail_panel)
        self._content_splitter.setStretchFactor(0, 3)
        self._content_splitter.setStretchFactor(1, 1)
        self._content_splitter.setSizes([900, 340])

        # Restore detail panel visibility from config
        show_panel = context.config.config.show_detail_panel
        self.detail_panel.setVisible(show_panel)

        # Outer splitter: sidebar | content area
        splitter = QSplitter()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self._content_splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([240, 1160])

        self.setCentralWidget(splitter)
        self.setStatusBar(StatusBarPanel(context, self))

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, ImportBatchCompletedEvent)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        add_files_action = QAction("Thêm file...", self)
        add_files_action.triggered.connect(self._on_add_files)
        file_menu.addAction(add_files_action)
        add_folder_action = QAction("Thêm thư mục...", self)
        add_folder_action.triggered.connect(self._on_add_folder)
        file_menu.addAction(add_folder_action)
        file_menu.addSeparator()
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
        select_all_action.triggered.connect(lambda: self.library_view._active_view().selectAll())
        edit_menu.addAction(select_all_action)

        # Grid/List is now the icon toggle at the start of LibraryToolbar
        # (same row as sort), not here -- one control for it, not two.
        view_menu = self.menuBar().addMenu("&View")
        sidebar_action = QAction("Hiện/Ẩn Sidebar", self, checkable=True)
        sidebar_action.setChecked(True)
        sidebar_action.toggled.connect(lambda checked: self.sidebar.setVisible(checked))
        view_menu.addAction(sidebar_action)

        self._detail_panel_action = QAction("Hiện/Ẩn Panel chi tiết", self, checkable=True)
        self._detail_panel_action.setChecked(self.context.config.config.show_detail_panel)
        self._detail_panel_action.toggled.connect(self._on_toggle_detail_panel)
        view_menu.addAction(self._detail_panel_action)

        tools_menu = self.menuBar().addMenu("&Tools")
        duplicates_action = QAction("Dọn dẹp trùng lặp...", self)
        duplicates_action.triggered.connect(self._on_open_duplicate_finder)
        tools_menu.addAction(duplicates_action)
        tools_menu.addSeparator()
        settings_action = QAction("Cài đặt...", self)
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

    def _on_toggle_detail_panel(self, checked: bool) -> None:
        self.detail_panel.setVisible(checked)
        self.context.config.config.show_detail_panel = checked
        self.context.config.save()

    def _on_open_duplicate_finder(self) -> None:
        DuplicateFinderDialog(self.context, self).exec()

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self.context, self, watcher=self.watcher, import_manager=self.import_manager)
        dialog.exec()
        if dialog.appearance_changed and self._on_appearance_changed:
            self._on_appearance_changed(self)

    def _start_directory(self) -> str:
        return self.context.config.config.last_used_directory or ""

    def _remember_directory(self, path: str) -> None:
        directory = path if Path(path).is_dir() else str(Path(path).parent)
        self.context.config.config.last_used_directory = directory
        self.context.config.save()

    def _on_add_files(self) -> None:
        if not self.import_manager:
            return
        filter_str = "Tài liệu (" + " ".join(f"*.{ext}" for ext in KNOWN_EXTENSIONS) + ");;Mọi file (*)"
        files, _selected_filter = QFileDialog.getOpenFileNames(
            self, "Chọn file để thêm vào thư viện", self._start_directory(), filter_str
        )
        if not files:
            return
        self._remember_directory(files[0])
        self.import_manager.add_files(files)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục để theo dõi", self._start_directory())
        if not folder:
            return
        self._remember_directory(folder)
        self.context.config.add_watch_folder(folder)
        if self.watcher:
            self.watcher.add_folder(folder)
        if self.import_manager:
            self.import_manager.scan_folder(folder)

    def _on_import_from_calibre(self) -> None:
        if not self.import_manager:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục thư viện Calibre (chứa metadata.db)", self._start_directory()
        )
        if not folder:
            return
        self._remember_directory(folder)
        importer = CalibreImporter(self.context, self.import_manager)
        try:
            count = importer.import_library(folder)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Không tìm thấy thư viện Calibre", str(exc))
            return
        QMessageBox.information(
            self, "Nhập từ Calibre", f"Đã đưa {count} sách vào hàng đợi xử lý. Thư viện Calibre gốc không bị thay đổi."
        )

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, ImportBatchCompletedEvent):
            self._show_import_summary(event)

    def _show_import_summary(self, event: ImportBatchCompletedEvent) -> None:
        QMessageBox.information(
            self,
            "Kết quả thêm file",
            f"Thêm thành công: {event.success}\n"
            f"Đã có trong thư viện (bỏ qua): {event.duplicate}\n"
            f"Thất bại: {event.failed}",
        )

    def dragEnterEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        if not self.import_manager:
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths:
            return
        event.acceptProposedAction()
        file_paths = [p for p in paths if Path(p).is_file()]
        folder_paths = [p for p in paths if Path(p).is_dir()]
        if file_paths:
            self.import_manager.add_files(file_paths)
        for folder in folder_paths:
            self.import_manager.scan_folder(folder)

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
