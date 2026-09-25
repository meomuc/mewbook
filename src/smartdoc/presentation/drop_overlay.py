# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cover shown over the window while files are dragged onto it: a dashed accent frame, the mascot and "Thả vào
đây để thêm vào thư viện". It only paints (mouse events pass through it); the main window shows it on drag-enter and
hides it on leave or drop, and does the actual adding. The line under the title says what is true: the original files
stay where they are."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from smartdoc.presentation.brand import mascot_pixmap
from smartdoc.presentation.theme_manager import theme_manager

TITLE = "Thả vào đây để thêm vào thư viện"
SUBTITLE = "PDF, EPUB, MOBI, AZW3 · file hoặc cả thư mục · file gốc giữ nguyên chỗ cũ"


class DropOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def show_over(self, area) -> None:
        self.setGeometry(area)
        self.raise_()
        self.show()

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        veil = QColor(tm.token("bg"))
        veil.setAlpha(225)
        painter.fillRect(self.rect(), veil)
        frame = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        pen = QPen(QColor(tm.token("accent")), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame, 10, 10)

        mascot = mascot_pixmap("logo", 130, self.devicePixelRatioF())
        centre_y = self.height() / 2
        if mascot is not None:
            width = mascot.width() / mascot.devicePixelRatio()
            painter.drawPixmap(int((self.width() - width) / 2), int(centre_y - 120), mascot)
        title_font = QFont(tm.font_family("content"))
        title_font.setPixelSize(22)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(tm.token("ink")))
        painter.drawText(QRectF(0, centre_y + 24, self.width(), 32), Qt.AlignCenter, TITLE)
        sub_font = QFont(tm.font_family("ui"))
        sub_font.setPixelSize(13)
        painter.setFont(sub_font)
        painter.setPen(QColor(tm.token("ink2")))
        painter.drawText(QRectF(0, centre_y + 60, self.width(), 22), Qt.AlignCenter, SUBTITLE)
        painter.end()
