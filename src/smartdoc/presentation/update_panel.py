# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings -> "Cập nhật" tab: the optional, notify-only check for a newer MewBook (S1-05)."""
from __future__ import annotations

import html
import logging
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from smartdoc import APP_DISPLAY_NAME, __version__
from smartdoc.application.update_checker import UpdateCheckError, UpdateInfo
from smartdoc.presentation.community import community_url, open_community_page, open_website, website_url
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.settings_widgets import SettingsPage
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)


class UpdatePanel(SettingsPage):
    _done = Signal(object)  # UpdateInfo | None | Exception

    def __init__(self, context, parent=None) -> None:
        super().__init__("Cập nhật & ủng hộ", "MewBook miễn phí. Nếu nó giúp ích, bạn có thể mời tác giả một ly cà phê.", parent)
        self.context = context
        self._busy = False
        self._relay = WorkerRelay(self)
        tm = theme_manager()

        version = QLabel(f"{APP_DISPLAY_NAME} {__version__}", self)
        self.add_row("Phiên bản đang dùng", "", version)

        self.enable_check = QCheckBox("Kiểm tra bản mới khi khởi động (tối đa mỗi ngày một lần)", self)
        self.enable_check.setChecked(context.config.config.update_check_enabled)
        self.add_row("Tự kiểm tra bản mới", "Tắt mặc định. Khi bật, MewBook chỉ đọc số phiên bản mới nhất và báo cho bạn; "
                     "nó không tải hay cài gì, và không gửi thông tin thư viện.", self.enable_check)

        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.check_button = QPushButton("Kiểm tra ngay", box)
        self.check_button.setIcon(line_icon("refresh", tm.token("ink"), 14))
        self.check_button.clicked.connect(self._on_check_now)
        row.addWidget(self.check_button)
        # The page that announces new versions works without the update check (and before a release feed exists).
        self.website_button = QPushButton("Trang web chính thức", box)
        self.website_button.setIcon(line_icon("globe", tm.token("ink"), 14))
        self.website_button.setToolTip("Mở trang web chính thức của Mèo Mực trong trình duyệt: tải bản mới và xem tin cập nhật.")
        self.website_button.setEnabled(bool(website_url()))
        self.website_button.clicked.connect(lambda _checked=False: open_website())
        row.addWidget(self.website_button)
        self.community_button = QPushButton("Fanpage cộng đồng", box)
        self.community_button.setIcon(line_icon("link", tm.token("ink"), 14))
        self.community_button.setToolTip("Mở fanpage Facebook của Mèo Mực trong trình duyệt: tin về các bản nâng cấp mới và nơi gửi góp ý.")
        self.community_button.setEnabled(bool(community_url()))
        self.community_button.clicked.connect(lambda _checked=False: open_community_page())
        row.addWidget(self.community_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.status_label = QLabel(box)
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setOpenExternalLinks(True)
        layout.addWidget(self.status_label)
        self.add_row("Kiểm tra và liên kết", "Tin về bản mới cũng được đăng ở fanpage.", box)

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
        relay, updates = self._relay, self.context.updates

        def target() -> None:
            try:
                result = updates.check_and_announce()
            except UpdateCheckError as exc:
                result = exc
            except Exception as exc:  # noqa: BLE001 -- always report back, or the button stays disabled
                logger.exception("Update check failed")
                result = exc
            post(relay, "_done", result)

        threading.Thread(target=target, name="update-check-now", daemon=True).start()

    def _on_done(self, result) -> None:
        self._busy = False
        self.check_button.setEnabled(self.context.updates.configured)
        if isinstance(result, Exception):
            self.status_label.setText(html.escape(str(result)))
        elif result is None:
            self.status_label.setText(f"Bạn đang dùng bản mới nhất ({__version__}).")
        else:
            self.status_label.setText(self._describe(result))

    @staticmethod
    def _describe(info: UpdateInfo) -> str:
        link = f'<a href="{html.escape(info.url, quote=True)}">{html.escape(info.url)}</a>'
        return f"Có bản mới: <b>{html.escape(info.version)}</b>. Xem thông tin và tải về tại {link}"
