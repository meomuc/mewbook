# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hashtags of one book as removable chips in a dashed (editable) frame, with a "+ thêm" that becomes a text box.

A chip has two parts: the tag (click = show every book with it) and a "×" (remove it). Typing in the box and pressing
Enter (or a comma) adds one or several tags -- "Python, AI" adds two. The widget never touches the database: it
reports the whole new list through `changed` (as the comma-joined text the library stores) and the panel saves it.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget

from smartdoc.presentation.editable_field import HALO
from smartdoc.presentation.flow_widget import FlowWidget
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager


def _clean(tag: str) -> str:
    return tag.strip().lstrip("#").strip()


class _Chip(QFrame):
    clicked = Signal(str)
    removed = Signal(str)

    def __init__(self, tag: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.tag = tag
        self.setObjectName("TagChip")
        self.label = QPushButton(f"#{tag}", self)
        self.label.setFlat(True)
        self.label.setCursor(Qt.PointingHandCursor)
        self.label.setToolTip(f"Xem các tài liệu có #{tag}")
        self.label.clicked.connect(lambda: self.clicked.emit(self.tag))
        self.remove_button = QToolButton(self)
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setToolTip(f"Bỏ #{tag} khỏi sách này")
        self.remove_button.clicked.connect(lambda: self.removed.emit(self.tag))
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 4, 0)
        row.setSpacing(2)
        row.addWidget(self.label)
        row.addWidget(self.remove_button)
        self.restyle()

    def restyle(self) -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#TagChip {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')}; border-radius: 11px; }}"
            f" QPushButton {{ border: none; background: transparent; color: {tm.token('ink')}; font-size: 12px;"
            f" font-weight: 600; min-height: 20px; padding: 0; }}"
            f" QToolButton {{ border: none; background: transparent; }}"
        )
        self.remove_button.setIcon(line_icon("close", tm.token("ink3"), 10))


class TagEditor(QFrame):
    changed = Signal(str)  # the new tags, comma-joined
    tag_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        self._chips: list[_Chip] = []
        self.setProperty("editable", True)
        self.setAttribute(Qt.WA_Hover, True)
        self._hovered = False

        self._flow = FlowWidget(self, h_spacing=6, v_spacing=6)
        self.add_button = QPushButton("+ thêm", self._flow)
        self.add_button.setFlat(True)
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.setToolTip("Thêm hashtag")
        self.add_button.clicked.connect(self._start_adding)
        self.line_edit = QLineEdit(self._flow)
        self.line_edit.setPlaceholderText("Gõ hashtag, Enter để thêm")
        self.line_edit.setMinimumWidth(150)
        self.line_edit.hide()
        self.line_edit.returnPressed.connect(self._commit)
        self.line_edit.editingFinished.connect(self._finish_adding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(HALO + 8, HALO + 8, HALO + 8, HALO + 8)
        layout.addWidget(self._flow)
        self._restyle()
        theme_manager().themeChanged.connect(self._restyle)
        self._rebuild()

    # -- state -------------------------------------------------------------------------------------------------------
    def set_tags(self, tags: list[str]) -> None:
        self._tags = [t for t in (_clean(t) for t in tags) if t]
        self._rebuild()

    def tags(self) -> list[str]:
        return list(self._tags)

    def _rebuild(self) -> None:
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips = []
        for tag in self._tags:
            chip = _Chip(tag, self._flow)
            chip.clicked.connect(self.tag_clicked)
            chip.removed.connect(self._remove)
            chip.show()
            self._chips.append(chip)
        adder = self.line_edit if not self.line_edit.isHidden() else self.add_button
        self.add_button.setVisible(self.line_edit.isHidden())
        self._flow.set_widgets([*self._chips, adder])

    def _remove(self, tag: str) -> None:
        self._tags = [t for t in self._tags if t != tag]
        self._rebuild()
        self.changed.emit(",".join(self._tags))

    def _start_adding(self) -> None:
        self.add_button.hide()
        self.line_edit.show()
        self.line_edit.setFocus()
        self._flow.set_widgets([*self._chips, self.line_edit])

    def _commit(self) -> None:
        added = [t for t in (_clean(part) for part in self.line_edit.text().split(",")) if t]
        self.line_edit.clear()
        known = {t.casefold() for t in self._tags}
        new = []
        for tag in added:
            if tag.casefold() not in known:
                known.add(tag.casefold())
                new.append(tag)
        if new:
            self._tags.extend(new)
            self._rebuild()
            self._start_adding()  # stay open for the next one
            self.changed.emit(",".join(self._tags))

    def _finish_adding(self) -> None:
        if self.line_edit.text().strip():
            return  # Enter was pressed with text: _commit handles it
        if not self.line_edit.isHidden() and not self.line_edit.hasFocus():
            self.line_edit.hide()
            self._rebuild()

    # -- look ----------------------------------------------------------------------------------------------------------
    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self.add_button.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {tm.token('ink3')}; font-size: 12px;"
            f" min-height: 22px; padding: 0 4px; text-align: left; }}"
            f" QPushButton:hover {{ color: {tm.token('accent')}; }}")
        self.line_edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {tm.token('accent')}; border-radius: 11px; background: {tm.token('surface')};"
            f" padding: 0 8px; min-height: 22px; font-size: 12px; }}")
        for chip in self._chips:
            chip.restyle()
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(HALO + 0.5, HALO + 0.5, -(HALO + 0.5), -(HALO + 0.5))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tm.token("surface")))
        painter.drawRoundedRect(box, 6, 6)
        painter.setBrush(Qt.NoBrush)
        editing = not self.line_edit.isHidden()
        if editing:
            painter.setPen(QPen(QColor(tm.token("accentsoft")), HALO))
            painter.drawRoundedRect(box.adjusted(-HALO / 2, -HALO / 2, HALO / 2, HALO / 2), 7, 7)
            painter.setPen(QPen(QColor(tm.token("accent")), 1))
        else:
            painter.setPen(QPen(QColor(tm.token("ink3") if self._hovered else tm.token("line2")), 1, Qt.DashLine))
        painter.drawRoundedRect(box, 6, 6)
        painter.end()
