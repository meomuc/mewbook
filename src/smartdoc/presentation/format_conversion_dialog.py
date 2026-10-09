# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C2 (Tuần 3, bản thử): "Chuyển đổi định dạng" -- chọn định dạng đích cho các sách đã chọn, xem trước kế
hoạch (sẽ chuyển / chưa hỗ trợ / có DRM bị từ chối) trước khi làm gì, rồi chạy nền qua Calibre's `ebook-convert`
(application/format_conversion.py), không chặn giao diện. Một cặp định dạng có rủi ro lệch bố cục (PDF làm nguồn)
hiện cảnh báo "định dạng gốc có thể không được giữ nguyên" ngay khi được chọn, không đợi đến lúc chạy xong mới biết.

Calibre không đi kèm MewBook -- khi chưa cài, hộp thoại chỉ hiện hướng dẫn cài bằng lời thường, không cho chạy gì.
Kết quả vào một thư mục riêng do người dùng chọn; file gốc không bao giờ bị sửa hay ghi đè (xem module docstring
của format_conversion.py để biết cách đảm bảo điều đó).
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton

from smartdoc.application.format_conversion import (
    INSTALL_HINT,
    ConversionJob,
    ConversionResult,
    FormatConversionService,
    NativeConverter,
    deferred_reason,
    is_pair_supported,
    is_risky_pair,
)
from smartdoc.core.event_bus import BackgroundTaskEvent
from smartdoc.core.perf_log import log_perf
from smartdoc.infrastructure.drm_detect import is_drm_protected
from smartdoc.presentation.busy_indicator import BusyIndicator
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.hint_label import HintLabel
from smartdoc.presentation.theme import ROLE_RESULT, role_css
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)

_WILL_CONVERT = "will_convert"
_UNSUPPORTED = "unsupported"
_DRM = "drm"

#: Target formats offered in the picker -- native pairs first (no Calibre needed), then Calibre-required.
_TARGET_FORMATS = ("epub", "mobi", "azw3", "pdf", "txt")


class FormatConversionDialog(DesignDialog):
    _progress = Signal(int, int)  # done, total -- individual items are only known once the batch finishes
    _finished = Signal(object)  # ConversionResult

    def __init__(self, context, docs: list[dict], parent=None, *, service: FormatConversionService | None = None) -> None:
        super().__init__(parent, title="Chuyển đổi định dạng", subtitle=f"{len(docs)} sách đã chọn -- bản thử",
                         icon="refresh", width=640)
        self.context = context
        self.docs = docs
        self.service = service or FormatConversionService(context)
        self._plan: dict[str, str] = {}  # doc id -> status
        self._results: dict[str, str] = {}  # doc id -> "" (ok) | error
        self._running = False
        self._cancel = threading.Event()
        self._relay = WorkerRelay(self)
        self._calibre_available = self.service.is_calibre_available()
        tm = theme_manager()

        if not self._calibre_available:
            self.body.addWidget(HintLabel(
                INSTALL_HINT + " Các định dạng hỗ trợ sẵn (EPUB↔PDF, EPUB↔TXT, PDF→TXT, TXT→EPUB) vẫn dùng được "
                "mà không cần Calibre.", self, color_token="warn"))
        else:
            self.body.addWidget(HintLabel(
                "File gốc không bị sửa hay xóa -- bản chuyển đổi được lưu vào một thư mục riêng. "
                "Các cặp ghi '(không cần Calibre)' chạy thẳng bằng thư viện đi kèm.", self))

        format_row = QHBoxLayout()
        format_row.setContentsMargins(0, 0, 0, 0)
        format_row.addWidget(QLabel("Đổi sang:", self))
        self.format_combo = QComboBox(self)
        for fmt in _TARGET_FORMATS:
            self.format_combo.addItem(fmt.upper(), fmt)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        format_row.addWidget(self.format_combo, 1)
        self.body.addLayout(format_row)

        self.risky_notice = HintLabel(
            "Định dạng gốc có thể không được giữ nguyên -- PDF chia trang cố định, đổi sang định dạng chảy chữ "
            "lại có thể làm lệch bố cục.", self, color_token="warn")
        self.risky_notice.setVisible(False)
        self.body.addWidget(self.risky_notice)

        self.output_frame = QFrame(self)
        self.output_frame.setObjectName("OutputCard")
        self.output_frame.setStyleSheet(f"#OutputCard {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
                                        f" border-radius: 8px; }}")
        self.output_label = QLabel(self.output_frame)
        self.output_label.setStyleSheet("background: transparent;")
        self.change_output_button = QPushButton("Đổi thư mục", self.output_frame)
        self.change_output_button.clicked.connect(self._on_change_output_folder)
        out_row = QHBoxLayout(self.output_frame)
        out_row.setContentsMargins(14, 12, 14, 12)
        out_row.addWidget(self.output_label, 1)
        out_row.addWidget(self.change_output_button)
        self.body.addWidget(self.output_frame)
        self._output_dir = context.config.config.conversion_output_folder or ""

        self.score_label = QLabel("", self)
        self.score_label.setTextFormat(Qt.RichText)
        self.score_label.setStyleSheet(role_css(ROLE_RESULT, tm.token("ink")))
        self.body.addWidget(self.score_label)
        self.book_list = QListWidget(self)
        self.book_list.setMinimumHeight(200)
        self.body.addWidget(self.book_list, 1)

        self.busy = BusyIndicator(self, dot_size=12)
        self.body.addWidget(self.busy)

        self.retry_button = self.add_footer_button("Chuyển lại cuốn lỗi", on_click=self.retry_failed, left=True)
        self.retry_button.setEnabled(False)
        self.retry_button.setVisible(False)
        self.run_button = self.add_footer_button("Bắt đầu chuyển đổi", "primary", on_click=self.start)
        self.done_button = self.add_footer_button("Đóng", on_click=self.accept)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._refresh_output_label()
        self._refresh_plan()

    # -- output folder -------------------------------------------------------------------------------------------

    def _refresh_output_label(self) -> None:
        text = self._output_dir or "(chưa chọn thư mục lưu file đã chuyển đổi)"
        self.output_label.setText(f"<b>Lưu vào:</b> {text}")

    def _on_change_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu file đã chuyển đổi", self._output_dir)
        if folder:
            self._output_dir = folder
            self.context.config.config.conversion_output_folder = folder
            self.context.config.save()
            self._refresh_output_label()
            self._refresh_plan()

    def _target_format(self) -> str:
        return self.format_combo.currentData() or _TARGET_FORMATS[0]

    def _on_format_changed(self, _index: int) -> None:
        self._refresh_plan()

    # -- the plan (task C2 AC: file lỗi/không hỗ trợ không dừng cả lô -- quyết định trước khi chạy) -----------------

    def _refresh_plan(self) -> None:
        target = self._target_format()
        any_risky = False
        self.book_list.clear()
        self._plan.clear()
        for doc in self.docs:
            doc_id = doc.get("id") or ""
            path = doc.get("file_path") or ""
            title = doc.get("title") or "(không có tên)"
            source_ext = (doc.get("extension") or Path(path).suffix.lstrip(".")).lower()
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, doc_id)

            if not path:
                status, note = _UNSUPPORTED, "Không tìm thấy file trên máy"
            elif source_ext == target:
                status, note = _UNSUPPORTED, f"Đã là định dạng .{target}"
            elif is_drm_protected(path):
                status, note = _DRM, "Có DRM, không chuyển đổi được"
            elif not is_pair_supported(source_ext, target):
                reason = deferred_reason(source_ext, target)
                status = _UNSUPPORTED
                note = f"Chưa hỗ trợ .{source_ext} → .{target}" + (f" ({reason})" if reason else "")
            else:
                _nc = NativeConverter()
                is_native = _nc.can_convert(source_ext, target)
                if not is_native and not self._calibre_available:
                    status = _UNSUPPORTED
                    note = f"Cần cài Calibre để chuyển .{source_ext} → .{target}"
                else:
                    status = _WILL_CONVERT
                    native_tag = " (không cần Calibre)" if is_native else " (dùng Calibre)"
                    note = "Sẽ chuyển đổi" + native_tag
                    if is_risky_pair(source_ext, target):
                        any_risky = True
                        note = "Sẽ chuyển đổi -- định dạng gốc có thể không được giữ nguyên" + native_tag
            self._plan[doc_id] = status
            self._paint_row(item, status, note)
            self.book_list.addItem(item)

        self.risky_notice.setVisible(any_risky)
        ready = sum(1 for status in self._plan.values() if status == _WILL_CONVERT)
        self.run_button.setEnabled(ready > 0 and not self._running and bool(self._output_dir))
        self.retry_button.setVisible(False)
        if not self._results:
            self.score_label.setText(f"<b>{ready} / {len(self.docs)} sách sẽ chuyển đổi</b>")

    def _paint_row(self, item: QListWidgetItem, status: str, note: str) -> None:
        tm = theme_manager()
        title = item.text().split("\n", 1)[0]
        item.setText(f"{title}\n{note}")
        item.setForeground(tm.color("err") if status == _DRM else tm.color("ink2") if status == _UNSUPPORTED else tm.color("ink"))

    # -- running --------------------------------------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        to_convert = [ConversionJob(doc.get("id") or "", doc.get("title") or "", doc.get("file_path") or "")
                     for doc in self.docs if self._plan.get(doc.get("id") or "") == _WILL_CONVERT]
        if not to_convert or not self._output_dir:
            return
        self._running = True
        self._perf_started_at = time.monotonic()
        self._cancel.clear()
        self.run_button.setEnabled(False)
        self.format_combo.setEnabled(False)
        self.change_output_button.setEnabled(False)
        self.retry_button.setVisible(False)
        self.busy.set_busy(True)

        service, relay, cancel = self.service, self._relay, self._cancel
        bus = self.context.event_bus
        target, output_dir = self._target_format(), self._output_dir

        def on_progress(done: int, total: int) -> None:
            post(relay, "_progress", done, total)
            bus.publish(BackgroundTaskEvent(task="format-conversion", done=done, total=total))

        def work() -> None:
            try:
                result = service.convert_many(to_convert, target, output_dir, progress=on_progress, should_cancel=cancel.is_set)
            except Exception:  # noqa: BLE001 -- the dialog must always get a report back, never hang "running"
                logger.exception("Batch format conversion crashed")
                result = ConversionResult(cancelled=True)
            bus.publish(BackgroundTaskEvent(task="format-conversion", done=1, total=1, finished=True))
            post(relay, "_finished", result)

        threading.Thread(target=work, name="format-conversion", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        self.busy.set_message(f"Đang chuyển đổi {done} / {total} sách…")

    def _on_finished(self, result: ConversionResult) -> None:
        self._running = False
        log_perf("format_conversion", time.monotonic() - self._perf_started_at,
                  items=len(result.items), succeeded=result.succeeded, failed=result.failed,
                  cancelled=result.cancelled)
        self.busy.set_busy(False)
        self.format_combo.setEnabled(True)
        self.change_output_button.setEnabled(True)
        for item_result in result.items:
            self._results[item_result.doc_id] = item_result.error if not item_result.ok else ""
            for row in range(self.book_list.count()):
                item = self.book_list.item(row)
                if item.data(Qt.UserRole) == item_result.doc_id:
                    title = item.text().split("\n", 1)[0]
                    item.setText(f"{title}\n{'Lỗi: ' + item_result.error if not item_result.ok else 'Đã chuyển đổi'}")
                    item.setForeground(theme_manager().color("err") if not item_result.ok else theme_manager().color("ink"))
                    break
        prefix = "Đã dừng. " if result.cancelled else ""
        self.score_label.setText(f"{prefix}Đã chuyển đổi {result.succeeded}, lỗi {result.failed}.")
        self.retry_button.setEnabled(result.failed > 0)
        self.retry_button.setVisible(result.failed > 0)
        self.run_button.setEnabled(False)  # a fresh plan (format/folder change) is what re-enables it

    def retry_failed(self) -> None:
        for doc_id in list(self._results):
            if self._results.get(doc_id):
                self._results.pop(doc_id)
        self._refresh_plan()
        self.start()

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        self._cancel.set()
        super().done(result)
