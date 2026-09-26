# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small building blocks of the Settings window (stage G9): a page with a heading, a row (bold label and a grey
explanation on the left at 230 px, the control on the right), the "Sắp có" badge, the ▲/▼ explanation pair of the
performance page and the pill column.

Only layout lives here; every control keeps the name and behaviour it had before, so the settings logic stays in
`settings_dialog.py`.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

LABEL_W = 230
SOON_TEXT = "Sắp có"


def _grey(label: QLabel) -> QLabel:
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme_manager().token('ink2')}; font-size: 13px; background: transparent;")
    return label


def soon_badge(parent: QWidget | None = None) -> QLabel:
    """The little "Sắp có" tag: what carries it is disabled and has no behaviour behind it."""
    tm = theme_manager()
    badge = QLabel(SOON_TEXT, parent)
    badge.setObjectName("SoonBadge")
    badge.setStyleSheet(f"#SoonBadge {{ color: {tm.token('ink3')}; border: 1px solid {tm.token('line2')};"
                        f" border-radius: 9px; padding: 1px 8px; font-size: 12px; background: transparent; }}")
    return badge


class SettingsPage(QScrollArea):
    """A scrolling page: a serif heading, a one-line explanation, then rows separated by hairlines."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("SettingsPage")
        holder = QWidget()
        holder.setObjectName("SettingsPageBody")
        self.setWidget(holder)
        tm = theme_manager()
        self.title_label = QLabel(title, holder)
        self.title_label.setStyleSheet(f"font-family: {tm.token('content')}; font-size: 22px; font-weight: 600;"
                                       f" color: {tm.token('ink')}; background: transparent;")
        self.subtitle_label = _grey(QLabel(subtitle, holder))
        self.subtitle_label.setVisible(bool(subtitle))
        self.rows = QVBoxLayout()
        self.rows.setSpacing(0)
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(4)
        outer.addWidget(self.title_label)
        outer.addWidget(self.subtitle_label)
        outer.addSpacing(10)
        outer.addLayout(self.rows)
        outer.addStretch(1)
        self._count = 0

    def add_row(self, label: str, description: str, control: QWidget | None = None, *, soon: bool = False,
                extra: QWidget | None = None) -> QFrame:
        """One setting: `label` and `description` on the left, `control` (and an optional `extra` block under it, for a
        list or a note) on the right. `soon` greys it out and adds the badge."""
        tm = theme_manager()
        row = QFrame(self)
        row.setObjectName("SettingRow")
        border = f"border-top: 1px solid {tm.token('line')};" if self._count else ""
        row.setStyleSheet(f"#SettingRow {{ {border} background: transparent; }}")
        name = QLabel(label, row)
        name.setStyleSheet(f"font-weight: 600; color: {tm.token('ink')}; background: transparent;")
        name.setWordWrap(True)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(name, 0, Qt.AlignTop)
        if soon:
            head.addWidget(soon_badge(row), 0, Qt.AlignTop)
        head.addStretch(1)
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addLayout(head)
        if description:
            left.addWidget(_grey(QLabel(description, row)))
        left.addStretch(1)
        left_holder = QWidget(row)
        left_holder.setFixedWidth(LABEL_W)
        left_holder.setLayout(left)
        right = QVBoxLayout()
        right.setSpacing(8)
        if control is not None:
            # A lone button keeps its natural width instead of stretching across the page.
            right.addWidget(control, 0, Qt.AlignLeft if isinstance(control, QPushButton) else Qt.Alignment())
        if extra is not None:
            right.addWidget(extra)
        right.addStretch(1)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(24)
        layout.addWidget(left_holder, 0, Qt.AlignTop)
        layout.addLayout(right, 1)
        if soon:
            for widget in row.findChildren(QWidget):
                if widget is not name and widget.objectName() != "SoonBadge" and not isinstance(widget, QLabel):
                    widget.setEnabled(False)
            row.setEnabled(False)
        self.rows.addWidget(row)
        self._count += 1
        return row

    def add_block(self, widget: QWidget) -> None:
        """A full-width block (a note, a panel) between rows."""
        self.rows.addWidget(widget)


def hint_pair(more: str, less: str, parent: QWidget | None = None) -> QLabel:
    """The two plain-words lines under a performance option: what raising it does, and what lowering it does."""
    tm = theme_manager()
    grey = tm.token("ink3")
    label = QLabel(f"<span style='color:{grey}'>▲</span> {more}<br><span style='color:{grey}'>▼</span> {less}", parent)
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 13px; background: transparent;")
    return label


class PillList(QListWidget):
    """The left column of Settings: one pill per page (a line icon and the name in capitals)."""

    page_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsPills")
        self.setFrameShape(QFrame.NoFrame)
        self.setSpacing(5)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedWidth(232)
        self.currentRowChanged.connect(self.page_selected)
        theme_manager().themeChanged.connect(self._restyle)
        self._entries: list[tuple[str, str]] = []
        self.itemSelectionChanged.connect(self._recolour_icons)
        self._restyle()

    def add_page(self, icon: str, name: str) -> None:
        self._entries.append((icon, name))
        item = QListWidgetItem(name.upper())
        item.setSizeHint(QSize(200, 34))
        self.addItem(item)
        self._recolour_icons()

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#SettingsPills {{ background: {tm.token('rail')}; padding: 8px 8px; outline: 0; }}"
            f" #SettingsPills::item {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
            f" border-radius: 6px; padding: 4px 8px; color: {tm.token('ink')}; font-size: 12px; }}"
            f" #SettingsPills::item:selected {{ background: {tm.token('accent')}; color: {tm.token('accentink')};"
            f" border-color: {tm.token('accent')}; }}"
            f" #SettingsPills::item:hover:!selected {{ border-color: {tm.token('ink3')}; }}"
        )
        self._recolour_icons()

    def _recolour_icons(self) -> None:
        tm = theme_manager()
        for row, (icon, _name) in enumerate(self._entries):
            item = self.item(row)
            if item is not None:
                item.setIcon(line_icon(icon, tm.token("accentink") if item.isSelected() else tm.token("ink2"), 14))


class ThemeCard(QFrame):
    """One of the seven theme cards: a tiny shelf drawn in the theme's own colours, its name and "Nền sáng/tối"."""

    chosen = Signal(str)

    def __init__(self, key: str, name: str, caption: str, parent: QWidget | None = None, *, tokens: dict | None = None) -> None:
        super().__init__(parent)
        from smartdoc.presentation.theme_manager import load_tokens, token_key_for

        self.key = key
        # `tokens`: the theme composed for the layout being chosen (a layout may retune colours), else the plain theme.
        self._tokens = tokens if tokens is not None else load_tokens().get(token_key_for(key), {})
        self._selected = False
        self.setFixedSize(150, 138)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.name = name
        self.caption = caption
        self.setAccessibleName(f"{name}, {caption}")

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override (a flow layout asks every child for it)
        return QSize(150, 138)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self.chosen.emit(self.key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.chosen.emit(self.key)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 -- Qt override
        from PySide6.QtGui import QColor, QPainter, QPen

        from smartdoc.presentation.theme_manager import parse_color

        tm = theme_manager()
        tokens = self._tokens

        def colour(name: str, fallback: str = "#888888") -> QColor:
            return parse_color(tokens.get(name, fallback))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outer = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(tm.color("accent") if self._selected else tm.color("line"), 2 if self._selected else 1))
        painter.setBrush(tm.color("surface"))
        painter.drawRoundedRect(outer, 8, 8)
        # The little shelf: the theme's own background, three books and the plank.
        art = outer.adjusted(1, 1, -1, -(outer.height() - 70))
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour("bg"))
        painter.drawRoundedRect(art, 7, 7)
        painter.drawRect(art.adjusted(0, 10, 0, 0))
        base = art.bottom() - 10
        for x, height, brush in ((art.left() + 14, 40, colour("accent")), (art.left() + 42, 32, colour("ink")),
                                 (art.left() + 68, 46, colour("surface2"))):
            painter.setBrush(brush)
            painter.drawRoundedRect(x, base - height, 22, height, 2, 2)
        painter.setBrush(colour("shelf"))
        painter.drawRect(art.left() + 6, base, art.width() - 12, 4)
        # Name and light/dark caption under the picture.
        painter.setPen(tm.color("ink"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        prefix = "✓ " if self._selected else ""
        painter.drawText(outer.adjusted(10, 74, -8, -30), Qt.AlignLeft | Qt.TextWordWrap, prefix + self.name)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(tm.color("ink3"))
        painter.drawText(outer.adjusted(10, 0, -8, -8), Qt.AlignLeft | Qt.AlignBottom, self.caption)


class LayoutCard(QFrame):
    """One layout ("kiểu giao diện") to pick: a thumbnail of the window's shape drawn from the layout's own metrics and
    the colours of its default theme (no picture files, so a new layout package needs no artwork)."""

    chosen = Signal(str)

    def __init__(self, key: str, name: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from smartdoc.presentation.layouts import compose_tokens, layout_for
        from smartdoc.presentation.theme_manager import load_tokens

        self.key = key
        self.name = name
        self.description = description
        self._spec = layout_for(key, any_shape=True)
        themes = load_tokens()
        default = self._spec.default_theme if self._spec.default_theme in themes else next(iter(themes))
        self._tokens = compose_tokens(themes[default], self._spec, default)
        self._selected = False
        self.setFixedSize(190, 168)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(description)
        self.setAccessibleName(f"{name}. {description}")

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        return QSize(190, 168)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self.chosen.emit(self.key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.chosen.emit(self.key)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 -- Qt override
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPen

        from smartdoc.presentation.theme_manager import parse_color

        tm = theme_manager()
        spec = self._spec

        def colour(name: str):
            return parse_color(self._tokens.get(name, "#888888"))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(tm.color("accent") if self._selected else tm.color("line"), 2 if self._selected else 1))
        painter.setBrush(tm.color("surface"))
        painter.drawRoundedRect(outer, 8, 8)
        art = QRectF(outer.left() + 6, outer.top() + 6, outer.width() - 12, 100)
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour("bg"))
        painter.drawRoundedRect(art, 6, 6)
        area = art.adjusted(6, 6, -6, -6)
        if spec.content_surface == "panel":  # the content sits on a rounded sheet inside the window ground
            radius = min(14.0, float(spec.metric("sheet_radius", 0)) * 0.55)
            painter.setBrush(colour("panel"))
            painter.drawRoundedRect(area, radius, radius)
            area = area.adjusted(6, 5, -6, -5)
        pill = float(spec.metric("control_radius", 0)) >= 100
        for i in range(3):  # the top bar's items
            painter.setBrush(colour("accent") if i == 0 else colour("surface2"))
            painter.drawRoundedRect(QRectF(area.left() + 4 + i * 26, area.top() + 2, 22, 7), 3.5 if pill else 1.5, 3.5 if pill else 1.5)
        base = area.bottom() - 10
        for x, height, brush in ((12, 34, colour("accent")), (40, 28, colour("ink")), (66, 38, colour("surface2"))):
            painter.setBrush(brush)
            painter.drawRoundedRect(QRectF(area.left() + x, base - height, 20, height), 2, 2)
        thick = max(3.0, float(spec.metric("ledge_thickness", 6)) / 3)
        overhang = 4.0 if spec.content_surface == "panel" else 0.0
        painter.setBrush(colour("shelf"))
        painter.drawRect(QRectF(area.left() + 2 - overhang, base, area.width() - 4 + 2 * overhang, thick))
        painter.setPen(tm.color("ink"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        prefix = "✓ " if self._selected else ""
        painter.drawText(outer.adjusted(10, 110, -8, -30).toRect(), Qt.AlignLeft | Qt.TextWordWrap, prefix + self.name)
        font.setBold(False)
        font.setPointSizeF(max(6.5, font.pointSizeF() - 1.5))
        painter.setFont(font)
        painter.setPen(tm.color("ink3"))
        painter.drawText(outer.adjusted(10, 128, -8, -6).toRect(), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.description)


def add_note_box(parent: QWidget, text: str, kind: str = "ok") -> QWidget:
    from smartdoc.presentation.design_dialog import note_box

    return note_box(parent, text, kind)
