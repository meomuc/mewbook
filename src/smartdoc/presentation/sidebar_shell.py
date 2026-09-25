# SPDX-License-Identifier: AGPL-3.0-or-later
"""The left column (226 px): logo on top, the navigation body in the middle, "Cài đặt" at the foot.

The shell is only the frame: what the middle shows (library pills, collections, authors, hashtags, formats) is the
`body` widget passed in, so the column looks the same in every theme and the body can be rebuilt without touching it.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from smartdoc import APP_DISPLAY_NAME, APP_NAME
from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.resources import brand_logo_path
from smartdoc.presentation.theme_manager import theme_manager


class SidebarShell(QFrame):
    settings_requested = Signal()

    def __init__(self, body: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.body = body
        body.setMinimumWidth(1)  # the column is 200-226 px wide; a long label elides instead of forcing the column wider
        self.setMinimumWidth(160)

        logo = QLabel(self)
        pixmap = QPixmap(str(brand_logo_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(QSize(36, 36), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._name = QLabel(APP_NAME, self)
        self._name.setObjectName("SidebarBrand")
        self._tagline = QLabel(APP_DISPLAY_NAME, self)
        self._tagline.setObjectName("SidebarTagline")
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self._name)
        names.addWidget(self._tagline)
        header = QHBoxLayout()
        header.setContentsMargins(16, 12, 16, 8)
        header.setSpacing(8)
        header.addWidget(logo)
        header.addLayout(names)
        header.addStretch(1)

        self.settings_button = QPushButton(vi.SETTINGS, self)
        self.settings_button.setObjectName("SidebarSettings")
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.settings_requested)
        footer = QFrame(self)
        footer.setObjectName("SidebarFooter")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(12, 8, 12, 8)
        footer_row.addWidget(self.settings_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(body, stretch=1)
        layout.addWidget(footer)
        self._apply_style()
        theme_manager().themeChanged.connect(self._apply_style)

    def _apply_style(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#SidebarShell {{ background: {tm.token('rail')}; border-right: 1px solid {tm.token('line')}; }}"
            f" #SidebarBrand {{ font-family: {tm.token('ui')}; font-size: 15px; font-weight: 700; color: {tm.token('ink')}; }}"
            f" #SidebarTagline {{ font-family: {tm.token('content')}; font-style: italic; font-size: 12px;"
            f" color: {tm.token('ink3')}; }}"
            f" #SidebarFooter {{ border-top: 1px solid {tm.token('line')}; }}"
            f" #SidebarSettings {{ border: none; background: transparent; text-align: left; color: {tm.token('ink')};"
            f" font-size: 13px; padding: 0 4px; }}"
            f" #SidebarSettings:hover {{ color: {tm.token('accent')}; }}"
        )
        self.settings_button.setIcon(line_icon("gear", tm.token("ink2")))
