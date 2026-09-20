# SPDX-License-Identifier: AGPL-3.0-or-later
"""The question "send an anonymous report of this error?" and what shows it (S1e, E-04, FR-ERR-03; ERR-A1, ERR-A4).

`ErrorReportDialog` is the modal question for one queued report ("Mèo gặp lỗi bất ngờ"): the user can read exactly what
would be sent (the preview is the payload itself, ERR-A4), send it, or not send it, and can make either answer the
standing one ("Luôn gửi tự động (ẩn danh)" / "Không hỏi lại"). Closing the window with [x] or Esc is "Không gửi": silence
is never consent.

`ErrorReportPrompt` decides when to ask. It listens (through QtEventBridge, because the error may have happened on any
thread) for `ErrorReportPendingEvent`, and:
- never runs the dialog inside the failing call (an error while painting repeats on every repaint, and a modal loop in
  the middle of a paint froze the window -- see app.py's crash dialog),
- asks about one report at a time; another that arrives meanwhile waits and is asked about afterwards, and
- at start-up asks about a report an earlier session never got an answer for (the newest one; the others are dropped so
  a bad day is one question, not twenty).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from smartdoc.application.error_report_queue import STATUS_PENDING
from smartdoc.application.error_reporter import ErrorReportError
from smartdoc.core.event_bus import ErrorReportPendingEvent
from smartdoc.presentation.qt_event_bridge import QtEventBridge

logger = logging.getLogger(__name__)

TITLE = "Mèo gặp lỗi bất ngờ"
QUESTION = (
    "Bạn có muốn gửi báo cáo lỗi ẩn danh để giúp sửa lỗi này không? "
    "Báo cáo <b>không</b> chứa tên sách, đường dẫn hay nội dung tài liệu của bạn."
)
THANKS = "Cảm ơn bạn. Mã báo cáo: {id}"


class ErrorReportDialog(QDialog):
    """Asks about one queued report. `sent` is True once the user chose "Gửi báo cáo"."""

    def __init__(self, context, report_id: str, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.report_id = report_id
        self.sent = False
        self._resolved = False
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(520)

        reporter = context.error_reports
        item = reporter.pending(report_id)

        layout = QVBoxLayout(self)
        self.heading = QLabel(f"😿 {TITLE}", self)
        self.heading.setStyleSheet("font-weight: 700; font-size: 16px;")
        layout.addWidget(self.heading)

        self.question_label = QLabel(QUESTION, self)
        self.question_label.setTextFormat(Qt.RichText)
        self.question_label.setWordWrap(True)
        layout.addWidget(self.question_label)

        # What went wrong, in the words that would be sent: the type and the scrubbed message.
        summary = ""
        if item is not None:
            report = item.report
            summary = f"{report.exception_type}: {report.message_scrubbed}" if report.message_scrubbed else report.exception_type
        self.summary_label = QLabel(summary, self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(self.summary_label)

        self.preview = QTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setFontFamily("Consolas")
        self.preview.setMinimumHeight(220)
        self.preview.hide()
        layout.addWidget(self.preview)

        self.always_check = QCheckBox("Luôn gửi tự động (ẩn danh)", self)
        self.always_check.setToolTip("Lần sau MewBook gửi báo cáo lỗi ẩn danh mà không hỏi. Đổi lại được trong Cài đặt.")
        self.never_check = QCheckBox("Không hỏi lại", self)
        self.never_check.setToolTip("Áp dụng khi bạn bấm \"Không gửi\": MewBook sẽ không thu thập hay gửi báo cáo lỗi nữa.")
        self.always_check.toggled.connect(lambda on: self.never_check.setChecked(False) if on else None)
        self.never_check.toggled.connect(lambda on: self.always_check.setChecked(False) if on else None)
        layout.addWidget(self.always_check)
        layout.addWidget(self.never_check)

        self.buttons_row = QHBoxLayout()
        self.preview_button = QPushButton("Xem nội dung sẽ gửi", self)
        self.preview_button.clicked.connect(self._toggle_preview)
        self.send_button = QPushButton("Gửi báo cáo", self)
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self._on_send)
        self.decline_button = QPushButton("Không gửi", self)
        self.decline_button.clicked.connect(self._on_decline)
        for button in (self.preview_button, self.send_button, self.decline_button):
            self.buttons_row.addWidget(button)
        layout.addLayout(self.buttons_row)

        self.thanks_label = QLabel(self)
        self.thanks_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.thanks_label.hide()
        layout.addWidget(self.thanks_label)
        self.close_button = QPushButton("Đóng", self)
        self.close_button.clicked.connect(self.accept)
        self.close_button.hide()
        layout.addWidget(self.close_button)

        if item is None:  # the report vanished (declined elsewhere, queue cleared): nothing left to ask
            self.send_button.setEnabled(False)
            self.preview_button.setEnabled(False)

    # -- actions -----------------------------------------------------------------------------------------------

    def _toggle_preview(self) -> None:
        if self.preview.isHidden():
            try:
                self.preview.setPlainText(self.context.error_reports.preview_text(self.report_id))
            except ErrorReportError:
                self.preview.setPlainText("Không còn báo cáo này.")
            self.preview.show()
            self.preview_button.setText("Ẩn nội dung sẽ gửi")
        else:
            self.preview.hide()
            self.preview_button.setText("Xem nội dung sẽ gửi")
            self.adjustSize()

    def _on_send(self) -> None:
        try:
            self.context.error_reports.approve(self.report_id, always=self.always_check.isChecked())
        except ErrorReportError:
            logger.warning("The report to send is gone")
            self.reject()
            return
        self._resolved = True
        self.sent = True
        self._show_thanks()

    def _on_decline(self) -> None:
        self._resolve_as_declined()
        self.reject()

    def _resolve_as_declined(self) -> None:
        if not self._resolved:
            self._resolved = True
            self.context.error_reports.decline(self.report_id, never=self.never_check.isChecked())

    def reject(self) -> None:
        # [x] and Esc are "no": a report is only ever sent after a click on "Gửi báo cáo".
        self._resolve_as_declined()
        super().reject()

    def _show_thanks(self) -> None:
        for widget in (self.question_label, self.summary_label, self.preview, self.always_check, self.never_check,
                       self.preview_button, self.send_button, self.decline_button):
            widget.hide()
        self.thanks_label.setText(THANKS.format(id=self.report_id))
        self.thanks_label.show()
        self.close_button.show()
        self.close_button.setDefault(True)
        self.adjustSize()


class ErrorReportPrompt(QObject):
    """Asks the user about queued error reports, one dialog at a time and never inside the failing call."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._open = False
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_event)
        self._bridge.subscribe(context.event_bus, ErrorReportPendingEvent)

    def _on_event(self, event: ErrorReportPendingEvent) -> None:
        # Always deferred: when the error happened on the GUI thread this slot runs *inside* the failing call.
        QTimer.singleShot(0, lambda: self.ask(event.report_id))

    def ask(self, report_id: str) -> bool:
        """Shows the dialog for `report_id`. False when it is not shown (one is open already, or nothing waits)."""
        reporter = self.context.error_reports
        item = reporter.pending(report_id)
        if self._open or item is None or item.status != STATUS_PENDING or reporter.effective_mode() != "ask":
            return False
        self._open = True
        dialog = ErrorReportDialog(self.context, report_id)
        try:
            dialog.exec()
        finally:
            self._open = False
            dialog.deleteLater()  # a dialog that is exec()ed and dropped is destroyed by Qt, not left to the collector
        # Something else may have arrived while this one was open (never the same report again: `exclude`).
        QTimer.singleShot(0, lambda: self.ask_about_waiting(exclude=report_id))
        return True

    def ask_about_waiting(self, exclude: str | None = None) -> None:
        """Asks about the newest report that is still waiting for an answer (from an earlier session, or one that
        arrived while a dialog was open); the older ones are dropped and not asked about again today."""
        reporter = self.context.error_reports
        waiting = [
            item for item in reporter.queue.items() if item.status == STATUS_PENDING and item.report.report_id != exclude
        ]
        if not waiting or reporter.effective_mode() != "ask":
            return
        *older, newest = waiting
        for item in older:
            reporter.decline(item.report.report_id)
        self.ask(newest.report.report_id)
