"""TDD-010 upgrade: sort dropdown + cover-size slider, placed just below the
Omnibar inside the content area (not a native QMainWindow toolbar docked at
the very top -- the spec's "ngay dưới Omnibar" placement only makes sense as
a row inside the content layout).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSlider, QWidget

from smartdoc.core.event_bus import CoverSizeChangedEvent, SortChangedEvent
from smartdoc.presentation.library_view import DEFAULT_ICON_WIDTH, SORT_OPTIONS

COVER_SIZE_MIN = 100
COVER_SIZE_MAX = 300


class LibraryToolbar(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context

        self.sort_combo = QComboBox(self)
        self.sort_combo.addItems(list(SORT_OPTIONS.keys()))
        # `activated` (user interaction only), not `currentIndexChanged`
        # (also fires on programmatic changes) -- the initial selection
        # shown here must not itself publish a SortChangedEvent, or every
        # search would lose relevance ranking before the user touched
        # anything (see library_view.LibraryListWidget's _current_sort).
        self.sort_combo.activated.connect(self._on_sort_activated)

        self.size_slider = QSlider(Qt.Horizontal, self)
        self.size_slider.setRange(COVER_SIZE_MIN, COVER_SIZE_MAX)
        self.size_slider.setValue(DEFAULT_ICON_WIDTH)
        self.size_slider.valueChanged.connect(self._on_size_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.addWidget(QLabel("Sắp xếp:"))
        layout.addWidget(self.sort_combo)
        layout.addStretch(1)
        layout.addWidget(QLabel("Cỡ bìa:"))
        layout.addWidget(self.size_slider)

    def _on_sort_activated(self, index: int) -> None:
        key = list(SORT_OPTIONS.keys())[index]
        self.context.event_bus.publish(SortChangedEvent(order_by=SORT_OPTIONS[key]))

    def _on_size_changed(self, value: int) -> None:
        self.context.event_bus.publish(CoverSizeChangedEvent(size=value))


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.core.event_bus import CoverSizeChangedEvent, SortChangedEvent
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.event_bus.subscribe(SortChangedEvent, lambda e: print("SortChangedEvent:", e.order_by))
        context.event_bus.subscribe(CoverSizeChangedEvent, lambda e: print("CoverSizeChangedEvent:", e.size))

        app = QApplication(sys.argv)
        apply_light_theme(app)
        toolbar = LibraryToolbar(context)
        toolbar.resize(500, 40)
        toolbar.show()
        sys.exit(app.exec())
