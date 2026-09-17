"""TDD-011: Omnibar Search UI.

Debounces keystrokes and publishes a SearchRequestedEvent on the EventBus —
it does not call the library view directly, per the integration rule that
modules communicate through context.event_bus rather than cross-calling.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit

from smartdoc.core.event_bus import SearchRequestedEvent
from smartdoc.presentation.theme import current_colors

DEBOUNCE_MS = 300


class OmnibarSearchBar(QLineEdit):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context

        colors = current_colors()
        self.setPlaceholderText("Tìm kiếm... (vd. author:nam python)")
        self.setClearButtonEnabled(True)
        self.setStyleSheet(
            f"""
            QLineEdit {{
                border: 1px solid {colors.border};
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 14px;
                background: {colors.surface};
                color: {colors.text};
            }}
            QLineEdit:focus {{ border: 1px solid {colors.accent}; }}
            """
        )

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._publish_search)

        self.textChanged.connect(lambda _text: self._timer.start())

    def _publish_search(self) -> None:
        self.context.event_bus.publish(SearchRequestedEvent(query=self.text().strip()))


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.event_bus.subscribe(SearchRequestedEvent, lambda e: print("SearchRequestedEvent:", repr(e.query)))

        app = QApplication(sys.argv)
        from smartdoc.presentation.theme import apply_light_theme

        apply_light_theme(app)
        bar = OmnibarSearchBar(context)
        bar.resize(400, 40)
        bar.show()
        sys.exit(app.exec())
