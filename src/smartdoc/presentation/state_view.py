# SPDX-License-Identifier: AGPL-3.0-or-later
"""The empty / waiting / nothing-found / error states of the "Kệ sách" design (stage G11).

Shown in the *middle* of the content area, never as a pop-up: the mascot picture for the situation, a title that says
what is going on, one sentence about what to do, and at most two buttons. The picture is chosen by role from the
project's own artwork (`brand.py`); a missing picture just means no picture, never a broken screen.

    logo      -> the library is empty ("thả sách vào")
    searching -> looking for something
    thinking  -> nothing matches the filter (button: "Xóa bộ lọc")
    waiting   -> waiting for a server or the network
    done      -> finished
    sad       -> something went wrong (says which file, suggests "Tìm lại file")
    dev       -> the AI is writing a summary
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.brand import accessible_name, mascot_pixmap
from smartdoc.presentation.theme_manager import theme_manager

MASCOT_HEIGHT = 150
MAX_BUTTONS = 2


class StateView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StateView")
        self.role = ""
        self.mascot_label = QLabel(self)
        self.mascot_label.setAlignment(Qt.AlignCenter)
        self.title_label = QLabel("", self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.text_label = QLabel("", self)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setWordWrap(True)
        self.buttons: list[QPushButton] = []
        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(10)
        self._button_row.setAlignment(Qt.AlignCenter)
        column = QVBoxLayout(self)
        column.setAlignment(Qt.AlignCenter)
        column.setSpacing(8)
        column.addStretch(1)
        column.addWidget(self.mascot_label)
        column.addSpacing(6)
        column.addWidget(self.title_label)
        column.addWidget(self.text_label)
        column.addSpacing(10)
        column.addLayout(self._button_row)
        column.addStretch(1)
        self._restyle()
        theme_manager().themeChanged.connect(self._restyle)

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self.title_label.setStyleSheet(f"font-family: {tm.token('content')}; font-size: 20px; font-weight: 600;"
                                       f" color: {tm.token('ink')};")
        self.text_label.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 14px;")
        self.text_label.setMaximumWidth(460)
        self.title_label.setMaximumWidth(520)

    def set_state(self, role: str, title: str, text: str = "",
                  buttons: list[tuple[str, Callable[[], None], bool]] | None = None) -> None:
        """`buttons` is up to two `(label, callback, primary)`; the mascot is the artwork of `role`."""
        self.role = role
        pixmap = mascot_pixmap(role, MASCOT_HEIGHT, self.devicePixelRatioF())
        self.mascot_label.setVisible(pixmap is not None)
        if pixmap is not None:
            self.mascot_label.setPixmap(pixmap)
            self.mascot_label.setAccessibleName(accessible_name(role))
        self.title_label.setText(title)
        self.text_label.setText(text)
        self.text_label.setVisible(bool(text))
        for button in self.buttons:
            self._button_row.removeWidget(button)
            button.hide()
            button.deleteLater()
        self.buttons = []
        for label, callback, primary in (buttons or [])[:MAX_BUTTONS]:
            button = QPushButton(label, self)
            if primary:
                button.setProperty("role", "primary")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(callback)
            self._button_row.addWidget(button)
            self.buttons.append(button)

    # -- the standard situations -------------------------------------------------------------------------------------
    def show_empty_library(self, on_add_files: Callable[[], None], on_add_folder: Callable[[], None]) -> None:
        self.set_state("logo", vi.STATE_EMPTY_TITLE, vi.STATE_EMPTY_TEXT,
                       [(vi.ADD_BOOKS, on_add_files, True), (vi.ADD_FOLDER, on_add_folder, False)])

    def show_no_match(self, on_clear_filter: Callable[[], None]) -> None:
        self.set_state("thinking", vi.STATE_NO_MATCH_TITLE, vi.STATE_NO_MATCH_TEXT, [(vi.CLEAR_FILTER, on_clear_filter, True)])

    def show_searching(self) -> None:
        self.set_state("searching", vi.STATE_SEARCHING_TITLE, vi.STATE_SEARCHING_TEXT)

    def show_waiting(self, what: str = "") -> None:
        self.set_state("waiting", vi.STATE_WAITING_TITLE, what or vi.STATE_WAITING_TEXT)

    def show_done(self, title: str, text: str = "") -> None:
        self.set_state("done", title, text)

    def show_error(self, title: str, text: str, buttons: list[tuple[str, Callable[[], None], bool]] | None = None) -> None:
        self.set_state("sad", title, text, buttons)

    def show_ai_writing(self) -> None:
        self.set_state("dev", vi.STATE_AI_TITLE, vi.STATE_AI_TEXT)
