# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dialog: Lưu trang web thành PDF — Task 3 (Tuần 3).

Flow: user pastes a URL → clicks "Lấy nội dung" → preview title + char count
→ shows copyright notice → clicks "Lưu PDF" → file is written and handed to
import_manager.add_files([dest]).  The dialog stays open so the user can save
multiple pages in one session.

Background fetch runs in a QThread so the UI stays responsive.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from smartdoc.application.webpage_to_pdf import (
    FetchedPage,
    WebpageToPdfError,
    default_save_folder,
    fetch_page,
    render_to_pdf,
    unique_pdf_path,
)
from smartdoc.presentation.theme import current_colors

logger = logging.getLogger(__name__)

_COPYRIGHT_NOTICE = (
    "Lưu ý bản quyền: bản sao này chỉ dành cho đọc cá nhân — "
    "vui lòng tôn trọng bản quyền trang gốc."
)


class _FetchWorker(QThread):
    """Runs fetch_page() off the GUI thread."""

    finished: Signal = Signal(object)   # FetchedPage
    failed: Signal = Signal(str)        # error message

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            page = fetch_page(self._url)
            self.finished.emit(page)
        except WebpageToPdfError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 -- isolate network worker
            logger.exception("Unexpected fetch error: %s", exc)
            self.failed.emit(f"Lỗi không mong đợi: {exc}")


class _RenderWorker(QThread):
    """Runs render_to_pdf() off the GUI thread."""

    finished: Signal = Signal(str)   # dest path
    failed: Signal = Signal(str)     # error message

    def __init__(self, page: FetchedPage, dest: str, parent=None) -> None:
        super().__init__(parent)
        self._page = page
        self._dest = dest

    def run(self) -> None:
        try:
            render_to_pdf(self._page, self._dest)
            self.finished.emit(self._dest)
        except WebpageToPdfError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 -- isolate render worker
            logger.exception("Unexpected render error: %s", exc)
            self.failed.emit(f"Lỗi không mong đợi: {exc}")


class WebpageToPdfDialog(QDialog):
    """Paste a URL, fetch its content, save to PDF, import into library."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.import_manager = context.import_queue
        self._fetched: FetchedPage | None = None
        self._fetch_worker: _FetchWorker | None = None
        self._render_worker: _RenderWorker | None = None

        self.setWindowTitle("Lưu trang web thành PDF")
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self) -> None:
        colors = current_colors()
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # URL row
        url_row = QHBoxLayout()
        url_label = QLabel("Địa chỉ trang:", self)
        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText("Dán URL vào đây (https://...)")
        self.url_edit.returnPressed.connect(self._on_fetch)
        self.fetch_button = QPushButton("Lấy nội dung", self)
        self.fetch_button.clicked.connect(self._on_fetch)
        url_row.addWidget(url_label)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.fetch_button)
        layout.addLayout(url_row)

        # Progress / status
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Preview area
        self.preview_label = QLabel(self)
        self.preview_label.setWordWrap(True)
        self.preview_label.setVisible(False)
        layout.addWidget(self.preview_label)

        # Copyright notice (always visible)
        muted = getattr(colors, "muted_text", "#888")
        notice = QLabel(_COPYRIGHT_NOTICE, self)
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {muted}; font-style: italic; font-size: 11px;")
        layout.addWidget(notice)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self.save_button = QPushButton("Lưu PDF vào thư viện", self)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save)
        close_button = QPushButton("Đóng", self)
        close_button.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(self.save_button)
        btn_row.addWidget(close_button)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ fetch

    def _on_fetch(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_edit.setText(url)

        self._fetched = None
        self.save_button.setEnabled(False)
        self.preview_label.setVisible(False)
        self.progress.setVisible(True)
        self.fetch_button.setEnabled(False)

        self._fetch_worker = _FetchWorker(url, self)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.failed.connect(self._on_fetch_error)
        self._fetch_worker.finished.connect(self._fetch_worker.deleteLater)
        self._fetch_worker.failed.connect(self._fetch_worker.deleteLater)
        self._fetch_worker.start()

    def _on_fetch_done(self, page: FetchedPage) -> None:
        self.progress.setVisible(False)
        self.fetch_button.setEnabled(True)
        self._fetched = page
        kchars = page.char_count // 1000
        self.preview_label.setText(
            f"<b>{page.title}</b><br/>"
            f"<span style='font-size:11px;color:#888;'>~{kchars}k ký tự · {page.source_url[:80]}</span>"
        )
        self.preview_label.setVisible(True)
        self.save_button.setEnabled(True)

    def _on_fetch_error(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.fetch_button.setEnabled(True)
        QMessageBox.warning(self, "Không tải được trang", msg)

    # ------------------------------------------------------------------ save

    def _on_save(self) -> None:
        if self._fetched is None:
            return

        cfg = self.context.config
        app_data_dir = Path(cfg.app_data_dir) if hasattr(cfg, "app_data_dir") else Path.home() / "SmartDocLibrary"
        folder = default_save_folder(app_data_dir)
        dest = str(unique_pdf_path(folder, self._fetched.title))

        self.save_button.setEnabled(False)
        self.progress.setVisible(True)

        self._render_worker = _RenderWorker(self._fetched, dest, self)
        self._render_worker.finished.connect(self._on_save_done)
        self._render_worker.failed.connect(self._on_save_error)
        self._render_worker.finished.connect(self._render_worker.deleteLater)
        self._render_worker.failed.connect(self._render_worker.deleteLater)
        self._render_worker.start()

    def _on_save_done(self, dest: str) -> None:
        self.progress.setVisible(False)
        self.save_button.setEnabled(True)
        self.import_manager.add_files([dest])
        QMessageBox.information(
            self,
            "Đã lưu",
            f"PDF đã được lưu và thêm vào thư viện:\n{dest}",
        )
        # Clear for the next URL
        self.url_edit.clear()
        self.preview_label.setVisible(False)
        self._fetched = None
        self.save_button.setEnabled(False)

    def _on_save_error(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.save_button.setEnabled(True)
        QMessageBox.critical(self, "Lỗi khi tạo PDF", msg)
