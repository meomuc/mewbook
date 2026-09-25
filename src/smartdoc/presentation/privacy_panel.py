# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings -> "Quyền riêng tư và báo lỗi": the standing choice about anonymous error reports (S1e, E-04, FR-ERR-04).

Three modes -- "Hỏi mỗi lần" (the default: ask after each error and show exactly what would be sent), "Luôn gửi ẩn danh"
and "Không bao giờ" (nothing is collected, written or sent) -- what a report holds and does not hold, the reports
waiting to be sent, the ids of the ones that were (so a user can ask for one to be deleted), and how to ask.

The choice is applied when Settings is saved (`apply`), like the other tabs, through `ErrorReporter.set_mode`, which is
what records the consent wording the user agreed to when they pick "always".
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc import APP_PRIVACY_CONTACT
from smartdoc.application.error_reporter import MODE_ALWAYS, MODE_ASK, MODE_NEVER
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.settings_widgets import SettingsPage, add_note_box
from smartdoc.presentation.theme_manager import theme_manager

_INTRO = (
    "MewBook có thể gửi báo cáo lỗi ẩn danh để chủ dự án sửa lỗi nhanh hơn. Việc này hoàn toàn tự nguyện: mặc định MewBook "
    "hỏi bạn sau mỗi lỗi, cho bạn xem đúng nội dung sẽ gửi và chỉ gửi khi bạn đồng ý.\n\n"
    "Một báo cáo gồm: loại lỗi, các dòng mã nơi lỗi xảy ra (tên hàm và số dòng), phiên bản MewBook, hệ điều hành, giao diện "
    "đang dùng, cỡ thư viện (theo khoảng) và một mã ngẫu nhiên riêng cho báo lỗi (không liên quan tới mã đánh giá). "
    "Báo cáo KHÔNG chứa tên hay đường dẫn file sách, tựa sách, tác giả, nội dung tài liệu, tên người dùng Windows, tên máy, "
    "email hay khóa API. MewBook không gửi thống kê sử dụng nào."
)
_MODES = (
    (MODE_ASK, "Hỏi mỗi lần", "Mặc định. Sau mỗi lỗi bất ngờ MewBook hỏi và cho bạn xem nội dung trước khi gửi."),
    (MODE_ALWAYS, "Luôn gửi ẩn danh", "Gửi báo cáo lỗi ẩn danh mà không hỏi (vẫn theo đúng các quy tắc ở trên)."),
    (MODE_NEVER, "Không bao giờ", "Không thu thập, không ghi và không gửi báo cáo lỗi. Báo lỗi thủ công (Trợ giúp) vẫn dùng được."),
)


_CONNECTIONS = (
    ("Open Library, Google Books (Apple Books, Tiki nếu bạn bật)", "Khi bạn tìm ảnh bìa hoặc thông tin sách.",
     "Tên sách và tác giả bạn đang tìm."),
    ("Nhà cung cấp AI bạn chọn", "Khi bạn bấm tóm tắt bằng AI.", "Thông tin của cuốn sách bạn yêu cầu tóm tắt. Ollama chạy trên máy bạn thì không rời máy."),
    ("Máy chủ đánh giá cộng đồng", "Khi bạn mở hoặc đăng đánh giá (có thể tắt trong Cài đặt).", "Nick name, số sao, nhận xét và mã cuốn sách."),
    ("Trang phát hành của MewBook", "Chỉ khi bạn bật tự kiểm tra bản mới hoặc bấm “Kiểm tra ngay”.", "Không gửi gì ngoài địa chỉ IP và số phiên bản, như mọi lần truy cập web."),
    ("Máy chủ nhận báo lỗi", "Chỉ khi bạn cho phép ở phần Khi MewBook gặp lỗi.", "Báo cáo ẩn danh, bạn xem được nội dung trước khi gửi."),
)


class PrivacyPanel(SettingsPage):
    def __init__(self, context, parent=None) -> None:
        super().__init__("Quyền riêng tư", "MewBook không có thống kê sử dụng. Đây là mọi thứ có thể rời khỏi máy bạn.", parent)
        self.context = context
        reporter = context.error_reports

        self.intro_label = QLabel(_INTRO, self)
        self.intro_label.setWordWrap(True)
        self.intro_label.setTextFormat(Qt.PlainText)
        self.add_block(self.intro_label)
        self.add_block(add_note_box(
            self, "<b>Báo cáo lỗi không có:</b> tên hay đường dẫn file sách, tựa sách, tác giả, nội dung tài liệu, "
                  "tên người dùng Windows, tên máy, email hay khóa API.", "ok"))

        group = QWidget(self)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_buttons: dict[str, QRadioButton] = {}
        for mode, label, tip in _MODES:
            button = QRadioButton(label, group)
            button.setToolTip(tip)
            button.setChecked(mode == reporter.mode())
            group_layout.addWidget(button)
            group_layout.addWidget(self._grey(tip))
            self.mode_buttons[mode] = button
        self.add_row("Khi MewBook gặp lỗi bất ngờ", "Chỉ bạn quyết định có gửi báo cáo hay không.", group)

        self.notice_label = QLabel(self)
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(f"color: {theme_manager().token('ink2')};")
        self.add_block(self.notice_label)
        if not reporter.enabled:
            self.notice_label.setText(
                "Bản này chạy từ mã nguồn hoặc chưa được dựng từ một commit sạch nên không thu thập và không gửi báo cáo lỗi; "
                "lựa chọn ở trên vẫn được lưu cho bản cài đặt chính thức."
            )
        elif reporter.mode() == MODE_ALWAYS and reporter.effective_mode() != MODE_ALWAYS:
            self.notice_label.setText("Nội dung thông báo quyền riêng tư đã đổi: MewBook sẽ hỏi lại ở lần lỗi tới.")

        self.waiting_label = QLabel(self)
        self.waiting_label.setWordWrap(True)
        self.clear_button = QPushButton("Xóa các báo cáo đang chờ", self)
        self.clear_button.setIcon(line_icon("close", theme_manager().token("ink"), 14))
        self.clear_button.clicked.connect(self._on_clear_waiting)
        waiting = QWidget(self)
        waiting_layout = QVBoxLayout(waiting)
        waiting_layout.setContentsMargins(0, 0, 0, 0)
        waiting_layout.addWidget(self.waiting_label)
        waiting_layout.addWidget(self.clear_button, 0, Qt.AlignLeft)
        self.add_row("Báo cáo đang chờ", "Chưa gửi, hoặc đang chờ bạn quyết định.", waiting)

        sent = QWidget(self)
        sent_layout = QVBoxLayout(sent)
        sent_layout.setContentsMargins(0, 0, 0, 0)
        self.sent_header = QLabel(self)
        sent_layout.addWidget(self.sent_header)
        self.sent_list = QListWidget(self)
        self.sent_list.setMaximumHeight(150)
        sent_layout.addWidget(self.sent_list)
        self.copy_button = QPushButton("Sao chép mã đã chọn", self)
        self.copy_button.clicked.connect(self._on_copy_selected)
        sent_layout.addWidget(self.copy_button, 0, Qt.AlignLeft)
        contact = APP_PRIVACY_CONTACT or "cách liên hệ ghi trong chính sách riêng tư của dự án"
        self.deletion_label = QLabel(
            "Muốn xóa một báo cáo đã gửi? Gửi mã báo cáo (ở danh sách trên) cho chủ dự án, báo cáo được xóa theo mã. "
            f"Liên hệ: {contact}. Báo cáo được giữ tối đa 90 ngày.",
            self,
        )
        self.deletion_label.setWordWrap(True)
        self.deletion_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sent_layout.addWidget(self.deletion_label)
        self.add_row("Báo cáo đã gửi", "Mã để bạn yêu cầu xóa.", sent)

        connections = QWidget(self)
        connections_layout = QVBoxLayout(connections)
        connections_layout.setContentsMargins(0, 0, 0, 0)
        for where, when, what in _CONNECTIONS:
            label = QLabel(f"<b>{where}</b><br>{when} {what}", connections)
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {theme_manager().token('ink2')}; font-size: 13px;")
            connections_layout.addWidget(label)
        self.add_row("Mọi kết nối mạng của MewBook", "Ngoài danh sách này, MewBook không kết nối đi đâu.", connections)

        self.sent_list.itemSelectionChanged.connect(self._update_state)
        self.refresh()

    @staticmethod
    def _grey(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme_manager().token('ink3')}; font-size: 13px; margin: 0 0 6px 24px;")
        return label

    # -- state ----------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        reporter = self.context.error_reports
        self.sent_list.clear()
        for record in reporter.sent_reports():
            when = datetime.fromtimestamp(record.sent_at).strftime("%d/%m/%Y %H:%M")
            item = QListWidgetItem(f"{when}  ·  {record.report_id}")
            item.setData(Qt.UserRole, record.report_id)
            self.sent_list.addItem(item)
        self.sent_header.setText("Mã các báo cáo đã gửi:" if self.sent_list.count() else "Mã các báo cáo đã gửi: chưa có báo cáo nào.")
        self.sent_list.setVisible(self.sent_list.count() > 0)
        waiting = len(reporter.queue.items())
        text = f"Đang chờ gửi hoặc chờ bạn quyết định: {waiting} báo cáo." if waiting else "Không có báo cáo nào đang chờ."
        status = self.context.error_uploader.status_text() if waiting else ""  # e.g. "Chưa gửi được báo cáo. Ứng dụng sẽ thử lại sau."
        self.waiting_label.setText(f"{text} {status}".strip())
        self._update_state()

    def _update_state(self) -> None:
        self.clear_button.setEnabled(bool(self.context.error_reports.queue.items()))
        self.copy_button.setEnabled(self.sent_list.currentItem() is not None)

    def _on_clear_waiting(self) -> None:
        self.context.error_reports.queue.clear()
        self.refresh()

    def _on_copy_selected(self) -> None:
        item = self.sent_list.currentItem()
        if item is not None:
            QApplication.clipboard().setText(item.data(Qt.UserRole))

    # -- what Settings reads -----------------------------------------------------------------------------------------

    def selected_mode(self) -> str:
        for mode, button in self.mode_buttons.items():
            if button.isChecked():
                return mode
        return MODE_ASK

    def apply(self) -> None:
        """Called when Settings is saved. Only a *change* is written, so opening and saving Settings never turns an
        older "always" consent into a fresh one."""
        reporter = self.context.error_reports
        chosen = self.selected_mode()
        if chosen != reporter.mode():
            reporter.set_mode(chosen)
