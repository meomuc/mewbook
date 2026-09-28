# SPDX-License-Identifier: AGPL-3.0-or-later
"""The yellow strip at the top of the content area: "12 sách không tìm thấy file. Tìm lại?" (stage G11).

It shows only while some book's file is missing (the same count the status bar shows) and offers one button that opens
"Tìm lại file". Nothing here touches a file; finding them again is the relink dialog's job.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from smartdoc.core.event_bus import LibraryFilesMissingEvent, LibraryUpdatedEvent
from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.line_icons import icon_pixmap
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.ornaments import notice_qss
from smartdoc.presentation.theme_manager import theme_manager


class MissingFilesStrip(QFrame):
    relink_requested = Signal()

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.setObjectName("MissingFilesStrip")
        self.icon_label = QLabel(self)
        self.text_label = QLabel(self)
        self.button = QPushButton(vi.FIND_AGAIN, self)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.relink_requested)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 6, 16, 6)
        row.setSpacing(10)
        row.addWidget(self.icon_label)
        row.addWidget(self.text_label, 1)
        row.addWidget(self.button)
        self._restyle()
        theme_manager().themeChanged.connect(self._restyle)
        self._refresh_timer = debounced(self, self._refresh_count)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_event)
        self._bridge.subscribe(context.event_bus, LibraryFilesMissingEvent)
        # A bulk change that isn't a relink check -- restoring a backup, "Đặt lại thư viện" -- can make books
        # missing or present again without ever publishing LibraryFilesMissingEvent; re-count so the strip
        # doesn't keep showing a number that no longer matches the library.
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self.set_count(context.db.count_missing())

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(f"#MissingFilesStrip {{ background: {tm.token('surface2')}; border-bottom: 1px solid {tm.token('warn')}; }}"
                           f" #MissingFilesStrip QLabel {{ color: {tm.token('ink')}; background: transparent; }}")
        self.setStyleSheet(self.styleSheet() + " " + notice_qss(tm, "#MissingFilesStrip"))
        self.icon_label.setPixmap(icon_pixmap("warn", tm.token("warn"), 16))

    def _on_event(self, event) -> None:
        if isinstance(event, LibraryFilesMissingEvent):
            self.set_count(event.count)
        else:
            self._refresh_timer.start()  # LibraryUpdatedEvent bursts during imports

    def _refresh_count(self) -> None:
        self.set_count(self.context.db.count_missing())

    def set_count(self, count: int) -> None:
        self.text_label.setText(vi.MISSING_FILES.format(n=f"{count:,}".replace(",", ".")) if count else "")
        self.setVisible(count > 0)
