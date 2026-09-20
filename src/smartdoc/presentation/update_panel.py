# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings -> "Cập nhật" tab: the optional, notify-only check for a newer MewBook (S1-05)."""
from __future__ import annotations

import html
import logging
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from smartdoc import __version__
from smartdoc.application.update_checker import UpdateCheckError, UpdateInfo
from smartdoc.presentation.community import community_url, open_community_page

logger = logging.getLogger(__name__)


class UpdatePanel(QWidget):
    _done = Signal(object)  # UpdateInfo | None | Exception

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._busy = False
        layout = QVBoxLayout(self)

        note = QLabel(
            f"Phiên bản đang dùng: {__version__}.\n\n"
            "MewBook có thể hỏi trang phát hành công khai xem có bản mới không. Việc này TẮT mặc định. Khi bật, MewBook chỉ "
            "đọc số phiên bản mới nhất và báo cho bạn; nó không tải hay cài gì. Không có mã cài đặt ẩn danh, thông tin "
            "thư viện hay cookie nào được gửi đi; máy chủ chỉ thấy địa chỉ IP của bạn và số phiên bản, như mọi lần "
            "truy cập web.",
            self,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.enable_check = QCheckBox("Kiểm tra bản mới khi khởi động (tối đa mỗi ngày một lần)", self)
        self.enable_check.setChecked(context.config.config.update_check_enabled)
        layout.addWidget(self.enable_check)

        row = QHBoxLayout()
        self.check_button = QPushButton("🔄 Kiểm tra ngay", self)
        self.check_button.clicked.connect(self._on_check_now)
        row.addWidget(self.check_button)
        # The page that announces new versions works without the update check (and before a release feed exists).
        self.community_button = QPushButton("📣 Fanpage cộng đồng", self)
        self.community_button.setToolTip("Mở fanpage Facebook của Mèo Mực trong trình duyệt: tin về các bản nâng cấp mới và nơi gửi góp ý.")
        self.community_button.setEnabled(bool(community_url()))
        self.community_button.clicked.connect(lambda _checked=False: open_community_page())
        row.addWidget(self.community_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setOpenExternalLinks(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        if not context.updates.configured:
            self.status_label.setText(
                "Chưa cấu hình nguồn thông tin bản phát hành trong bản dựng này, nên chưa kiểm tra được."
                + (" Tin về các bản nâng cấp mới vẫn được đăng ở fanpage cộng đồng." if community_url() else "")
            )
            self.check_button.setEnabled(False)
            self.enable_check.setEnabled(False)
        self._done.connect(self._on_done)

    def is_enabled(self) -> bool:
        return self.enable_check.isChecked()

    def _on_check_now(self) -> None:
        self._busy = True
        self.check_button.setEnabled(False)
        self.status_label.setText("Đang kiểm tra...")

        def target() -> None:
            try:
                result = self.context.updates.check_and_announce()
            except UpdateCheckError as exc:
                result = exc
            except Exception as exc:  # noqa: BLE001 -- always report back, or the button stays disabled
                logger.exception("Update check failed")
                result = exc
            self._done.emit(result)

        threading.Thread(target=target, name="update-check-now", daemon=True).start()

    def _on_done(self, result) -> None:
        self._busy = False
        self.check_button.setEnabled(self.context.updates.configured)
        if isinstance(result, Exception):
            self.status_label.setText(f"⚠️ {html.escape(str(result))}")
        elif result is None:
            self.status_label.setText(f"✅ Bạn đang dùng bản mới nhất ({__version__}).")
        else:
            self.status_label.setText(self._describe(result))

    @staticmethod
    def _describe(info: UpdateInfo) -> str:
        link = f'<a href="{html.escape(info.url, quote=True)}">{html.escape(info.url)}</a>'
        return f"⬆️ Có bản mới: <b>{html.escape(info.version)}</b>. Xem thông tin và tải về tại {link}"
