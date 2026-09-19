"""Gradient cover-art placeholder, shown wherever a document has no real
cover image yet -- a flat gray rectangle read as "broken," a book-spine-like
gradient block reads as "no cover art *yet*" instead.

Shared by the library grid (library_view.py), the new List view's cover
thumbnail column, and the Document Detail Panel's big cover -- one paint
routine so all three stay visually consistent instead of drifting apart.
"""
from __future__ import annotations

import zlib

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPixmap, QTextLayout

from smartdoc.presentation.theme import ThemeColors

# ~155deg: mostly top-left-to-bottom-right, tilted slightly past pure
# diagonal -- matches the design spec's "gradient tối theo góc ~155deg".
_ANGLE_DEGREES = 155
_SPINE_WIDTH_RATIO = 0.07  # left-edge "book spine" band width, as a fraction of the pixmap's width
# Below this width (the List view's 32px thumbnails) there's no room for
# readable text, so the placeholder is just the gradient.
_MIN_WIDTH_FOR_TEXT = 60
_TITLE_MAX_LINES = 3


def _pair_index(doc_id: str, count: int) -> int:
    # crc32, not hash(): Python salts str hashes per process, so hash()
    # gave the same book a different color on every launch.
    return zlib.crc32((doc_id or "").encode("utf-8")) % count


def gradient_pixmap(
    doc_id: str,
    size: QSize,
    colors: ThemeColors,
    title: str = "",
    author: str = "",
    bottom_reserve: float = 0.0,
) -> QPixmap:
    """A deterministic-per-book gradient block: the same doc_id always
    picks the same gradient pair (stable across reloads, re-renders and
    launches), but different books in the same library land on different
    pairs from `colors.cover_gradients`, so a shelf of covers-less
    documents still looks visually varied rather than one repeated flat
    block. With a title (and author), they're set in the lower part of the
    cover like a real book jacket, so a coverless book is still
    recognisable at a glance. `bottom_reserve` (a fraction of the height)
    keeps that text clear of something the caller stamps along the bottom
    edge afterwards, such as the file-format badge."""
    pixmap = QPixmap(size)
    pair = colors.cover_gradients[_pair_index(doc_id, len(colors.cover_gradients))]

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    width, height = size.width(), size.height()
    if colors.cover_flat:
        painter.fillRect(0, 0, width, height, QColor(pair[0]))
    else:
        gradient = _angled_gradient(width, height, _ANGLE_DEGREES)
        gradient.setColorAt(0.0, QColor(pair[0]))
        gradient.setColorAt(1.0, QColor(pair[1]))
        painter.fillRect(0, 0, width, height, gradient)

    spine_width = max(1, round(width * _SPINE_WIDTH_RATIO))
    if colors.cover_spine[3] > 0:
        painter.fillRect(0, 0, spine_width, height, QColor(*colors.cover_spine))
        # A faint highlight right after the spine, like the crease of a hardback.
        painter.fillRect(spine_width, 0, max(1, spine_width // 3), height, QColor(255, 255, 255, 14))

    if title and colors.cover_jacket_text and width >= _MIN_WIDTH_FOR_TEXT:
        _paint_jacket_text(painter, width, height, spine_width, title, author, colors, bottom_reserve)

    painter.end()
    return pixmap


def _jacket_font(pixel_size: int, bold: bool, colors: ThemeColors) -> QFont:
    font = QFont()
    font.setFamilies(list(colors.font_families))
    font.setPixelSize(max(colors.jacket_min_px, pixel_size))
    font.setBold(bold)
    return font


def _wrapped_lines(text: str, font: QFont, width: float, max_lines: int) -> list[str]:
    """Word-wrapped lines of `text` in `width` px, at most `max_lines`
    (the last one elided with "…" if the text runs over)."""
    layout = QTextLayout(text, font)
    layout.beginLayout()
    lines: list[tuple[int, int]] = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        lines.append((line.textStart(), line.textLength()))
    layout.endLayout()
    result = [text[start : start + length].strip() for start, length in lines[:max_lines]]
    if len(lines) > max_lines and result:
        rest = text[lines[max_lines - 1][0] :]
        result[-1] = QFontMetricsF(font).elidedText(rest, Qt.ElideRight, width)
    return result


def _paint_jacket_text(
    painter: QPainter,
    width: int,
    height: int,
    spine_width: int,
    title: str,
    author: str,
    colors: ThemeColors,
    bottom_reserve: float = 0.0,
) -> None:
    left = spine_width + width * 0.06
    text_width = width - left - width * 0.07
    bottom = height - height * (0.08 + bottom_reserve)

    # Proportional on grid-sized covers, capped on the detail panel's big
    # one -- a jacket title is a label, not a headline.
    title_font = _jacket_font(min(round(width * 0.08), 16), bold=True, colors=colors)
    author_font = _jacket_font(min(round(width * 0.062), 12), bold=False, colors=colors)
    ink = QColor(colors.cover_text_color)
    title_lines = _wrapped_lines(title, title_font, text_width, _TITLE_MAX_LINES)
    title_line_height = QFontMetricsF(title_font).height() * 0.98
    author_line_height = QFontMetricsF(author_font).height()

    y = bottom - len(title_lines) * title_line_height
    if author:
        y -= author_line_height + height * 0.02

    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(title_font)
    ink.setAlpha(235)
    painter.setPen(ink)
    for line in title_lines:
        painter.drawText(QRectF(left, y, text_width, title_line_height), Qt.AlignLeft | Qt.AlignVCenter, line)
        y += title_line_height
    if author:
        y += height * 0.02
        painter.setFont(author_font)
        ink.setAlpha(150)
        painter.setPen(ink)
        elided = QFontMetricsF(author_font).elidedText(author, Qt.ElideRight, text_width)
        painter.drawText(QRectF(left, y, text_width, author_line_height), Qt.AlignLeft | Qt.AlignVCenter, elided)


def _angled_gradient(width: int, height: int, angle_degrees: float) -> QLinearGradient:
    """A QLinearGradient running at `angle_degrees` across a width x height
    rect (0deg = left-to-right, 90deg = top-to-bottom, matching CSS's
    `linear-gradient(Ndeg, ...)` convention that the design spec's numbers
    come from)."""
    import math

    radians = math.radians(angle_degrees - 90)
    center = QPointF(width / 2, height / 2)
    # Half-diagonal is long enough that the gradient's start/end points
    # always land outside the rect regardless of angle, so the two color
    # stops are never both inside the visible area (which would clip the
    # gradient instead of spanning the full box).
    half_diagonal = ((width**2 + height**2) ** 0.5) / 2
    dx = half_diagonal * math.sin(radians)
    dy = -half_diagonal * math.cos(radians)
    start = QPointF(center.x() - dx, center.y() - dy)
    end = QPointF(center.x() + dx, center.y() + dy)
    return QLinearGradient(start, end)


if __name__ == "__main__":
    from smartdoc.presentation.theme import BROADSHEET

    pix = gradient_pixmap("doc-123", QSize(84, 120), BROADSHEET)
    assert not pix.isNull()
    pix2 = gradient_pixmap("doc-123", QSize(84, 120), BROADSHEET)
    assert pix.toImage() == pix2.toImage()  # deterministic per doc_id
    print("gradient_pixmap OK")
