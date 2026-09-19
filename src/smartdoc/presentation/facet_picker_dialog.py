""""Xem tất cả": every author (or hashtag) in one searchable list.

The sidebar shows only the top few of a group with thousands of values; this is
the way to reach the rest. Typing filters the list (case- and accent-blind, so
"nha ca" finds "Nhã Ca"); a click switches the filter to that value and closes,
Ctrl/Shift+click adds it and keeps the list open for picking several.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from smartdoc.domain.author_names import search_key
from smartdoc.domain.library_filter import AUTHORS, CATEGORY_LABELS, MODE_GO, MODE_TOGGLE
from smartdoc.presentation.sidebar_style import CountRowDelegate
from smartdoc.presentation.theme import current_colors

_VALUE_ROLE = Qt.UserRole + 1
# A 3,000-row QListWidget scrolls fine, but typing re-filters it per keystroke; this keeps that instant.
_MAX_ROWS = 400


class FacetPickerDialog(QDialog):
    def __init__(self, context, category: str, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.category = category
        noun = "tác giả" if category == AUTHORS else "hashtag"
        self.setWindowTitle(f"Chọn {noun}")
        self.resize(380, 520)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(f"Gõ để tìm {noun}…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._fill)

        self.list = QListWidget(self)
        self.list.setItemDelegate(CountRowDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.itemClicked.connect(self._on_clicked)

        self.info_label = QLabel(self)
        self.info_label.setStyleSheet(f"color: {current_colors().muted_text};")
        hint = QLabel("Nhấp: chuyển tới · Ctrl+nhấp: chọn thêm", self)
        hint.setStyleSheet(f"color: {current_colors().muted_text}; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list, stretch=1)
        layout.addWidget(self.info_label)
        layout.addWidget(hint)

        self._choices = self.context.facets.counts(category, self.context.filters.current, keep_selected=True)
        self._haystacks = [search_key(choice.label) for choice in self._choices]
        self._fill()
        self.search_edit.setFocus()

    def _fill(self) -> None:
        needle = search_key(self.search_edit.text())
        flt = self.context.filters.current
        brush = QBrush(QColor(current_colors().selected_bg))
        self.list.clear()
        matched = 0
        for choice, haystack in zip(self._choices, self._haystacks):
            if needle and needle not in haystack:
                continue
            matched += 1
            if self.list.count() >= _MAX_ROWS:
                continue
            item = QListWidgetItem(f"{choice.label} ({choice.count})")
            item.setData(_VALUE_ROLE, choice.value)
            if flt.has_value(self.category, choice.value):
                item.setBackground(brush)
            self.list.addItem(item)
        shown = self.list.count()
        more = f" — hiện {shown:,}, gõ thêm để thu hẹp".replace(",", ".") if matched > shown else ""
        self.info_label.setText(f"{matched:,} kết quả{more}".replace(",", "."))

    def _additive_click(self) -> bool:
        return bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier))

    def _on_clicked(self, item: QListWidgetItem) -> None:
        value = item.data(_VALUE_ROLE)
        additive = self._additive_click()
        self.context.filters.select(self.category, value, MODE_TOGGLE if additive else MODE_GO)
        if additive:
            self._fill()  # stay open, with the new selection highlighted
        else:
            self.accept()
