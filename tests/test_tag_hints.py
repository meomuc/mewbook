# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hashtag hints while typing in the detail panel: from two characters, existing library tags that match, never one the
book already has; picking one fills the box."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from smartdoc.presentation.tag_editor import MIN_HINT_CHARS, TagEditor, current_segment, suggest_tags

KNOWN = {"văn-học": 40, "văn-hóa": 12, "lịch-sử": 30, "python": 25, "python-nâng-cao": 3, "machine-learning": 8, "AI": 5}


def test_nothing_is_offered_before_two_characters():
    assert MIN_HINT_CHARS == 2
    assert suggest_tags("p", KNOWN, []) == [] and suggest_tags("#p", KNOWN, []) == [] and suggest_tags("", KNOWN, []) == []
    assert suggest_tags("py", KNOWN, []) == ["python", "python-nâng-cao"]


def test_matching_ignores_case_and_accents_and_puts_prefix_matches_first():
    assert suggest_tags("VAN", KNOWN, []) == ["văn-học", "văn-hóa"]  # the more used one first
    assert suggest_tags("hoc", KNOWN, []) == ["văn-học"]  # in the middle of a tag
    assert suggest_tags("su", KNOWN, [])[0] == "lịch-sử"
    assert suggest_tags("hoc", {"nhập-học": 1, "học-tập": 1}, []) == ["học-tập", "nhập-học"]  # starts-with beats contains


def test_a_tag_the_book_already_has_is_never_offered():
    assert suggest_tags("py", KNOWN, ["python"]) == ["python-nâng-cao"]
    assert suggest_tags("van", KNOWN, ["Văn-Học"]) == ["văn-hóa"]  # same tag, different spelling of the case


def test_only_the_last_comma_part_is_matched():
    assert current_segment("python, #văn") == "văn"
    assert suggest_tags("python, van", KNOWN, []) == ["văn-học", "văn-hóa"]
    assert len(suggest_tags("a" * 2, {f"aa{i}": i for i in range(20)}, [])) == 6  # a short list


def _editor(qapp):
    editor = TagEditor()
    editor.resize(320, 120)
    editor.show()
    editor.set_known_tags_source(lambda: dict(KNOWN))
    editor.set_tags(["python"])
    editor.add_button.click()
    return editor


def _type(editor, text):
    editor.line_edit.setText(text)
    editor.line_edit.textEdited.emit(text)  # what typing does


def test_the_hint_list_appears_right_under_the_box_wherever_the_window_sits_on_screen(qapp):
    """Regression: the popup is a top-level window (Qt.ToolTip), so its position is always in SCREEN coordinates. A previous
    version computed a position relative to the main window instead and handed that straight to move() -- right only by
    coincidence when the main window happened to sit at the screen's top-left corner; everywhere else the list showed up far
    from the box that was actually typed into (reported: it appeared over the middle of the library grid instead of under the
    detail panel's Hashtag box)."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(37, 51, 0, 0)  # the box does not sit at its window's own origin
    editor = TagEditor(container)
    layout.addWidget(editor)
    container.move(213, 97)  # the window itself is not at the screen's top-left corner either
    container.show()
    editor.set_known_tags_source(lambda: dict(KNOWN))
    editor.add_button.click()

    _type(editor, "py")

    assert editor._popup.isVisible()
    assert editor._popup.pos() == editor.line_edit.mapToGlobal(QPoint(0, editor.line_edit.height() + 2))
    container.deleteLater()


def test_hints_appear_from_two_characters_and_exclude_the_books_own_tags(qapp):
    editor = _editor(qapp)
    _type(editor, "p")
    assert editor._popup is None or not editor._popup.isVisible()
    _type(editor, "py")
    assert editor._popup.isVisible() and [editor._popup.item(i).text() for i in range(editor._popup.count())] == ["#python-nâng-cao"]
    _type(editor, "x")
    assert not editor._popup.isVisible()
    editor.deleteLater()


def test_picking_a_hint_fills_the_box_and_enter_adds_it(qapp):
    editor = _editor(qapp)
    changes = []
    editor.changed.connect(changes.append)
    _type(editor, "van")
    editor._popup.setCurrentRow(1)
    editor._popup.itemClicked.emit(editor._popup.item(1))
    # itemClicked now auto-commits; the tag is added without a separate Enter press.
    assert not editor._popup.isVisible()
    assert changes == ["python,văn-hóa"]
    assert editor.line_edit.text() == ""  # cleared by auto-commit
    editor.deleteLater()


def test_the_keyboard_can_move_through_the_hints_and_take_one(qapp):
    editor = _editor(qapp)
    _type(editor, "van")
    key = lambda k: QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier)  # noqa: E731
    assert editor.eventFilter(editor.line_edit, key(Qt.Key_Down))
    assert editor._popup.currentRow() == 0
    assert editor.eventFilter(editor.line_edit, key(Qt.Key_Return))  # takes the highlighted hint, does not commit
    assert editor.line_edit.text() == "văn-học" and editor.tags() == ["python"]
    editor.deleteLater()
