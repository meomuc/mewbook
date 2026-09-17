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

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QTextDocument
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QLabel, QMainWindow, QPushButton, QSpinBox, QTextBrowser, QToolBar, QVBoxLayout, QWidget

from smartdoc.infrastructure.epub_reader import EpubDocument, EpubReadError
from smartdoc.presentation.file_actions import FileActionEngine

_ZOOM_STEP = 0.15
_ZOOM_MIN = 0.25
_ZOOM_MAX = 4.0


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
        self.context = context
        self.doc = doc
        self.file_actions = FileActionEngine(context)
        self.setWindowTitle(doc.get("title") or "Đọc tài liệu")
        self.resize(900, 1000)

        extension = (doc.get("extension") or "").lower()
        file_path = doc.get("file_path", "")

        if extension == "pdf" and Path(file_path).exists():
            self._build_pdf_reader(file_path)
        elif extension == "epub" and Path(file_path).exists():
            self._build_epub_reader(file_path)
        else:
            self._build_fallback(file_path)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        epub_doc = getattr(self, "_epub_doc", None)
        if epub_doc is not None:
            epub_doc.close()
        super().closeEvent(event)

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

        self.setCentralWidget(self.pdf_view)
        self._build_pdf_toolbar()
        self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_current_page_changed)

    def _build_pdf_toolbar(self) -> None:
        toolbar = QToolBar("Công cụ đọc", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        prev_action = QAction("◀ Trang trước", self)
        prev_action.setShortcut(QKeySequence.MoveToPreviousPage if hasattr(QKeySequence, "MoveToPreviousPage") else "PgUp")
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

        self.setCentralWidget(self.epub_view)
        self._build_epub_toolbar()
        self._current_chapter = -1  # forces the first _go_to_chapter(0) to actually load
        self._go_to_chapter(0)

    def _build_epub_toolbar(self) -> None:
        toolbar = QToolBar("Công cụ đọc", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        prev_action = QAction("◀ Chương trước", self)
        prev_action.setShortcut("PgUp")
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
