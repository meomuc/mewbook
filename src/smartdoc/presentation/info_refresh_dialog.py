# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cập nhật ngay: a small window that runs the on-demand file scan (application/info_refresh.py) and shows it going.

It is *not* modal -- the main window stays usable while it runs (it is shown with `show()`, not `exec()`) -- and the
work is on a worker thread that reports through a WorkerRelay. It starts as soon as it opens; closing it cancels the
scan between two books. The end says how many books got newer information, and how many files could not be found.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QProgressBar

from smartdoc.application.info_refresh import RefreshResult
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)


class InfoRefreshDialog(DesignDialog):
    _progress = Signal(int, int)
    _finished = Signal(object, str)  # (RefreshResult | None, error text)

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent, title="Cập nhật thông tin sách", subtitle="Đọc lại file để cập nhật dung lượng, mã nội dung, số trang",
                         icon="refresh", width=520)
        self.context = context
        self._cancel = threading.Event()
        self._running = False
        self._relay = WorkerRelay(self)
        self.status_label = QLabel("Đang chuẩn bị…", self)
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)  # busy until the first report
        self.progress_bar.setTextVisible(True)
        self.note_label = QLabel("Bạn vẫn dùng MewBook bình thường trong lúc này. Tên sách, tác giả và hashtag bạn đã sửa "
                                 "không bị thay đổi.", self)
        self.note_label.setWordWrap(True)
        for widget in (self.status_label, self.progress_bar, self.note_label):
            self.body.addWidget(widget)
        self.body.addStretch(1)
        self.action_button = self.add_footer_button("Dừng", on_click=self._on_action)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancel.clear()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Đang quét thư viện…")
        self.action_button.setText("Dừng")
        relay, service, cancel = self._relay, self.context.info_refresh, self._cancel

        def work() -> None:
            try:
                result = service.run(progress=lambda done, total: post(relay, "_progress", done, total), should_cancel=cancel.is_set)
                post(relay, "_finished", result, "")
            except Exception as exc:  # noqa: BLE001 -- a worker must always report back, or the window shows "running" forever
                logger.exception("Info refresh failed")
                post(relay, "_finished", None, f"Không quét xong được: {exc}")

        threading.Thread(target=work, name="info-refresh", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)
        self.status_label.setText(f"Đang quét: {done} / {total} sách")

    def _on_finished(self, result: RefreshResult | None, error: str) -> None:
        self._running = False
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.action_button.setText("Đóng")
        if error or result is None:
            self.status_label.setText(error)
            return
        text = f"Đã cập nhật thông tin mới cho {result.updated} / {result.checked} sách."
        if result.missing:
            text += f" {result.missing} sách không thấy file."
        if result.skipped_cloud:
            text += f" {result.skipped_cloud} file chỉ có trên đám mây (chưa tải về) được bỏ qua."
        if result.cancelled:
            text = "Đã dừng. " + text
        self.status_label.setText(text)

    def _on_action(self) -> None:
        self.close()

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        self._cancel.set()
        super().done(result)
