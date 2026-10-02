"""Main window of the "Kệ sách" design: [sidebar 226] | [toolbar + shelf/table] | [detail panel 324], status bar below.

One layout for every theme (themes differ in colour and type only, via ThemeManager). Widths are remembered; below
1200 px the detail panel floats over the right edge instead of taking a column, and below 1100 px the sidebar
narrows to 200 px and the toolbar keeps icons only. The window never exceeds the screen (see dialog_size).
The old menu bar is kept but hidden -- its actions stay on the window so their shortcuts (Ctrl+A, Del, Ctrl+C...) work
and the toolbar's "Công cụ" menu reuses them.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from smartdoc import APP_DISPLAY_NAME, APP_NAME
from smartdoc.application.calibre_migrator import CalibreImporter
from smartdoc.application.library_export import export_library_csv
from smartdoc.application.smart_classifier import ClassifyScope, SmartClassifyService
from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.about_dialog import AboutDialog
from smartdoc.presentation.active_filter_bar import ActiveFilterBar
from smartdoc.presentation.add_document_dialog import AddDocumentDialog
from smartdoc.presentation.author_cleanup_dialog import AuthorCleanupDialog
from smartdoc.presentation.app_toolbar import COMPACT_BELOW, AppToolbar
from smartdoc.presentation.community import open_community_page, open_website
from smartdoc.presentation.detail_panel import DocumentDetailPanel
from smartdoc.presentation.dialog_size import fit_window_to_screen
from smartdoc.presentation.drop_overlay import DropOverlay
from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog
from smartdoc.presentation.excluded_books_dialog import ExcludedBooksDialog
from smartdoc.presentation.import_card import ImportStatusCard
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.manual_report_dialog import ManualReportDialog
from smartdoc.presentation.omnibar import OmnibarSearchBar
from smartdoc.presentation.library_cleanup_dialog import LibraryCleanupDialog
from smartdoc.presentation.relink_dialog import RelinkDialog
from smartdoc.presentation.resources import app_icon_path
from smartdoc.presentation.settings_dialog import SettingsDialog
from smartdoc.presentation.sidebar import LibrarySidebar
from smartdoc.presentation.sidebar_shell import SidebarShell
from smartdoc.presentation.missing_files_strip import MissingFilesStrip
from smartdoc.presentation.smart_classify_wizard import SmartClassifyWizard
from smartdoc.presentation.status_bar_panel import StatusBarPanel
from smartdoc.presentation.task_progress_dialog import run_with_progress
from smartdoc.presentation.theme_manager import DETAIL_W, SIDEBAR_W, theme_manager
from smartdoc.presentation.toolbar import LibraryToolbar

MIN_WINDOW_SIZE = (1024, 640)
DETAIL_OVERLAY_BELOW = 1200  # under this width the detail panel floats over the right edge
SIDEBAR_COMPACT_W = 200


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
        # Called (with this window) after Settings closes if the user changed theme/font -- app.py rebuilds the
        # window in place (same context, fresh widgets), so nothing needs an app restart.
        self._on_appearance_changed = on_appearance_changed

        self._fitted_to_screen = False
        self.setWindowTitle(f"{APP_NAME} – {APP_DISPLAY_NAME}")
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        self.resize(1400, 860)
        fit_window_to_screen(self)  # a small screen gets a smaller window, never one over the taskbar
        self.setAcceptDrops(True)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._apply_window_style()
        theme_manager().themeChanged.connect(self._apply_window_style)

        config = context.config.config
        self.omnibar = OmnibarSearchBar(context)
        self.toolbar = LibraryToolbar(context)
        self.library_view = LibraryListWidget(context, import_manager=import_manager)
        self.library_view.set_view_mode(config.view_mode)
        self.detail_panel = DocumentDetailPanel(context)
        self.detail_panel.close_requested.connect(self._on_detail_close_requested)
        self.detail_panel.ereader_requested.connect(self._on_send_to_ereader)

        # The menu bar is hidden but alive: its actions carry the shortcuts and feed the toolbar's menus.
        self._build_menu()
        self.sidebar = LibrarySidebar(context)
        # How adding books is going (progress, then ONE summary) -- a card in the library, never a pop-up.
        self.import_card = ImportStatusCard(context, import_manager, self.smart_classifier)
        self.missing_strip = MissingFilesStrip(context)
        self.missing_strip.relink_requested.connect(self._on_open_relink)
        self.classify_wizard: SmartClassifyWizard | None = None  # made when asked for (Công cụ, or a right-click)
        # What the list is filtered by, with a one-click way out; hidden when nothing is.
        self.filter_bar = ActiveFilterBar(context)
        self.library_view.smart_classify_requested.connect(self._on_classify_selected)
        self.library_view.add_files_requested.connect(self._on_add_files)
        self.library_view.add_folder_requested.connect(self._on_add_folder)
        self._detail_floating = False
        self._narrow = self.width() < COMPACT_BELOW
        self._show_detail = config.show_detail_panel
        self._compose()  # the shape of the window: this class draws the shelf look, a subclass another

        status_bar = StatusBarPanel(context, self)
        status_bar.relink_requested.connect(self._on_open_relink)
        self.setStatusBar(status_bar)

        self.drop_overlay = DropOverlay(self)  # not a child of the splitter: it would become a pane of it

    def _compose(self) -> None:
        """Arranges the parts built in __init__ (toolbar, sidebar, import card, filter bar, library, detail panel) into the
        window: [sidebar | toolbar + list | detail panel]. A layout with another shape overrides this and `_relayout`."""
        config = self.context.config.config
        self.app_toolbar = AppToolbar(self.omnibar, self.toolbar, self._build_add_menu(), self._build_tools_menu())
        self.app_toolbar.detail_button.setChecked(config.show_detail_panel)
        self.app_toolbar.detail_toggled.connect(self._on_toggle_detail_panel)
        self.sidebar_shell = SidebarShell(self.sidebar)
        self.sidebar_shell.settings_requested.connect(self._on_open_settings)

        main_area = QWidget()
        main_area.setObjectName("MainArea")
        main_area.setMinimumWidth(480)  # smaller than any font-driven hint, so the columns can always be narrowed
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.app_toolbar)
        main_layout.addWidget(self.import_card)
        main_layout.addWidget(self.missing_strip)
        main_layout.addWidget(self.filter_bar)
        main_layout.addWidget(self.library_view, stretch=1)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self.sidebar_shell)
        self._splitter.addWidget(main_area)
        self._splitter.addWidget(self.detail_panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.splitterMoved.connect(self._remember_column_widths)
        self.setCentralWidget(self._splitter)
        self._relayout()

    def _on_detail_close_requested(self) -> None:
        self.app_toolbar.detail_button.setChecked(False)

    def _content_rect(self):
        """The area the drop overlay covers: everything the window shows above its status bar."""
        return self._splitter.geometry()

    def _apply_window_style(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(f"QMainWindow, #MainArea {{ background: {tm.token('bg')}; }}")

    # -- responsive layout --------------------------------------------------------------------------------------------
    def _column_widths(self) -> tuple[int, int]:
        config = self.context.config.config
        compact = self.width() < COMPACT_BELOW
        sidebar = SIDEBAR_COMPACT_W if compact else (config.sidebar_width or SIDEBAR_W)
        return sidebar, config.detail_width or DETAIL_W

    def _relayout(self, *, resize_columns: bool = True) -> None:
        """Applies the window's current width: floating detail panel, icon-only toolbar and (unless the user is just
        dragging the window edge, where the stretch factors keep the side columns as they are) the column widths."""
        width = self.width()
        sidebar, detail = self._column_widths()
        floating = width < DETAIL_OVERLAY_BELOW
        if floating != self._detail_floating:
            self._detail_floating = floating
            resize_columns = True
            if floating:
                self.detail_panel.setParent(self)
                self.detail_panel.raise_()
            else:
                self._splitter.addWidget(self.detail_panel)
        self.detail_panel.setVisible(self._show_detail)
        if resize_columns:
            # The splitter has not been laid out for the new width yet when this runs from resizeEvent: size it first,
            # or Qt would scale the numbers below to its old width.
            self._splitter.setGeometry(0, 0, width, self._splitter.height())
            if floating:
                self._splitter.setSizes([sidebar, max(200, width - sidebar)])
            else:
                self._splitter.setSizes(
                    [sidebar, max(200, width - sidebar - (detail if self._show_detail else 0)), detail])
        self._place_floating_detail()

    def _place_floating_detail(self) -> None:
        if not self._detail_floating:
            return
        _sidebar, detail = self._column_widths()
        detail = min(detail, max(240, self.width() - 240))
        status_h = self.statusBar().height() if self.statusBar() is not None else 0
        self.detail_panel.setGeometry(self.width() - detail, 0, detail, self.height() - status_h)
        self.detail_panel.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        if hasattr(self, "_splitter") and self._splitter is not None:
            narrow = self.width() < COMPACT_BELOW
            self._relayout(resize_columns=narrow != self._narrow)
            self._narrow = narrow

    def _remember_column_widths(self, *_args) -> None:
        if self._detail_floating:
            return
        sizes = self._splitter.sizes()
        config = self.context.config.config
        if self.width() >= COMPACT_BELOW and sizes[0] > 0:
            config.sidebar_width = sizes[0]
        if self._show_detail and sizes[2] > 0:
            config.detail_width = sizes[2]

    def _build_add_menu(self) -> QMenu:
        menu = QMenu(self)
        for label, slot in ((vi.ADD_FILES, self._on_add_files), (vi.ADD_FOLDER, self._on_add_folder),
                            (vi.IMPORT_CALIBRE, self._on_import_from_calibre)):
            menu.addAction(label, slot)
        return menu

    def _build_tools_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(vi.TOOL_SMART_CLASSIFY, lambda: self.open_smart_classify())
        menu.addAction(vi.TOOL_AUTHOR_CLEANUP, self._on_open_author_cleanup)
        menu.addAction(vi.TOOL_DUPLICATES, self._on_open_duplicate_finder)
        menu.addAction(vi.TOOL_TRASH, self._on_open_trash)
        menu.addAction(vi.TOOL_EXCLUDED, self._on_open_excluded)
        menu.addAction(vi.TOOL_GATHER, self._on_open_gather)
        menu.addAction(vi.TOOL_METADATA_UPDATE, self._on_open_metadata_batch_update)
        menu.addAction(vi.TOOL_RELINK, self._on_open_relink)
        menu.addAction("Dọn dẹp thư viện…", self._on_open_library_cleanup)
        menu.addAction(vi.TOOL_SEND_EREADER, self._on_send_to_ereader)
        menu.addAction(vi.TOOL_CONVERT_FORMAT, self._on_convert_format)
        menu.addSeparator()
        menu.addAction(vi.TOOL_EXPORT, self._on_export_library)
        menu.addAction(vi.TOOL_BACKUP, lambda: self._on_open_settings(initial_tab="backup"))
        menu.addSeparator()
        help_menu = menu.addMenu(vi.TOOL_HELP_HEADING)
        help_menu.addAction("Giới thiệu…", self._on_open_about)
        help_menu.addAction("Trang web chính thức", lambda: open_website())
        help_menu.addAction("Fanpage cộng đồng", lambda: open_community_page())
        help_menu.addAction("Báo lỗi…", self._on_open_error_report)
        return menu

    def _on_open_author_cleanup(self) -> None:
        dialog = AuthorCleanupDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()

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
        send_ereader_action = QAction("Gửi tới máy đọc sách...", self)
        send_ereader_action.triggered.connect(self._on_send_to_ereader)
        file_menu.addAction(send_ereader_action)
        convert_format_action = QAction(vi.TOOL_CONVERT_FORMAT, self)
        convert_format_action.triggered.connect(self._on_convert_format)
        file_menu.addAction(convert_format_action)
        file_menu.addSeparator()
        exit_action = QAction("Thoát", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        select_all_action = QAction("Chọn tất cả", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(lambda: self.library_view._active_view().selectAll())
        edit_menu.addAction(select_all_action)
        clear_selection_action = QAction("⬜ Bỏ chọn", self)
        clear_selection_action.setShortcut("Ctrl+Shift+A")
        clear_selection_action.triggered.connect(self.library_view.clear_selection)
        edit_menu.addAction(clear_selection_action)
        edit_menu.addSeparator()
        edit_selected_action = QAction("Chỉnh sửa", self)
        edit_selected_action.triggered.connect(self.library_view.edit_selected)
        edit_menu.addAction(edit_selected_action)
        delete_selected_action = QAction("Xóa", self)
        delete_selected_action.setShortcut("Del")
        delete_selected_action.triggered.connect(self.library_view.delete_selected)
        edit_menu.addAction(delete_selected_action)
        edit_menu.addSeparator()
        copy_action = QAction("Sao chép", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.library_view.copy_selected)
        edit_menu.addAction(copy_action)
        cut_action = QAction("Cắt", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.triggered.connect(self.library_view.cut_selected)
        edit_menu.addAction(cut_action)
        paste_action = QAction("Dán", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.library_view.paste_files)
        edit_menu.addAction(paste_action)

        tools_menu = self.menuBar().addMenu("&Tools")
        duplicates_action = QAction("Dọn dẹp trùng lặp...", self)
        duplicates_action.triggered.connect(self._on_open_duplicate_finder)
        tools_menu.addAction(duplicates_action)
        smart_classify_action = QAction("Phân loại thông minh danh sách đang xem...", self)
        smart_classify_action.triggered.connect(lambda: self.open_smart_classify())
        tools_menu.addAction(smart_classify_action)
        relink_action = QAction("Tìm lại file thiếu...", self)
        relink_action.triggered.connect(self._on_open_relink)
        tools_menu.addAction(relink_action)
        cleanup_action = QAction("Dọn dẹp thư viện (file quá nhỏ, sách mất file)...", self)
        cleanup_action.triggered.connect(self._on_open_library_cleanup)
        tools_menu.addAction(cleanup_action)
        backup_action = QAction("Sao lưu thư viện...", self)
        backup_action.triggered.connect(lambda: self._on_open_settings(initial_tab="backup"))
        tools_menu.addAction(backup_action)
        tools_menu.addSeparator()
        settings_action = QAction("Cài đặt...", self)
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("Giới thiệu (About)...", self)
        about_action.triggered.connect(self._on_open_about)
        help_menu.addAction(about_action)
        website_action = QAction("Trang web chính thức", self)
        website_action.setToolTip("Mở trang web chính thức của Mèo Mực trong trình duyệt: giới thiệu, tải bản mới, tin cập nhật và lộ trình.")
        website_action.triggered.connect(lambda _checked=False: open_website())
        help_menu.addAction(website_action)
        community_action = QAction("Fanpage cộng đồng & tin cập nhật", self)
        community_action.setToolTip("Mở fanpage Facebook của Mèo Mực trong trình duyệt: tin về các bản nâng cấp mới và nơi gửi góp ý.")
        community_action.triggered.connect(lambda _checked=False: open_community_page())
        help_menu.addAction(community_action)
        report_action = QAction("Báo lỗi…", self)
        report_action.triggered.connect(self._on_open_error_report)
        help_menu.addAction(report_action)

        self.menuBar().setVisible(False)
        for menu_action in self.menuBar().actions():
            if menu_action.menu():
                self.addActions(menu_action.menu().actions())  # keeps shortcuts alive while the bar is hidden

    def _on_toggle_detail_panel(self, checked: bool) -> None:
        self._show_detail = checked
        self.detail_panel.setVisible(checked)
        self._relayout()
        self.context.config.config.show_detail_panel = checked
        self.context.config.save()

    def _on_open_duplicate_finder(self) -> None:
        DuplicateFinderDialog(self.context, self).exec()

    def _on_open_metadata_batch_update(self) -> None:
        """"Cập nhật thông tin sách" -- the merged file-facts + bibliographic-lookup tool. Not modal, so the
        library stays usable while it runs on a background thread."""
        from smartdoc.presentation.metadata_batch_dialog import MetadataBatchUpdateDialog

        old = getattr(self, "_metadata_batch_dialog", None)
        if old is not None and shiboken6.isValid(old) and old.isVisible():
            if old.isMinimized():  # "Chạy nền" minimizes it while it works -- bring it back, not just to the front
                old.showNormal()
            old.raise_()
            old.activateWindow()
            return
        dialog = MetadataBatchUpdateDialog(self.context, self.library_view.classification_scope, self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._metadata_batch_dialog = dialog
        dialog.show()

    def _on_open_gather(self) -> None:
        from smartdoc.presentation.gather_dialog import GatherDialog

        dialog = GatherDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()

    def _on_open_trash(self) -> None:
        from smartdoc.presentation.trash_dialog import TrashDialog

        dialog = TrashDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()

    def _on_open_excluded(self) -> None:
        dialog = ExcludedBooksDialog(self.context, self.import_manager, self)
        dialog.exec()
        dialog.deleteLater()

    def _on_export_library(self) -> None:
        """Saves the list of books as a CSV file (spreadsheet-ready), written off the GUI thread."""
        name = f"MewBook-danh-sach-{datetime.now():%Y-%m-%d}.csv"
        path, _filter = QFileDialog.getSaveFileName(self, "Xuất danh sách sách", str(Path(self._start_directory()) / name), "CSV (*.csv)")
        if not path:
            return
        self._remember_directory(str(Path(path).parent))
        count, error = run_with_progress(
            self, title="Xuất danh sách", message="Mèo đang ghi danh sách sách ra file CSV…", delay_ms=400,
            work=lambda progress: export_library_csv(self.context.db, path, lambda done, total: progress(done, total, "Đang ghi…")))
        if count is None:
            QMessageBox.warning(self, "Chưa xuất được", f"Không ghi được file: {error}")
        else:
            self.import_card.show_notice(f"Đã xuất {count:,} sách ra {Path(path).name}.".replace(",", "."))

    def _on_open_relink(self) -> None:
        dialog = RelinkDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()

    def _on_open_library_cleanup(self) -> None:
        dialog = LibraryCleanupDialog(self.context, self, on_relink=self._on_open_relink)
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
        dialog.calibre_import_requested.connect(self._on_import_from_calibre)
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
        # Reading a big Calibre catalogue and queueing every book took long enough on the GUI thread to look like a hang.
        count, error = run_with_progress(
            self, title="Nhập từ Calibre", message="Mèo đang đọc thư viện Calibre và xếp sách vào hàng chờ nhập…",
            work=lambda _progress: importer.import_library(folder), delay_ms=400,
            hint="Đọc xong, thanh tiến trình nhập sách sẽ hiện ở đầu danh sách. Thư viện Calibre chỉ được đọc, không bị thay đổi.")
        if count is None:
            if "metadata.db" in error:  # CalibreImporter's FileNotFoundError: the folder holds no catalogue
                self.import_card.show_notice("Thư mục này không phải thư viện Calibre (không thấy metadata.db).")
            else:
                self.import_card.show_notice(f"Không đọc được thư viện Calibre: {error}")
            return
        if count == 0:
            self.import_card.show_notice("Không tìm thấy sách nào để thêm trong thư viện Calibre này.")
        # Otherwise the progress card appears by itself; the Calibre library is only read, never changed.

    def _on_send_to_ereader(self) -> None:
        self.library_view.send_selected_to_ereader()

    def _on_convert_format(self) -> None:
        self.library_view.convert_selected_documents()

    def _on_classify_selected(self, doc_ids: list) -> None:
        scope = ClassifyScope(doc_ids=tuple(doc_ids), description=f"{len(doc_ids):,} sách đã chọn trong danh sách")
        self.open_smart_classify(selected_scope=scope)

    def open_smart_classify(self, selected_scope: ClassifyScope | None = None) -> SmartClassifyWizard:
        """Shows the three-step classification dialog. A job that is already running (dialog sent to the background)
        is picked up again instead of starting a second dialog."""
        wizard = self.classify_wizard
        if wizard is not None and (wizard.isVisible() or self.smart_classifier.running):
            wizard.show()
            wizard.raise_()
            return wizard
        if wizard is not None:
            wizard.deleteLater()
        wizard = SmartClassifyWizard(self.context, self.smart_classifier, self.library_view.classification_scope, self,
                                     selected_scope=selected_scope)
        wizard.background_finished.connect(self.import_card.show_notice)
        wizard.finished.connect(self._on_classify_wizard_closed)
        self.classify_wizard = wizard
        wizard.show()
        return wizard

    def _on_classify_wizard_closed(self, _result: int) -> None:
        # Closed with a job still running = "Chạy nền": keep the dialog so its events (and the result) are not lost.
        if not self.smart_classifier.running:
            wizard, self.classify_wizard = self.classify_wizard, None
            if wizard is not None:
                wizard.deleteLater()

    def dragEnterEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_overlay.show_over(self._content_rect())

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        self.drop_overlay.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        self.drop_overlay.hide()
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
        if self.statusBar().has_task("ereader-send"):
            work.append("gửi sách sang máy đọc")
        if self.statusBar().has_task("format-conversion"):
            work.append("chuyển đổi định dạng")
        return work

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        if not self._fitted_to_screen:
            self._fitted_to_screen = True  # once: the frame is only known now, and the user may move it later
            fit_window_to_screen(self)
            self._relayout()  # the real width is known now (the constructor's was only a guess)

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
