# SPDX-License-Identifier: AGPL-3.0-or-later
"""TagEditor's hint popup, end to end through real Qt events (task B1) -- tests/test_tag_hints.py already covers
`suggest_tags()` itself and drives the popup by calling its slots/eventFilter directly; these instead dispatch a
genuine mouse click and real key presses through Qt's own event system, and check the AC points that file does
not: the input keeps keyboard focus, and Esc leaves the typed text alone."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from smartdoc.presentation.tag_editor import TagEditor

KNOWN = {"văn-học": 40, "văn-hóa": 12, "lịch-sử": 30, "python": 25, "python-nâng-cao": 3}


def _editor(qapp):
    editor = TagEditor()
    editor.resize(320, 120)
    editor.show()
    editor.set_known_tags_source(lambda: dict(KNOWN))
    editor.set_tags(["python"])
    editor.add_button.click()
    editor.line_edit.setFocus()
    QTest.qWaitForWindowExposed(editor)
    return editor


def _type(editor, text):
    editor.line_edit.setText(text)
    editor.line_edit.textEdited.emit(text)  # what typing does


def test_clicking_a_hint_with_a_real_mouse_click_fills_the_box(qapp):
    editor = _editor(qapp)
    changes = []
    editor.changed.connect(changes.append)
    _type(editor, "van")
    popup = editor._popup
    assert popup.isVisible() and popup.count() == 2

    item = popup.item(1)  # "văn-hóa", the less-used one -- picking it must not just coincidentally match row 0
    QTest.mouseClick(popup.viewport(), Qt.LeftButton, Qt.NoModifier, popup.visualItemRect(item).center())

    assert editor.line_edit.text() == "văn-hóa"
    assert not popup.isVisible()
    editor._commit()
    assert changes == ["python,văn-hóa"]
    editor.deleteLater()


def test_the_input_keeps_keyboard_focus_after_picking_a_hint_by_click(qapp):
    """AC: "danh sách không cướp focus của ô nhập" -- the popup must never take it, including from a real click."""
    editor = _editor(qapp)
    _type(editor, "van")
    popup = editor._popup
    item = popup.item(0)

    QTest.mouseClick(popup.viewport(), Qt.LeftButton, Qt.NoModifier, popup.visualItemRect(item).center())

    assert editor.line_edit.hasFocus()
    editor.deleteLater()


def test_popup_is_a_never_activates_never_focuses_tool_window(qapp):
    editor = _editor(qapp)
    _type(editor, "van")
    popup = editor._popup

    assert popup.focusPolicy() == Qt.NoFocus
    assert popup.testAttribute(Qt.WA_ShowWithoutActivating)
    editor.deleteLater()


def test_escape_hides_the_list_and_leaves_the_typed_text_untouched(qapp):
    editor = _editor(qapp)
    _type(editor, "van")
    assert editor._popup.isVisible()

    QTest.keyClick(editor.line_edit, Qt.Key_Escape)

    assert not editor._popup.isVisible()
    assert editor.line_edit.text() == "van"  # Esc dismisses the hints, not what was already typed
    editor.deleteLater()


def test_arrow_keys_move_through_real_hints_and_enter_takes_the_highlighted_one(qapp):
    editor = _editor(qapp)
    _type(editor, "van")
    assert editor._popup.currentRow() == -1

    QTest.keyClick(editor.line_edit, Qt.Key_Down)
    assert editor._popup.currentRow() == 0
    QTest.keyClick(editor.line_edit, Qt.Key_Down)
    assert editor._popup.currentRow() == 1
    QTest.keyClick(editor.line_edit, Qt.Key_Up)
    assert editor._popup.currentRow() == 0

    QTest.keyClick(editor.line_edit, Qt.Key_Return)
    assert editor.line_edit.text() == "văn-học"  # row 0 -- taken, not committed yet
    assert editor.tags() == ["python"]
    assert not editor._popup.isVisible()
    editor.deleteLater()


def test_a_tag_already_on_the_book_never_appears_in_the_live_popup(qapp):
    editor = _editor(qapp)  # already has "python"
    _type(editor, "py")

    assert [editor._popup.item(i).text() for i in range(editor._popup.count())] == ["#python-nâng-cao"]
    editor.deleteLater()
