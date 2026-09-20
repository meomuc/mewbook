"""TDD-010 (with the menu bar + toolbar Milestone D upgrades applied).

4-pane layout: sidebar (virtual collections + faceted filters) on the left,
omnibar + sort/cover-size toolbar + library grid in the center, and a
collapsible document detail panel on the right.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from smartdoc import APP_DISPLAY_NAME
from smartdoc.application.calibre_migrator import CalibreImporter
from smartdoc.application.smart_classifier import ClassifyScope, SmartClassifyService
from smartdoc.core.config import THEME_CHOICES
from smartdoc.core.event_bus import ImportBatchCompletedEvent
from smartdoc.presentation.about_dialog import AboutDialog
from smartdoc.presentation.add_document_dialog import AddDocumentDialog
from smartdoc.presentation.community import open_community_page
from smartdoc.presentation.detail_panel import DocumentDetailPanel
from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog
from smartdoc.presentation.active_filter_bar import ActiveFilterBar
from smartdoc.presentation.filter_chips import FilterChipBar
from smartdoc.presentation.icon_rail_sidebar import RAIL_WIDTH, IconRailSidebar
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.manual_report_dialog import ManualReportDialog
from smartdoc.presentation.omnibar import OmnibarSearchBar
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.resources import app_icon_path, brand_logo_path
from smartdoc.presentation.selection_action_bar import SelectionActionBar
from smartdoc.presentation.relink_dialog import RelinkDialog
from smartdoc.presentation.settings_dialog import SettingsDialog
from smartdoc.presentation.smart_classify_bar import SmartClassifyBar
from smartdoc.presentation.smart_classify_dialogs import SmartClassifyOfferDialog
from smartdoc.presentation.sidebar import LibrarySidebar
from smartdoc.presentation.status_bar_panel import StatusBarPanel
from smartdoc.presentation.theme import THEMES, action_css, action_text, current_colors
from smartdoc.presentation.theme_effects import (
    GrainOverlay,
    RetroTitleBar,
    apply_font_letter_spacing,
    theme_preview_pixmap,
)
from smartdoc.presentation.toolbar import LibraryToolbar


class MainWindow(QMainWindow):
    def __init__(
        self,
        context,
        watcher=None,
        import_manager=None,
        parent=None,
        on_appearance_changed=None,
        smart_classifier: SmartClassifyService | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager
        # Cheap to build: no model, tokenizer or worker process exists until a
        # classification job actually starts. app.py passes one in so it
        # survives the window being rebuilt for a theme change.
        self.smart_classifier = smart_classifier or SmartClassifyService(context)
        # Called (with this window) after Settings closes if the user
        # changed theme/font -- see app.py's on_appearance_changed, which
        # rebuilds the window in place rather than requiring a real app
        # restart (theme.py can't live-restyle already-built stylesheets).
        self._on_appearance_changed = on_appearance_changed

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1400, 800)
        self.setAcceptDrops(True)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        colors = current_colors()
        # background/surface are the chrome-family tokens (dark for Inky
        # Night, light otherwise) -- always paired with sidebar_text here,
        # never text, which is fixed dark because the content grid/list is
        # always light. Pairing text with a dark background would render
        # invisible dark-on-dark menu text on Inky Night.
        self.setStyleSheet(
            f"QMainWindow {{ background: {colors.background}; color: {colors.sidebar_text}; }}"
            f" QSplitter::handle {{ background: {colors.border}; }}"
            f" QSplitter::handle:horizontal {{ width: 1px; }}"
            f" QMenuBar {{ background: {colors.background}; color: {colors.sidebar_text}; }}"
            f" QMenuBar::item:selected {{ background: {colors.border}; }}"
            f" QMenu {{ background: {colors.surface}; color: {colors.sidebar_text}; border: 1px solid {colors.border}; }}"
            f" QMenu::item:selected {{ background: {colors.selected_bg}; color: {colors.selected_text}; }}"
            # Thin, arrow-less scrollbars everywhere in the window.
            f" QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}"
            f" QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}"
            f" QScrollBar::handle {{ background: {colors.border}; border-radius: 4px; min-height: 30px; min-width: 30px; }}"
            f" QScrollBar::handle:hover {{ background: {colors.muted_text}; }}"
            f" QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}"
            f" QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
        )

        # Each theme is designed around its own navigation/detail
        # structure, not just its own palette (see theme.py's layout_mode /
        # icon_rail_sidebar): "Mực Đêm" collapses the sidebar to an icon
        # rail, "Kệ Sách Gỗ" drops the right-hand detail panel in favour of
        # a filter chip bar on top and a selection action bar along the
        # bottom. Everything below the chrome -- the same library view, the
        # same event bus, the same collections/filters -- is shared.
        self.sidebar = IconRailSidebar(context) if colors.icon_rail_sidebar else LibrarySidebar(context)
        if isinstance(self.sidebar, IconRailSidebar):
            self.sidebar.add_requested.connect(self._on_add_files)
            self.sidebar.settings_requested.connect(self._on_open_settings)
        self._uses_action_bar = colors.layout_mode == "action_bar"

        self.omnibar = OmnibarSearchBar(context)
        self.toolbar = LibraryToolbar(context)
        self.library_view = LibraryListWidget(context, import_manager=import_manager)
        self.library_view.set_view_mode(context.config.config.view_mode)
        self.library_view.set_grid_icon_width(colors.default_cover_width)

        self.detail_panel = None if self._uses_action_bar else DocumentDetailPanel(context)
        self.filter_chips = FilterChipBar(context) if colors.show_filter_chips else None
        self.action_bar = SelectionActionBar(context) if self._uses_action_bar else None

        # Must come after self.library_view exists -- several Edit menu
        # actions connect directly to its bound methods (not lambdas), so
        # the attribute lookup happens at connect time.
        self._build_menu()

        library_container = QWidget()
        library_container.setObjectName("LibraryContainer")
        library_container.setStyleSheet(f"#LibraryContainer {{ background: {colors.content_bg}; }}")
        library_layout = QVBoxLayout(library_container)
        library_layout.setContentsMargins(0, 0, 0, 8)
        library_layout.setSpacing(0)
        self.smart_bar = SmartClassifyBar(context, self.smart_classifier, self.library_view.classification_scope)
        library_layout.addWidget(self.smart_bar)
        # What the list is filtered by, with a one-click way out; hidden when nothing is.
        self.filter_bar = ActiveFilterBar(context)
        library_layout.addWidget(self.filter_bar)
        library_layout.addWidget(self.library_view)
        self.library_view.smart_classify_requested.connect(self._on_classify_selected)

        if self.detail_panel is not None:
            # Inner splitter: library view | detail panel
            self._content_splitter = QSplitter(Qt.Horizontal)
            self._content_splitter.setHandleWidth(1)
            self._content_splitter.addWidget(library_container)
            self._content_splitter.addWidget(self.detail_panel)
            self._content_splitter.setStretchFactor(0, 3)
            self._content_splitter.setStretchFactor(1, 1)
            self._content_splitter.setSizes([900, 340])
            self.detail_panel.setVisible(context.config.config.show_detail_panel)
            content_widget = self._content_splitter
        else:
            self._content_splitter = None
            content_widget = library_container

        # Outer splitter: sidebar | content area
        splitter = QSplitter()
        splitter.setHandleWidth(1)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(content_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 5)
        sidebar_width = RAIL_WIDTH if colors.icon_rail_sidebar else 240
        splitter.setSizes([sidebar_width, 1400 - sidebar_width])

        # Brand, search and the view/sort controls live in one bar across
        # the whole window, above sidebar | library | detail panel -- the
        # way the design mockups lay out every theme.
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        if colors.titlebar_text:
            central_layout.addWidget(RetroTitleBar(colors, central))
        central_layout.addWidget(self._build_header_bar(colors))
        central_layout.addWidget(splitter, stretch=1)
        if self.action_bar is not None:
            # Across the whole window bottom, under the sidebar too.
            central_layout.addWidget(self.action_bar)
        self.setCentralWidget(central)
        # Film grain over everything (mouse-transparent), for themes that want it.
        self.grain_overlay = GrainOverlay(central) if colors.grain_overlay else None
        status_bar = StatusBarPanel(context, self)
        status_bar.relink_requested.connect(self._on_open_relink)
        self.setStatusBar(status_bar)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, ImportBatchCompletedEvent)

    def _build_header_bar(self, colors) -> QWidget:
        header = QWidget(self)
        header.setObjectName("HeaderBar")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header.setStyleSheet(
            f"#HeaderBar {{ background: {colors.header_bg}; border-bottom: 1px solid {colors.border}; }}"
            f" #HeaderBar QLabel {{ color: {colors.sidebar_text}; background: transparent; }}"
        )
        row = QHBoxLayout(header)
        side = max(16, colors.page_margin)
        row.setContentsMargins(0 if colors.icon_rail_sidebar else side, 10, side, 10)
        row.setSpacing(12)

        logo = QLabel(header)
        logo.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(brand_logo_path()))
        if not pixmap.isNull():
            logo_px = 34 if colors.icon_rail_sidebar else 30
            logo.setPixmap(pixmap.scaled(logo_px, logo_px, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if colors.icon_rail_sidebar:
            # Centered over the icon rail's column, like the mockup.
            logo.setFixedWidth(RAIL_WIDTH)
        row.addWidget(logo)
        if colors.icon_rail_sidebar:
            row.addSpacing(8)
        brand_name = APP_DISPLAY_NAME.upper() if colors.brand_caps else APP_DISPLAY_NAME
        brand = QLabel(f"{colors.brand_prefix}{brand_name}", header)
        brand.setObjectName("BrandLabel")
        if colors.brand_caps:
            # Quiet, spaced-out wordmark (Japandi) instead of a bold title.
            brand.setStyleSheet("font-weight: 400; font-size: 17px;")
            apply_font_letter_spacing(brand, 118)
        else:
            brand.setStyleSheet("font-weight: 700; font-size: 19px;")
        row.addWidget(brand)
        row.addSpacing(8)

        self.omnibar.setMaximumWidth(680)
        row.addWidget(self.omnibar, stretch=3)
        if self.filter_chips is not None:
            row.addWidget(self.filter_chips)
        row.addStretch(1)
        row.addWidget(self.toolbar)
        if colors.header_add_button:
            # Some themes put "add" right in the header instead of only in
            # the File menu.
            add_button = QPushButton(action_text(colors.add_button_label), header)
            add_button.setObjectName("HeaderAddButton")
            add_button.setCursor(Qt.PointingHandCursor)
            if colors.action_style == "default":
                add_button.setStyleSheet(
                    f"QPushButton {{ background: {colors.accent}; color: {colors.accent_text}; border: none;"
                    f" border-radius: {colors.control_radius}px; padding: 9px 18px; font-weight: 600; font-size: 14px; }}"
                    f" QPushButton:hover {{ background: {colors.selected_text}; }}"
                )
            else:
                add_button.setStyleSheet(f"QPushButton {{ {action_css(colors, font_px=14)} }}")
            add_button.clicked.connect(self._on_add_files)
            row.addWidget(add_button)
        if not colors.show_cover_size_slider:
            self.toolbar.set_size_control_visible(False)
        return header

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        add_files_action = QAction("📄 Thêm file...", self)
        add_files_action.triggered.connect(self._on_add_files)
        file_menu.addAction(add_files_action)
        add_folder_action = QAction("📁 Thêm thư mục...", self)
        add_folder_action.triggered.connect(self._on_add_folder)
        file_menu.addAction(add_folder_action)
        file_menu.addSeparator()
        import_calibre_action = QAction("📥 Nhập từ thư viện Calibre...", self)
        import_calibre_action.triggered.connect(self._on_import_from_calibre)
        file_menu.addAction(import_calibre_action)
        file_menu.addSeparator()
        send_ereader_action = QAction("📱 Gửi tới máy đọc sách...", self)
        send_ereader_action.triggered.connect(self._on_send_to_ereader)
        file_menu.addAction(send_ereader_action)
        file_menu.addSeparator()
        exit_action = QAction("🚪 Thoát", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        select_all_action = QAction("☑️ Chọn tất cả", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(lambda: self.library_view._active_view().selectAll())
        edit_menu.addAction(select_all_action)
        clear_selection_action = QAction("⬜ Bỏ chọn", self)
        clear_selection_action.setShortcut("Ctrl+Shift+A")
        clear_selection_action.triggered.connect(self.library_view.clear_selection)
        edit_menu.addAction(clear_selection_action)
        edit_menu.addSeparator()
        edit_selected_action = QAction("✏️ Chỉnh sửa", self)
        edit_selected_action.triggered.connect(self.library_view.edit_selected)
        edit_menu.addAction(edit_selected_action)
        delete_selected_action = QAction("🗑️ Xóa", self)
        delete_selected_action.setShortcut("Del")
        delete_selected_action.triggered.connect(self.library_view.delete_selected)
        edit_menu.addAction(delete_selected_action)
        edit_menu.addSeparator()
        copy_action = QAction("📋 Sao chép", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.library_view.copy_selected)
        edit_menu.addAction(copy_action)
        cut_action = QAction("✂️ Cắt", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.triggered.connect(self.library_view.cut_selected)
        edit_menu.addAction(cut_action)
        paste_action = QAction("📥 Dán", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.library_view.paste_files)
        edit_menu.addAction(paste_action)

        # Grid/List is now the icon toggle at the start of LibraryToolbar
        # (same row as sort), not here -- one control for it, not two.
        view_menu = self.menuBar().addMenu("&View")
        sidebar_action = QAction("◀▶ Hiện/Ẩn Sidebar", self, checkable=True)
        sidebar_action.setChecked(True)
        sidebar_action.toggled.connect(lambda checked: self.sidebar.setVisible(checked))
        view_menu.addAction(sidebar_action)

        self._detail_panel_action = QAction("ℹ️ Hiện/Ẩn Panel chi tiết", self, checkable=True)
        self._detail_panel_action.setChecked(self.context.config.config.show_detail_panel)
        self._detail_panel_action.toggled.connect(self._on_toggle_detail_panel)
        # "Kệ Sách Gỗ" has no detail panel at all (its selection action bar
        # replaces it) -- a toggle that can't do anything is worse than no
        # toggle, so it's disabled with an explanation rather than hidden.
        if self.detail_panel is None:
            self._detail_panel_action.setEnabled(False)
            self._detail_panel_action.setChecked(False)
            self._detail_panel_action.setToolTip(
                "Giao diện \"Walnut Library\" dùng thanh hành động ở đáy thay cho panel chi tiết."
            )
        view_menu.addAction(self._detail_panel_action)

        tools_menu = self.menuBar().addMenu("&Tools")
        duplicates_action = QAction("🧹 Dọn dẹp trùng lặp...", self)
        duplicates_action.triggered.connect(self._on_open_duplicate_finder)
        tools_menu.addAction(duplicates_action)
        smart_classify_action = QAction("✨ Phân loại thông minh danh sách đang xem...", self)
        smart_classify_action.triggered.connect(lambda: self.smart_bar.ask_and_start(self.library_view.classification_scope()))
        tools_menu.addAction(smart_classify_action)
        relink_action = QAction("🔎 Tìm lại file thiếu...", self)
        relink_action.triggered.connect(self._on_open_relink)
        tools_menu.addAction(relink_action)
        backup_action = QAction("💾 Sao lưu thư viện...", self)
        backup_action.triggered.connect(lambda: self._on_open_settings(initial_tab="backup"))
        tools_menu.addAction(backup_action)
        tools_menu.addSeparator()
        settings_action = QAction("⚙️ Cài đặt...", self)
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("ℹ️ Giới thiệu (About)...", self)
        about_action.triggered.connect(self._on_open_about)
        help_menu.addAction(about_action)
        community_action = QAction("📣 Fanpage cộng đồng & tin cập nhật", self)
        community_action.setToolTip("Mở fanpage Facebook của Mèo Mực trong trình duyệt: tin về các bản nâng cấp mới và nơi gửi góp ý.")
        community_action.triggered.connect(lambda _checked=False: open_community_page())
        help_menu.addAction(community_action)
        report_action = QAction("🐞 Báo lỗi…", self)
        report_action.triggered.connect(self._on_open_error_report)
        help_menu.addAction(report_action)

        self._build_theme_picker()

    def _build_theme_picker(self) -> None:
        """A theme switcher parked in the menu bar's right corner --
        switching look-and-feel is something people try repeatedly (and
        compare back and forth), so it shouldn't be buried three clicks
        deep in Settings. Picking one here goes through exactly the same
        save + rebuild path as the Settings tab does (see
        app.py's on_appearance_changed), so the two stay in sync."""
        colors = current_colors()
        self.theme_picker = QComboBox(self)
        self.theme_picker.setToolTip("Đổi giao diện")
        self.theme_picker.setIconSize(QSize(40, 25))
        for key in THEME_CHOICES:
            self.theme_picker.addItem(QIcon(theme_preview_pixmap(THEMES[key])), THEMES[key].display_name, key)
        current_index = self.theme_picker.findData(self.context.config.config.theme)
        if current_index >= 0:
            self.theme_picker.setCurrentIndex(current_index)
        self.theme_picker.setStyleSheet(
            f"QComboBox {{ background: {colors.surface}; color: {colors.sidebar_text};"
            f" border: 1px solid {colors.border}; border-radius: 6px; padding: 2px 8px; margin-right: 8px; }}"
        )
        self.theme_picker.activated.connect(self._on_theme_picked)

        corner = QWidget(self)
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.addWidget(self.theme_picker)
        self.menuBar().setCornerWidget(corner, Qt.TopRightCorner)

    def _on_theme_picked(self, index: int) -> None:
        key = self.theme_picker.itemData(index)
        if not key or key == self.context.config.config.theme:
            return
        self.context.config.config.theme = key
        self.context.config.save()
        if self._on_appearance_changed:
            self._on_appearance_changed(self)

    def _on_toggle_detail_panel(self, checked: bool) -> None:
        if self.detail_panel is None:
            return
        self.detail_panel.setVisible(checked)
        self.context.config.config.show_detail_panel = checked
        self.context.config.save()

    def _on_open_duplicate_finder(self) -> None:
        DuplicateFinderDialog(self.context, self).exec()

    def _on_open_relink(self) -> None:
        dialog = RelinkDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()

    def _on_open_about(self) -> None:
        AboutDialog(self, identity=self.context.identity).exec()

    def _on_open_error_report(self) -> None:
        dialog = ManualReportDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()

    def _on_open_settings(self, initial_tab: str | None = None) -> None:
        dialog = SettingsDialog(self.context, self, watcher=self.watcher, import_manager=self.import_manager, initial_tab=initial_tab)
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
        AddDocumentDialog(self.context, self.import_manager, self).exec()

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

    def _on_send_to_ereader(self) -> None:
        self.library_view.send_selected_to_ereader()

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, ImportBatchCompletedEvent):
            self._show_import_summary(event)

    def _show_import_summary(self, event: ImportBatchCompletedEvent) -> None:
        summary = (
            f"Thêm thành công: {event.success}\n"
            f"Đã có trong thư viện (bỏ qua): {event.duplicate}\n"
            f"Thất bại: {event.failed}"
        )
        mode = self.context.config.config.smart_classify_on_import
        new_ids = list(event.doc_ids)
        can_classify = bool(new_ids) and mode != "never" and self.smart_classifier.availability()[0]
        if not can_classify or mode == "always":
            QMessageBox.information(self, "Kết quả thêm file", summary)
            if can_classify:
                self.smart_classifier.enqueue(new_ids)
            return

        # One compact popup carries both the import result and the question,
        # instead of a summary box followed by a second box.
        dialog = SmartClassifyOfferDialog(len(new_ids), summary, self)
        dialog.exec()
        wants = dialog.wants_classification()
        if dialog.remember_choice():
            self.context.config.config.smart_classify_on_import = "always" if wants else "never"
            self.context.config.save()
        if wants:
            self.smart_classifier.enqueue(new_ids)

    def _on_classify_selected(self, doc_ids: list) -> None:
        scope = ClassifyScope(doc_ids=tuple(doc_ids), description=f"{len(doc_ids):,} tài liệu đã chọn")
        self.smart_bar.ask_and_start(scope, subject="các tài liệu đã chọn")

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

    def _running_work(self) -> list[str]:
        """What the app is busy with in the background, for the exit prompt."""
        work = []
        pending = self.import_manager.pending_count() if self.import_manager else 0
        if pending:
            work.append(f"nhập {pending} tài liệu")
        if self.smart_classifier.running:
            work.append("phân loại thông minh")
        return work

    def closeEvent(self, event) -> None:
        work = self._running_work()
        if work:
            answer = QMessageBox.question(
                self,
                "Đang xử lý",
                f"Ứng dụng đang {' và '.join(work)}.\n\n"
                "Nếu thoát bây giờ, các tác vụ này sẽ bị dừng và ứng dụng có thể "
                "không phản hồi tới khoảng 10 giây cho đến khi dừng hẳn.\n\nBạn vẫn muốn thoát?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)  # the stops below block until the work has ended
        try:
            self._stop_background_work()
        finally:
            if work:
                QApplication.restoreOverrideCursor()
        # The database stays open here: events the workers published while
        # stopping are still queued for the GUI thread and refresh widgets
        # once this returns. app.py closes it after the event loop ends.
        event.accept()

    def _stop_background_work(self) -> None:
        if self.watcher:
            self.watcher.stop()
        if self.import_manager:
            self.import_manager.stop()
        self.smart_classifier.stop()


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
