"""In-app Document Reader window.

A single independent top-level window (not a modal dialog), so the user can
keep reading while the main library window stays usable. PDF is rendered
with Qt's own QtPdf module; EPUB with QTextBrowser reading chapters (in
spine order) out of the zip via infrastructure/epub_reader.py -- Qt has no
first-party EPUB widget, but QTextBrowser's HTML subset is enough for
typical chapter markup (headings, paragraphs, bold/italic, inline images).
AZW3/MOBI aren't real zip/OPF containers, so they (and any EPUB that fails
to parse) fall back to a plain "open with the OS's own app" message rather
than a half-working embedded renderer.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QKeySequence, QPalette, QPixmap, QTextDocument
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from smartdoc.infrastructure.epub_reader import EpubDocument, EpubReadError
from smartdoc.presentation.file_actions import FileActionEngine

logger = logging.getLogger(__name__)

_ZOOM_STEP = 0.15
_ZOOM_MIN = 0.25
_ZOOM_MAX = 4.0

# Kindle formats. Not zip/OPF containers like EPUB, so they can't be read
# directly -- they're unpacked to a temporary EPUB/HTML first (see
# _build_mobi_reader) and then rendered by the regular readers below.
_MOBI_LIKE_EXTENSIONS = {"mobi", "azw3", "azw", "prc"}

# One fixed reading look, independent of whichever of the 3 library themes
# is active (see the design spec's "3 màn hình cần thêm" section, listed
# separately from the per-theme color requirements) -- dark chrome around
# the reading area, warm paper instead of glaring white for the page/text
# itself.
_CHROME_BG = "#28211b"
_CHROME_TEXT = "#cfc3ac"
_PAPER_BG = "#e7dfd0"
_PAPER_TEXT = "#2c2416"

# How long the floating prev/next buttons stay visible after the last
# scroll before fading back out of the way.
_FLOATING_NAV_HIDE_MS = 2200
_FLOATING_NAV_MARGIN = 18


class _FloatingNavButtons(QWidget):
    """Prev/next buttons floating over the reading area itself, revealed
    by scrolling and auto-hidden again once scrolling stops.

    The toolbar at the top already has the same two actions, but once
    you've scrolled a few pages down that toolbar is the furthest thing
    from where your eyes and cursor actually are -- these sit right where
    you're already reading, then get out of the way again so they never
    permanently cover part of a page.
    """

    def __init__(self, parent: QWidget, on_previous, on_next) -> None:
        super().__init__(parent)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(_FLOATING_NAV_HIDE_MS)
        self._hide_timer.timeout.connect(self.hide)

        self.previous_button = QPushButton("◀", self)
        self.previous_button.setToolTip("Trang trước (PageUp hoặc ←)")
        self.next_button = QPushButton("▶", self)
        self.next_button.setToolTip("Trang sau (PageDown hoặc →)")
        for button in (self.previous_button, self.next_button):
            button.setFixedSize(44, 44)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: rgba(40,33,27,0.82); color: {_CHROME_TEXT};"
                " border: none; border-radius: 22px; font-size: 17px; }"
                " QPushButton:hover { background: rgba(40,33,27,0.96); }"
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
    """Resolves <img> tags referenced (relatively) from whichever chapter
    is currently displayed, by pulling the image bytes straight out of the
    EPUB zip -- QTextBrowser has no idea these paths live inside an
    archive, so the default resource loader can't find them on its own."""

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


class ReaderWindow(QMainWindow):
    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        # QMainWindow embeds as a child widget when given a parent (unlike
        # QDialog, which is always top-level) -- force it to stay an
        # independent top-level window so a parent widget (e.g. the detail
        # panel) can still own it for lifetime management without visually
        # nesting it.
        self.setWindowFlag(Qt.Window, True)
        # Closing a QMainWindow only hides it by default, which would leave
        # the whole rendered document (a PDF's page cache, or an entire
        # unpacked Kindle book in a temp dir) resident for the rest of the
        # session -- and, since the window never actually dies, it would
        # keep occupying one of the slots reader_manager hands out.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.context = context
        self.doc = doc
        self.file_actions = FileActionEngine(context)
        self.setWindowTitle(doc.get("title") or "Đọc tài liệu")
        self.resize(900, 1000)
        # Evenly-sized, comfortably-padded toolbar controls: the default Qt
        # tool button hugs its label, so a row of mixed-length Vietnamese
        # labels ("Vừa trang" vs "Toàn màn hình") came out visually ragged
        # and fiddly to hit. A min-width plus real padding makes them read
        # as one balanced strip and gives each a proper click target.
        self.setStyleSheet(
            f"QMainWindow {{ background: {_CHROME_BG}; }}"
            f" QToolBar {{ background: {_CHROME_BG}; color: {_CHROME_TEXT}; border: none;"
            "   spacing: 4px; padding: 6px 10px; }"
            f" QToolBar QLabel {{ color: {_CHROME_TEXT}; padding: 0 2px; }}"
            f" QToolBar QSpinBox {{ background: {_PAPER_BG}; color: {_PAPER_TEXT};"
            "   border: none; border-radius: 4px; padding: 4px 6px; min-width: 52px; }"
            f" QToolButton {{ color: {_CHROME_TEXT}; padding: 6px 12px; border-radius: 6px;"
            "   min-width: 86px; }"
            " QToolButton:hover { background: rgba(255,255,255,0.10); }"
            " QToolButton:pressed { background: rgba(255,255,255,0.18); }"
            f" QToolButton:checked {{ background: rgba(255,255,255,0.16); color: {_PAPER_BG}; }}"
            f" QToolBar::separator {{ background: rgba(255,255,255,0.18); width: 1px; margin: 4px 8px; }}"
        )

        extension = (doc.get("extension") or "").lower()
        file_path = doc.get("file_path", "")

        if extension == "pdf" and Path(file_path).exists():
            self._build_pdf_reader(file_path)
        elif extension == "epub" and Path(file_path).exists():
            self._build_epub_reader(file_path)
        elif extension in _MOBI_LIKE_EXTENSIONS and Path(file_path).exists():
            self._build_mobi_reader(file_path)
        else:
            self._build_fallback(file_path)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        epub_doc = getattr(self, "_epub_doc", None)
        if epub_doc is not None:
            epub_doc.close()
        # Kindle books are unpacked into a temp directory to be readable at
        # all (see _build_mobi_reader) -- without this, every MOBI opened
        # would leave a full copy of itself behind in %TEMP%.
        tempdir = getattr(self, "_mobi_tempdir", None)
        if tempdir:
            shutil.rmtree(tempdir, ignore_errors=True)
            self._mobi_tempdir = None
        super().closeEvent(event)

    # ── Shared navigation plumbing (PDF pages / EPUB chapters) ──────────

    def _attach_floating_nav(self, view: QWidget, on_previous, on_next) -> None:
        """Overlays the prev/next buttons on a scrollable reading view and
        wires them to appear whenever that view is scrolled."""
        self.floating_nav = _FloatingNavButtons(view, on_previous, on_next)
        self._nav_previous = on_previous
        self._nav_next = on_next
        scrollbar = view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.valueChanged.connect(lambda _value: self.floating_nav.reveal())
        # Keeps the overlay centred/bottom-anchored as the window resizes;
        # an event filter rather than subclassing the view, since both
        # QPdfView and QTextBrowser get the same treatment.
        view.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 -- Qt override
        if event.type() == QEvent.Resize:
            nav = getattr(self, "floating_nav", None)
            if nav is not None and nav.parentWidget() is watched:
                nav.reposition()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        """Left/Right (and Space/Backspace) page through the document --
        PageUp/PageDown are already bound as toolbar action shortcuts, but
        reaching for the arrow keys is the more natural reflex while
        reading, and Space is what every other reader in the world uses."""
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
        """Kindle formats have no zip/OPF container to read chapters out
        of, and Qt has no renderer for them, so they used to land on the
        "open it in another app" fallback -- even though they're listed as
        a supported format the library happily imports.

        Instead, unpack the book into a temporary EPUB (or HTML, for older
        MOBI 6 files) and hand that to the readers that already exist. The
        temp directory is cleaned up when the window closes.
        """
        try:
            import mobi
        except ImportError:
            logger.warning("The 'mobi' package isn't installed -- cannot read Kindle formats.")
            self._build_fallback(file_path)
            return

        try:
            tempdir, extracted_path = mobi.extract(file_path)
        except Exception:
            # Unpacking covers a lot of ground (DRM, truncated files, old
            # PalmDOC variants); any failure just means falling back to
            # the OS's own reader rather than taking the window down.
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

    def _build_html_reader(self, html_path: str) -> None:
        """Renders a single self-contained HTML file (what MOBI 6 unpacks
        to) -- no chapter navigation, since there are no spine entries to
        page through, just the whole book in one scrollable view."""
        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(False)
        browser.setOpenLinks(False)
        browser.setStyleSheet(f"QTextBrowser {{ background: {_PAPER_BG}; color: {_PAPER_TEXT}; border: none; }}")
        browser.document().setDefaultStyleSheet(f"body {{ color: {_PAPER_TEXT}; }}")
        try:
            browser.setHtml(Path(html_path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            logger.exception("Failed to read unpacked HTML: %s", html_path)
            self._build_fallback(html_path)
            return

        self.epub_view = browser  # same attribute the zoom/scroll plumbing below expects
        self.setCentralWidget(browser)

        toolbar = QToolBar("Công cụ đọc", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        zoom_out_action = QAction("Thu nhỏ chữ (−)", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: browser.zoomOut(1))
        toolbar.addAction(zoom_out_action)
        zoom_in_action = QAction("Phóng to chữ (+)", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(lambda: browser.zoomIn(1))
        toolbar.addAction(zoom_in_action)
        toolbar.addSeparator()
        fullscreen_action = QAction("Toàn màn hình", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.toggled.connect(self._toggle_fullscreen)
        toolbar.addAction(fullscreen_action)

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
        # Tints the margin/letterbox area around pages to match the reader's
        # dark chrome -- QPdfView has no simple backgroundColor property,
        # but does respect a palette role like any other QWidget. The
        # rendered page content itself stays whatever color the source PDF
        # page actually is (typically white) -- that can't be recolored
        # without image post-processing, which is out of scope here.
        pdf_palette = self.pdf_view.palette()
        pdf_palette.setColor(QPalette.Dark, QColor(_CHROME_BG))
        self.pdf_view.setPalette(pdf_palette)
        self.pdf_view.setBackgroundRole(QPalette.Dark)
        self.pdf_view.setAutoFillBackground(True)

        self.setCentralWidget(self.pdf_view)
        self._build_pdf_toolbar()
        self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_current_page_changed)
        self._attach_floating_nav(self.pdf_view, self._go_previous_page, self._go_next_page)

    def _build_pdf_toolbar(self) -> None:
        toolbar = QToolBar("Công cụ đọc", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        prev_action = QAction("◀ Trang trước", self)
        prev_action.setShortcut(QKeySequence.MoveToPreviousPage if hasattr(QKeySequence, "MoveToPreviousPage") else "PgUp")
        prev_action.setToolTip("Trang trước (PageUp, ← hoặc Backspace)")
        prev_action.triggered.connect(self._go_previous_page)
        toolbar.addAction(prev_action)

        page_count = max(1, self._pdf_document.pageCount())
        self.page_spin = QSpinBox(self)
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(page_count)
        self.page_spin.valueChanged.connect(self._go_to_page)
        toolbar.addWidget(self.page_spin)
        toolbar.addWidget(QLabel(f" / {page_count}  ", self))

        next_action = QAction("Trang sau ▶", self)
        next_action.setShortcut("PgDown")
        next_action.setToolTip("Trang sau (PageDown, → hoặc Space)")
        next_action.triggered.connect(self._go_next_page)
        toolbar.addAction(next_action)

        toolbar.addSeparator()

        zoom_out_action = QAction("Thu nhỏ (−)", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: self._adjust_zoom(-_ZOOM_STEP))
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("Phóng to (+)", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(lambda: self._adjust_zoom(_ZOOM_STEP))
        toolbar.addAction(zoom_in_action)

        fit_width_action = QAction("Vừa chiều rộng", self)
        fit_width_action.triggered.connect(lambda: self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth))
        toolbar.addAction(fit_width_action)

        fit_page_action = QAction("Vừa trang", self)
        fit_page_action.triggered.connect(lambda: self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView))
        toolbar.addAction(fit_page_action)

        toolbar.addSeparator()

        fullscreen_action = QAction("Toàn màn hình", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.toggled.connect(self._toggle_fullscreen)
        toolbar.addAction(fullscreen_action)

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

    def _adjust_zoom(self, delta: float) -> None:
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        new_zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, self.pdf_view.zoomFactor() + delta))
        self.pdf_view.setZoomFactor(new_zoom)

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
        # Warm paper instead of a glaring white page -- applied as both the
        # widget's own background/text (frame/scrollbar area) and a default
        # stylesheet on its document (the actual chapter HTML), since a
        # chapter's own markup could otherwise still render with no
        # explicit color and fall back to black-on-white.
        self.epub_view.setStyleSheet(f"QTextBrowser {{ background: {_PAPER_BG}; color: {_PAPER_TEXT}; border: none; }}")
        self.epub_view.document().setDefaultStyleSheet(f"body {{ color: {_PAPER_TEXT}; }}")

        self.setCentralWidget(self.epub_view)
        self._build_epub_toolbar()
        self._current_chapter = -1  # forces the first _go_to_chapter(0) to actually load
        self._go_to_chapter(0)
        self._attach_floating_nav(
            self.epub_view,
            lambda: self._go_to_chapter(self._current_chapter - 1),
            lambda: self._go_to_chapter(self._current_chapter + 1),
        )

    def _build_epub_toolbar(self) -> None:
        toolbar = QToolBar("Công cụ đọc", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        prev_action = QAction("◀ Chương trước", self)
        prev_action.setShortcut("PgUp")
        prev_action.setToolTip("Chương trước (PageUp, ← hoặc Backspace)")
        prev_action.triggered.connect(lambda: self._go_to_chapter(self._current_chapter - 1))
        toolbar.addAction(prev_action)

        chapter_count = max(1, self._epub_doc.chapter_count)
        self.chapter_spin = QSpinBox(self)
        self.chapter_spin.setMinimum(1)
        self.chapter_spin.setMaximum(chapter_count)
        self.chapter_spin.valueChanged.connect(lambda n: self._go_to_chapter(n - 1))
        toolbar.addWidget(self.chapter_spin)
        toolbar.addWidget(QLabel(f" / {chapter_count}  ", self))

        next_action = QAction("Chương sau ▶", self)
        next_action.setShortcut("PgDown")
        next_action.setToolTip("Chương sau (PageDown, → hoặc Space)")
        next_action.triggered.connect(lambda: self._go_to_chapter(self._current_chapter + 1))
        toolbar.addAction(next_action)

        toolbar.addSeparator()

        zoom_out_action = QAction("Thu nhỏ chữ (−)", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: self.epub_view.zoomOut(1))
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("Phóng to chữ (+)", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(lambda: self.epub_view.zoomIn(1))
        toolbar.addAction(zoom_in_action)

        toolbar.addSeparator()

        fullscreen_action = QAction("Toàn màn hình", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.toggled.connect(self._toggle_fullscreen)
        toolbar.addAction(fullscreen_action)

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

    def _toggle_fullscreen(self, checked: bool) -> None:
        self.showFullScreen() if checked else self.showNormal()


if __name__ == "__main__":
    import sys
    import tempfile

    import fitz
    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

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
        apply_light_theme(app)
        window = ReaderWindow(context, doc)
        window.show()
        sys.exit(app.exec())
