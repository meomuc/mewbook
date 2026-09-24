"""TDD-010 upgrade: view-mode toggle + sort dropdown + cover-size slider,
placed just below the Omnibar inside the content area (not a native
QMainWindow toolbar docked at the very top -- the spec's "ngay dưới
Omnibar" placement only makes sense as a row inside the content layout).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QStyle,
    QToolButton,
    QWidget,
)

from smartdoc.application.cloud_reviews import CloudReviewError
from smartdoc.application.rating_sync import sync_all_rating_stats
from smartdoc.core.event_bus import CoverSizeChangedEvent, SortChangedEvent, ViewModeChangedEvent
from smartdoc.presentation.library_view import DEFAULT_ICON_WIDTH, HIGHEST_RATED_SORT_LABEL, SORT_OPTIONS
from smartdoc.presentation.theme import current_colors

COVER_SIZE_MIN = 100
COVER_SIZE_MAX = 300


class LibraryToolbar(QWidget):
    _rating_sync_finished = Signal(str, str)  # (order_by, error_message)

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._rating_sync_finished.connect(self._on_rating_sync_finished)

        self.grid_view_button = QToolButton(self)
        self.grid_view_button.setCheckable(True)
        self.grid_view_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogListView))
        self.grid_view_button.setIconSize(QSize(18, 18))
        self.grid_view_button.setToolTip("Dạng lưới (Grid)")

        self.list_view_button = QToolButton(self)
        self.list_view_button.setCheckable(True)
        self.list_view_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.list_view_button.setIconSize(QSize(18, 18))
        self.list_view_button.setToolTip("Dạng danh sách (List)")

        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.setExclusive(True)
        self._view_mode_group.addButton(self.grid_view_button)
        self._view_mode_group.addButton(self.list_view_button)

        is_list_mode = context.config.config.view_mode == "list"
        self.grid_view_button.setChecked(not is_list_mode)
        self.list_view_button.setChecked(is_list_mode)
        self.grid_view_button.clicked.connect(lambda: self._on_view_mode_clicked("grid"))
        self.list_view_button.clicked.connect(lambda: self._on_view_mode_clicked("list"))

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

        # Lives at the right end of the main window's header bar (see
        # MainWindow._build_header_bar): compact, no stretch of its own.
        colors = current_colors()
        for button in (self.grid_view_button, self.list_view_button):
            button.setAutoRaise(True)
            button.setFixedSize(32, 30)
        self.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 3px; background: transparent; }}"
            f" QToolButton:checked {{ background: {colors.selected_bg}; }}"
            f" QToolButton:hover {{ background: {colors.border}; }}"
            f" QComboBox {{ background: {colors.surface}; color: {colors.sidebar_text};"
            f" border: 1px solid {colors.border}; border-radius: 3px; padding: 5px 10px; min-width: 150px; }}"
            f" QComboBox::drop-down {{ border: none; width: 20px; }}"
        )
        self.sort_combo.setToolTip("Sắp xếp")
        self.size_slider.setFixedWidth(110)
        self.size_slider.setToolTip("Cỡ bìa")
        size_label = QLabel("Cỡ bìa", self)
        size_label.setStyleSheet(f"color: {colors.muted_text};")
        self._size_label = size_label

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.grid_view_button)
        layout.addWidget(self.list_view_button)
        layout.addSpacing(14)
        layout.addWidget(self.sort_combo)
        layout.addSpacing(14)
        layout.addWidget(size_label)
        layout.addWidget(self.size_slider)

    def set_size_control_visible(self, visible: bool) -> None:
        self._size_label.setVisible(visible)
        self.size_slider.setVisible(visible)

    def _on_view_mode_clicked(self, mode: str) -> None:
        self.context.config.config.view_mode = mode
        self.context.config.save()
        self.context.event_bus.publish(ViewModeChangedEvent(mode=mode))

    def _on_sort_activated(self, index: int) -> None:
        key = list(SORT_OPTIONS.keys())[index]
        order_by = SORT_OPTIONS[key]
        if key != HIGHEST_RATED_SORT_LABEL:
            self.context.event_bus.publish(SortChangedEvent(order_by=order_by))
            return

        # Only this one sort option ever touches the network -- every other
        # sort works purely off the local index (see rating_sync.py).
        self.sort_combo.setEnabled(False)
        self.setToolTip("Đang đồng bộ đánh giá từ Supabase...")

        def worker() -> None:
            try:
                sync_all_rating_stats(self.context)
                self._rating_sync_finished.emit(order_by, "")
            except CloudReviewError as exc:
                self._rating_sync_finished.emit(order_by, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_rating_sync_finished(self, order_by: str, error: str) -> None:
        self.sort_combo.setEnabled(True)
        self.setToolTip("")
        if error:
            QMessageBox.warning(self, "Chưa lấy được điểm đánh giá", error)
            return
        self.context.event_bus.publish(SortChangedEvent(order_by=order_by))

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
