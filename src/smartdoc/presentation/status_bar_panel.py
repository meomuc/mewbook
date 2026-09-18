"""Bottom status bar: at-a-glance library/collection/connection status.

Built as a real QStatusBar (QMainWindow.setStatusBar) rather than a plain
widget docked at the bottom, so it gets the OS-native "thin bar, small
text" treatment for free. Refreshes on LibraryUpdatedEvent and
CollectionSelectedEvent -- the same two events the library view itself
reacts to, so the counts here never lag behind what's on screen.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStatusBar

from smartdoc.core.event_bus import CollectionSelectedEvent, LibraryUpdatedEvent
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.theme import current_colors

# Same green/crimson pair settings_dialog.py's connection test uses -- one
# consistent "connected vs. not" color language across the app instead of
# each status indicator inventing its own.
_STATUS_OK_COLOR = "green"
_STATUS_MISSING_COLOR = "crimson"


class StatusBarPanel(QStatusBar):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._active_collection_id: str | None = None

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
        self.author_label = QLabel("anhtiensinh", self)
        self.author_label.setToolTip("SmartDoc Library -- phát triển bởi anhtiensinh")

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
        self.addPermanentWidget(self.author_label)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, CollectionSelectedEvent)

        self.refresh()

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, CollectionSelectedEvent):
            self._active_collection_id = event.collection_id
        self.refresh()

    def refresh(self) -> None:
        total = self.context.db.count_documents()
        complete, incomplete = self.context.db.count_metadata_completeness()
        self.files_label.setText(f"📚 {total} tài liệu  ·  ✅ {complete} đủ thông tin  ·  ⚠️ {incomplete} thiếu thông tin")

        if self._active_collection_id:
            row = self.context.db.get_collection(self._active_collection_id)
            name = row["name"] if row else "Bộ sưu tập"
            count = self.context.db.count_documents_in_collection(self._active_collection_id)
            self.collection_label.setText(f"📁 {name}: {count} tài liệu")
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
