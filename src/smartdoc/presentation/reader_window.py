# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-app Document Reader window (stage G10).

A single independent top-level window (not a modal dialog), so the user can keep reading while the main library window
stays usable. PDF is rendered with Qt's own QtPdf module; EPUB with QTextBrowser reading chapters (in spine order) out
of the zip via infrastructure/epub_reader.py -- Qt has no first-party EPUB widget, but QTextBrowser's HTML subset is
enough for typical chapter markup. AZW3/MOBI are unpacked to a temporary EPUB/HTML first (see `_build_mobi_reader`);
anything that cannot be read shows a plain "open it with another app" message.

The frame follows the "Kệ sách" design: a top bar (☰ contents, title and format, ‹ Trang [n] / N ›, − 110% +, "Vừa trang |
Vừa chiều rộng", full screen), a contents column on the left that folds away, the page on a `surface2` ground (dark
themes get a warm dark page), and a bottom bar with the key hints and "Cửa sổ đọc đang mở: N / M". Keys: ← → Space
Backspace PgUp PgDn turn pages, Ctrl+G goes to a page, F11 toggles full screen, Esc leaves it.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPointF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette, QPixmap, QShortcut, QStandardItem, QStandardItemModel, QTextDocument
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import ReadingProgressUpdatedEvent
from smartdoc.infrastructure.epub_reader import EpubDocument, EpubReadError
from smartdoc.presentation.dialog_size import fit_window_to_screen
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

logger = logging.getLogger(__name__)

_ZOOM_STEP = 0.15
_ZOOM_MIN = 0.25
_ZOOM_MAX = 4.0
_ZOOM_CHOICES = (50, 75, 100, 110, 125, 150, 200, 300)

# Kindle formats. Not zip/OPF containers like EPUB, so they can't be read directly -- they're unpacked to a temporary
# EPUB/HTML first (see _build_mobi_reader) and then rendered by the regular readers below.
_MOBI_LIKE_EXTENSIONS = {"mobi", "azw3", "azw", "prc"}

# How long the floating prev/next buttons stay visible after the last scroll before fading back out of the way.
_FLOATING_NAV_HIDE_MS = 2200
_FLOATING_NAV_MARGIN = 18
TOC_WIDTH = 230


class _ReaderEvents(QObject):
    """One place the windows and the manager meet: "the number of open reader windows changed"."""

    changed = Signal()


reader_events = _ReaderEvents()


def reader_limit(context) -> int:
    """Reader windows allowed at once: Settings > Hiệu năng, else the default of 5."""
    from smartdoc.presentation.reader_manager import MAX_OPEN_READERS

    return max(1, int(context.config.config.max_reader_windows or MAX_OPEN_READERS))


def _key_cap(text: str, parent: QWidget) -> QLabel:
    tm = theme_manager()
    cap = QLabel(text, parent)
    cap.setStyleSheet(f"border: 1px solid {tm.token('line2')}; border-radius: 3px; padding: 0 4px; font-size: 11px;"
                      f" color: {tm.token('ink2')}; background: {tm.token('surface')};")
    return cap


class _FloatingNavButtons(QWidget):
    """Prev/next buttons floating over the reading area itself, revealed by scrolling and auto-hidden again once
    scrolling stops. The top bar already has the same two buttons, but once you've scrolled a few pages down that bar is
    the furthest thing from where your eyes and cursor actually are."""

    def __init__(self, parent: QWidget, on_previous, on_next) -> None:
        super().__init__(parent)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(_FLOATING_NAV_HIDE_MS)
        self._hide_timer.timeout.connect(self.hide)

        tm = theme_manager()
        self.previous_button = QPushButton(self)
        self.previous_button.setIcon(line_icon("chevron_left", "#ffffff", 18))
        self.previous_button.setToolTip("Trang trước (PageUp hoặc ←)")
        self.next_button = QPushButton(self)
        self.next_button.setIcon(line_icon("chevron_right", "#ffffff", 18))
        self.next_button.setToolTip("Trang sau (PageDown hoặc →)")
        for button in (self.previous_button, self.next_button):
            button.setFixedSize(44, 44)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: rgba(20,20,20,0.78); border: none; border-radius: 22px; }}"
                f" QPushButton:hover {{ background: {tm.token('accent')}; }}"
            )
        self.previous_button.clicked.connect(lambda: (on_previous(), self.reveal()))
        self.next_button.clicked.connect(lambda: (on_next(), self.reveal()))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.next_button)
        self.hide()

    def reveal(self) -> None:
        self.reposition()
        self.show()
        self.raise_()
        self._hide_timer.start()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - _FLOATING_NAV_MARGIN
        self.move(max(0, x), max(0, y))


class _EpubTextBrowser(QTextBrowser):
    """Resolves <img> tags referenced (relatively) from whichever chapter is currently displayed, by pulling the image
    bytes straight out of the EPUB zip -- QTextBrowser has no idea these paths live inside an archive."""

    def __init__(self, epub_doc: EpubDocument, parent=None) -> None:
        super().__init__(parent)
        self._epub_doc = epub_doc
        self.current_chapter_index = 0

    def loadResource(self, resource_type: int, url: QUrl):  # noqa: N802 -- Qt override
        if resource_type == QTextDocument.ImageResource:
            data = self._epub_doc.read_resource(self.current_chapter_index, url.toString())
            if data:
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    return pixmap
        return super().loadResource(resource_type, url)


class ReaderTopBar(QFrame):
    """☰  Title PDF        ‹ Trang [57] / 248 ›   − 110% +  [Vừa trang | Vừa chiều rộng]  ⛶"""

    toc_toggled = Signal(bool)
    previous_requested = Signal()
    next_requested = Signal()
    page_chosen = Signal(int)
    zoom_out_requested = Signal()
    zoom_in_requested = Signal()
    zoom_percent_chosen = Signal(int)
    fit_page_requested = Signal()
    fit_width_requested = Signal()
    fullscreen_toggled = Signal(bool)

    def __init__(self, title: str, format_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ReaderTopBar")
        tm = theme_manager()
        ink = tm.token("ink")

        def flat(icon: str | None, tooltip: str, checkable: bool = False, text: str = "") -> QPushButton:
            button = QPushButton(text, self)
            if icon:
                button.setIcon(line_icon(icon, ink, 16))
            button.setToolTip(tooltip)
            button.setCheckable(checkable)
            button.setFixedSize(34, 32)
            button.setCursor(Qt.PointingHandCursor)
            return button

        self.toc_button = flat("panel", "Mục lục", checkable=True)
        self.toc_button.setChecked(True)
        self.toc_button.toggled.connect(self.toc_toggled)
        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(f"font-family: {tm.token('content')}; font-weight: 600; font-size: 15px; color: {ink};")
        self.format_label = QLabel(format_label, self)
        self.format_label.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px;")

        self.previous_button = flat("chevron_left", "Trang trước (PageUp, ← hoặc Backspace)")
        self.previous_button.clicked.connect(self.previous_requested)
        self.next_button = flat("chevron_right", "Trang sau (PageDown, → hoặc Space)")
        self.next_button.clicked.connect(self.next_requested)
        self.page_caption = QLabel("Trang", self)
        self.page_spin = QSpinBox(self)
        self.page_spin.setMinimum(1)
        self.page_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.page_spin.setFixedWidth(56)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setToolTip("Tới trang (Ctrl+G)")
        self.page_spin.valueChanged.connect(self.page_chosen)
        self.total_label = QLabel(" / 1", self)

        self.zoom_out_button = flat(None, "Thu nhỏ (−)", text="−")
        self.zoom_out_button.clicked.connect(self.zoom_out_requested)
        self.zoom_combo = QComboBox(self)
        self.zoom_combo.setEditable(False)
        for percent in _ZOOM_CHOICES:
            self.zoom_combo.addItem(f"{percent}%", percent)
        self.zoom_combo.setCurrentIndex(_ZOOM_CHOICES.index(100))
        self.zoom_combo.activated.connect(lambda index: self.zoom_percent_chosen.emit(self.zoom_combo.itemData(index)))
        self.zoom_in_button = flat("plus", "Phóng to (+)")
        self.zoom_in_button.clicked.connect(self.zoom_in_requested)

        self.fit_page_button = QPushButton("Vừa trang", self)
        self.fit_page_button.setCheckable(True)
        self.fit_width_button = QPushButton("Vừa chiều rộng", self)
        self.fit_width_button.setCheckable(True)
        self.fit_width_button.setChecked(True)
        self.fit_page_button.clicked.connect(lambda: self._chose_fit(page=True))
        self.fit_width_button.clicked.connect(lambda: self._chose_fit(page=False))
        self.fullscreen_button = flat("expand", "Toàn màn hình (F11)", checkable=True)
        self.fullscreen_button.toggled.connect(self.fullscreen_toggled)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(6)
        row.addWidget(self.toc_button)
        row.addSpacing(6)
        row.addWidget(self.title_label)
        row.addWidget(self.format_label)
        row.addStretch(1)
        self.page_widgets = [self.previous_button, self.page_caption, self.page_spin, self.total_label, self.next_button]
        for widget in self.page_widgets:
            row.addWidget(widget)
        row.addSpacing(14)
        self.zoom_widgets = [self.zoom_out_button, self.zoom_combo, self.zoom_in_button]
        for widget in self.zoom_widgets:
            row.addWidget(widget)
        row.addSpacing(8)
        self.fit_widgets = [self.fit_page_button, self.fit_width_button]
        for widget in self.fit_widgets:
            row.addWidget(widget)
        row.addSpacing(8)
        row.addWidget(self.fullscreen_button)
        self._restyle()

    def _restyle(self) -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#ReaderTopBar {{ background: {tm.token('surface')}; border-bottom: 1px solid {tm.token('line')}; }}"
            f" #ReaderTopBar QPushButton:checked {{ background: {tm.token('accentsoft')}; }}"
        )

    def _chose_fit(self, *, page: bool) -> None:
        self.fit_page_button.setChecked(page)
        self.fit_width_button.setChecked(not page)
        (self.fit_page_requested if page else self.fit_width_requested).emit()

    def set_total(self, total: int, caption: str = "Trang") -> None:
        self.page_spin.setMaximum(max(1, total))
        self.total_label.setText(f" / {max(1, total)}")
        self.page_caption.setText(caption)

    def show_navigation(self, on: bool) -> None:
        for widget in self.page_widgets:
            widget.setVisible(on)

    def show_zoom(self, on: bool, *, percent_and_fit: bool = True) -> None:
        for widget in self.zoom_widgets:
            widget.setVisible(on)
        for widget in (self.zoom_combo, *self.fit_widgets):
            widget.setVisible(on and percent_and_fit)


class ReaderWindow(QMainWindow):
    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        # QMainWindow embeds as a child widget when given a parent (unlike QDialog, which is always top-level) -- force it
        # to stay an independent top-level window so a parent widget can still own it for lifetime management.
        self.setWindowFlag(Qt.Window, True)
        # Closing a QMainWindow only hides it by default, which would leave the whole rendered document resident and keep
        # occupying one of the slots reader_manager hands out.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.context = context
        self.doc = doc
        self.file_actions = FileActionEngine(context)
        self.setWindowTitle(doc.get("title") or "Đọc tài liệu")
        self.resize(1100, 900)
        self.setMinimumSize(640, 420)
        self._fitted_to_screen = False
        fit_window_to_screen(self)  # 900 px tall is more than a laptop screen has above its taskbar
        self.closed = False
        self._toc_visible = True
        self._page_label = "Trang"
        tm = theme_manager()
        self.setStyleSheet(f"QMainWindow {{ background: {tm.token('bg')}; }}")

        extension = (doc.get("extension") or "").lower()
        file_path = doc.get("file_path", "")
        self._build_frame(doc, extension)

        if extension == "pdf" and Path(file_path).exists():
            self._build_pdf_reader(file_path)
        elif extension == "epub" and Path(file_path).exists():
            self._build_epub_reader(file_path)
        elif extension in _MOBI_LIKE_EXTENSIONS and Path(file_path).exists():
            self._build_mobi_reader(file_path)
        else:
            self._build_fallback(file_path)

        self._install_shortcuts()
        self._start_reading_history()
        reader_events.changed.connect(self._update_open_count)
        self._update_open_count()

    # ── Reading history: when it was opened and where the reader is (the "Trang đầu" screen) ──────────

    _POSITION_SAVE_DELAY_MS = 800  # a page turn is remembered a moment later, not written on every keypress

    def _reading_unit_and_total(self) -> tuple[str, int]:
        if hasattr(self, "pdf_view"):
            return "page", max(1, self._pdf_document.pageCount())
        if getattr(self, "_epub_doc", None) is not None:
            return "chapter", max(1, self._epub_doc.chapter_count)
        return "page", 0

    def _start_reading_history(self) -> None:
        self._history_ready = False
        self._pending_position = 0
        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.setInterval(self._POSITION_SAVE_DELAY_MS)
        self._position_timer.timeout.connect(self._flush_position)
        doc_id = self.doc.get("id")
        if not doc_id:
            return
        unit, total = self._reading_unit_and_total()
        saved = self.context.db.get_reading_progress(doc_id) or {}
        self.context.db.record_reading_open(doc_id, unit=unit, total=total)
        self.context.event_bus.publish(ReadingProgressUpdatedEvent(doc_id=doc_id))
        target = int(saved.get("position") or 0)
        self._history_ready = True  # from here on a page change is the reader's own, not the initial load
        if 1 < target <= max(total, 1) and total:
            self._resume_at(unit, target)

    def _resume_at(self, unit: str, position: int) -> None:
        """Back to where the reader left off (1-based page or chapter)."""
        if unit == "chapter" and getattr(self, "_epub_doc", None) is not None:
            self._go_to_chapter(position - 1)
        elif hasattr(self, "pdf_view"):
            QTimer.singleShot(0, lambda: self._go_to_page(position))  # after the view has laid out its pages

    def _remember_position(self, position: int) -> None:
        if getattr(self, "_history_ready", False) and self.doc.get("id"):
            self._pending_position = position
            self._position_timer.start()

    def _flush_position(self) -> None:
        if self._pending_position > 0 and self.doc.get("id"):
            _, total = self._reading_unit_and_total()
            self.context.db.record_reading_position(self.doc["id"], self._pending_position, total=total)
            self.context.event_bus.publish(ReadingProgressUpdatedEvent(doc_id=self.doc["id"]))
            self._pending_position = 0

    # ── The frame: top bar, contents column, page area, bottom bar ──────────

    def _build_frame(self, doc: dict, extension: str) -> None:
        tm = theme_manager()
        self.top_bar = ReaderTopBar(doc.get("title") or "Đọc tài liệu", extension.upper())
        self.top_bar.toc_toggled.connect(self._set_toc_visible)
        self.top_bar.fullscreen_toggled.connect(self._toggle_fullscreen)
        self.top_bar.show_navigation(False)
        self.top_bar.show_zoom(False)

        self.toc_heading = QLabel("MỤC LỤC", self)
        self.toc_heading.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px; letter-spacing: 1px; padding: 12px 14px 4px 14px;")
        self.toc_view = QTreeView(self)
        self.toc_view.setHeaderHidden(True)
        self.toc_view.setEditTriggers(QTreeView.NoEditTriggers)
        self.toc_view.setFrameShape(QFrame.NoFrame)
        self.toc_view.setStyleSheet(f"QTreeView {{ background: transparent; color: {tm.token('ink')}; outline: 0; }}"
                                    f" QTreeView::item {{ padding: 4px 4px; border-radius: 4px; }}"
                                    f" QTreeView::item:selected {{ background: {tm.token('accentsoft')}; color: {tm.token('ink')}; }}")
        self.toc_panel = QFrame(self)
        self.toc_panel.setObjectName("ReaderToc")
        self.toc_panel.setFixedWidth(TOC_WIDTH)
        self.toc_panel.setStyleSheet(f"#ReaderToc {{ background: {tm.token('surface')}; border-right: 1px solid {tm.token('line')}; }}")
        toc_layout = QVBoxLayout(self.toc_panel)
        toc_layout.setContentsMargins(0, 0, 0, 0)
        toc_layout.setSpacing(0)
        toc_layout.addWidget(self.toc_heading)
        toc_layout.addWidget(self.toc_view, 1)
        self.toc_panel.hide()

        self.page_area = QFrame(self)  # where the document view goes
        self.page_area.setObjectName("ReaderPageArea")
        self.page_area.setStyleSheet(f"#ReaderPageArea {{ background: {tm.token('surface2')}; }}")
        self.page_layout = QVBoxLayout(self.page_area)
        self.page_layout.setContentsMargins(0, 0, 0, 0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.toc_panel)
        body.addWidget(self.page_area, 1)

        self.hints_row = QHBoxLayout()
        self.hints_row.setSpacing(5)
        self.hints_row.setContentsMargins(12, 0, 12, 0)
        for text in ("Phím", None, "chuyển trang,", "F11", "toàn màn hình,", "Ctrl", "+", "G", "tới trang"):
            if text is None:
                self.hints_row.addWidget(_key_cap("←", self))
                self.hints_row.addWidget(_key_cap("→", self))
            elif text in ("F11", "Ctrl", "G"):
                self.hints_row.addWidget(_key_cap(text, self))
            else:
                label = QLabel(text, self)
                label.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 12px;")
                self.hints_row.addWidget(label)
        self.hints_row.addStretch(1)
        self.open_count_label = QLabel("", self)
        self.open_count_label.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 12px;")
        self.bottom_bar = QFrame(self)
        self.bottom_bar.setObjectName("ReaderBottom")
        self.bottom_bar.setFixedHeight(28)
        self.bottom_bar.setStyleSheet(f"#ReaderBottom {{ background: {tm.token('surface')}; border-top: 1px solid {tm.token('line')}; }}")
        bottom = QHBoxLayout(self.bottom_bar)
        bottom.setContentsMargins(0, 0, 12, 0)
        bottom.addLayout(self.hints_row, 1)
        bottom.addWidget(self.open_count_label)

        container = QWidget(self)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.top_bar)
        outer.addLayout(body, 1)
        outer.addWidget(self.bottom_bar)
        self._container = container
        self.setCentralWidget(container)

    def _install_view(self, view: QWidget) -> None:
        self.page_layout.addWidget(view)

    def _set_toc_visible(self, visible: bool) -> None:
        self._toc_visible = visible
        self.toc_panel.setVisible(visible and self.toc_view.model() is not None)

    def _show_toc(self, model) -> None:
        self.toc_view.setModel(model)
        self.toc_panel.setVisible(self._toc_visible)
        self.top_bar.toc_button.setVisible(True)

    def _install_shortcuts(self) -> None:
        def bind(keys, slot):
            for key in keys if isinstance(keys, (list, tuple)) else [keys]:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.setContext(Qt.WindowShortcut)
                shortcut.activated.connect(slot)

        bind("F11", self._toggle_fullscreen_shortcut)
        bind("Esc", self._leave_fullscreen)
        bind("Ctrl+G", self.focus_page_box)
        bind(["PgUp"], self._page_previous)
        bind(["PgDown"], self._page_next)

    def _update_open_count(self) -> None:
        from smartdoc.presentation.reader_manager import open_count

        count = max(1, open_count())  # this window counts even before the manager has listed it
        self.open_count_label.setText(f"Cửa sổ đọc đang mở: {count} / {reader_limit(self.context)}")

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        if not self._fitted_to_screen:
            self._fitted_to_screen = True
            fit_window_to_screen(self)
        self._update_open_count()

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._position_timer.stop()
        self._flush_position()  # the last page turn is not lost to the delay
        epub_doc = getattr(self, "_epub_doc", None)
        if epub_doc is not None:
            epub_doc.close()
        # Kindle books are unpacked into a temp directory to be readable at all (see _build_mobi_reader) -- without this,
        # every MOBI opened would leave a full copy of itself behind in %TEMP%.
        tempdir = getattr(self, "_mobi_tempdir", None)
        if tempdir:
            shutil.rmtree(tempdir, ignore_errors=True)
            self._mobi_tempdir = None
        super().closeEvent(event)
        self.closed = True  # the manager stops counting it at once; Qt deletes the widget a little later
        reader_events.changed.emit()

    # ── Shared navigation plumbing (PDF pages / EPUB chapters) ──────────

    def _attach_floating_nav(self, view: QWidget, on_previous, on_next) -> None:
        """Overlays the prev/next buttons on a scrollable reading view and wires them to appear whenever that view is
        scrolled."""
        self.floating_nav = _FloatingNavButtons(view, on_previous, on_next)
        self._nav_previous = on_previous
        self._nav_next = on_next
        scrollbar = view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.valueChanged.connect(lambda _value: self.floating_nav.reveal())
        # Keeps the overlay centred/bottom-anchored as the window resizes; an event filter rather than subclassing the
        # view, since both QPdfView and QTextBrowser get the same treatment.
        view.installEventFilter(self)
        self.top_bar.previous_requested.connect(on_previous)
        self.top_bar.next_requested.connect(on_next)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 -- Qt override
        if event.type() == QEvent.Resize:
            nav = getattr(self, "floating_nav", None)
            if nav is not None and nav.parentWidget() is watched:
                nav.reposition()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        """Left/Right (and Space/Backspace) page through the document -- reaching for the arrow keys is the more natural
        reflex while reading, and Space is what every other reader in the world uses."""
        previous = getattr(self, "_nav_previous", None)
        next_ = getattr(self, "_nav_next", None)
        if previous is not None and next_ is not None:
            if event.key() in (Qt.Key_Left, Qt.Key_Backspace):
                previous()
                self._reveal_floating_nav()
                return
            if event.key() in (Qt.Key_Right, Qt.Key_Space):
                next_()
                self._reveal_floating_nav()
                return
        super().keyPressEvent(event)

    def _reveal_floating_nav(self) -> None:
        nav = getattr(self, "floating_nav", None)
        if nav is not None:
            nav.reveal()

    def _page_previous(self) -> None:
        if getattr(self, "_nav_previous", None):
            self._nav_previous()

    def _page_next(self) -> None:
        if getattr(self, "_nav_next", None):
            self._nav_next()

    def focus_page_box(self) -> None:
        """Ctrl+G: put the cursor in the page box, ready to type a number."""
        if self.top_bar.page_spin.isVisible():
            self.top_bar.page_spin.setFocus()
            self.top_bar.page_spin.selectAll()

    # ── Fallback for formats without an embedded viewer ─────────────────

    def _build_fallback(self, file_path: str) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignCenter)
        message = QLabel(
            "Ứng dụng chưa hỗ trợ xem trước định dạng này ngay trong cửa sổ đọc.\n"
            "Nhấn nút bên dưới để mở file bằng ứng dụng mặc định của hệ điều hành."
        )
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        open_button = QPushButton("Mở bằng ứng dụng khác")
        open_button.clicked.connect(lambda: self.file_actions.open_file(file_path))
        layout.addWidget(message)
        layout.addWidget(open_button, alignment=Qt.AlignCenter)
        self.setCentralWidget(container)

    # ── MOBI / AZW3 (Kindle formats) ───────────────────────────────────

    def _build_mobi_reader(self, file_path: str) -> None:
        """Kindle formats have no zip/OPF container to read chapters out of, and Qt has no renderer for them. Unpack the
        book into a temporary EPUB (or HTML, for older MOBI 6 files) and hand that to the readers that already exist.
        The temp directory is cleaned up when the window closes."""
        try:
            import mobi
        except ImportError:
            logger.warning("The 'mobi' package isn't installed -- cannot read Kindle formats.")
            self._build_fallback(file_path)
            return

        try:
            tempdir, extracted_path = mobi.extract(file_path)
        except Exception:
            # Unpacking covers a lot of ground (DRM, truncated files, old PalmDOC variants); any failure just means
            # falling back to the OS's own reader rather than taking the window down.
            logger.exception("Failed to unpack Kindle file: %s", file_path)
            self._build_fallback(file_path)
            return

        self._mobi_tempdir = tempdir
        suffix = Path(extracted_path).suffix.lower()
        if suffix == ".epub":
            self._build_epub_reader(extracted_path)
        elif suffix == ".pdf":
            self._build_pdf_reader(extracted_path)
        else:
            self._build_html_reader(extracted_path)

    def _paper_style(self) -> str:
        tm = theme_manager()
        # A page of warm paper on the (grey) reading ground; the dark themes get a warm dark page.
        return f"QTextBrowser {{ background: {tm.token('surface')}; color: {tm.token('ink')}; border: none; padding: 18px 40px; }}"

    def _build_html_reader(self, html_path: str) -> None:
        """Renders a single self-contained HTML file (what MOBI 6 unpacks to) -- no chapter navigation, since there are no
        spine entries to page through, just the whole book in one scrollable view."""
        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(False)
        browser.setOpenLinks(False)
        browser.setStyleSheet(self._paper_style())
        browser.document().setDefaultStyleSheet(f"body {{ color: {theme_manager().token('ink')}; }}")
        try:
            browser.setHtml(Path(html_path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            logger.exception("Failed to read unpacked HTML: %s", html_path)
            self._build_fallback(html_path)
            return

        self.epub_view = browser  # same attribute the zoom/scroll plumbing below expects
        self._install_view(browser)
        self.top_bar.show_zoom(True, percent_and_fit=False)
        self.top_bar.zoom_out_requested.connect(lambda: browser.zoomOut(1))
        self.top_bar.zoom_in_requested.connect(lambda: browser.zoomIn(1))
        self.top_bar.toc_button.hide()  # one long page: nothing to list

    # ── PDF reader ────────────────────────────────────────────────────

    def _build_pdf_reader(self, file_path: str) -> None:
        self._pdf_document = QPdfDocument(self)
        self._pdf_document.load(file_path)
        if self._pdf_document.status() == QPdfDocument.Status.Error:
            self._build_fallback(file_path)
            return

        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self._pdf_document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        # Tints the margin around the pages with the reading ground (QPdfView has no backgroundColor property, but does
        # respect a palette role). The rendered page itself stays whatever colour the source PDF page is.
        pdf_palette = self.pdf_view.palette()
        pdf_palette.setColor(QPalette.Dark, QColor(theme_manager().token("surface2")))
        self.pdf_view.setPalette(pdf_palette)
        self.pdf_view.setBackgroundRole(QPalette.Dark)
        self.pdf_view.setAutoFillBackground(True)

        self._install_view(self.pdf_view)
        self._build_pdf_controls()
        self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_current_page_changed)
        self._attach_floating_nav(self.pdf_view, self._go_previous_page, self._go_next_page)
        bookmarks = QPdfBookmarkModel(self)
        bookmarks.setDocument(self._pdf_document)
        self._pdf_bookmarks = bookmarks
        if bookmarks.rowCount() > 0:
            self._show_toc(bookmarks)
            self.toc_view.clicked.connect(self._on_toc_clicked)
        else:
            self.top_bar.toc_button.hide()  # a PDF without bookmarks has no contents to show

    def _build_pdf_controls(self) -> None:
        bar = self.top_bar
        bar.show_navigation(True)
        bar.show_zoom(True)
        page_count = max(1, self._pdf_document.pageCount())
        bar.set_total(page_count, "Trang")
        self.page_spin = bar.page_spin
        bar.page_chosen.connect(self._go_to_page)
        bar.zoom_out_requested.connect(lambda: self._adjust_zoom(-_ZOOM_STEP))
        bar.zoom_in_requested.connect(lambda: self._adjust_zoom(_ZOOM_STEP))
        bar.zoom_percent_chosen.connect(lambda percent: self._set_zoom(percent / 100))
        bar.fit_width_requested.connect(lambda: self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth))
        bar.fit_page_requested.connect(lambda: self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView))

    def _on_toc_clicked(self, index: QModelIndex) -> None:
        page = index.data(int(QPdfBookmarkModel.Role.Page))
        if isinstance(page, int) and page >= 0:
            self.pdf_view.pageNavigator().jump(page, QPointF(0, 0))

    def _go_previous_page(self) -> None:
        nav = self.pdf_view.pageNavigator()
        if nav.currentPage() > 0:
            nav.jump(nav.currentPage() - 1, QPointF(0, 0))

    def _go_next_page(self) -> None:
        nav = self.pdf_view.pageNavigator()
        if nav.currentPage() < self._pdf_document.pageCount() - 1:
            nav.jump(nav.currentPage() + 1, QPointF(0, 0))

    def _go_to_page(self, page_number_1based: int) -> None:
        nav = self.pdf_view.pageNavigator()
        target = page_number_1based - 1
        if target != nav.currentPage():
            nav.jump(target, QPointF(0, 0))

    def _on_current_page_changed(self, page: int) -> None:
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page + 1)
        self.page_spin.blockSignals(False)
        self._remember_position(page + 1)

    def _adjust_zoom(self, delta: float) -> None:
        self._set_zoom(self.pdf_view.zoomFactor() + delta)

    def _set_zoom(self, factor: float) -> None:
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        factor = max(_ZOOM_MIN, min(_ZOOM_MAX, factor))
        self.pdf_view.setZoomFactor(factor)
        self.top_bar.fit_page_button.setChecked(False)
        self.top_bar.fit_width_button.setChecked(False)
        nearest = min(_ZOOM_CHOICES, key=lambda choice: abs(choice - factor * 100))
        self.top_bar.zoom_combo.setCurrentIndex(_ZOOM_CHOICES.index(nearest))

    # ── EPUB reader ───────────────────────────────────────────────────

    def _build_epub_reader(self, file_path: str) -> None:
        try:
            self._epub_doc = EpubDocument(file_path)
        except EpubReadError:
            self._build_fallback(file_path)
            return

        self.epub_view = _EpubTextBrowser(self._epub_doc, self)
        self.epub_view.setOpenExternalLinks(False)
        self.epub_view.setOpenLinks(False)
        # Warm paper instead of a glaring white page -- applied as both the widget's own background/text and a default
        # stylesheet on its document (the actual chapter HTML), since a chapter's own markup could otherwise still render
        # with no explicit colour and fall back to black-on-white.
        self.epub_view.setStyleSheet(self._paper_style())
        self.epub_view.document().setDefaultStyleSheet(f"body {{ color: {theme_manager().token('ink')}; }}")

        self._install_view(self.epub_view)
        self._build_epub_controls()
        self._current_chapter = -1  # forces the first _go_to_chapter(0) to actually load
        self._go_to_chapter(0)
        self._attach_floating_nav(
            self.epub_view,
            lambda: self._go_to_chapter(self._current_chapter - 1),
            lambda: self._go_to_chapter(self._current_chapter + 1),
        )
        self._fill_epub_contents()

    def _build_epub_controls(self) -> None:
        bar = self.top_bar
        bar.show_navigation(True)
        bar.show_zoom(True, percent_and_fit=False)
        chapter_count = max(1, self._epub_doc.chapter_count)
        bar.set_total(chapter_count, "Chương")
        self.chapter_spin = bar.page_spin
        bar.page_chosen.connect(lambda n: self._go_to_chapter(n - 1))
        bar.zoom_out_requested.connect(lambda: self.epub_view.zoomOut(1))
        bar.zoom_in_requested.connect(lambda: self.epub_view.zoomIn(1))

    def _fill_epub_contents(self) -> None:
        model = QStandardItemModel(self)
        for index in range(self._epub_doc.chapter_count):
            item = QStandardItem(f"Chương {index + 1}")
            item.setData(index, Qt.UserRole)
            item.setEditable(False)
            model.appendRow(item)
        self._epub_contents = model
        self._show_toc(model)
        self.toc_view.clicked.connect(lambda idx: self._go_to_chapter(idx.data(Qt.UserRole)))

    def _go_to_chapter(self, index: int) -> None:
        index = max(0, min(index, self._epub_doc.chapter_count - 1))
        if index == self._current_chapter:
            return
        self._current_chapter = index
        self.epub_view.current_chapter_index = index
        self.epub_view.setHtml(self._epub_doc.chapter_html(index))
        self.chapter_spin.blockSignals(True)
        self.chapter_spin.setValue(index + 1)
        self.chapter_spin.blockSignals(False)
        model = self.toc_view.model()
        if model is not None and 0 <= index < model.rowCount():
            self.toc_view.setCurrentIndex(model.index(index, 0))
        self._remember_position(index + 1)

    # ── Full screen ───────────────────────────────────────────────────

    def _toggle_fullscreen(self, checked: bool) -> None:
        self.showFullScreen() if checked else self.showNormal()
        if self.top_bar.fullscreen_button.isChecked() != checked:
            self.top_bar.fullscreen_button.setChecked(checked)

    def _toggle_fullscreen_shortcut(self) -> None:
        self._toggle_fullscreen(not self.isFullScreen())

    def _leave_fullscreen(self) -> None:
        if self.isFullScreen():
            self._toggle_fullscreen(False)


if __name__ == "__main__":
    import sys
    import tempfile

    import pymupdf as fitz
    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "demo.pdf"
        pdf = fitz.open()
        for i in range(3):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Demo page {i + 1}")
        pdf.save(str(pdf_path))
        pdf.close()

        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Demo PDF", "author": "Someone", "file_path": str(pdf_path), "extension": "pdf", "created_at": 0.0}
        )
        doc = context.db.get_document("d1")

        app = QApplication(sys.argv)
        theme_manager().apply(app, "broadsheet")
        window = ReaderWindow(context, doc)
        window.show()
        sys.exit(app.exec())
