"""Pill-shaped format filter chips -- the "Kệ Sách Gỗ" theme's top bar.

Replaces a dropdown with chips that are all visible at once: with only a
handful of formats in a library, a dropdown hides every option but the
selected one behind a click, while chips show the whole choice set (and
each one's document count) at a glance.

The chips are built from the formats actually present in the library
(db.count_by_extension), not a hardcoded list -- a chip for a format the
user owns nothing in would just be a dead control.

Filtering itself goes through the shared FilterService (context.filters), the
same one the sidebar and the search box use, so chips, sidebar and library
view stay in sync automatically -- this widget adds another way to drive the
one filter, not a second filtering mechanism. A chip click means "show me
this" (it replaces that group's selection and leaves the other groups alone).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QWidget

from smartdoc.core.event_bus import FilterChangedEvent, LibraryUpdatedEvent
from smartdoc.domain.library_filter import COLLECTIONS, FORMATS, MODE_GO
from smartdoc.infrastructure.database import READING_LIST_ID, READING_LIST_NAME
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.theme import current_colors

BAR_HEIGHT = 40
_ALL_CHIP_LABEL = "Tất cả"
# Key of the reading-list chip in _chips (formats are keyed by extension,
# "Tất cả" by None).
READING_LIST_CHIP = "__reading_list__"


class FilterChipBar(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._chips: dict[str | None, QPushButton] = {}

        self.setFixedHeight(BAR_HEIGHT)
        colors = current_colors()
        self.setStyleSheet("FilterChipBar { background: transparent; }")
        del colors

        self._row = QHBoxLayout()
        self._row.setContentsMargins(4, 0, 4, 0)
        self._row.setSpacing(8)
        self._row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        chips_host = QWidget(self)
        chips_host.setLayout(self._row)

        # A library with many formats shouldn't push chips off the edge
        # where they can't be reached at all.
        scroll = QScrollArea(self)
        scroll.setWidget(chips_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("background: transparent;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._refresh_timer = debounced(self, self.refresh)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)

        self.refresh()

    @property
    def _active_extension(self) -> str | None:
        formats = self.context.filters.current.formats
        return formats[0].lower() if formats else None

    @property
    def _reading_list_active(self) -> bool:
        return READING_LIST_ID in self.context.filters.current.collections

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, FilterChangedEvent):
            self.refresh()
        else:
            self._refresh_timer.start()

    def refresh(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chips.clear()

        total = self.context.db.count_documents()
        nothing_filtered = self.context.filters.current.is_empty()
        self._add_chip(None, f"{_ALL_CHIP_LABEL}  {total:,}".replace(",", "."), total, active=nothing_filtered)
        reading = self.context.db.count_documents_in_collection(READING_LIST_ID)
        self._add_chip(READING_LIST_CHIP, f"★ {READING_LIST_NAME}", reading, active=self._reading_list_active)
        for extension, count in self.context.db.count_by_extension().items():
            if not extension:
                continue
            self._add_chip(extension, extension.upper(), count, active=extension == self._active_extension)
        self._row.addStretch(1)

    def _add_chip(self, key: str | None, label: str, count: int, *, active: bool) -> None:
        # Only "Tất cả" shows its count on the chip itself (as in the
        # mockup); the others keep it in the tooltip.
        chip = QPushButton(label, self)
        chip.setToolTip(f"{count:,} tài liệu")
        chip.setCursor(Qt.PointingHandCursor)
        chip.setCheckable(True)
        chip.setChecked(active)
        chip.setStyleSheet(self._chip_style(active))
        chip.clicked.connect(lambda _checked=False, value=key: self._on_chip_clicked(value))
        self._row.addWidget(chip)
        self._chips[key] = chip

    def _chip_style(self, active: bool) -> str:
        colors = current_colors()
        if active:
            return (
                f"QPushButton {{ background: {colors.accent}; color: {colors.accent_text};"
                " border: none; border-radius: 16px; padding: 7px 16px; font-weight: 600; }"
            )
        return (
            f"QPushButton {{ background: rgba(32,30,29,.08); color: {colors.muted_text};"
            " border: none; border-radius: 16px; padding: 7px 16px; }"
            f" QPushButton:hover {{ background: rgba(32,30,29,.13); color: {colors.sidebar_text}; }}"
        )

    def _on_chip_clicked(self, key: str | None) -> None:
        filters = self.context.filters
        if key is None:
            filters.clear()  # "Tất cả" means everything: no chip, no search text
        elif key == READING_LIST_CHIP:
            filters.select(COLLECTIONS, READING_LIST_ID, MODE_GO)
        else:
            # Clicking the active chip again clears it (MODE_GO on the only selected value).
            filters.select(FORMATS, key, MODE_GO)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        for i in range(5):
            context.db.add_or_update_document(
                f"d{i}",
                {
                    "title": f"Book {i}",
                    "author": "A",
                    "file_path": f"b{i}.pdf",
                    "extension": "pdf" if i % 2 == 0 else "epub",
                    "created_at": float(i),
                },
            )

        app = QApplication(sys.argv)
        apply_theme(app, "woodshelf")
        context.event_bus.subscribe(FilterChangedEvent, lambda e: print("filter ->", e.filter))
        bar = FilterChipBar(context)
        bar.resize(700, BAR_HEIGHT)
        bar.show()
        sys.exit(app.exec())
