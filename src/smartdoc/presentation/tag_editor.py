# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hashtags of one book as removable chips in a dashed (editable) frame, with a "+ thêm" that becomes a text box.

A chip has two parts: the tag (click = show every book with it) and a "×" (remove it). Typing in the box and pressing
Enter (or a comma) adds one or several tags -- "Python, AI" adds two. The widget never touches the database: it
reports the whole new list through `changed` (as the comma-joined text the library stores) and the panel saves it.

Hashtag hints: from two typed characters on, the hashtags that already exist in the library and match what is being
typed (ignoring case and accents; those that start with it first) are offered in a small list under the box, never
including one the book already has. Picking one -- click, or Down + Enter -- fills the box with it, so the whole word
need not be typed; Enter then adds it like anything typed. The list never takes the keyboard focus.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.duplicate_finder import normalize

from smartdoc.presentation.editable_field import HALO
from smartdoc.presentation.flow_widget import FlowWidget
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager


MIN_HINT_CHARS = 2  # hints start from this many typed characters
MAX_HINTS = 6


def _clean(tag: str) -> str:
    return tag.strip().lstrip("#").strip()


def current_segment(text: str) -> str:
    """The hashtag being typed: what follows the last comma, without a leading #."""
    return _clean(text.rsplit(",", 1)[-1])


def suggest_tags(typed: str, known: dict[str, int], already: Iterable[str], limit: int = MAX_HINTS) -> list[str]:
    """The library hashtags to offer for the text being typed (`known`: tag -> number of books).

    Nothing below MIN_HINT_CHARS characters. A tag matches when it contains what was typed, ignoring case and accents
    ("van hoc" finds "văn-học"); those that start with it come first, then the more used ones. A tag the book already has
    is never offered."""
    fragment = normalize(current_segment(typed))
    if len(fragment.replace(" ", "")) < MIN_HINT_CHARS:
        return []
    have = {normalize(tag) for tag in already}
    starts: list[tuple[int, str]] = []
    inside: list[tuple[int, str]] = []
    for tag, count in known.items():
        folded = normalize(tag)
        if not folded or folded in have or fragment not in folded:
            continue
        (starts if folded.startswith(fragment) else inside).append((-count, tag))
    ranked = sorted(starts) + sorted(inside)
    return [tag for _count, tag in ranked[:limit]]


class _HintPopup(QListWidget):
    """The list of hints under the text box. A tool window that never takes focus, so typing goes on uninterrupted."""

    def __init__(self, anchor: QWidget) -> None:
        super().__init__(anchor.window())
        self._anchor = anchor
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.restyle()

    def restyle(self) -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"QListWidget {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')}; border-radius: 6px;"
            f" color: {tm.token('ink')}; font-size: 12px; }}"
            f" QListWidget::item {{ padding: 3px 10px; }}"
            f" QListWidget::item:selected {{ background: {tm.token('accentsoft')}; color: {tm.token('ink')}; }}")

    def show_hints(self, tags: list[str]) -> None:
        self.clear()
        for tag in tags:
            self.addItem(QListWidgetItem(f"#{tag}"))
        if not tags:
            self.hide()
            return
        row_height = self.sizeHintForRow(0) or 24
        self.setFixedSize(max(self._anchor.width(), 180), row_height * len(tags) + 4)
        # This popup is a top-level window (Qt.ToolTip): move() takes SCREEN coordinates, never coordinates relative to
        # a parent widget. mapTo(parentWidget(), ...) gave a position inside the main window's own coordinate space,
        # which move() then read as a screen position -- the list showed up wherever the main window's top-left corner
        # happened to be offset to, nowhere near the box that was actually typed into.
        self.move(self._anchor.mapToGlobal(QPoint(0, self._anchor.height() + 2)))
        self.show()
        self.raise_()

    def move_selection(self, delta: int) -> None:
        row = self.currentRow()
        self.setCurrentRow(max(0, min(self.count() - 1, row + delta)) if row >= 0 else (0 if delta > 0 else self.count() - 1))

    def chosen(self) -> str:
        item = self.currentItem()
        return item.text().lstrip("#") if item is not None and self.isVisible() else ""


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
        self._known_source: Callable[[], dict[str, int]] | None = None
        self._known: dict[str, int] = {}
        self._popup: _HintPopup | None = None
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
        self.line_edit.textEdited.connect(self._update_hints)
        self.line_edit.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(HALO + 8, HALO + 8, HALO + 8, HALO + 8)
        layout.addWidget(self._flow)
        self._restyle()
        theme_manager().themeChanged.connect(self._restyle)
        self._rebuild()

    # -- hashtag hints -----------------------------------------------------------------------------------------------
    def set_known_tags_source(self, source: Callable[[], dict[str, int]]) -> None:
        """Where the library's existing hashtags (tag -> books) come from; asked when the box opens, not per keystroke."""
        self._known_source = source

    def _hint_popup(self) -> _HintPopup:
        if self._popup is None:
            self._popup = _HintPopup(self.line_edit)
            # A mouse click should immediately add the tag (fill + commit in one gesture).
            self._popup.itemClicked.connect(lambda _item: self._fill_from_hint(commit=True))
        return self._popup

    def _update_hints(self, text: str) -> None:
        hints = suggest_tags(text, self._known, self._tags)
        if hints:
            self._hint_popup().show_hints(hints)
        elif self._popup is not None:
            self._popup.hide()

    def _hide_hints(self) -> None:
        if self._popup is not None:
            self._popup.hide()

    def _fill_from_hint(self, *, commit: bool = False) -> None:
        tag = self._popup.chosen() if self._popup is not None else ""
        if not tag:
            return
        head = self.line_edit.text().rsplit(",", 1)[0] + ", " if "," in self.line_edit.text() else ""
        self.line_edit.setText(head + tag)
        self._hide_hints()
        self.line_edit.setFocus()
        self.line_edit.setCursorPosition(len(self.line_edit.text()))
        if commit:
            self._commit()  # mouse click: add immediately, no extra Enter needed

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 -- Qt override
        """Down/Up move through the hints, Enter takes the highlighted one, Esc closes the list -- while it is showing."""
        if watched is self.line_edit and event.type() == QEvent.KeyPress and self._popup is not None and self._popup.isVisible():
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self._popup.move_selection(1 if key == Qt.Key_Down else -1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter) and self._popup.chosen():
                self._fill_from_hint()
                return True
            if key == Qt.Key_Escape:
                self._hide_hints()
                return True
        return super().eventFilter(watched, event)

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
        if self._known_source is not None:
            self._known = self._known_source()
        self._hide_hints()
        self.add_button.hide()
        self.line_edit.show()
        self.line_edit.setFocus()
        self._flow.set_widgets([*self._chips, self.line_edit])

    def _commit(self) -> None:
        self._hide_hints()
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
        self._hide_hints()
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
        if self._popup is not None:
            self._popup.restyle()
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
