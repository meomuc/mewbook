"""The sidebar's filter section: hashtags, authors and formats.

Replaces the old faceted tree (see docs/FILTER_REDESIGN_SPEC.md). What changed
and why:

* One click means "show me this" (it replaces that group's selection and keeps
  the other groups); Ctrl/Shift+click -- or "Thêm vào lựa chọn" in the
  right-click menu -- adds to the selection. There is no double click.
* Counts are live: each one is "how many documents if I pick this", given
  everything else selected, and choices that would show nothing disappear.
* Few-valued groups (hashtags, formats) are wrapping chips; the long one
  (authors -- thousands) shows the top few plus a searchable "Xem tất cả".
* Refreshes update widgets in place instead of rebuilding a tree, so the panel
  no longer jumps or loses its scroll position.
* Everything goes through context.filters, so the "Đang lọc" bar, the search
  box and the detail panel always agree with what is highlighted here.

Folders the user made (facet_groups) show as "" entries that select all their
members at once; right-click manages them as before.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import FilterChangedEvent, LibraryUpdatedEvent
from smartdoc.domain.library_filter import (
    AUTHORS,
    FORMATS,
    MODE_GO,
    MODE_TOGGLE,
    TAGS,
    LibraryFilter,
    value_key,
)
from smartdoc.domain.author_names import NO_TAG, UNKNOWN_AUTHOR
from smartdoc.presentation.author_cleanup_dialog import AuthorCleanupDialog
from smartdoc.presentation.facet_picker_dialog import FacetPickerDialog
from smartdoc.presentation.flow_widget import FlowWidget
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.quick_filter import QuickFilterBox
from smartdoc.presentation.sidebar_style import ROW_HEIGHT, CountRowDelegate, section_font
from smartdoc.presentation.theme import current_colors, section_text
from smartdoc.presentation.theme_manager import theme_manager

TAG_CHIP_LIMIT = 14
AUTHOR_ROW_LIMIT = 8

SORT_BY_COUNT = "count"
SORT_BY_NAME = "name"
_SORT_LABELS = {SORT_BY_COUNT: "Số tài liệu (nhiều → ít)", SORT_BY_NAME: "Tên (A → Z)"}

# Which key facet folders are stored under (see database.FACET_CATEGORIES).
_GROUP_CATEGORY = {TAGS: "tag", AUTHORS: "author", FORMATS: "extension"}
_SECTIONS = ((TAGS, "Hashtag"), (AUTHORS, "Tác giả"), (FORMATS, "Định dạng"))
HINT_TEXT = "Nhấp: chuyển tới mục đó · Ctrl+nhấp: chọn thêm"


@dataclass
class _Entry:
    """One selectable line: a single value, or a user folder of several."""

    value: str
    label: str
    count: int
    selected: bool = False
    group_id: str | None = None  # set on folder entries
    members: tuple[str, ...] = ()
    in_group: str | None = None  # the folder a plain value is filed under
    bucket: bool = False  # "Chưa phân loại" / "Không rõ": not a real name, can't be renamed


def _dot_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(5, 5, 6, 6)
    painter.end()
    return QIcon(pixmap)


def _fmt(count: int) -> str:
    return f"{count:,}".replace(",", ".")


class _Section(QWidget):
    """A heading you can fold, with an optional "⋯" menu, above its content."""

    def __init__(self, key: str, title: str, panel: "FacetPanel") -> None:
        super().__init__(panel)
        self.key = key
        self.title = title
        self._panel = panel
        self._badge = 0

        self.header = QToolButton(self)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.header.setFont(section_font(self.header.font()))
        self.header.setAutoRaise(True)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setLayoutDirection(Qt.RightToLeft)  # the fold chevron sits at the right end
        self.header.clicked.connect(self.toggle)
        self.menu_button = QToolButton(self)
        self.menu_button.setText("⋯")
        self.menu_button.setToolTip("Sắp xếp, tạo nhóm")
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setAutoRaise(True)
        self.menu_button.clicked.connect(lambda: panel._show_section_menu(key, self.menu_button))
        self.menu_button.setVisible(key != FORMATS)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(4)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.header)
        head.addStretch(1)
        head.addWidget(self.menu_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(2)
        layout.addLayout(head)
        layout.addWidget(self.body)
        self.refresh_header()

    @property
    def collapsed(self) -> bool:
        return self.key in self._panel.collapsed_sections

    def toggle(self) -> None:
        self._panel.set_section_collapsed(self.key, not self.collapsed)

    def set_badge(self, selected: int) -> None:
        self._badge = selected
        self.refresh_header()

    def refresh_header(self) -> None:
        badge = f"  ·  {self._badge}" if self._badge else ""
        self.header.setText(f"{section_text(self.title)}{badge}")
        self.header.setIcon(line_icon("chevron_right" if self.collapsed else "chevron_down", theme_manager().token("ink3"), 12))
        self.body.setVisible(not self.collapsed)


class FacetPanel(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.collapsed_sections: set[str] = set(context.config.config.collapsed_filter_sections)
        self._sort_keys = {TAGS: SORT_BY_COUNT, AUTHORS: SORT_BY_COUNT, FORMATS: SORT_BY_COUNT}
        self._expanded: set[str] = set()  # sections showing every value, not just the top few
        self._chips: dict[str, dict[str, QPushButton]] = {TAGS: {}, FORMATS: {}}
        self._entries: dict[str, dict[str, _Entry]] = {TAGS: {}, AUTHORS: {}, FORMATS: {}}

        colors = current_colors()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("FacetPanel")
        self.setStyleSheet(
            f"#FacetPanel {{ background: {colors.sidebar_bg}; }}"
            f" QToolButton {{ border: none; color: {colors.muted_text}; background: transparent; padding: 2px 4px; }}"
            f" QToolButton:hover {{ color: {colors.accent}; }}"
            f" QPushButton#FacetChip {{ background: transparent; color: {colors.sidebar_text};"
            f" border: 1px solid {colors.border}; border-radius: 12px; padding: 0 10px; min-height: 22px; font-size: 12px; }}"
            f" QPushButton#FacetChip:hover {{ border-color: {colors.accent}; }}"
            f" QPushButton#FacetChip:checked {{ background: {colors.selected_bg}; color: {colors.selected_text};"
            f" border-color: {colors.selected_border}; font-weight: 600; }}"
            f" QPushButton#FacetMore {{ background: transparent; color: {colors.accent}; border: none;"
            f" text-align: left; padding: 2px 4px; }}"
            f" QPushButton#FacetMore:hover {{ text-decoration: underline; }}"
        )

        self.quick_filter = QuickFilterBox(context, self)

        self.sections: dict[str, _Section] = {}
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 0, 8, 8)
        content_layout.setSpacing(0)
        for key, title in _SECTIONS:
            section = _Section(key, title, self)
            self.sections[key] = section
            content_layout.addWidget(section)
        content_layout.addStretch(1)

        self._build_tag_section()
        self._build_author_section()
        self._build_format_section()

        scroll = QScrollArea(self)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        self.scroll_area = scroll

        # The click rules are a tooltip, not a permanent paragraph: the sidebar stays quiet (design rule).
        self.quick_filter.setToolTip(HINT_TEXT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.quick_filter)
        layout.addWidget(scroll, stretch=1)

        self._refresh_timer = debounced(self, self.refresh)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)

        self.refresh()

    # -- construction -----------------------------------------------------------

    def _make_more_button(self) -> QPushButton:
        button = QPushButton(self)
        button.setObjectName("FacetMore")
        button.setCursor(Qt.PointingHandCursor)
        button.setFlat(True)
        button.hide()
        return button

    def _build_cloud(self, category: str) -> FlowWidget:
        cloud = FlowWidget(self, h_spacing=5, v_spacing=5)
        self.sections[category].body_layout.addWidget(cloud)
        return cloud

    def _build_tag_section(self) -> None:
        self.tag_cloud = self._build_cloud(TAGS)
        self.tags_more = self._make_more_button()
        self.tags_more.clicked.connect(lambda: self._toggle_expanded(TAGS))
        self.sections[TAGS].body_layout.addWidget(self.tags_more)

    def _build_author_section(self) -> None:
        rows = QListWidget(self)
        rows.setItemDelegate(CountRowDelegate(rows))
        rows.setMouseTracking(True)
        rows.setSelectionMode(QAbstractItemView.NoSelection)
        rows.setFocusPolicy(Qt.NoFocus)
        rows.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rows.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rows.setFrameShape(QFrame.NoFrame)
        colors = current_colors()
        rows.setStyleSheet(f"QListWidget {{ border: none; outline: 0; background: transparent; color: {colors.sidebar_text}; }}")
        rows.itemClicked.connect(self._on_author_row_clicked)
        rows.setContextMenuPolicy(Qt.CustomContextMenu)
        rows.customContextMenuRequested.connect(self._on_author_row_menu)
        self.author_rows = rows
        self.sections[AUTHORS].body_layout.addWidget(rows)
        self.authors_more = self._make_more_button()
        self.authors_more.clicked.connect(self.open_author_picker)
        self.sections[AUTHORS].body_layout.addWidget(self.authors_more)

    def _build_format_section(self) -> None:
        self.format_cloud = self._build_cloud(FORMATS)

    # -- events -------------------------------------------------------------------

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, FilterChangedEvent):
            self.refresh()  # a selection change: show it straight away
        else:
            self._refresh_timer.start()  # imports fire one event per file

    def set_section_collapsed(self, key: str, collapsed: bool) -> None:
        if collapsed:
            self.collapsed_sections.add(key)
        else:
            self.collapsed_sections.discard(key)
        self.context.config.config.collapsed_filter_sections = sorted(self.collapsed_sections)
        self.context.config.save()
        self.sections[key].refresh_header()

    def _toggle_expanded(self, category: str) -> None:
        self._expanded.symmetric_difference_update({category})
        self.refresh()

    # -- building the entries ---------------------------------------------------------

    def _entries_for(self, category: str, flt: LibraryFilter) -> tuple[list[_Entry], list[_Entry], int]:
        """(folders, values, hidden) for one group: the folder entries; the
        values to show (top N, plus anything selected, plus the buckets); and how
        many were left out."""
        facets = self.context.facets
        counts = facets.counts(category, flt)
        group_key = _GROUP_CATEGORY[category]
        groups = self.context.db.list_facet_groups(group_key) if category != FORMATS else []
        filed: dict[str, str] = {}
        for group in groups:
            for member in group["members"]:
                filed[value_key(category, member)] = group["id"]

        folders: list[_Entry] = []
        for group in groups:
            members = tuple(group["members"])
            wanted = {value_key(category, m) for m in members}
            live = [c.value for c in counts if value_key(category, c.value) in wanted]
            count = facets.group_count(category, members, flt) if members else 0
            selected = bool(live) and all(flt.has_value(category, value) for value in live)
            if count or selected:
                folders.append(
                    _Entry(group["id"], group["name"], count, selected, group_id=group["id"], members=tuple(live or members))
                )

        if self._sort_keys[category] == SORT_BY_NAME:
            counts = sorted(counts, key=lambda c: (c.value in (UNKNOWN_AUTHOR, NO_TAG), c.label.casefold()))
        limit = {TAGS: TAG_CHIP_LIMIT, AUTHORS: AUTHOR_ROW_LIMIT}.get(category)
        shown: list[_Entry] = []
        hidden = 0
        real_shown = 0
        for choice in counts:
            entry = _Entry(
                choice.value,
                choice.label,
                choice.count,
                flt.has_value(category, choice.value),
                in_group=filed.get(value_key(category, choice.value)),
                bucket=choice.value in (UNKNOWN_AUTHOR, NO_TAG),
            )
            is_bucket = entry.bucket
            if limit is None or category in self._expanded or entry.selected or is_bucket or real_shown < limit:
                shown.append(entry)
                real_shown += 0 if is_bucket or entry.selected else 1
            else:
                hidden += 1
        return folders, shown, hidden

    def refresh(self) -> None:
        flt = self.context.filters.current
        for category, _title in _SECTIONS:
            folders, values, hidden = self._entries_for(category, flt)
            self._entries[category] = {e.value: e for e in (*folders, *values)}
            self.sections[category].set_badge(len(flt.values(category)))
            if category == AUTHORS:
                self._fill_author_rows(folders, values, hidden)
            else:
                self._fill_chips(category, folders, values, hidden)

    # -- chips (hashtags, formats) ------------------------------------------------------

    def _cloud_for(self, category: str) -> FlowWidget:
        return self.tag_cloud if category == TAGS else self.format_cloud

    def _fill_chips(self, category: str, folders: list[_Entry], values: list[_Entry], hidden: int) -> None:
        cloud = self._cloud_for(category)
        pool = self._chips[category]
        wanted = [*folders, *values]
        keep = {entry.value for entry in wanted}
        for stale in [v for v, button in pool.items() if v not in keep and not button.isHidden()]:
            pool[stale].hide()  # kept in the pool (never deleted): it is reused if the value comes back
        # Widgets are reused and only re-ordered, so a refresh doesn't flicker or lose hover state.
        ordered: list[QPushButton] = []
        for entry in wanted:
            button = pool.get(entry.value)
            if button is None:
                button = QPushButton(cloud)
                button.setObjectName("FacetChip")
                button.setCheckable(True)
                button.setCursor(Qt.PointingHandCursor)
                button.setContextMenuPolicy(Qt.CustomContextMenu)
                button.clicked.connect(lambda _c=False, c=category, v=entry.value: self._on_chip_clicked(c, v))
                button.customContextMenuRequested.connect(
                    lambda _pos, c=category, v=entry.value, b=button: self._show_entry_menu(c, v, b.mapToGlobal(_pos))
                )
                pool[entry.value] = button
            prefix = "📂 " if entry.group_id else ""
            button.setText(f"{prefix}{entry.label} · {_fmt(entry.count)}")
            button.setToolTip(
                "Không có tài liệu nào với các bộ lọc khác đang bật" if not entry.count else f"{_fmt(entry.count)} tài liệu"
            )
            button.setChecked(entry.selected)
            # A picked chip shows an accent dot as well as the accent border: not colour alone.
            button.setIcon(_dot_icon(theme_manager().token("accent")) if entry.selected else QIcon())
            button.show()
            ordered.append(button)
        cloud.set_widgets(ordered)
        if category == TAGS:
            self._set_more(self.tags_more, TAGS, hidden, "hashtag")

    def _set_more(self, button: QPushButton, category: str, hidden: int, noun: str) -> None:
        if category in self._expanded:
            button.setText("Thu gọn")
            button.show()
        elif hidden:
            button.setText(f"Xem thêm {_fmt(hidden)} {noun}…")
            button.show()
        else:
            button.hide()

    def _on_chip_clicked(self, category: str, value: str) -> None:
        self._apply(category, self._entries[category].get(value), value)

    # -- author rows ---------------------------------------------------------------------

    def _fill_author_rows(self, folders: list[_Entry], values: list[_Entry], hidden: int) -> None:
        rows = self.author_rows
        rows.clear()
        colors = current_colors()
        selected_brush = QBrush(QColor(colors.selected_bg))
        for entry in (*folders, *values):
            prefix = "📂 " if entry.group_id else ""
            item = QListWidgetItem(f"{prefix}{entry.label} ({entry.count})")
            item.setData(Qt.UserRole + 1, entry.value)
            item.setToolTip(f"{_fmt(entry.count)} tài liệu")
            if entry.selected:
                # The delegate draws any row with a background role as "selected".
                item.setBackground(selected_brush)
            rows.addItem(item)
        rows.setFixedHeight(max(rows.count(), 1) * ROW_HEIGHT + 4)
        if hidden:
            total = hidden + len([e for e in values if not e.bucket])
            self.authors_more.setText(f"Xem tất cả {_fmt(total)} tác giả…")
            self.authors_more.show()
        else:
            self.authors_more.hide()

    def _on_author_row_clicked(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.UserRole + 1)
        self._apply(AUTHORS, self._entries[AUTHORS].get(value), value)

    def _on_author_row_menu(self, position) -> None:
        item = self.author_rows.itemAt(position)
        if item is not None:
            self._show_entry_menu(AUTHORS, item.data(Qt.UserRole + 1), self.author_rows.viewport().mapToGlobal(position))

    def open_author_picker(self) -> None:
        FacetPickerDialog(self.context, AUTHORS, self).exec()

    # -- applying a click ------------------------------------------------------------------

    def _additive_click(self) -> bool:
        """Ctrl or Shift held: add to the selection instead of switching to this value."""
        return bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier))

    def _apply(self, category: str, entry: _Entry | None, value: str, *, additive: bool | None = None) -> None:
        additive = self._additive_click() if additive is None else additive
        filters = self.context.filters
        if entry is not None and entry.group_id:
            members = entry.members
            flt = filters.current
            all_selected = bool(members) and all(flt.has_value(category, m) for m in members)
            if additive:
                filters.set(
                    flt.with_values(category, [v for v in flt.values(category) if v not in members])
                    if all_selected
                    else flt.with_values(category, (*flt.values(category), *members))
                )
            elif all_selected and len(flt.values(category)) == len(members):
                filters.remove(category)
            else:
                filters.select_many(category, members)
            return
        filters.select(category, value, MODE_TOGGLE if additive else MODE_GO)

    # -- menus --------------------------------------------------------------------------------

    def _exec_menu(self, menu: QMenu, global_pos):
        """Thin seam so tests can patch this instead of QMenu.exec, which opens a
        real modal loop that hangs forever under an offscreen Qt platform."""
        return menu.exec(global_pos)

    def _show_section_menu(self, category: str, anchor: QWidget) -> None:
        menu = QMenu(self)
        actions: dict = {}
        sort_menu = menu.addMenu("Sắp xếp")
        for key, label in _SORT_LABELS.items():
            action = sort_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._sort_keys[category] == key)
            actions[action] = ("sort", key)
        actions[menu.addAction("Tạo nhóm mới...")] = ("new_group", None)
        if category == AUTHORS:
            actions[menu.addAction("Gợi ý dọn tên tác giả...")] = ("cleanup", None)
        chosen = self._exec_menu(menu, anchor.mapToGlobal(anchor.rect().bottomLeft()))
        if chosen is None or chosen not in actions:
            return
        command, arg = actions[chosen]
        if command == "sort":
            self._sort_keys[category] = arg
            self.refresh()
        elif command == "cleanup":
            AuthorCleanupDialog(self.context, self).exec()
            self.refresh()
        elif self._prompt_new_group(_GROUP_CATEGORY[category]):
            self.refresh()

    def _show_entry_menu(self, category: str, value: str, global_pos) -> None:
        entry = self._entries.get(category, {}).get(value)
        if entry is None:
            return
        category_key = _GROUP_CATEGORY[category]
        menu = QMenu(self)
        actions: dict = {}
        actions[menu.addAction("Thêm vào lựa chọn (Ctrl+nhấp)")] = ("add",)
        menu.addSeparator()

        if entry.group_id:
            actions[menu.addAction("Đổi tên nhóm...")] = ("rename_group",)
            actions[menu.addAction("Xóa nhóm (các mục bên trong được giữ lại)")] = ("delete_group",)
        elif category != FORMATS and not entry.bucket:
            # Formats come from the files themselves -- only the two metadata-backed groups can be edited.
            if category == AUTHORS:
                actions[menu.addAction("Đổi tên tác giả (cập nhật metadata)...")] = ("rename",)
            else:
                actions[menu.addAction("Đổi tên hashtag (cập nhật metadata)...")] = ("rename",)
                actions[menu.addAction("Xóa hashtag khỏi mọi tài liệu...")] = ("delete_tag",)
            move_menu = menu.addMenu("Chuyển vào nhóm")
            for group in self.context.db.list_facet_groups(category_key):
                if group["id"] != entry.in_group:
                    actions[move_menu.addAction(group["name"])] = ("move", group["id"])
            actions[move_menu.addAction("Nhóm mới...")] = ("move_new",)
            if entry.in_group:
                actions[menu.addAction("Bỏ khỏi nhóm")] = ("move", None)

        chosen = self._exec_menu(menu, global_pos)
        if chosen is None or chosen not in actions:
            return
        command, *args = actions[chosen]
        if command == "add":
            self._apply(category, entry, value, additive=True)
        elif command == "rename":
            self._rename_value(category, value)
        elif command == "delete_tag":
            self._delete_tag(value)
        elif command == "move":
            self.context.db.move_facet_value(category_key, value, args[0])
            self.refresh()
        elif command == "move_new":
            new_group = self._prompt_new_group(category_key)
            if new_group:
                self.context.db.move_facet_value(category_key, value, new_group)
                self.refresh()
        elif command == "rename_group":
            self._rename_group(entry.group_id, entry.label)
        elif command == "delete_group":
            self._delete_group(entry.group_id)

    def _prompt_new_group(self, category_key: str) -> str | None:
        name, accepted = QInputDialog.getText(self, "Tạo nhóm mới", "Tên nhóm:")
        name = name.strip()
        if not accepted or not name:
            return None
        return self.context.db.create_facet_group(category_key, name)

    def _rename_group(self, group_id: str, current: str) -> None:
        name, accepted = QInputDialog.getText(self, "Đổi tên nhóm", "Tên mới:", text=current)
        name = name.strip()
        if accepted and name and name != current:
            self.context.db.rename_facet_group(group_id, name)
            self.refresh()

    def _delete_group(self, group_id: str) -> None:
        confirm = QMessageBox.question(
            self,
            "Xóa nhóm",
            "Xóa nhóm này? Các mục bên trong sẽ trở lại danh sách chung -- không tài liệu nào bị thay đổi.",
        )
        if confirm == QMessageBox.Yes:
            self.context.db.delete_facet_group(group_id)
            self.refresh()

    def _rename_value(self, category: str, old_value: str) -> None:
        title = "Đổi tên tác giả" if category == AUTHORS else "Đổi tên hashtag"
        new_value, accepted = QInputDialog.getText(self, title, "Tên mới:", text=old_value)
        new_value = new_value.strip()
        if not accepted or not new_value or new_value == old_value:
            return
        if category == AUTHORS:
            changed = self.context.db.rename_person(old_value, new_value)
        else:
            changed = self.context.db.rename_tag(old_value, new_value)
        if changed:
            # The selection must follow the rename, or the library stays filtered on a value that no longer exists.
            flt = self.context.filters.current
            if flt.has_value(category, old_value):
                self.context.filters.set(flt.without(category, old_value).with_value(category, new_value, "add"))
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self.refresh()

    def _delete_tag(self, tag: str) -> None:
        confirm = QMessageBox.question(
            self, "Xóa hashtag", f"Xóa hashtag \"{tag}\" khỏi tất cả tài liệu đang có?\n\n(Các file không bị xóa.)"
        )
        if confirm != QMessageBox.Yes:
            return
        if self.context.db.delete_tag(tag):
            self.context.filters.remove(TAGS, tag)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self.refresh()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        for i, (author, tags, ext) in enumerate(
            [("Nhã Ca", "Thơ, Tiểu thuyết", "epub"), ("NHÃ CA", "Tiểu thuyết", "pdf"), ("Unknown", "", "epub")]
        ):
            context.db.add_or_update_document(
                f"d{i}",
                {"title": f"B{i}", "author": author, "file_path": f"{i}.{ext}", "extension": ext, "tags": tags, "created_at": float(i)},
            )
        app = QApplication(sys.argv)
        apply_light_theme(app)
        panel = FacetPanel(context)
        panel.resize(260, 520)
        panel.show()
        sys.exit(app.exec())
