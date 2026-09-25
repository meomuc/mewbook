# SPDX-License-Identifier: AGPL-3.0-or-later
"""Help -> "Báo lỗi…": a report the user writes (S1e, E-04, FR-ERR-04).

Describe what happened, optionally add the end of the log, press "Xem nội dung sẽ gửi", read exactly what will be sent,
then "Gửi báo cáo". There is always a preview: the send button stays off until the current text and choices have been
previewed, and editing anything afterwards switches it off again -- what is sent is what was read (ERR-A4).

A manual report is an explicit act, so it works whatever the standing mode is (even "Không bao giờ", which is about
what MewBook does on its own). A build that does not collect (running from source) says so instead.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout

from smartdoc.application.error_reporter import ErrorReportError
from smartdoc.domain.error_report import MAX_NOTE_CHARS, payload_json

TITLE = "Báo lỗi"
THANKS = "Cảm ơn bạn. Mã báo cáo: {id}"
_INFO = (
    "Mô tả điều đã xảy ra và bạn mong đợi gì. Đừng ghi tên sách, đường dẫn hay thông tin cá nhân: MewBook tự che những gì nó "
    "nhận ra, và bạn xem lại toàn bộ nội dung trước khi gửi."
)


class ManualReportDialog(QDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._report = None  # the report that was previewed; None whenever what is on screen has not been previewed
        self.sent = False
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        self.info_label = QLabel(_INFO, self)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.note_edit = QPlainTextEdit(self)
        self.note_edit.setPlaceholderText("Mô tả lỗi...")
        self.note_edit.setMinimumHeight(110)
        self.note_edit.textChanged.connect(self._on_edited)
        layout.addWidget(self.note_edit)
        self.counter_label = QLabel(self)
        self.counter_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        self.counter_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.counter_label)

        self.log_check = QCheckBox("Kèm phần cuối nhật ký (tối đa 50 dòng, đã che thông tin cá nhân)", self)
        self.log_check.toggled.connect(self._on_edited)
        layout.addWidget(self.log_check)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.preview = QTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setFontFamily("Consolas")
        self.preview.setMinimumHeight(220)
        self.preview.hide()
        layout.addWidget(self.preview)

        row = QHBoxLayout()
        self.preview_button = QPushButton("Xem nội dung sẽ gửi", self)
        self.preview_button.clicked.connect(self._on_preview)
        self.send_button = QPushButton("Gửi báo cáo", self)
        self.send_button.clicked.connect(self._on_send)
        self.cancel_button = QPushButton("Hủy", self)
        self.cancel_button.clicked.connect(self.reject)
        for button in (self.preview_button, self.send_button, self.cancel_button):
            row.addWidget(button)
        layout.addLayout(row)

        self.thanks_label = QLabel(self)
        self.thanks_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.thanks_label.hide()
        layout.addWidget(self.thanks_label)
        self.close_button = QPushButton("Đóng", self)
        self.close_button.clicked.connect(self.accept)
        self.close_button.hide()
        layout.addWidget(self.close_button)

        if not context.error_reports.enabled:
            self.note_edit.setEnabled(False)
            self.log_check.setEnabled(False)
            self.status_label.setText("Bản này chạy từ mã nguồn (hoặc chưa dựng từ một commit sạch) nên không gửi được báo cáo lỗi.")
        self._on_edited()

    # -- state ---------------------------------------------------------------------------------------------------

    def _on_edited(self, *_args) -> None:
        text = self.note_edit.toPlainText()
        if len(text) > MAX_NOTE_CHARS:
            self.note_edit.setPlainText(text[:MAX_NOTE_CHARS])  # re-enters this slot once, with the cut text
            return
        self._report = None  # whatever was previewed is no longer what would be sent
        self.counter_label.setText(f"{len(text)}/{MAX_NOTE_CHARS}")
        self.preview_button.setEnabled(self.context.error_reports.enabled and bool(text.strip()))
        self.send_button.setEnabled(False)
        if self.context.error_reports.enabled and not self.preview.isHidden():
            self.preview.hide()
            self.status_label.setText("Đã sửa: hãy bấm \"Xem nội dung sẽ gửi\" lại trước khi gửi.")

    def _on_preview(self) -> None:
        try:
            report = self.context.error_reports.build_manual(self.note_edit.toPlainText(), include_log=self.log_check.isChecked())
        except ErrorReportError as exc:
            self.status_label.setText(f"{exc}")
            return
        self._report = report
        self.preview.setPlainText(payload_json(report.to_payload(), indent=2))
        self.preview.show()
        self.status_label.setText("Đây là toàn bộ nội dung sẽ được gửi. Bấm \"Gửi báo cáo\" nếu bạn đồng ý.")
        self.send_button.setEnabled(True)

    def _on_send(self) -> None:
        if self._report is None:
            return
        try:
            self.context.error_reports.submit(self._report)
        except ErrorReportError as exc:
            self.status_label.setText(f"{exc}")
            return
        self.sent = True
        for widget in (self.info_label, self.note_edit, self.counter_label, self.log_check, self.status_label, self.preview,
                       self.preview_button, self.send_button, self.cancel_button):
            widget.hide()
        self.thanks_label.setText(THANKS.format(id=self._report.report_id))
        self.thanks_label.show()
        self.close_button.show()
        self.adjustSize()
