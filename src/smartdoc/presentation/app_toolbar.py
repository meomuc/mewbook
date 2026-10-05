# SPDX-License-Identifier: AGPL-3.0-or-later
"""The main window's toolbar (54 px): "+ Thêm sách ▾" · search · view switch · cover size · sort · "Công cụ ▾" · detail toggle.

It only arranges controls that already exist (the search box and LibraryToolbar keep their own logic) and owns two
menu buttons whose actions the main window supplies -- so the toolbar never needs to know what "add" or a tool does.
When the toolbar itself is narrower than ICONS_ONLY_BELOW (a narrow window, or a wide one with the detail panel
open) the buttons drop their words; the tooltips keep them.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QToolButton, QWidget

from smartdoc.presentation import strings as vi
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import TOOLBAR_H, theme_manager

COMPACT_BELOW = 1100  # window width: the sidebar narrows to 200 px
ICONS_ONLY_BELOW = 900  # the toolbar's own width: the buttons drop their words (tooltips keep them)


class AppToolbar(QWidget):
    detail_toggled = Signal(bool)

    def __init__(self, omnibar: QWidget, library_toolbar, add_menu: QMenu, tools_menu: QMenu, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AppToolbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(TOOLBAR_H)
        self.omnibar = omnibar
        self.library_toolbar = library_toolbar

        self.add_button = QPushButton(vi.ADD_BOOKS, self)
        self.add_button.setProperty("role", "primary")
        self.add_button.setMenu(add_menu)
        self.add_button.setToolTip(vi.ADD_BOOKS)
        self.tools_button = QPushButton(vi.TOOLS, self)
        self.tools_button.setMenu(tools_menu)
        self.tools_button.setToolTip(vi.TOOLS)
        self.detail_button = QToolButton(self)
        self.detail_button.setCheckable(True)
        self.detail_button.setToolTip(vi.TOGGLE_DETAIL)
        self.detail_button.setFixedSize(32, 30)
        self.detail_button.toggled.connect(self.detail_toggled)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(8)
        row.addWidget(self.add_button)
        omnibar.setMinimumWidth(160)
        row.addWidget(omnibar, stretch=1)
        row.addSpacing(8)
        row.addWidget(library_toolbar)
        row.addSpacing(8)
        row.addWidget(self.tools_button)
        row.addWidget(self.detail_button)
        # Ctrl+F jumps to the search box from anywhere in the window.
        self._find_shortcut = QShortcut("Ctrl+F", self)
        self._find_shortcut.setContext(Qt.WindowShortcut)
        self._find_shortcut.activated.connect(self._focus_search)
        self._compact = False
        self._apply_style()
        theme_manager().themeChanged.connect(self._apply_style)

    def _focus_search(self) -> None:
        self.omnibar.setFocus()
        self.omnibar.selectAll()

    def _apply_style(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(f"#AppToolbar {{ background: {tm.token('bg')}; border-bottom: 1px solid {tm.token('line')}; }}")
        self.add_button.setIcon(line_icon("plus", tm.token("accentink")))
        self.tools_button.setIcon(line_icon("tools", tm.token("ink2")))
        self.detail_button.setIcon(line_icon("panel", tm.token("ink2")))
        self.detail_button.setStyleSheet(
            f"QToolButton {{ border: 1px solid transparent; border-radius: 6px; background: transparent; }}"
            f" QToolButton:hover {{ border-color: {tm.token('line2')}; }}"
            f" QToolButton:checked {{ background: {tm.token('accentsoft')}; border-color: {tm.token('accent')}; }}"
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self.set_compact(self.width() < ICONS_ONLY_BELOW)

    @property
    def is_compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        self.add_button.setText("" if compact else vi.ADD_BOOKS)
        self.tools_button.setText("" if compact else vi.TOOLS)
        self.library_toolbar.set_compact(compact)
