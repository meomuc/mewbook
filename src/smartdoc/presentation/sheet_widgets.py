# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small pieces shared by the sheet-shaped layout ("Tối giản"): the vertical area label and cover pictures at a given
size. Everything reads colours from ThemeManager; nothing knows which layout or theme is applied."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from smartdoc.presentation.cover_placeholder import gradient_pixmap
from smartdoc.presentation.theme import current_colors
from smartdoc.presentation.theme_manager import theme_manager

_COVER_CACHE: dict[tuple, QPixmap] = {}
_COVER_CACHE_MAX = 120
MIN_COVER_ASPECT, MAX_COVER_ASPECT = 1.15, 1.7  # height / width bounds for a book cover shown at natural proportions


class VerticalLabel(QWidget):
    """An area label turned 90 degrees, reading bottom-to-top, in the content typeface ("Mới thêm tuần này")."""

    def __init__(self, text: str, parent: QWidget | None = None, *, pixel_size: int = 14) -> None:
        super().__init__(parent)
        self._text = text
        self._pixel_size = pixel_size
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAccessibleName(text)
        self._fit()

    def _font(self) -> QFont:
        font = QFont(theme_manager().font_family("content"))
        font.setPixelSize(self._pixel_size)
        return font

    def _fit(self) -> None:
        metrics = QFontMetrics(self._font())
        self.setFixedSize(metrics.height() + 4, metrics.horizontalAdvance(self._text) + 6)

    def set_text(self, text: str) -> None:
        self._text = text
        self.setAccessibleName(text)
        self._fit()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 -- Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self._font())
        painter.setPen(QColor(theme_manager().token("ink2")))
        painter.translate(0, self.height())
        painter.rotate(-90)
        painter.drawText(0, 0, self.height(), self.width(), Qt.AlignLeft | Qt.AlignVCenter, self._text)


def cover_pixmap(doc: dict, height: int, *, width: int | None = None, dpr: float = 1.0) -> QPixmap:
    """The book's cover at `height` px: its real picture if the file exists (kept at its own proportions unless `width`
    is given, then filled and cropped to that box), otherwise the deterministic gradient jacket with the title."""
    cover_path = doc.get("cover_path") or ""
    real = QPixmap(cover_path) if cover_path and Path(cover_path).exists() else QPixmap()
    if not real.isNull() and width is None:
        aspect = max(MIN_COVER_ASPECT, min(MAX_COVER_ASPECT, real.height() / max(1, real.width())))
        width = int(height / aspect)
    elif width is None:
        width = int(height / 1.42)
    key = (doc.get("id"), cover_path, width, height, round(dpr, 2), theme_manager().key)
    cached = _COVER_CACHE.get(key)
    if cached is not None:
        return cached
    box = QSize(int(width * dpr), int(height * dpr))
    if not real.isNull():
        fitted = real.scaled(box, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x, y = (fitted.width() - box.width()) // 2, (fitted.height() - box.height()) // 2
        result = fitted.copy(x, y, box.width(), box.height())
    else:
        result = gradient_pixmap(str(doc.get("id") or doc.get("title") or ""), box, current_colors(),
                                 doc.get("title") or "", doc.get("author") or "")
    result.setDevicePixelRatio(dpr)
    if len(_COVER_CACHE) >= _COVER_CACHE_MAX:
        _COVER_CACHE.clear()
    _COVER_CACHE[key] = result
    return result


def draw_cover(painter: QPainter, rect: QRectF, doc: dict, *, radius: float = 3.0, shadow: bool = True,
               dpr: float = 1.0) -> None:
    """Paints the cover of `doc` filling `rect` (rounded corners, a soft drop shadow underneath)."""
    tm = theme_manager()
    if shadow:
        base = tm.color("shadow")
        painter.setPen(Qt.NoPen)
        for spread, scale in ((10, 0.05), (6, 0.08), (3, 0.14)):
            tone = QColor(base)
            tone.setAlpha(int(base.alpha() * scale))
            painter.setBrush(tone)
            painter.drawRoundedRect(rect.adjusted(-spread + 2, -spread + 8, spread - 2, spread + 4), radius + 4, radius + 4)
    painter.save()
    clip = QPainterPath()
    clip.addRoundedRect(rect, radius, radius)
    painter.setClipPath(clip)
    pixmap = cover_pixmap(doc, int(rect.height()), width=int(rect.width()), dpr=dpr)
    painter.drawPixmap(rect.topLeft(), pixmap)
    painter.restore()
