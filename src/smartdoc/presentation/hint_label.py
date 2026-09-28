# SPDX-License-Identifier: AGPL-3.0-or-later
"""HintLabel: the shared widget for the "hướng dẫn" (guidance) text role -- see docs/UI_TEXT_ROLES.md.

Guidance text is static, secondary and can run long (write-into-file warnings, format notes, empty-state
explanations...). Shown in full it used to eat four or five lines of a dialog; this widget caps it at roughly two
lines and folds anything longer behind a "Xem hướng dẫn" / "Ẩn hướng dẫn" toggle instead, so no screen ever shows
more than two guidance lines at once (task A1's acceptance criteria). It is a drop-in replacement for a QLabel used
for this role: `HintLabel(text, parent)` where the old code did `QLabel(text, parent); .setWordWrap(True)`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from smartdoc.presentation.theme import ROLE_HINT, role_css
from smartdoc.presentation.theme_manager import theme_manager

# Rough character budget for two lines of hint-role text (12px) in a typical dialog body width. A heuristic, not a
# pixel measurement (the real width depends on the dialog and the font actually installed) -- collapsing a little
# early is harmless, since the toggle is one click away and never hides information, only defers it.
COLLAPSE_AT_CHARS = 160


class HintLabel(QWidget):
    """A guidance-role label. `color_token` is a ThemeManager token name (default "ink3", the muted-text token
    every theme package defines); like any other themed widget it restyles itself on theme change rather than
    fixing a color at construction time."""

    def __init__(self, text: str = "", parent: QWidget | None = None, *, color_token: str = "ink3") -> None:
        super().__init__(parent)
        self._color_token = color_token
        self._full_text = ""
        self._expanded = False

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.PlainText)
        self._toggle = QLabel(self)
        self._toggle.setTextFormat(Qt.RichText)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.setVisible(False)
        self._toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._toggle.linkActivated.connect(self._on_toggle_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._label)
        layout.addWidget(self._toggle)

        theme_manager().themeChanged.connect(self._restyle)
        self._restyle()
        self.set_text(text)

    # -- QLabel-compatible surface, so existing call sites need only change the constructor line -------------------
    def setWordWrap(self, on: bool) -> None:  # noqa: N802 -- Qt naming, kept for drop-in QLabel replacement
        self._label.setWordWrap(on)

    def text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802 -- Qt naming, kept for drop-in QLabel replacement
        self.set_text(text)

    # -- own API -----------------------------------------------------------------------------------------------
    def set_text(self, text: str) -> None:
        self._full_text = text
        self._expanded = False
        self._toggle.setVisible(len(text) > COLLAPSE_AT_CHARS)
        self._render()

    def is_expanded(self) -> bool:
        return self._expanded

    def _render(self) -> None:
        shown = (self._full_text if self._expanded or len(self._full_text) <= COLLAPSE_AT_CHARS
                 else self._full_text[:COLLAPSE_AT_CHARS].rstrip() + "…")
        self._label.setText(shown)
        self._toggle.setText('<a href="#">Ẩn hướng dẫn</a>' if self._expanded else '<a href="#">Xem hướng dẫn</a>')

    def _on_toggle_clicked(self, _href: str) -> None:
        self._expanded = not self._expanded
        self._render()

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self._label.setStyleSheet(role_css(ROLE_HINT, tm.token(self._color_token)))
        self._toggle.setStyleSheet(f"font-size: 12px; color: {tm.token('accent')};")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    theme_manager().apply(app, "broadsheet")
    demo = HintLabel(
        "MewBook không tự chọn bản nào để xóa: hãy xem từng nhóm và chọn bản giữ lại. “Bỏ khỏi thư viện”: file vẫn "
        "nằm trên máy. “Chuyển vào Thùng rác”: file vào thùng rác của MewBook, khôi phục được trước hạn."
    )
    demo.resize(360, 90)
    demo.show()
    app.exec()
