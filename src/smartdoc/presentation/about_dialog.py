"""Help -> About dialog: app identity plus a way to re-read the EULA/Privacy
notice at any time after the first-launch prompt (see eula_dialog.py's
EULA_TEXT, the single source for that wording, reused verbatim here).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from smartdoc import APP_COPYRIGHT, APP_DESCRIPTION, APP_DISPLAY_NAME, APP_NAME, __version__
from smartdoc.core.diagnostics import current_log_path, support_info
from smartdoc.presentation.eula_dialog import EULA_TEXT
from smartdoc.presentation.resources import brand_logo_path

_LOGO_SIZE = 64


class AboutDialog(QDialog):
    def __init__(self, parent=None, *, identity=None) -> None:
        super().__init__(parent)
        self._identity = identity
        self.setWindowTitle("Giới thiệu")
        # Fixed size -- an About dialog has fixed content, no reason to
        # ever grow beyond it.
        self.setFixedSize(440, 520)

        self._info_page = self._build_info_page()
        self._legal_page = self._build_legal_page()

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._info_page)
        self.stack.addWidget(self._legal_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    def _build_info_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        logo_label = QLabel(page)
        logo_label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(brand_logo_path()))
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaled(_LOGO_SIZE, _LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(logo_label)

        title = QLabel(APP_DISPLAY_NAME, page)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: 700; font-size: 18px;")
        layout.addWidget(title)

        self.version_label = QLabel(f"Phiên bản {__version__}", page)
        self.version_label.setAlignment(Qt.AlignCenter)
        self.version_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.version_label)

        subtitle = QLabel(f"{APP_NAME} -- {APP_DESCRIPTION.lower()}", page)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        author = QLabel("Phát triển bởi Anhtiensinh", page)
        author.setAlignment(Qt.AlignCenter)
        layout.addWidget(author)

        copyright_label = QLabel(APP_COPYRIGHT, page)
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(copyright_label)

        if self._identity is not None:
            id_label = QLabel(f"Mã cài đặt ẩn danh: {self._identity.short_id}", page)
            id_label.setAlignment(Qt.AlignCenter)
            id_label.setStyleSheet("color: palette(mid); font-size: 11px;")
            id_label.setToolTip(
                "Mã ngẫu nhiên sinh ra khi cài đặt, dùng để nhận biết bài đánh giá của bạn mà không cần đăng ký. "
                "Không chứa thông tin cá nhân; cài lại ứng dụng sẽ sinh mã mới."
            )
            layout.addWidget(id_label)

        layout.addStretch(1)

        support_row = QHBoxLayout()
        self.copy_support_button = QPushButton("📋 Sao chép thông tin hỗ trợ", page)
        self.copy_support_button.setToolTip("Phiên bản, hệ điều hành và đường dẫn file nhật ký -- gửi kèm khi báo lỗi.")
        self.copy_support_button.clicked.connect(self._on_copy_support_info)
        support_row.addWidget(self.copy_support_button)
        self.open_logs_button = QPushButton("📂 Thư mục nhật ký", page)
        self.open_logs_button.clicked.connect(self._on_open_logs)
        self.open_logs_button.setEnabled(current_log_path() is not None)
        support_row.addWidget(self.open_logs_button)
        layout.addLayout(support_row)

        self.legal_button = QPushButton("📄 Điều khoản pháp lý (Legal & Privacy)", page)
        self.legal_button.clicked.connect(lambda: self.stack.setCurrentWidget(self._legal_page))
        layout.addWidget(self.legal_button)

        return page

    def _build_legal_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        heading = QLabel("Điều khoản pháp lý (Legal & Privacy)", page)
        heading.setStyleSheet("font-weight: 700;")
        layout.addWidget(heading)

        self.legal_text_area = QTextEdit(page)
        self.legal_text_area.setReadOnly(True)
        self.legal_text_area.setPlainText(EULA_TEXT)
        layout.addWidget(self.legal_text_area, stretch=1)

        self.back_button = QPushButton("← Quay lại", page)
        self.back_button.clicked.connect(lambda: self.stack.setCurrentWidget(self._info_page))
        layout.addWidget(self.back_button)

        return page

    def _on_copy_support_info(self) -> None:
        QApplication.clipboard().setText(support_info(self._identity))
        self.copy_support_button.setText("✅ Đã sao chép")

    def _on_open_logs(self) -> None:
        log_path = current_log_path()
        if log_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path.parent)))


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from smartdoc.presentation.theme import apply_light_theme

    app = QApplication(sys.argv)
    apply_light_theme(app)
    AboutDialog().exec()
