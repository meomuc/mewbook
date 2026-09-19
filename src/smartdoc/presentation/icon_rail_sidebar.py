"""Collapsed icon-rail sidebar -- the "Mực Đêm" theme's navigation.

A narrow rail of line icons instead of a permanently-expanded list, so the
dark chrome takes as little room as possible from the (deliberately light)
grid. "Tất cả" shows every document; "Bộ sưu tập" / "Bộ lọc" slide out the
matching panel (clicking the active one again collapses it back); "Thêm"
and "Cài đặt" (pinned to the bottom) just ask the main window to open the
add / settings dialogs.

The panels themselves are the *existing* collection list and filter
widgets, re-parented into the flyout -- the rail changes how you
reach them, not what they are, so nothing about collections/filtering
behaves differently on this theme.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from smartdoc.presentation.facet_panel import FacetPanel
from smartdoc.presentation.sidebar import CollectionListPanel
from smartdoc.presentation.theme import current_colors

RAIL_WIDTH = 80
FLYOUT_WIDTH = 220
_BUTTON_SIZE = 64  # inset inside the rail, so the active accent block has breathing room
_ICON_PX = 20
_ICON_LABEL_PX = 8  # the tiny caption under each icon, per the design spec


def _line_icon(kind: str, color: str) -> QIcon:
    """Thin monochrome line icons, drawn rather than shipped as files or
    emoji -- emoji ignore the theme's text color, which is the whole look
    of this rail (muted icons, white on the active accent block)."""
    scale = 3  # draw large, let Qt scale down smoothly
    size = _ICON_PX * scale
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(scale, scale)
    pen = QPen(QColor(color), 1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if kind == "all":  # calendar-like card
        painter.drawRoundedRect(QRectF(3, 4.5, 14, 12), 2, 2)
        painter.drawLine(QPointF(3, 8.5), QPointF(17, 8.5))
        painter.drawLine(QPointF(7, 2.5), QPointF(7, 5.5))
        painter.drawLine(QPointF(13, 2.5), QPointF(13, 5.5))
    elif kind == "collections":  # folder
        path = QPainterPath()
        path.moveTo(2.5, 5.5)
        path.lineTo(2.5, 15.5)
        path.lineTo(17.5, 15.5)
        path.lineTo(17.5, 7)
        path.lineTo(9.5, 7)
        path.lineTo(8, 4.5)
        path.lineTo(3.5, 4.5)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "filters":  # person (the facet panel is authors/formats/tags)
        painter.drawEllipse(QPointF(10, 7), 3.2, 3.2)
        path = QPainterPath()
        path.moveTo(4, 17)
        path.cubicTo(4.5, 12.5, 15.5, 12.5, 16, 17)
        painter.drawPath(path)
    elif kind == "add":
        painter.drawLine(QPointF(10, 3.5), QPointF(10, 16.5))
        painter.drawLine(QPointF(3.5, 10), QPointF(16.5, 10))
    elif kind == "settings":  # sun-like gear
        painter.drawEllipse(QPointF(10, 10), 3, 3)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-0.7, -0.7), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7)):
            painter.drawLine(QPointF(10 + dx * 5.5, 10 + dy * 5.5), QPointF(10 + dx * 7, 10 + dy * 7))
    painter.end()
    return QIcon(pixmap)


class IconRailSidebar(QWidget):
    add_requested = Signal()
    settings_requested = Signal()

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._active_key: str | None = None

        colors = current_colors()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"IconRailSidebar {{ background: {colors.sidebar_bg}; }}")

        self.collections_panel = CollectionListPanel(context, self)
        self.facet_panel = FacetPanel(context, self)

        self.flyout = QStackedWidget(self)
        self.flyout.setFixedWidth(FLYOUT_WIDTH)
        self.flyout.addWidget(self.collections_panel)
        self.flyout.addWidget(self.facet_panel)
        self.flyout.setStyleSheet(
            f"QStackedWidget {{ background: {colors.sidebar_bg}; border-left: 1px solid {colors.border}; }}"
        )
        self.flyout.hide()

        rail = QWidget(self)
        rail.setFixedWidth(RAIL_WIDTH)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 8, 0, 14)
        rail_layout.setSpacing(0)

        self._buttons: dict[str, QToolButton] = {}
        for key, label in (
            ("all", "Tất cả"),
            ("collections", "Bộ sưu tập"),
            ("filters", "Bộ lọc"),
            ("add", "Thêm"),
        ):
            rail_layout.addWidget(self._make_rail_button(rail, key, label), alignment=Qt.AlignHCenter)
        rail_layout.addStretch(1)
        rail_layout.addWidget(self._make_rail_button(rail, "settings", "Cài đặt"), alignment=Qt.AlignHCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(rail)
        layout.addWidget(self.flyout)

        self._update_button_styles()

    def _make_rail_button(self, parent: QWidget, key: str, label: str) -> QToolButton:
        button = QToolButton(parent)
        button.setText(label)
        button.setToolTip(label)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(_ICON_PX, _ICON_PX))
        button.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        button.clicked.connect(lambda _checked=False, k=key: self._on_rail_clicked(k))
        self._buttons[key] = button
        return button

    def _on_rail_clicked(self, key: str) -> None:
        if key == "all":
            self.show_everything()
        elif key == "add":
            self.add_requested.emit()
        elif key == "settings":
            self.settings_requested.emit()
        else:
            self.toggle_panel(key)

    def show_everything(self) -> None:
        self._active_key = None
        self.flyout.hide()
        # Clears collections *and* facets -- same "All wins" rule as the
        # full sidebar's "Tất cả tài liệu" row.
        self.collections_panel._show_everything()
        self._update_button_styles()
        self.updateGeometry()

    def toggle_panel(self, key: str) -> None:
        if self._active_key == key:
            self._active_key = None
            self.flyout.hide()
        else:
            self._active_key = key
            self.flyout.setCurrentWidget(
                self.collections_panel if key == "collections" else self.facet_panel
            )
            self.flyout.show()
        self._update_button_styles()
        self.updateGeometry()

    def _update_button_styles(self) -> None:
        colors = current_colors()
        # With no flyout open, the library is showing "everything" as far
        # as the rail is concerned -- so "Tất cả" is the highlighted item.
        highlighted = self._active_key or "all"
        for key, button in self._buttons.items():
            active = key == highlighted
            # The active item is a solid, rounded accent block (per the
            # design spec), not just a tinted label.
            background = colors.accent if active else "transparent"
            foreground = colors.accent_text if active else colors.muted_text
            button.setIcon(_line_icon(key, foreground))
            button.setStyleSheet(
                f"QToolButton {{ background: {background}; color: {foreground}; border: none;"
                f" border-radius: 4px; font-size: {_ICON_LABEL_PX}pt; padding: 8px 2px 6px 2px; }}"
                f" QToolButton:hover {{ background: {colors.accent if active else colors.border}; }}"
            )

    def sizeHint(self):  # noqa: N802 -- Qt override
        hint = super().sizeHint()
        hint.setWidth(RAIL_WIDTH + (FLYOUT_WIDTH if self.flyout.isVisible() else 0))
        return hint


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "A", "author": "N", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
        )

        app = QApplication(sys.argv)
        apply_theme(app, "inkynight")
        rail = IconRailSidebar(context)
        rail.resize(300, 600)
        rail.show()
        sys.exit(app.exec())
