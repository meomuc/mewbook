# SPDX-License-Identifier: AGPL-3.0-or-later
"""The main window of the sheet layout ("Tối giản", layouts/toi-gian/LAYOUT_SPEC.md).

It is the same window as `MainWindow` -- the same search box, toolbar, sidebar, import card, filter bar, library list,
detail panel and status bar, so every function, shortcut and safety rule is shared -- arranged differently: the content
sits on one large rounded sheet (the window's ground shows around it), a top bar with four destinations replaces the
sidebar's header and the toolbar's buttons, the filter column has no border, and the detail panel is a rounded card.
There are two screens under the top bar: "Trang đầu" (home_page.HomePage) and the library. "Sẽ đọc" and "Bộ sưu tập"
are the library with the matching filter switched on.

Nothing here knows a theme: the shape comes from the layout's metrics, the colours from ThemeManager."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QStackedWidget, QVBoxLayout, QWidget

from smartdoc.core.event_bus import DocumentSelectedEvent, FilterChangedEvent
from smartdoc.domain.library_filter import AUTHORS, COLLECTIONS
from smartdoc.presentation.community import open_community_page, open_website
from smartdoc.presentation.home_page import HomePage
from smartdoc.presentation.main_window import DETAIL_OVERLAY_BELOW, MainWindow
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.reader_manager import open_reader
from smartdoc.presentation.sheet_topbar import COLLECTIONS as NAV_COLLECTIONS
from smartdoc.presentation.sheet_topbar import HOME, LIBRARY, READING_LIST, SheetTopBar
from smartdoc.presentation.theme_manager import theme_manager

FILTER_COLUMN_W = 216


class _SheetCanvas(QWidget):
    """The window's ground with a soft shadow under the sheet (painted here: a graphics effect on a sheet this large
    would redraw all of its children into a bitmap on every update)."""

    def __init__(self, sheet: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sheet = sheet
        self.setAutoFillBackground(False)

    def paintEvent(self, _event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(tm.token("bg")))
        radius = float(tm.metric("sheet_radius", 26))
        base = tm.color("shadow")
        painter.setPen(Qt.NoPen)
        rect = QRectF(self._sheet.geometry())
        for spread, scale in ((18, 0.020), (12, 0.030), (7, 0.045), (3, 0.06)):
            tone = QColor(base)
            tone.setAlpha(int(base.alpha() * scale))
            painter.setBrush(tone)
            painter.drawRoundedRect(rect.adjusted(-spread, -spread + 8, spread, spread + 4), radius + spread, radius + spread)


class SheetMainWindow(MainWindow):
    def _compose(self) -> None:
        tm = theme_manager()
        self.sidebar_shell = None  # the layout has no sidebar frame: its logo and Settings live in the top bar
        self._splitter = None
        self._page_name = HOME

        self.top_bar = SheetTopBar(self._build_add_menu(), self._build_tools_menu(), self._build_more_menu())
        self.top_bar.settings_requested.connect(self._on_open_settings)
        self.top_bar.destination_chosen.connect(self.go_to)

        self.home_page = HomePage(self.context)
        self.home_page.open_requested.connect(self._open_book)
        self.home_page.library_requested.connect(self.show_library)
        self.home_page.author_requested.connect(self._show_author)
        self.home_page.add_folder_requested.connect(self._on_add_folder)
        self.home_page.calibre_requested.connect(self._on_import_from_calibre)

        self.library_page = self._build_library_page()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.library_page)

        self.sheet = QFrame()
        self.sheet.setObjectName("Sheet")
        self.sheet.setAttribute(Qt.WA_StyledBackground, True)
        sheet_layout = QVBoxLayout(self.sheet)
        sheet_layout.setContentsMargins(0, 0, 0, 0)
        sheet_layout.setSpacing(0)
        sheet_layout.addWidget(self.top_bar)
        sheet_layout.addWidget(self.pages, stretch=1)

        canvas = _SheetCanvas(self.sheet)
        canvas.setObjectName("SheetCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(int(tm.metric("sheet_margin_x", 22)), int(tm.metric("sheet_margin_y", 14)),
                                         int(tm.metric("sheet_margin_x", 22)), int(tm.metric("sheet_margin_y", 14)))
        canvas_layout.addWidget(self.sheet)
        self.setCentralWidget(canvas)

        self._filter_bridge = QtEventBridge(self)
        self._filter_bridge.event_received.connect(lambda _event: self._sync_destination())
        self._filter_bridge.subscribe(self.context.event_bus, FilterChangedEvent)
        self._filter_bridge.event_received.connect(self._on_selection_event)
        self._filter_bridge.subscribe(self.context.event_bus, DocumentSelectedEvent)
        self._apply_window_style()
        self.top_bar.set_destination(HOME)
        self.pages.setCurrentWidget(self.home_page)
        self._relayout()

    def _build_more_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("Sao lưu thư viện…", lambda: self._on_open_settings("backup"))
        menu.addAction("Quyền riêng tư…", lambda: self._on_open_settings("privacy"))
        menu.addSeparator()
        menu.addAction("Giới thiệu…", self._on_open_about)
        menu.addAction("Trang web chính thức", lambda: open_website())
        menu.addAction("Fanpage cộng đồng", lambda: open_community_page())
        menu.addAction("Báo lỗi…", self._on_open_error_report)
        menu.addSeparator()
        menu.addAction("Bộ sưu tập", lambda: self.go_to(NAV_COLLECTIONS))  # folded here in a narrow window
        return menu

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("LibraryPage")
        # Filter column: the sidebar, without its frame.
        self.sidebar.setMinimumWidth(1)
        column = QWidget()
        column.setFixedWidth(FILTER_COLUMN_W)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(18, 4, 0, 18)
        column_layout.addWidget(self.sidebar)

        # Centre: title, search and view controls, then the import card, missing-files strip, filter chips and the list.
        self.library_title = QLabel("Thư viện")
        self.library_title.setObjectName("LibraryTitle")
        self.omnibar.setMinimumWidth(220)
        self.omnibar.setMaximumWidth(260)
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)
        header.setSpacing(12)
        header.addWidget(self.library_title)
        header.addStretch(1)
        header.addWidget(self.omnibar)
        header.addWidget(self.toolbar)
        centre = QWidget()
        centre.setMinimumWidth(420)
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(8, 0, 8, 0)
        centre_layout.setSpacing(6)
        centre_layout.addLayout(header)
        centre_layout.addWidget(self.import_card)
        centre_layout.addWidget(self.missing_strip)
        centre_layout.addWidget(self.filter_bar)
        centre_layout.addWidget(self.library_view, stretch=1)

        # Detail: a rounded card on the right (a floating overlay in a narrow window, see _relayout).
        self.detail_slot = QWidget()
        self.detail_slot_layout = QVBoxLayout(self.detail_slot)
        self.detail_slot_layout.setContentsMargins(0, 4, 18, 18)
        self.detail_slot_layout.addWidget(self.detail_panel)
        self.detail_slot.setFixedWidth(self._detail_width() + 18)

        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(column)
        row.addWidget(centre, stretch=1)
        row.addWidget(self.detail_slot)
        return page

    def _detail_width(self) -> int:
        from smartdoc.presentation.theme_manager import DETAIL_W

        return max(int(theme_manager().metric("detail_width", 320)), DETAIL_W)  # the panel's own content needs its width

    # -- navigation ---------------------------------------------------------------------------------------------------
    def go_to(self, destination: str) -> None:
        """A top-bar destination. Trang đầu shows the home screen; the other three show the library, with the filter
        that goes with them ("Sẽ đọc" = the reading list; the rest start unfiltered)."""
        if destination == HOME:
            self.top_bar.set_destination(HOME)
            self.pages.setCurrentWidget(self.home_page)
            self._page_name = HOME
            return
        self.context.filters.clear()
        if destination == READING_LIST:
            self.context.filters.select(COLLECTIONS, self.context.db.ensure_reading_list())
        self.show_library()
        self.top_bar.set_destination(destination)
        if destination == NAV_COLLECTIONS:
            self.sidebar.collections_list.setFocus()

    def show_library(self) -> None:
        """The library screen with whatever filters are set."""
        self.pages.setCurrentWidget(self.library_page)
        self._page_name = LIBRARY
        self._sync_destination()
        self._relayout()

    def _sync_destination(self) -> None:
        """Keeps the top bar honest while the library is showing: "Sẽ đọc" only while the reading list is the one
        filter; every other state (unfiltered, or filtered by anything else) is "Thư viện"."""
        if self._page_name != LIBRARY:
            return
        current = self.context.filters.current
        reading_list = self.context.db.ensure_reading_list()
        only_reading_list = (tuple(current.collections) == (reading_list,) and not current.tags and not current.authors
                             and not current.formats and not current.query)
        self.top_bar.set_destination(READING_LIST if only_reading_list else LIBRARY)

    def _show_author(self, name: str) -> None:
        self.context.filters.clear()
        self.context.filters.select(AUTHORS, name)
        self.show_library()

    def _open_book(self, doc: dict) -> None:
        open_reader(self.context, doc, self)

    # -- shape --------------------------------------------------------------------------------------------------------
    def _apply_window_style(self, _key: str = "") -> None:
        tm = theme_manager()
        radius = int(tm.metric("sheet_radius", 26))
        title_font = tm.token("content")
        self.setStyleSheet(
            f"QMainWindow {{ background: {tm.token('bg')}; }}"
            f" #Sheet {{ background: {tm.token('panel')}; border: 1px solid {tm.token('line')}; border-radius: {radius}px; }}"
            f" #LibraryPage, #HomePage {{ background: transparent; }}"
            f" #LibraryTitle {{ color: {tm.token('ink')}; font-family: {title_font}; font-size: 30px; font-weight: 500;"
            f" background: transparent; }}"
        )

    def _column_widths(self) -> tuple[int, int]:
        return FILTER_COLUMN_W, self._detail_width() + 18

    def _relayout(self, *, resize_columns: bool = True) -> None:
        """Below 1200 px the detail card floats over the right edge of the sheet instead of taking a column."""
        if not hasattr(self, "detail_slot"):
            return
        floating = self.width() < DETAIL_OVERLAY_BELOW
        self._detail_floating = floating
        show = self._show_detail
        if floating:
            if self.detail_panel.parent() is not self.library_page:
                self.detail_panel.setParent(self.library_page)
            self.detail_slot.setVisible(False)
            self.detail_panel.setVisible(show)
            self._place_floating_detail()
        else:
            if self.detail_panel.parent() is not self.detail_slot:
                self.detail_slot_layout.addWidget(self.detail_panel)
            self.detail_slot.setVisible(show)
            self.detail_panel.setVisible(show)

    def _place_floating_detail(self) -> None:
        if not self._detail_floating or not hasattr(self, "library_page"):
            return
        width = min(self._detail_width(), max(240, self.library_page.width() - 240))
        self.detail_panel.setGeometry(self.library_page.width() - width - 14, 4, width, self.library_page.height() - 18)
        self.detail_panel.raise_()

    def _on_toggle_detail_panel(self, checked: bool) -> None:
        self._show_detail = checked
        self.context.config.config.show_detail_panel = checked
        self.context.config.save()
        self._relayout()

    def _remember_column_widths(self, *_args) -> None:  # the sheet's columns have fixed widths
        return

    def _on_detail_close_requested(self) -> None:
        self._on_toggle_detail_panel(False)

    def _on_selection_event(self, event) -> None:
        """Choosing a book brings the detail card back if it was closed (there is no toolbar button to reopen it)."""
        if isinstance(event, DocumentSelectedEvent) and not self._show_detail and getattr(event, "doc", None):
            self._on_toggle_detail_panel(True)

    def _content_rect(self):
        return self.centralWidget().geometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._relayout()
