"""The "Đang lọc" bar: what the library is filtered by, right above the list.

Before this, the only way to learn why the list was short was to hunt through
the sidebar, and some filters (the detail panel's author link) weren't shown
there at all. This bar renders the shared LibraryFilter (core/filter_service.py)
as removable chips -- `Tác giả: Nhã Ca ✕` -- with how many documents remain, and
a "Xóa lọc" button that clears *everything*, search text included. It takes no
room when nothing is filtered.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from smartdoc.core.event_bus import FilterChangedEvent, LibraryUpdatedEvent
from smartdoc.domain.library_filter import CATEGORY_LABELS, QUERY, LibraryFilter, display_value
from smartdoc.presentation.flow_widget import FlowWidget
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.theme_manager import theme_manager

CLEAR_LABEL = "Xóa lọc"
SAVE_LABEL = "Lưu thành bộ sưu tập"


class ActiveFilterBar(QFrame):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.setObjectName("ActiveFilterBar")
        self.chip_buttons: list[QPushButton] = []  # the visible chips, in order
        self._chip_pool: list[QPushButton] = []

        self._flow = FlowWidget(self, h_spacing=6, v_spacing=6)

        self.count_label = QLabel(self)
        self.save_button = QPushButton(SAVE_LABEL, self)
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.setObjectName("BarAction")
        self.save_button.setToolTip("Tạo bộ sưu tập từ các điều kiện đang lọc; nó tự cập nhật khi thư viện thay đổi")
        self.save_button.clicked.connect(self._on_save_clicked)
        self.clear_button = QPushButton(CLEAR_LABEL, self)
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setObjectName("BarAction")
        self.clear_button.setToolTip("Bỏ mọi bộ lọc và ô tìm kiếm (phím Esc trong danh sách)")
        self.clear_button.clicked.connect(self.context.filters.clear)

        # "Đang lọc  31 / 7.545 tài liệu   [Loại  Giá trị ✕] ...        Xóa lọc  Lưu thành bộ sưu tập"
        self.title_label = QLabel("Đang lọc", self)
        self.title_label.setObjectName("FilterTitle")
        self.count_label.setObjectName("FilterCount")
        lead = QHBoxLayout()
        lead.setSpacing(8)
        lead.addWidget(self.title_label)
        lead.addWidget(self.count_label)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 8, 16, 8)
        outer.setSpacing(12)
        outer.addLayout(lead)
        outer.addWidget(self._flow, stretch=1)
        outer.addWidget(self.clear_button, alignment=Qt.AlignVCenter)
        outer.addWidget(self.save_button, alignment=Qt.AlignVCenter)

        self._apply_style()
        self._refresh_count_timer = debounced(self, self._update_count)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self.rebuild()

    def _apply_style(self) -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#ActiveFilterBar {{ background: {tm.token(tm.layout.content_surface)}; border-bottom: 1px solid {tm.token('line')}; }}"
            f" QLabel {{ color: {tm.token('ink2')}; background: transparent; font-size: 12px; }}"
            f" #FilterTitle {{ color: {tm.token('ink')}; font-size: 13px; font-weight: 600; }}"
            f" #FilterCount {{ color: {tm.token('ink2')}; font-size: 13px; }}"
            f" QPushButton#FilterChip {{ background: {tm.token('surface')}; color: {tm.token('ink')};"
            f" border: 1px solid {tm.token('line2')}; border-radius: 12px; padding: 0 10px; min-height: 22px; font-size: 12px; }}"
            f" QPushButton#FilterChip:hover {{ border-color: {tm.token('accent')}; }}"
            f" QPushButton#BarAction {{ background: transparent; color: {tm.token('accent')}; border: none;"
            f" text-decoration: underline; padding: 0 4px; min-height: 22px; font-size: 12px; }}"
            f" QPushButton#BarAction:hover {{ color: {tm.token('ink')}; }}"
        )

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, FilterChangedEvent):
            self.rebuild()
        else:
            self._refresh_count_timer.start()  # imports fire one of these per file

    def rebuild(self) -> None:
        flt = self.context.filters.current
        if flt.is_empty():
            self._show_chips([])
            self.hide()
            return

        names = {row["id"]: row["name"] for row in self.context.db.list_collections()}
        wanted: list[tuple[str, str, str]] = []
        for category, value in flt.chips():
            label = display_value(category, self.context.facets.label_for(category, value), names)
            wanted.append((f"{CATEGORY_LABELS[category]}: {label}", category, value))
        if flt.query:
            wanted.append((f"Tìm: “{flt.query}”", QUERY, flt.query))
        self._show_chips(wanted)
        self._update_count()
        self.save_button.setVisible(bool(flt.chips()))
        self.show()

    def _show_chips(self, wanted: list[tuple[str, str, str]]) -> None:
        """Puts `wanted` on the chips, making more when needed and only hiding the
        spare ones: chip widgets are reused, never deleted, so a rebuild can't
        leave the flow holding (or Qt deleting) a chip that is still referenced."""
        while len(self._chip_pool) < len(wanted):
            chip = QPushButton(self._flow)
            chip.setObjectName("FilterChip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip("Bỏ bộ lọc này")
            chip.clicked.connect(lambda _checked=False, c=chip: self._remove(c.property("category"), c.property("value")))
            self._chip_pool.append(chip)
        for chip, (text, category, value) in zip(self._chip_pool, wanted):
            chip.setText(f"{text}  ✕")
            chip.setProperty("category", category)
            chip.setProperty("value", value)
            chip.show()
        for chip in self._chip_pool[len(wanted):]:
            chip.hide()
        self.chip_buttons = self._chip_pool[: len(wanted)]
        self._flow.set_widgets(self.chip_buttons)

    def _remove(self, category: str, value: str) -> None:
        if category == QUERY:
            self.context.filters.set_query("")
        else:
            self.context.filters.remove(category, value)

    def _update_count(self) -> None:
        flt = self.context.filters.current
        shown = self.context.facets.total(flt)
        total = self.context.facets.library_total()
        self.count_label.setText(f"{shown:,} / {total:,} tài liệu".replace(",", "."))

    def _on_save_clicked(self) -> None:
        from smartdoc.presentation.save_filter_dialog import save_filter_as_collection

        save_filter_as_collection(self.context, self.context.filters.current, self)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "A", "author": "Nhã Ca", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
        )
        app = QApplication(sys.argv)
        apply_light_theme(app)
        bar = ActiveFilterBar(context)
        context.filters.set(LibraryFilter(authors=("Nhã Ca",), formats=("pdf",), query="sài gòn"))
        bar.resize(700, 60)
        bar.show()
        sys.exit(app.exec())
