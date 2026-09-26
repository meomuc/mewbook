# SPDX-License-Identifier: AGPL-3.0-or-later
""""Trang đầu": the opening screen of the sheet layout ("Tối giản", layouts/toi-gian/LAYOUT_SPEC.md section 3).

Left: a headline, the size of the library, the main search box and a few shortcut chips. Middle: the book being read
(or, for a library never read from, the newest one) standing on a large ledge. Right, standing on the same ledge: the
"author of the month" card and the "recently read" card. Under the ledge: what was added this week, each with a "Đọc"
button. All of it comes from the same database as the library (`recent_reading`, `author_of_the_month`,
`query_documents`) -- nothing here keeps its own copy of the data -- and it is redrawn when the library changes.

The page is laid out by hand (the pictures overlap the ledge, which a box layout cannot express) in `_geometry()`; below
1200 px wide, or 700 px tall, the cover shrinks, the "recently read" card is dropped and three books are shown under the
ledge instead of four. Empty library: the headline says so, two buttons start an import, and the mascot stands on the
ledge."""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QPushButton, QToolButton, QWidget

from smartdoc.core.event_bus import DocumentIndexedEvent, ImportBatchCompletedEvent, LibraryUpdatedEvent
from smartdoc.domain.author_names import NO_TAG
from smartdoc.domain.library_filter import COLLECTIONS, FORMATS, TAGS
from smartdoc.presentation.brand import mascot_pixmap
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.reader_window import reader_events
from smartdoc.presentation.sheet_widgets import VerticalLabel, cover_pixmap, draw_cover
from smartdoc.presentation.theme_manager import theme_manager

WEEK = 7 * 86400
NEW_ITEMS = 4  # books under the ledge (three in a small window), plus one tilted "there is more" cover
CARD_W = 150
MARGIN = 58


@dataclass
class _Chip:
    label: str
    category: str
    value: str


class HomePage(QWidget):
    open_requested = Signal(dict)  # a book to open in the reader
    library_requested = Signal()  # go to the Thư viện screen (the filters are already set)
    author_requested = Signal(str)
    add_folder_requested = Signal()
    calibre_requested = Signal()

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.setObjectName("HomePage")
        self.setMouseTracking(True)
        self._total = 0
        self._recent: list[dict] = []
        self._recent_index = 0
        self._hero: dict | None = None
        self._hero_caption = ""
        self._author: dict | None = None
        self._new_docs: list[dict] = []
        self._new_label = "Mới thêm"
        self._chips: list[_Chip] = []
        self._hits: list[tuple[QRectF, str, object]] = []  # clickable areas painted by hand: (rect, action, payload)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Tên sách, tác giả hoặc nội dung")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._on_search)
        self.search.addAction(line_icon("search", theme_manager().token("ink3")), QLineEdit.LeadingPosition)
        self._chip_buttons: list[QPushButton] = []
        self.author_link = QPushButton("Xem sách", self)
        self.author_link.setCursor(Qt.PointingHandCursor)
        self.author_link.setFlat(True)
        self.author_link.clicked.connect(self._on_author_link)
        self.prev_button = QToolButton(self)
        self.next_button = QToolButton(self)
        self.read_button = QToolButton(self)
        for button, tip in ((self.prev_button, "Cuốn đọc trước"), (self.next_button, "Cuốn đọc sau"),
                            (self.read_button, "Đọc tiếp")):
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.setCursor(Qt.PointingHandCursor)
        self.prev_button.clicked.connect(lambda: self._step_recent(-1))
        self.next_button.clicked.connect(lambda: self._step_recent(1))
        self.read_button.clicked.connect(self._read_current)
        self._read_buttons: list[QPushButton] = []
        self.all_link = QPushButton("Xem cả thư viện", self)
        self.all_link.setFlat(True)
        self.all_link.setCursor(Qt.PointingHandCursor)
        self.all_link.clicked.connect(self.library_requested)
        self.add_folder_button = QPushButton("Thêm thư mục sách", self)
        self.add_folder_button.setProperty("role", "primary")
        self.add_folder_button.clicked.connect(self.add_folder_requested)
        self.calibre_button = QPushButton("Nhập từ Calibre", self)
        self.calibre_button.clicked.connect(self.calibre_requested)

        self._label_new = VerticalLabel(self._new_label, self)
        self._label_author = VerticalLabel("Tác giả của tháng", self)
        self._label_recent = VerticalLabel("Đọc gần đây", self)

        self._refresh_timer = debounced(self, self.refresh, 300)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(lambda _event: self._refresh_timer.start())
        for event_type in (LibraryUpdatedEvent, DocumentIndexedEvent, ImportBatchCompletedEvent):
            self._bridge.subscribe(context.event_bus, event_type)
        reader_events.changed.connect(self._refresh_timer.start)
        self._restyle()
        theme_manager().themeChanged.connect(self._restyle)
        self.refresh()

    # -- data ---------------------------------------------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-reads everything the page shows from the database."""
        db = self.context.db
        self._total = db.count_documents_matching()
        self._recent = [d for d in db.recent_reading(10)]
        self._recent_index = min(self._recent_index, max(0, len(self._recent) - 1))
        newest = db.query_documents(order_by="created_at DESC", limit=NEW_ITEMS + 2)
        if self._recent:
            self._hero, self._hero_caption = self._recent[0], self._reading_caption(self._recent[0])
        elif newest:
            self._hero, self._hero_caption = newest[0], "Mới thêm"
        else:
            self._hero, self._hero_caption = None, ""
        hero_id = self._hero.get("id") if self._hero else None
        self._new_docs = [d for d in newest if d.get("id") != hero_id][:NEW_ITEMS + 1]
        week_ago = time.time() - WEEK
        self._new_label = "Mới thêm tuần này" if any((d.get("created_at") or 0) >= week_ago for d in self._new_docs) else "Mới thêm"
        self._label_new.set_text(self._new_label)
        self._author = db.author_of_the_month()
        self._chips = self._build_chips()
        self._rebuild_widgets()
        self._place()
        self.update()

    @staticmethod
    def _reading_caption(doc: dict) -> str:
        position, total = int(doc.get("position") or 0), int(doc.get("total") or 0)
        unit = "chương" if doc.get("unit") == "chapter" else "trang"
        if position > 0 and total > 0:
            return f"Đang đọc · {unit} {position} / {total}"
        return "Đang đọc"

    def _build_chips(self) -> list[_Chip]:
        db = self.context.db
        chips: list[_Chip] = []
        tag, extension = db.most_common_tag(), db.most_common_extension()
        if tag:
            chips.append(_Chip(f"#{tag}", TAGS, tag))
        if extension:
            chips.append(_Chip(extension.upper(), FORMATS, extension))
        chips.append(_Chip("Chưa phân loại", TAGS, NO_TAG))
        chips.append(_Chip("Sẽ đọc", COLLECTIONS, db.ensure_reading_list()))
        return chips if self._total else []

    def _rebuild_widgets(self) -> None:
        for button in self._chip_buttons + self._read_buttons:
            button.setParent(None)
            button.deleteLater()  # a discarded widget is destroyed by Qt, not left to the cycle collector
        self._chip_buttons, self._read_buttons = [], []
        for chip in self._chips:
            button = QPushButton(chip.label, self)
            button.setProperty("chip", True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _c=False, c=chip: self._apply_chip(c))
            button.show()
            self._chip_buttons.append(button)
        for doc in self._new_docs[:NEW_ITEMS]:
            button = QPushButton("Đọc", self)
            button.setProperty("role", "outline")
            button.setCursor(Qt.PointingHandCursor)
            button.setAccessibleName(f"Đọc {doc.get('title') or 'sách này'}")
            button.clicked.connect(lambda _c=False, d=doc: self.open_requested.emit(d))
            button.show()
            self._read_buttons.append(button)
        self._restyle()

    # -- actions ------------------------------------------------------------------------------------------------------
    def _apply_chip(self, chip: _Chip) -> None:
        self.context.filters.clear()
        self.context.filters.select(chip.category, chip.value)
        self.library_requested.emit()

    def _on_search(self) -> None:
        self.context.filters.clear()
        self.context.filters.set_query(self.search.text().strip())
        self.library_requested.emit()

    def _on_author_link(self) -> None:
        if self._author:
            self.author_requested.emit(self._author["author"])

    def _step_recent(self, delta: int) -> None:
        if self._recent:
            self._recent_index = (self._recent_index + delta) % len(self._recent)
            self._place()
            self.update()

    def _read_current(self) -> None:
        if self._recent:
            self.open_requested.emit(self._recent[self._recent_index])

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() == Qt.LeftButton:
            point = event.position()
            for rect, action, payload in self._hits:
                if rect.contains(point):
                    if action == "open":
                        self.open_requested.emit(payload)
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        over = any(rect.contains(event.position()) for rect, _a, _p in self._hits)
        self.setCursor(Qt.PointingHandCursor if over else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    # -- geometry -----------------------------------------------------------------------------------------------------
    @property
    def _compact(self) -> bool:
        return self.width() < 1200 or self.height() < 700

    def _geometry(self) -> dict:
        tm = theme_manager()
        w, h = self.width(), self.height()
        hero_h = 230 if self._compact else int(tm.metric("hero_cover_height", 300))
        ledge_t = int(tm.metric("ledge_thickness", 18))
        ledge_y = min(h - 290, max(hero_h + 96, int(h * 0.56)))
        hero_doc = self._hero or {}
        hero_w = cover_pixmap(hero_doc, hero_h).width() if self._hero else int(hero_h / 1.42)
        return {"w": w, "h": h, "hero_h": hero_h, "hero_w": hero_w, "ledge_y": ledge_y, "ledge_t": ledge_t,
                "hero_x": int(w * 0.29), "hero_y": ledge_y - hero_h, "n_items": 3 if self._compact else NEW_ITEMS}

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._place()

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        self.refresh()

    def _place(self) -> None:
        """Positions the real child widgets (the pictures and texts are painted in paintEvent, from the same numbers)."""
        g = self._geometry()
        w, h, ledge_y = g["w"], g["h"], g["ledge_y"]
        empty = self._total == 0
        left_w = min(380, int(w * 0.26))
        self.search.setVisible(not empty)
        top = 50 if self._compact else 70
        text_bottom = top + int((36 if self._compact else 46) * 2.5) + 10 + 44  # under the headline and the size line
        self.search.setGeometry(MARGIN, text_bottom + 14, left_w, 40)
        chip_x, chip_y = MARGIN, self.search.geometry().bottom() + 16
        for button in self._chip_buttons:
            hint = button.sizeHint()
            if chip_x + hint.width() > MARGIN + left_w + 20:
                chip_x, chip_y = MARGIN, chip_y + 38
            button.setGeometry(chip_x, chip_y, hint.width(), 30)
            chip_x += hint.width() + 8
        self.add_folder_button.setVisible(empty)
        self.calibre_button.setVisible(empty)
        self.add_folder_button.setGeometry(MARGIN, text_bottom + 14, 190, 40)
        self.calibre_button.setGeometry(MARGIN + 202, text_bottom + 14, 160, 40)

        # Cards standing on the ledge (right side).
        show_author, show_recent = self._author is not None and not empty, bool(self._recent) and not self._compact
        card_h = int(g["hero_h"] * 0.74)
        recent_x = w - MARGIN - CARD_W
        author_x = (recent_x - 60 - CARD_W) if show_recent else (w - MARGIN - CARD_W)
        self._author_rect = QRectF(author_x, ledge_y - card_h, CARD_W, card_h)
        self._recent_rect = QRectF(recent_x, ledge_y - card_h, CARD_W, card_h)
        self._label_author.setVisible(show_author)
        self._label_recent.setVisible(show_recent)
        self._label_author.move(int(author_x) - self._label_author.width() - 6, ledge_y - self._label_author.height())
        self._label_recent.move(int(recent_x) - self._label_recent.width() - 6, ledge_y - self._label_recent.height())
        self.author_link.setVisible(show_author)
        self.author_link.setGeometry(int(author_x) + 14, int(self._author_rect.top()) + 64, CARD_W - 28, 24)
        for button in (self.prev_button, self.next_button, self.read_button):
            button.setVisible(show_recent)
        by = int(self._recent_rect.bottom()) - 46
        self.prev_button.setGeometry(int(recent_x) + 14, by + 4, 26, 30)
        self.read_button.setGeometry(int(recent_x) + CARD_W // 2 - 19, by, 38, 38)
        self.next_button.setGeometry(int(recent_x) + CARD_W - 40, by + 4, 26, 30)

        # Under the ledge.
        items_y = ledge_y + g["ledge_t"] + 40
        item_w = min(300, max(190, (w - 150 - 150) // max(1, g["n_items"])))
        self._items_y, self._item_w = items_y, item_w
        self._label_new.setVisible(bool(self._new_docs))
        self._label_new.move(74, items_y + 4)
        for index, button in enumerate(self._read_buttons):
            visible = index < g["n_items"]
            button.setVisible(visible)
            button.setGeometry(150 + index * item_w + 128 + 18, items_y + 96, 62, 32)
        self.all_link.setVisible(not empty)
        self.all_link.adjustSize()
        self.all_link.move(w - MARGIN - self.all_link.width(), h - 46)

    # -- painting -----------------------------------------------------------------------------------------------------
    def _font(self, role: str, size: int, weight: int = 400, italic: bool = False) -> QFont:
        font = QFont(theme_manager().font_family(role))
        font.setPixelSize(size)
        font.setWeight(QFont.Weight(weight))
        font.setItalic(italic)
        return font

    def paintEvent(self, _event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        g = self._geometry()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        self._hits = []
        self._paint_headline(painter, g, tm)
        self._paint_ledge(painter, g, tm)
        if self._total == 0:
            self._paint_empty(painter, g, tm)
        else:
            self._paint_hero(painter, g, tm)
            if self._author is not None:
                self._paint_author_card(painter, tm)
            if self._recent and not self._compact:
                self._paint_recent_card(painter, tm)
            self._paint_new_items(painter, g, tm)
        painter.end()

    def _paint_headline(self, painter: QPainter, g: dict, tm) -> None:
        empty = self._total == 0
        size = 36 if self._compact else 46
        painter.setFont(self._font("content", size, 500))
        painter.setPen(QColor(tm.token("ink")))
        title = "Thư viện\nđang trống" if empty else "Đọc tiếp &\nMới thêm"
        top = 70 if not self._compact else 50
        painter.drawText(QRect(MARGIN, top, min(400, int(g["w"] * 0.28)), int(size * 2.5)), Qt.AlignLeft | Qt.AlignTop, title)
        painter.setFont(self._font("ui", 14))
        painter.setPen(QColor(tm.token("ink2")))
        sub = ("Thêm thư mục sách để Mèo bắt đầu sắp xếp giúp bạn."
               if empty else f"{self._total:,} tài liệu, tất cả nằm trên máy bạn".replace(",", "."))
        y = top + int(size * 2.5) + 10
        painter.drawText(QRect(MARGIN, y, min(400, int(g["w"] * 0.28)), 40), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, sub)

    def _paint_ledge(self, painter: QPainter, g: dict, tm) -> None:
        y, t, w = g["ledge_y"], g["ledge_t"], g["w"]
        shadow = QLinearGradient(0, y + t, 0, y + t + 30)
        under = tm.color("under")
        shadow.setColorAt(0, under)
        clear = QColor(under)
        clear.setAlpha(0)
        shadow.setColorAt(1, clear)
        painter.fillRect(QRect(0, y + t, w, 30), shadow)
        board = QLinearGradient(0, y, 0, y + t)
        board.setColorAt(0, tm.color("shelftop"))
        board.setColorAt(1, tm.color("shelf"))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, y, w, t), t / 2, t / 2)
        painter.fillPath(path, board)

    def _paint_hero(self, painter: QPainter, g: dict, tm) -> None:
        if not self._hero:
            return
        x, y, cw, ch = g["hero_x"], g["hero_y"], g["hero_w"], g["hero_h"]
        painter.setFont(self._font("content", 13, 400, True))
        painter.setPen(QColor(tm.token("ink2")))
        painter.drawText(QRect(x - 30, y - 30, cw + 60, 20), Qt.AlignHCenter | Qt.AlignVCenter, self._hero_caption)
        rect = QRectF(x, y, cw, ch)
        draw_cover(painter, rect, self._hero, radius=float(tm.metric("cover_radius", 3)), dpr=self.devicePixelRatioF())
        self._paint_format_chip(painter, rect, self._hero)
        self._hits.append((rect, "open", self._hero))

    def _paint_format_chip(self, painter: QPainter, cover: QRectF, doc: dict) -> None:
        extension = (doc.get("extension") or "").upper()
        if not extension:
            return
        font = self._font("ui", 10, 700)
        metrics = QFontMetrics(font)
        chip = QRectF(cover.left() + 6, cover.top() + 6, metrics.horizontalAdvance(extension) + 12, 16)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRoundedRect(chip, 8, 8)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(chip, Qt.AlignCenter, extension)
        painter.restore()

    def _paint_author_card(self, painter: QPainter, tm) -> None:
        card, info = self._author_rect, self._author
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(card, 18, 18)
        painter.setClipPath(clip)
        painter.fillPath(clip, QColor(tm.token("accent")))
        ink = QColor(tm.token("accentink"))
        painter.setPen(ink)
        size = 17
        while size > 12 and QFontMetrics(self._font("content", size, 600)).horizontalAdvance(info["author"]) > card.width() - 28:
            size -= 1  # a long name gets a smaller type before it gets an ellipsis
        name_font = self._font("content", size, 600)
        painter.setFont(name_font)
        painter.drawText(QRectF(card.left() + 14, card.top() + 14, card.width() - 28, 24), Qt.AlignLeft | Qt.AlignVCenter,
                         QFontMetrics(name_font).elidedText(info["author"], Qt.ElideRight, int(card.width() - 28)))
        painter.setFont(self._font("ui", 12))
        books = info["books"]
        painter.drawText(QRectF(card.left() + 14, card.top() + 40, card.width() - 28, 18), Qt.AlignLeft | Qt.AlignVCenter,
                         f"{books} tài liệu")
        covers = info["cover_paths"]
        for index, path in enumerate(covers[:3]):  # a small fan of covers at the foot of the card
            doc = {"id": f"author-{index}-{path}", "cover_path": path, "title": "", "author": ""}
            painter.save()
            painter.translate(card.left() + 34 + index * 34, card.bottom() - 6)
            painter.rotate(-10 + index * 10)
            draw_cover(painter, QRectF(-27, -80, 54, 80), doc, radius=2, shadow=False, dpr=self.devicePixelRatioF())
            painter.restore()
        painter.restore()
        self._author_link_style(tm)

    def _paint_recent_card(self, painter: QPainter, tm) -> None:
        card = self._recent_rect
        doc = self._recent[self._recent_index]
        painter.save()
        painter.setPen(QPen(QColor(tm.token("line")), 1))
        painter.setBrush(QColor(tm.token("surface")))
        painter.drawRoundedRect(card, 18, 18)
        painter.setPen(QColor(tm.token("ink")))
        title_font = self._font("ui", 13, 700)
        painter.setFont(title_font)
        painter.drawText(QRectF(card.left() + 12, card.top() + 12, card.width() - 24, 34), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                         QFontMetrics(title_font).elidedText(doc.get("title") or "", Qt.ElideRight, int(card.width() - 24) * 2))
        painter.setFont(self._font("ui", 12))
        painter.setPen(QColor(tm.token("ink2")))
        painter.drawText(QRectF(card.left() + 12, card.top() + 48, card.width() - 24, 16), Qt.AlignHCenter | Qt.AlignVCenter,
                         QFontMetrics(self._font("ui", 12)).elidedText(doc.get("author") or "", Qt.ElideRight, int(card.width() - 24)))
        disc = QRectF(card.center().x() - 32, card.top() + 72, 64, 64)  # round cover
        clip = QPainterPath()
        clip.addEllipse(disc)
        painter.setClipPath(clip)
        painter.drawPixmap(disc.topLeft(), cover_pixmap(doc, 64, width=64, dpr=self.devicePixelRatioF()))
        painter.setClipping(False)
        position, total = int(doc.get("position") or 0), int(doc.get("total") or 0)
        bar = QRectF(card.left() + 14, disc.bottom() + 16, card.width() - 28, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tm.token("line2")))
        painter.drawRoundedRect(bar, 2, 2)
        fraction = min(1.0, position / total) if total else 0.0
        painter.setBrush(QColor(tm.token("accent")))
        painter.drawRoundedRect(QRectF(bar.left(), bar.top(), max(4.0, bar.width() * fraction), 4), 2, 2)
        painter.drawEllipse(QPointF(bar.left() + bar.width() * fraction, bar.center().y()), 4.5, 4.5)
        painter.setFont(self._font("ui", 10))
        painter.setPen(QColor(tm.token("ink3")))
        unit = "chương" if doc.get("unit") == "chapter" else "trang"
        painter.drawText(QRectF(bar.left(), bar.bottom() + 4, 80, 14), Qt.AlignLeft, f"{unit} {position}" if position else "")
        painter.drawText(QRectF(bar.right() - 60, bar.bottom() + 4, 60, 14), Qt.AlignRight, str(total) if total else "")
        painter.restore()

    def _paint_new_items(self, painter: QPainter, g: dict, tm) -> None:
        count = g["n_items"]
        for index, doc in enumerate(self._new_docs[:count]):
            x, y = 150 + index * self._item_w, self._items_y
            rect = QRectF(x, y, 100, 142)
            draw_cover(painter, rect, doc, radius=2, dpr=self.devicePixelRatioF())
            self._paint_format_chip(painter, rect, doc)
            self._hits.append((rect, "open", doc))
            tx = x + 118
            width = self._item_w - 130
            rating = doc.get("avg_rating")
            ty = y + 2
            if rating:
                stars = max(0, min(5, round(float(rating))))
                painter.setFont(self._font("ui", 10))
                painter.setPen(QColor(tm.token("accent")))
                painter.drawText(QRectF(tx, ty, width, 12), Qt.AlignLeft, "★" * stars + "☆" * (5 - stars))
                ty += 16
            title_font = self._font("ui", 13, 600)
            painter.setFont(title_font)
            painter.setPen(QColor(tm.token("ink")))
            painter.drawText(QRectF(tx, ty, width, 36), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                             QFontMetrics(title_font).elidedText(doc.get("title") or "", Qt.ElideRight, int(width) * 2 - 20))
            painter.setFont(self._font("ui", 12))
            painter.setPen(QColor(tm.token("ink2")))
            author = doc.get("author") or ""
            if author and author.strip().lower() != "unknown":
                painter.drawText(QRectF(tx, ty + 38, width, 16), Qt.AlignLeft,
                                 QFontMetrics(self._font("ui", 12)).elidedText(author, Qt.ElideRight, int(width)))
        if len(self._new_docs) > count and not self._compact:  # the tilted cover half out of the window: "there is more"
            doc = self._new_docs[count]
            painter.save()
            painter.translate(150 + count * self._item_w + 40, self._items_y - 8)
            painter.rotate(6)
            draw_cover(painter, QRectF(0, 0, 100, 142), doc, radius=2, dpr=self.devicePixelRatioF())
            painter.restore()

    def _paint_empty(self, painter: QPainter, g: dict, tm) -> None:
        pixmap = mascot_pixmap("waiting", g["hero_h"], self.devicePixelRatioF())
        if pixmap is not None:
            width = pixmap.width() / max(1.0, self.devicePixelRatioF())
            painter.drawPixmap(QPointF(g["hero_x"] + 40, g["ledge_y"] - pixmap.height() / max(1.0, self.devicePixelRatioF()) + 4), pixmap)
            del width
        steps = (("Thêm thư mục sách", "Chọn thư mục đang chứa sách; Mèo quét và giữ nguyên file của bạn."),
                 ("Nhập từ Calibre", "Mèo chỉ đọc thư viện Calibre của bạn, không sửa gì trong đó."),
                 ("Kéo thả vào cửa sổ", "Thả file hoặc thư mục vào đây để thêm ngay."))
        card_w = min(300, (g["w"] - 2 * MARGIN - 40) // 3)
        for index, (title, text) in enumerate(steps):
            rect = QRectF(MARGIN + index * (card_w + 20), self._items_y - 4, card_w, 120)
            painter.setPen(QPen(QColor(tm.token("line")), 1))
            painter.setBrush(QColor(tm.token("surface2")))
            painter.drawRoundedRect(rect, 18, 18)
            painter.setPen(QColor(tm.token("accent")))
            painter.setFont(self._font("content", 22, 600))
            painter.drawText(QRectF(rect.left() + 16, rect.top() + 10, 30, 30), Qt.AlignLeft, str(index + 1))
            painter.setPen(QColor(tm.token("ink")))
            painter.setFont(self._font("ui", 14, 700))
            painter.drawText(QRectF(rect.left() + 16, rect.top() + 44, rect.width() - 32, 20), Qt.AlignLeft, title)
            painter.setPen(QColor(tm.token("ink2")))
            painter.setFont(self._font("ui", 12))
            painter.drawText(QRectF(rect.left() + 16, rect.top() + 68, rect.width() - 32, 44), Qt.AlignLeft | Qt.TextWordWrap, text)

    # -- style --------------------------------------------------------------------------------------------------------
    def _author_link_style(self, tm) -> None:
        self.author_link.setStyleSheet(
            f"QPushButton {{ color: {tm.token('accentink')}; background: transparent; border: none; text-align: left;"
            f" text-decoration: underline; font-size: 12px; }}")

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        radius = int(min(int(tm.metric("control_radius", 6)), 20))
        self.setStyleSheet(
            f"#HomePage {{ background: transparent; }}"
            f" QLineEdit {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')};"
            f" border-radius: {radius}px; min-height: 38px; padding: 0 14px; }}"
            f" QPushButton[chip=\"true\"] {{ background: {tm.token('surface2')}; color: {tm.token('ink')}; border: none;"
            f" border-radius: {radius}px; min-height: 30px; padding: 0 14px; font-size: 12px; font-weight: 600; }}"
            f" QPushButton[chip=\"true\"]:hover {{ background: {tm.token('accentsoft')}; }}"
            f" QPushButton[role=\"outline\"] {{ background: transparent; border: 1px solid {tm.token('line2')};"
            f" border-radius: {radius}px; min-height: 30px; padding: 0 12px; font-weight: 600; }}"
            f" QPushButton[role=\"outline\"]:hover {{ border-color: {tm.token('accent')}; }}"
            f" QPushButton[flat=\"true\"], QPushButton:flat {{ background: transparent; border: none; color: {tm.token('link')};"
            f" text-decoration: underline; min-height: 24px; padding: 0 4px; }}"
            f" QToolButton {{ border: none; background: transparent; border-radius: 19px; }}"
        )
        self.prev_button.setIcon(line_icon("chevron_left", tm.token("ink2"), 14))
        self.next_button.setIcon(line_icon("chevron_right", tm.token("ink2"), 14))
        self.read_button.setIcon(line_icon("book", tm.token("accentink"), 16))
        self.read_button.setStyleSheet(f"QToolButton {{ background: {tm.token('ink')}; border-radius: 19px; }}")
        self._author_link_style(tm)
        self.update()
