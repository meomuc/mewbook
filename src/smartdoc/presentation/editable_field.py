# SPDX-License-Identifier: AGPL-3.0-or-later
"""A field you can change in place, drawn so it cannot be mistaken for a read-only line.

Design rule ("Ô sửa được"): an editable field is *not* told apart by colour alone -- it has a dashed 1 px outline, a pen
icon and a surface fill; while you type the outline turns solid accent with a 3 px soft halo. A read-only line has
no outline and no icon. The frame paints all of that itself (QSS cannot draw a dashed rounded outline plus a halo), and
wraps a plain QLineEdit, so callers keep using `field.edit` (text, editingFinished, ...).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit

from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

HALO = 3  # px of soft ring around a field being edited


class EditableField(QFrame):
    def __init__(self, edit: QLineEdit, parent=None) -> None:
        super().__init__(parent)
        self.edit = edit
        edit.setParent(self)
        edit.setFrame(False)
        edit.setStyleSheet("QLineEdit { background: transparent; border: none; padding: 0; }")
        edit.installEventFilter(self)
        self._pen_action = edit.addAction(line_icon("pen", theme_manager().token("ink3"), 14), QLineEdit.TrailingPosition)
        self._pen_action.setToolTip("Bấm vào ô để sửa")
        self.setProperty("editable", True)
        self.setAttribute(Qt.WA_Hover, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(HALO + 8, HALO + 5, HALO + 8, HALO + 5)
        layout.addWidget(edit)
        self._hovered = False

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 -- Qt override
        if watched is self.edit and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self.update()
        return False

    def enterEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self.edit.setFocus()  # a click on the padding edits too
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(HALO + 0.5, HALO + 0.5, -(HALO + 0.5), -(HALO + 0.5))
        editing = self.edit.hasFocus()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tm.token("surface")))
        painter.drawRoundedRect(box, 6, 6)
        painter.setBrush(Qt.NoBrush)
        if editing:
            halo = QPen(QColor(tm.token("accentsoft")), HALO)
            painter.setPen(halo)
            painter.drawRoundedRect(box.adjusted(-HALO / 2, -HALO / 2, HALO / 2, HALO / 2), 7, 7)
            painter.setPen(QPen(QColor(tm.token("accent")), 1))
        else:
            pen = QPen(QColor(tm.token("ink3") if self._hovered else tm.token("line2")), 1, Qt.DashLine)
            painter.setPen(pen)
        painter.drawRoundedRect(box, 6, 6)
        painter.end()
