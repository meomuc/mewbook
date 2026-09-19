"""Bottom status bar: at-a-glance library/collection/connection status.

Built as a real QStatusBar (QMainWindow.setStatusBar) rather than a plain
widget docked at the bottom, so it gets the OS-native "thin bar, small
text" treatment for free. Refreshes on LibraryUpdatedEvent and
FilterChangedEvent -- the same two events the library view itself
reacts to, so the counts here never lag behind what's on screen.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QStatusBar

from smartdoc import APP_DISPLAY_NAME, APP_NAME, APP_PUBLISHER
from smartdoc.core.event_bus import FilterChangedEvent, LibraryFilesMissingEvent, LibraryUpdatedEvent
from smartdoc.presentation.donate_dialog import DonateDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.theme import current_colors

# Same green/crimson pair settings_dialog.py's connection test uses -- one
# consistent "connected vs. not" color language across the app instead of
# each status indicator inventing its own.
_STATUS_OK_COLOR = "green"
_STATUS_MISSING_COLOR = "crimson"


class _MissingFilesLabel(QLabel):
    """"N sách không tìm thấy file. Tìm lại?" -- shown only while some books have lost their file; a click asks
    the main window to open the relink dialog."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _DonateTicker(QLabel):
    """A small scrolling ticker calling out the donate popup -- a static
    label here would be easy to lose among the other status bar items, so
    the text instead scrolls through a fixed-width window on a timer, like
    a classic marquee, to actually catch the eye. Click opens DonateDialog.
    """

    clicked = Signal()

    _MESSAGE = "☕☕ Tác giả là một con nghiện cà phê và mê sách! Nếu bạn thấy ứng dụng này hữu ích, hãy mời tác giả một ly cà phê☕☕"
    _GAP = "    •    "
    _WINDOW_CHARS = 42
    _TICK_MS = 220

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loop_text = self._MESSAGE + self._GAP
        self._offset = 0
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Ủng hộ tác giả một ly cà phê ☕ (bấm để xem mã QR)")
        colors = current_colors()
        self.setStyleSheet(f"color: {colors.accent}; font-weight: 600;")
        self.setFixedWidth(self.fontMetrics().averageCharWidth() * self._WINDOW_CHARS)

        self._timer = QTimer(self)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _tick(self) -> None:
        doubled = self._loop_text * 2
        self.setText(doubled[self._offset : self._offset + self._WINDOW_CHARS])
        self._offset = (self._offset + 1) % len(self._loop_text)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        self.clicked.emit()
        super().mousePressEvent(event)


class StatusBarPanel(QStatusBar):
    relink_requested = Signal()  # the "N sách không tìm thấy file. Tìm lại?" label was clicked

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._active_collection_ids: tuple[str, ...] = ()

        colors = current_colors()
        # A top border so the bar reads as its own strip, separated from
        # whatever's directly above it (library view or detail panel) --
        # QStatusBar spans the full window width, under both.
        self.setStyleSheet(f"QStatusBar {{ border-top: 1px solid {colors.border}; }}")

        self.files_label = QLabel(self)
        self.collection_label = QLabel(self)
        self.folders_label = QLabel(self)
        self.cloud_label = QLabel(self)
        self.ai_label = QLabel(self)
        self.author_label = QLabel("Dev:AnhTienSinh", self)
        self.author_label.setToolTip(f"{APP_DISPLAY_NAME} ({APP_NAME}) -- phát triển bởi {APP_PUBLISHER}")
        self.missing_label = _MissingFilesLabel(self)
        self.missing_label.setCursor(Qt.PointingHandCursor)
        self.missing_label.setVisible(False)
        self.missing_label.clicked.connect(self.relink_requested)
        self.donate_ticker = _DonateTicker(self)
        self.donate_ticker.clicked.connect(self._on_donate_clicked)

        for label in (
            self.files_label,
            self.collection_label,
            self.folders_label,
            self.cloud_label,
            self.ai_label,
        ):
            # Rich text so the function-name vs. status-value color split
            # below actually renders instead of showing raw HTML tags.
            label.setTextFormat(Qt.RichText)
            self.addWidget(label)
        self.addWidget(self.missing_label)
        self.addPermanentWidget(self.donate_ticker)
        self.addPermanentWidget(self.author_label)

        self._refresh_timer = debounced(self, self.refresh)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)
        self._bridge.subscribe(context.event_bus, LibraryFilesMissingEvent)

        self.refresh()

    def _on_donate_clicked(self) -> None:
        DonateDialog(self).exec()

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, FilterChangedEvent):
            self._active_collection_ids = event.filter.collections
            self.refresh()
        elif isinstance(event, LibraryFilesMissingEvent):
            self._show_missing(event.count)
        else:
            self._refresh_timer.start()  # LibraryUpdatedEvent bursts during imports

    def _show_missing(self, count: int) -> None:
        self.missing_label.setVisible(count > 0)
        if count > 0:
            self.missing_label.setText(f"<span style='color:{_STATUS_MISSING_COLOR}; font-weight:600;'>⚠️ {count} sách không tìm thấy file. Tìm lại?</span>")
            self.missing_label.setTextFormat(Qt.RichText)

    def refresh(self) -> None:
        self._show_missing(self.context.db.count_missing())
        total = self.context.db.count_documents()
        complete, incomplete = self.context.db.count_metadata_completeness()
        self.files_label.setText(f"📚 {total} tài liệu  ·  ✅ {complete} đủ thông tin  ·  ⚠️ {incomplete} thiếu thông tin")

        ids = self._active_collection_ids
        if len(ids) == 1:
            row = self.context.db.get_collection(ids[0])
            name = row["name"] if row else "Bộ sưu tập"
            count = self.context.db.count_documents_in_collection(ids[0])
            self.collection_label.setText(f"📁 {name}: {count} tài liệu")
        elif ids:
            # Several collections combined: the count is of their union
            # (a document in two of them counts once), matching what the
            # library view is actually showing.
            sql, params = self.context.db.collections_where_fragment(ids)
            count = self.context.db.count_documents_matching(where_sql=sql, params=params)
            self.collection_label.setText(f"📁 {len(ids)} bộ sưu tập: {count} tài liệu")
        else:
            self.collection_label.setText("")

        folder_count = len(self.context.config.config.watch_folders)
        self.folders_label.setText(f"👁 {folder_count} thư mục đang theo dõi")

        config = self.context.config.config
        cloud_ok = bool(config.supabase_url and config.supabase_anon_key)
        self.cloud_label.setText(self._status_html("☁️", "Review", cloud_ok))

        ai_ok = bool(config.ai_provider and config.ai_api_key)
        self.ai_label.setText(self._status_html("🤖", "AI Tóm tắt", ai_ok))

    def _status_html(self, icon: str, function_name: str, connected: bool) -> str:
        """Icon, then the feature name (muted -- what it is), then the
        status (colored/bold -- whether it's on) -- so the two don't read
        as one flat run of text."""
        colors = current_colors()
        status_color = _STATUS_OK_COLOR if connected else _STATUS_MISSING_COLOR
        status_text = "✓ Đã kết nối" if connected else "✗ Chưa cấu hình"
        return (
            f'{icon} <span style="color:{colors.muted_text};">{function_name}</span>'
            f'  <span style="color:{status_color}; font-weight:600;">{status_text}</span>'
        )


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QMainWindow

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Complete Book", "author": "Someone", "file_path": "a.pdf", "cover_path": "a.webp", "created_at": 0.0}
        )
        context.db.add_or_update_document("d2", {"title": "Missing info", "author": "Unknown", "file_path": "b.pdf", "created_at": 0.0})

        app = QApplication(sys.argv)
        apply_light_theme(app)
        window = QMainWindow()
        window.setStatusBar(StatusBarPanel(context))
        window.resize(900, 200)
        window.show()
        sys.exit(app.exec())
