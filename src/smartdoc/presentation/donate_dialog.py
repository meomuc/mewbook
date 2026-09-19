"""Small "buy the author a coffee" popup -- opened by clicking the donate
ticker in the status bar (see status_bar_panel.py). Purely informational:
this just displays the author's own VietQR bank code as a static image, the
same one any banking app would scan to send a transfer. No payment flow,
no in-app purchase, nothing collected -- donations are entirely voluntary
(see the EULA/Privacy notice in presentation/eula_dialog.py).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from smartdoc.presentation.resources import donate_qr_path
from smartdoc.presentation.theme import current_colors

_QR_DISPLAY_SIZE = 260


class DonateDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ủng hộ tác giả")
        # Fixed, small size -- a QR popup has no content that benefits from
        # growing, and an unconstrained dialog here would otherwise be free
        # to balloon to whatever Qt's default sizing picks.
        self.setFixedSize(320, 420)

        colors = current_colors()
        # surface is the chrome-family token (dark for Inky Night) -- pair
        # it with sidebar_text, not text, which stays fixed dark since the
        # content grid/list is always light (see theme.py's token docs).
        self.setStyleSheet(f"QDialog {{ background: {colors.surface}; color: {colors.sidebar_text}; }}")

        message = QLabel(
            "☕ Cảm ơn bạn đã dùng Mèo Mực!\n\nNếu ứng dụng làm bạn vui, mời tác giả một ly cà phê nhé 😽",
            self,
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet(f"color: {colors.sidebar_text}; font-size: 13px;")

        self.qr_label = QLabel(self)
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setFixedSize(_QR_DISPLAY_SIZE, _QR_DISPLAY_SIZE)
        pixmap = QPixmap(str(donate_qr_path()))
        if not pixmap.isNull():
            self.qr_label.setPixmap(
                pixmap.scaled(_QR_DISPLAY_SIZE, _QR_DISPLAY_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.qr_label.setText("(Chưa có mã QR)")
            self.qr_label.setStyleSheet(f"color: {colors.muted_text}; border: 1px dashed {colors.border};")

        footer = QLabel("Hoàn toàn tự nguyện - Không phải điều kiện để dùng ứng dụng.", self)
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(f"color: {colors.muted_text}; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addWidget(message)
        layout.addWidget(self.qr_label, alignment=Qt.AlignCenter)
        layout.addWidget(footer)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from smartdoc.presentation.theme import apply_light_theme

    app = QApplication(sys.argv)
    apply_light_theme(app)
    DonateDialog().exec()
