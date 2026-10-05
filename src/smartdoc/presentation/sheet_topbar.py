# SPDX-License-Identifier: AGPL-3.0-or-later
"""The top bar of the sheet layout ("Tối giản"), inside the rounded sheet: logo and name on the left, four pill
destinations in the middle (Trang đầu, Thư viện, Sẽ đọc, Bộ sưu tập), and on the right "+ Thêm sách", the tools menu,
Settings and a "more" menu.

It only arranges controls and emits which destination was chosen; what a destination shows, and what the menus do, is
decided by the window that owns it (`sheet_window.SheetMainWindow`). Below `COMPACT_BELOW` px the "Bộ sưu tập" item folds
into the more menu and "Thêm sách" shortens to "Thêm", as the layout spec says."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QVBoxLayout

from smartdoc import APP_DISPLAY_NAME, APP_NAME
from smartdoc.presentation import strings as vi
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.resources import brand_logo_path
from smartdoc.presentation.theme_manager import theme_manager

HOME, LIBRARY, READING_LIST, COLLECTIONS = "home", "library", "reading_list", "collections"
DESTINATIONS = (
    (HOME, "Trang đầu", "book"),
    (LIBRARY, "Thư viện", "grid"),
    (READING_LIST, "Sẽ đọc", "star"),
    (COLLECTIONS, "Bộ sưu tập", "bolt"),
)
COMPACT_BELOW = 1100  # window width: "Bộ sưu tập" moves into the more menu, "Thêm sách" becomes "Thêm"


class SheetTopBar(QFrame):
    destination_chosen = Signal(str)
    settings_requested = Signal()

    def __init__(self, add_menu: QMenu, tools_menu: QMenu, more_menu: QMenu, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SheetTopBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(int(theme_manager().metric("topbar_height", 72)))
        self._compact = False

        logo = QLabel(self)
        pixmap = QPixmap(str(brand_logo_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(QSize(38, 38), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        name = QLabel(APP_NAME.upper(), self)
        name.setObjectName("SheetBrand")
        tagline = QLabel(APP_DISPLAY_NAME, self)
        tagline.setObjectName("SheetTagline")
        names = QVBoxLayout()
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(0)
        names.addWidget(name)
        names.addWidget(tagline)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, label, icon in DESTINATIONS:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, k=key: self.destination_chosen.emit(k))
            self._group.addButton(button)
            self.buttons[key] = button
            button.setProperty("icon_name", icon)
            button.toggled.connect(lambda _checked, b=button: self._recolor(b))

        self.add_button = QPushButton(vi.ADD_BOOKS, self)
        self.add_button.setProperty("role", "outline")
        self.add_button.setMenu(add_menu)
        self.add_button.setToolTip(vi.ADD_BOOKS)
        self.tools_button = self._icon_button("tools", vi.TOOLS, tools_menu)
        self.settings_button = self._icon_button("gear", vi.SETTINGS, None)
        self.settings_button.clicked.connect(self.settings_requested)
        self.more_button = self._icon_button(None, "Thêm tùy chọn", more_menu)
        self.more_button.setText("⋯")

        row = QHBoxLayout(self)
        row.setContentsMargins(34, 0, 22, 0)
        row.setSpacing(6)
        row.addWidget(logo)
        row.addSpacing(8)
        row.addLayout(names)
        row.addStretch(1)
        for button in self.buttons.values():
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.add_button)
        row.addSpacing(8)
        row.addWidget(self.tools_button)
        row.addWidget(self.settings_button)
        row.addWidget(self.more_button)
        self._apply_style()
        theme_manager().themeChanged.connect(self._apply_style)

    def _icon_button(self, icon: str | None, tooltip: str, menu: QMenu | None) -> QToolButton:
        button = QToolButton(self)
        button.setProperty("bar_icon", icon or "")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedSize(38, 38)
        if menu is not None:
            button.setMenu(menu)
            button.setPopupMode(QToolButton.InstantPopup)
        return button

    def set_destination(self, key: str) -> None:
        """Marks `key` as the open destination (no signal): the window calls this when it navigates by itself."""
        button = self.buttons.get(key)
        if button is not None:
            button.setChecked(True)
        else:  # a destination folded away in compact mode, or none of the four (e.g. a filtered library)
            checked = self._group.checkedButton()
            if checked is not None:
                self._group.setExclusive(False)
                checked.setChecked(False)
                self._group.setExclusive(True)

    def current_destination(self) -> str | None:
        for key, button in self.buttons.items():
            if button.isChecked():
                return key
        return None

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        self.buttons[COLLECTIONS].setVisible(not compact)
        self.add_button.setText("Thêm" if compact else vi.ADD_BOOKS)

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        window = self.window()
        self.set_compact((window.width() if window is not None else self.width()) < COMPACT_BELOW)

    def _apply_style(self, _key: str = "") -> None:
        tm = theme_manager()
        radius = int(min(int(tm.metric("control_radius", 6)), 19))
        self.setStyleSheet(
            f"#SheetTopBar {{ background: transparent; }}"
            f" #SheetBrand {{ color: {tm.token('ink')}; font-family: {tm.token('ui')}; font-size: 20px; font-weight: 800;"
            f" letter-spacing: 1px; background: transparent; }}"
            f" #SheetTagline {{ color: {tm.token('ink3')}; font-family: {tm.token('content')}; font-size: 12px;"
            f" font-style: italic; background: transparent; }}"
            f" QPushButton[nav=\"true\"] {{ background: transparent; color: {tm.token('ink2')}; border: none;"
            f" border-radius: {radius}px; min-height: 38px; padding: 0 20px; font-weight: 600; font-size: 14px; }}"
            f" QPushButton[nav=\"true\"]:hover {{ color: {tm.token('ink')}; background: {tm.token('surface2')}; }}"
            f" QPushButton[nav=\"true\"]:checked {{ background: {tm.token('accent')}; color: {tm.token('accentink')}; }}"
            f" QPushButton[role=\"outline\"] {{ background: transparent; color: {tm.token('ink')};"
            f" border: 1px solid {tm.token('line2')}; border-radius: {radius}px; min-height: 38px; padding: 0 20px;"
            f" font-weight: 600; }}"
            f" QPushButton[role=\"outline\"]:hover {{ border-color: {tm.token('accent')}; }}"
            f" QPushButton[role=\"outline\"]::menu-indicator {{ image: none; width: 0; }}"
            f" QToolButton {{ background: transparent; color: {tm.token('ink2')}; border: none; border-radius: 19px;"
            f" font-size: 18px; font-weight: 700; }}"
            f" QToolButton:hover {{ background: {tm.token('surface2')}; }}"
            f" QToolButton::menu-indicator {{ image: none; width: 0; }}"
        )
        for key, button in self.buttons.items():
            icon = str(button.property("icon_name"))
            button.setIcon(line_icon(icon, tm.token("accentink") if button.isChecked() else tm.token("ink2"), 15))
        self.add_button.setIcon(line_icon("plus", tm.token("ink"), 14))
        for button in (self.tools_button, self.settings_button):
            name = str(button.property("bar_icon"))
            if name:
                button.setIcon(line_icon(name, tm.token("ink2"), 18))

    def _recolor(self, button: QPushButton) -> None:
        tm = theme_manager()
        button.setIcon(line_icon(str(button.property("icon_name")),
                                 tm.token("accentink") if button.isChecked() else tm.token("ink2"), 15))
