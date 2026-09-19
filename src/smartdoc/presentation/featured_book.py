"""The "featured book" of an asymmetric grid (ThemeColors.grid_layout ==
"featured", used by Japandi): the page's first book shown large, beside
the ordinary grid of the others, instead of every book in one even grid.

Qt's QListView can't span one item over several grid cells, so the large
book is its own widget placed next to the grid (see
LibraryListWidget); the grid model then holds the remaining books. It
behaves like a grid card: click selects it (the detail panel follows),
double-click opens it, right-click shows the usual document menu.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from smartdoc.presentation.cover_placeholder import gradient_pixmap
from smartdoc.presentation.theme import current_colors, qt_weight

FEATURED_SCALE = 2.3  # the featured cover is this many grid covers wide
_TEXT_GAP = 14


class FeaturedBookCard(QWidget):
    clicked = Signal(dict)
    double_clicked = Signal(dict)
    context_menu_requested = Signal(dict, QPoint)  # (doc, global position)

    def __init__(self, parent=None, *, cover_aspect: float = 1.42, content_font_size: int = 13) -> None:
        super().__init__(parent)
        self._doc: dict | None = None
        self._selected = False
        self._cover_aspect = cover_aspect
        self._font_px = content_font_size
        self._cover_width = 300
        self._pixmap: QPixmap | None = None
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._apply_size()

    # -- state ---------------------------------------------------------------

    def document(self) -> dict | None:
        return self._doc

    def set_document(self, doc: dict | None) -> None:
        self._doc = doc
        self._pixmap = None
        self._selected = False
        self.setVisible(doc is not None)
        self.setToolTip((doc or {}).get("title") or "")
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    def set_cover_width(self, grid_cover_width: int) -> None:
        self._cover_width = round(grid_cover_width * FEATURED_SCALE)
        self._pixmap = None
        self._apply_size()
        self.update()

    def _cover_size(self) -> QSize:
        return QSize(self._cover_width, round(self._cover_width * self._cover_aspect))

    def _apply_size(self) -> None:
        cover = self._cover_size()
        self.setFixedWidth(cover.width() + 4)
        self.setMinimumHeight(cover.height() + _TEXT_GAP + 60)

    # -- painting ------------------------------------------------------------

    def _cover_pixmap(self) -> QPixmap:
        if self._pixmap is not None:
            return self._pixmap
        size = self._cover_size()
        doc = self._doc or {}
        path = doc.get("cover_path")
        source = QPixmap(path) if path and Path(path).exists() else QPixmap()
        if source.isNull():
            colors = dataclasses.replace(current_colors(), cover_jacket_text=True)
            self._pixmap = gradient_pixmap(
                doc.get("id", ""), size, colors, title=doc.get("title") or "", author=""
            )
        else:
            scaled = source.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self._pixmap = scaled.copy(
                (scaled.width() - size.width()) // 2, (scaled.height() - size.height()) // 2, size.width(), size.height()
            )
        return self._pixmap

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._doc is None:
            return
        colors = current_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        cover = QRect(QPoint(2, 2), self._cover_size())

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(cover), colors.cover_radius, colors.cover_radius)
        painter.save()
        painter.setClipPath(clip)
        painter.drawPixmap(cover.topLeft(), self._cover_pixmap())
        painter.restore()
        if self._selected:
            pen = QPen(QColor(colors.accent))
            pen.setWidth(max(1, colors.card_outline_width))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(cover).adjusted(-1, -1, 1, 1), colors.cover_radius, colors.cover_radius)

        title_font = QFont()
        title_font.setPixelSize(self._font_px + 3)
        title_font.setWeight(qt_weight(colors.card_title_weight))
        author_font = QFont()
        author_font.setPixelSize(self._font_px)
        author_font.setWeight(qt_weight(colors.font_weight))
        width = cover.width()
        y = cover.bottom() + _TEXT_GAP
        title_metrics = QFontMetrics(title_font)
        painter.setFont(title_font)
        painter.setPen(QColor(colors.accent if self._selected else colors.text))
        painter.drawText(
            QRect(cover.left(), y, width, title_metrics.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            title_metrics.elidedText(self._doc.get("title") or "", Qt.ElideRight, width),
        )
        author = self._doc.get("author") or ""
        if author:
            y += title_metrics.height() + 6
            author_metrics = QFontMetrics(author_font)
            painter.setFont(author_font)
            painter.setPen(QColor(colors.muted_text))
            painter.drawText(
                QRect(cover.left(), y, width, author_metrics.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                author_metrics.elidedText(author, Qt.ElideRight, width),
            )
        painter.end()

    # -- input ---------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._doc is None:
            return
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._doc)
        elif event.button() == Qt.RightButton:
            self.clicked.emit(self._doc)
            self.context_menu_requested.emit(self._doc, event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._doc is not None and event.button() == Qt.LeftButton:
            self.double_clicked.emit(self._doc)
