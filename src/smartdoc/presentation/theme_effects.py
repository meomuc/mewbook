"""Window-level decorations some themes ask for, done the Qt way:

- GrainOverlay: a film-grain dot pattern over the whole window
  (ThemeColors.grain_overlay). The CSS original is a pseudo-element with
  `pointer-events: none` and `mix-blend-mode: multiply`; here it's a child
  widget that ignores the mouse and paints a tiled, ~5%-opaque dot pattern
  -- dark dots at low opacity over a light page look the same as a
  multiply blend.
- RetroTitleBar: the fake old-OS title strip with three pastel dots and a
  path (ThemeColors.titlebar_text). Drawn inside the window rather than
  replacing Windows' own title bar, which would mean a frameless window
  and re-implementing move/resize/snap.
- theme_preview_pixmap: a small picture of a theme (header, sidebar,
  covers, detail panel) for the theme pickers.
"""
from __future__ import annotations

import zlib

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from smartdoc.presentation.theme import ThemeColors

_GRAIN_TILE = 5  # px; one dot per ~2.5px at the spec's density after 2x2 dots per tile
_GRAIN_ALPHA = 13  # ~5% of 255


def _grain_tile() -> QPixmap:
    tile = QPixmap(_GRAIN_TILE, _GRAIN_TILE)
    tile.fill(Qt.transparent)
    painter = QPainter(tile)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0, _GRAIN_ALPHA))
    # Two offset dots per tile break up the grid so it reads as grain.
    painter.drawRect(0, 0, 1, 1)
    painter.drawRect(2, 3, 1, 1)
    painter.end()
    return tile


class GrainOverlay(QWidget):
    """Covers its parent completely, never takes input, follows resizes."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("GrainOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self._brush = QBrush(_grain_tile())
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 -- Qt override
        if watched is self.parent() and event.type() in (QEvent.Resize, QEvent.ChildAdded):
            self.setGeometry(self.parent().rect())
            self.raise_()
        return False

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._brush)
        painter.end()


_DOT_COLORS = ("#f2a6d0", "#f2d9a0", "#9fe3ee")


class RetroTitleBar(QWidget):
    def __init__(self, colors: ThemeColors, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RetroTitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#RetroTitleBar {{ background: {colors.header_bg}; border-bottom: 1px solid {colors.border}; }}"
            f" #RetroTitleBar QLabel {{ background: transparent; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 7, 16, 7)
        row.setSpacing(7)
        for color in _DOT_COLORS:
            dot = QLabel(self)
            dot.setFixedSize(11, 11)
            dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
            row.addWidget(dot)
        row.addSpacing(10)
        self.path_label = QLabel(colors.titlebar_text or "", self)
        self.path_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 12px;")
        row.addWidget(self.path_label)
        row.addStretch(1)


def theme_preview_pixmap(colors: ThemeColors, size: QSize = QSize(84, 52)) -> QPixmap:
    """A miniature of the theme's main window, for the theme pickers."""
    w, h = size.width(), size.height()
    pixmap = QPixmap(size)
    pixmap.fill(QColor(colors.background))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    top = 0
    if colors.titlebar_text:
        painter.fillRect(0, 0, w, 5, QColor(colors.surface))
        for i, dot in enumerate(_DOT_COLORS):
            painter.setBrush(QColor(dot))
            painter.drawEllipse(QRectF(3 + i * 4, 1.5, 2.5, 2.5))
        top = 5
    header_h = max(6, h // 7)
    painter.fillRect(0, top, w, header_h, QColor(colors.header_bg))
    painter.setBrush(QColor(colors.surface))
    painter.drawRoundedRect(QRectF(w * 0.22, top + 2, w * 0.4, header_h - 4), min(colors.control_radius, 3), min(colors.control_radius, 3))
    body_top = top + header_h

    sidebar_w = w * (0.1 if colors.icon_rail_sidebar else 0.2)
    painter.fillRect(QRectF(0, body_top, sidebar_w, h - body_top), QColor(colors.sidebar_bg))
    painter.setBrush(QColor(colors.selected_bg))
    painter.drawRoundedRect(QRectF(2, body_top + 4, sidebar_w - 4, 4), 1, 1)
    for i in range(3):
        painter.fillRect(QRectF(4, body_top + 12 + i * 6, sidebar_w * 0.6, 1.5), QColor(colors.muted_text))

    panel_w = w * 0.2 if colors.layout_mode == "detail_panel" else 0
    painter.fillRect(QRectF(sidebar_w, body_top, w - sidebar_w - panel_w, h - body_top), QColor(colors.content_bg))
    if panel_w:
        painter.fillRect(QRectF(w - panel_w, body_top, panel_w, h - body_top), QColor(colors.panel_bg))
        painter.setBrush(QColor(colors.accent))
        painter.drawRoundedRect(QRectF(w - panel_w + 4, body_top + 5, panel_w - 8, (panel_w - 8) * 1.3), 1, 1)

    cover_w = (w - sidebar_w - panel_w - 8) / 4.6
    radius = min(colors.cover_radius, 2)
    x0 = sidebar_w + 4
    featured = colors.grid_layout == "featured"
    for i in range(4):
        pair = colors.cover_gradients[zlib.crc32(str(i).encode()) % len(colors.cover_gradients)]
        painter.setBrush(QColor(pair[0]))
        if featured and i == 0:
            rect = QRectF(x0, body_top + 5, cover_w * 1.9, cover_w * 2.4)
            x0 += cover_w * 2.1
        else:
            rect = QRectF(x0, body_top + 5, cover_w, cover_w * 1.42)
            x0 += cover_w * 1.15
        painter.drawRoundedRect(rect, radius, radius)
        if i == 1:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor(colors.accent))
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), radius, radius)
            painter.setPen(Qt.NoPen)

    painter.setPen(QColor(colors.border if colors.border.startswith("#") else colors.muted_text))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))
    painter.end()
    return pixmap


def apply_font_letter_spacing(label: QLabel, percent: float) -> None:
    font = QFont(label.font())
    font.setLetterSpacing(QFont.PercentageSpacing, percent)
    label.setFont(font)
