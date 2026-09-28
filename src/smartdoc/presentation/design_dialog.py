# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shared frame of every dialog in the "Kệ sách" design, and the one template for dangerous actions.

Frame: a header (line icon, the title in the content face at 17 px / 600, a one-line subtitle, a × button), a body with
16 px margins, and a footer strip on the `surface2` colour -- notes or an "undo" link on the left, "Hủy" and the main
button on the right. The main button always says what it will do ("Áp dụng 4 mục", "Cập nhật 10 đường dẫn"), never "OK".

Dangerous actions (deleting files, restoring a backup, deleting a collection, merging authors) all go through
`DangerConfirmDialog`: it lists exactly what will happen, says what is NOT touched in a green box, and keeps the final
button locked until the person ticks "Tôi hiểu ...". The final button is outlined in the error colour until then... and
filled once unlocked, so it can never be pressed by habit.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

BODY_MARGIN = 16
HEADER_TITLE_PX = 17


class DesignDialog(QDialog):
    """See the module docstring. Subclasses add widgets to `self.body` and buttons with `add_footer_button`."""

    def __init__(self, parent=None, *, title: str, subtitle: str = "", icon: str | None = None,
                 width: int | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("DesignDialog")
        if width:
            self.setMinimumWidth(width)
            self.resize(width, self.height())
        self._icon_name = icon
        tm = theme_manager()

        self._icon_label = QLabel(self)
        self._icon_label.setFixedWidth(24)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("DialogTitle")
        self.subtitle_label = QLabel(subtitle, self)
        self.subtitle_label.setObjectName("DialogSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        # No close (×) button here: the window's own title bar already has one, and every dialog's footer already
        # has an explicit, labelled way out (Hủy / Đóng / Xong) -- a third way to do the same thing was one too many.
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        header = QHBoxLayout()
        header.setContentsMargins(BODY_MARGIN + 2, 14, 12, 12)
        header.setSpacing(10)
        header.addWidget(self._icon_label, 0, Qt.AlignTop)
        header.addLayout(titles, 1)
        self._header = QFrame(self)
        self._header.setObjectName("DialogHeader")
        self._header.setLayout(header)

        self.body_widget = QWidget(self)
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(BODY_MARGIN + 2, 8, BODY_MARGIN + 2, BODY_MARGIN)
        self.body.setSpacing(12)

        self._footer = QFrame(self)
        self._footer.setObjectName("DialogFooter")
        self._footer.setProperty("role", "dialogFooter")
        self.footer_left = QHBoxLayout()
        self.footer_left.setSpacing(12)
        self.footer_right = QHBoxLayout()
        self.footer_right.setSpacing(8)
        footer = QHBoxLayout(self._footer)
        footer.setContentsMargins(BODY_MARGIN + 2, 10, BODY_MARGIN + 2, 10)
        footer.addLayout(self.footer_left)
        footer.addStretch(1)
        footer.addLayout(self.footer_right)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header)
        outer.addWidget(self.body_widget, 1)
        outer.addWidget(self._footer)
        self._restyle()
        tm.themeChanged.connect(self._restyle)

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#DesignDialog {{ background: {tm.token('bg')}; }}"
            f" #DialogTitle {{ font-family: {tm.token('content')}; font-size: {HEADER_TITLE_PX}px; font-weight: 600;"
            f" color: {tm.token('ink')}; }}"
            f" #DialogSubtitle {{ color: {tm.token('ink2')}; font-size: 13px; }}"
            f" #DialogFooter {{ background: {tm.token('surface2')}; border-top: 1px solid {tm.token('line')}; }}"
            f" #DialogHeader {{ background: transparent; }}"
        )
        if self._icon_name:
            self._icon_label.setPixmap(line_icon(self._icon_name, tm.token("ink"), 20).pixmap(20, 20))

    # -- footer ------------------------------------------------------------------------------------------------------
    def add_footer_button(self, text: str, role: str = "default", *, on_click=None, left: bool = False) -> QPushButton:
        """A footer button; `role` is "default", "primary" (the filled main action), "danger" (outlined) or
        "dangerSolid". `on_click` defaults to nothing: connect it or use accept()/reject() yourself."""
        button = QPushButton(text, self)
        if role != "default":
            button.setProperty("role", role)
        if on_click is not None:
            button.clicked.connect(on_click)
        (self.footer_left if left else self.footer_right).addWidget(button)
        return button

    def add_footer_note(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("FooterNote")
        label.setStyleSheet(f"color: {theme_manager().token('ink3')}; font-size: 13px;")
        self.footer_left.addWidget(label)
        return label

    def add_footer_link(self, text: str, icon: str | None = None, on_click=None) -> QPushButton:
        button = QPushButton(text, self)
        button.setFlat(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(f"QPushButton {{ border: none; background: transparent; color: {theme_manager().token('ink')};"
                             f" padding: 0 4px; min-height: 24px; }} QPushButton:disabled {{ color: {theme_manager().token('ink3')}; }}")
        if icon:
            button.setIcon(line_icon(icon, theme_manager().token("ink2"), 14))
        if on_click is not None:
            button.clicked.connect(on_click)
        self.footer_left.addWidget(button)
        return button

    def add_note_box(self, text: str, kind: str = "ok", *, rich: bool = True) -> QFrame:
        """A framed line in the body: kind "ok" is the green "Không bị đụng tới..." box, "warn" the amber one."""
        return note_box(self, text, kind, rich=rich)


def note_box(parent: QWidget, text: str, kind: str = "ok", *, rich: bool = True) -> QFrame:
    tm = theme_manager()
    colour = tm.token("ok" if kind == "ok" else "warn")
    box = QFrame(parent)
    box.setObjectName("NoteBox")
    box.setStyleSheet(f"#NoteBox {{ background: {tm.token('surface')}; border: 1px solid {colour}; border-radius: 6px; }}")
    label = QLabel(text, box)
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setStyleSheet(f"color: {tm.token('ink')}; font-size: 13px; background: transparent;")
    mark = QLabel(box)
    mark.setPixmap(line_icon("check" if kind == "ok" else "warn", colour, 16).pixmap(16, 16))
    row = QHBoxLayout(box)
    row.setContentsMargins(12, 10, 12, 10)
    row.setSpacing(10)
    row.addWidget(mark, 0, Qt.AlignTop)
    row.addWidget(label, 1)
    box.label = label  # type: ignore[attr-defined]
    return box


class DangerConfirmDialog(DesignDialog):
    """"Xóa 2 file khỏi máy?": the template for every irreversible action. `items` are listed as plain lines,
    `safe_text` (HTML allowed) says what is not touched, `ack_text` is the sentence to tick, `action_text` labels the
    final button (locked until the box is ticked) and `cancel_text` the harmless one -- which is the default."""

    def __init__(self, parent=None, *, title: str, subtitle: str = "Bước xác nhận cuối", message: str,
                 items: list[str] | None = None, safe_text: str = "", ack_text: str, action_text: str,
                 cancel_text: str = "Không làm") -> None:
        super().__init__(parent, title=title, subtitle=subtitle, icon="warn", width=520)
        tm = theme_manager()
        self.message_label = QLabel(message, self)
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.RichText)
        self.body.addWidget(self.message_label)
        self.items_label: QLabel | None = None
        if items:
            box = QFrame(self)
            box.setObjectName("ItemsBox")
            box.setStyleSheet(f"#ItemsBox {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')};"
                              f" border-radius: 6px; }}")
            self.items_label = QLabel("\n".join(items), box)
            self.items_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.items_label.setWordWrap(True)
            self.items_label.setStyleSheet("background: transparent; font-size: 13px;")
            inner = QVBoxLayout(box)
            inner.setContentsMargins(12, 10, 12, 10)
            inner.addWidget(self.items_label)
            self.body.addWidget(box)
        self.safe_box = None
        if safe_text:
            self.safe_box = self.add_note_box(safe_text, "ok")
            self.body.addWidget(self.safe_box)
        self.ack_box = QCheckBox(ack_text, self)
        self.body.addWidget(self.ack_box)

        self.cancel_button = self.add_footer_button(cancel_text, on_click=self.reject)
        self.cancel_button.setDefault(True)
        self.confirm_button = self.add_footer_button(action_text, "danger", on_click=self.accept)
        self.confirm_button.setEnabled(False)
        self.ack_box.toggled.connect(self._on_ack_toggled)

    def _on_ack_toggled(self, checked: bool) -> None:
        self.confirm_button.setEnabled(checked)
        # Outlined while locked, filled once the person has said they understand.
        self.confirm_button.setProperty("role", "dangerSolid" if checked else "danger")
        self.confirm_button.style().unpolish(self.confirm_button)
        self.confirm_button.style().polish(self.confirm_button)


def confirm_danger(parent, **kwargs) -> bool:
    """Runs a DangerConfirmDialog; True only when the person ticked the box and pressed the final button."""
    dialog = DangerConfirmDialog(parent, **kwargs)
    accepted = dialog.exec() == QDialog.Accepted
    dialog.deleteLater()
    return accepted


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    demo = QApplication(sys.argv)
    theme_manager().apply(demo, "broadsheet")
    dlg = DangerConfirmDialog(
        title="Xóa 2 file khỏi máy?", message="Hai file dưới đây sẽ bị <b>xóa khỏi ổ cứng</b>. Không hoàn tác được.",
        items=["D:\\a.pdf – 12,4 MB", "E:\\b.pdf – 12,2 MB"], safe_text="<b>Không bị đụng tới:</b> bản bạn giữ lại.",
        ack_text="Tôi hiểu 2 file sẽ bị xóa vĩnh viễn", action_text="Xóa 2 file", cancel_text="Không xóa")
    dlg.exec()
