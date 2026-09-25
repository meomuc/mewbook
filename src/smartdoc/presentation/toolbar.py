"""TDD-010 upgrade: view-mode toggle + sort dropdown + cover-size slider,
placed just below the Omnibar inside the content area (not a native
QMainWindow toolbar docked at the very top -- the spec's "ngay dưới
Omnibar" placement only makes sense as a row inside the content layout).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QToolButton,
    QWidget,
)

from smartdoc.application.cloud_reviews import CloudReviewError
from smartdoc.application.rating_sync import sync_all_rating_stats
from smartdoc.core.event_bus import CoverSizeChangedEvent, SortChangedEvent, ViewModeChangedEvent
from smartdoc.presentation.library_view import DEFAULT_ICON_WIDTH, HIGHEST_RATED_SORT_LABEL, SORT_OPTIONS
from smartdoc.presentation.line_icons import icon_pixmap, line_icon
from smartdoc.presentation.theme_manager import theme_manager

COVER_SIZE_MIN = 100
COVER_SIZE_MAX = 300


class LibraryToolbar(QWidget):
    _rating_sync_finished = Signal(str, str)  # (order_by, error_message)

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._rating_sync_finished.connect(self._on_rating_sync_finished)

        # "Lưới bìa | Bảng": one segmented switch, text + line icon (the text goes away when the window is narrow).
        self.grid_view_button = QToolButton(self)
        self.grid_view_button.setCheckable(True)
        self.grid_view_button.setText(" Lưới bìa")
        self.grid_view_button.setToolTip("Dạng lưới bìa")

        self.list_view_button = QToolButton(self)
        self.list_view_button.setCheckable(True)
        self.list_view_button.setText(" Bảng")
        self.list_view_button.setToolTip("Dạng bảng")

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

        self.sort_combo.setToolTip("Sắp xếp")
        self.sort_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.sort_combo.setMinimumContentsLength(11)  # the longest label ("Được đánh giá cao nhất") is elided
        self.sort_combo.setMinimumWidth(112)  # explicit, or the font's width decides how narrow the window may get
        self.grid_view_button.setMinimumWidth(96)
        self.list_view_button.setMinimumWidth(72)
        self.size_slider.setFixedWidth(72)
        self.size_slider.setToolTip("Cỡ bìa")
        self._small_icon = QLabel(self)
        self._large_icon = QLabel(self)
        self._size_label = self._small_icon  # kept for set_size_control_visible()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.grid_view_button)
        layout.addWidget(self.list_view_button)
        layout.addSpacing(16)
        layout.addWidget(self._small_icon)
        layout.addSpacing(4)
        layout.addWidget(self.size_slider)
        layout.addSpacing(4)
        layout.addWidget(self._large_icon)
        layout.addSpacing(16)
        layout.addWidget(self.sort_combo)
        self._apply_style()
        theme_manager().themeChanged.connect(self._apply_style)

    def _apply_style(self, _key: str = "") -> None:
        """Segmented switch + icons from the current theme's tokens (also re-run when the theme changes)."""
        tm = theme_manager()
        line, accent = tm.token("line2"), tm.token("accent")
        self.setStyleSheet(
            f"QToolButton {{ border: 1px solid {line}; background: {tm.token('surface')}; color: {tm.token('ink2')};"
            f" min-height: 28px; padding: 0 10px; font-size: 13px; }}"
            f" QToolButton:hover {{ color: {tm.token('ink')}; }}"
            f" QToolButton:checked {{ background: {tm.token('accentsoft')}; color: {tm.token('ink')}; font-weight: 600; }}"
            f" QToolButton:focus {{ border-color: {accent}; }}"
        )
        self.grid_view_button.setStyleSheet(
            "QToolButton { border-top-left-radius: 6px; border-bottom-left-radius: 6px; border-right: none; }")
        self.list_view_button.setStyleSheet(
            "QToolButton { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }")
        for button, name in ((self.grid_view_button, "grid"), (self.list_view_button, "table")):
            button.setIcon(line_icon(name, tm.token("ink2")))
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._small_icon.setPixmap(icon_pixmap("image", tm.token("ink3"), 12))
        self._large_icon.setPixmap(icon_pixmap("image", tm.token("ink3"), 16))

    def set_compact(self, compact: bool) -> None:
        """Icons only (tooltips carry the words) in a narrow window."""
        style = Qt.ToolButtonIconOnly if compact else Qt.ToolButtonTextBesideIcon
        self.grid_view_button.setToolButtonStyle(style)
        self.list_view_button.setToolButtonStyle(style)
        self.sort_combo.setMinimumWidth(88 if compact else 112)

    def set_size_control_visible(self, visible: bool) -> None:
        self._small_icon.setVisible(visible)
        self._large_icon.setVisible(visible)
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

        if not self.context.config.config.community_reviews_enabled:
            self.context.event_bus.publish(SortChangedEvent(order_by=order_by))  # switched off: sort by what is stored locally
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
