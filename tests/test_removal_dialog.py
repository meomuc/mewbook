# SPDX-License-Identifier: AGPL-3.0-or-later
"""The two-option dialog every "delete a book" action asks: Xóa khỏi thư viện (keeps the file) or Xóa file."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog

from smartdoc.application.removal import RemovalMode
from smartdoc.presentation.removal_dialog import RemovalChoiceDialog, ask_removal


def _dialog(qapp, total: int = 2) -> RemovalChoiceDialog:
    return RemovalChoiceDialog(None, titles=["Sách A", "Sách B"][:total], total=total)


def test_the_safe_choice_is_the_default_and_keeps_the_file(qapp):
    dialog = _dialog(qapp)
    assert dialog.mode() is RemovalMode.REMOVE_FROM_LIBRARY
    assert dialog.keep_file_option.isChecked() and not dialog.delete_file_option.isChecked()
    assert "Xóa khỏi thư viện" in dialog.confirm_button.text()
    dialog.deleteLater()


def test_choosing_to_delete_the_file_changes_the_mode_and_the_button(qapp):
    dialog = _dialog(qapp)
    dialog.delete_file_option.setChecked(True)
    assert dialog.mode() is RemovalMode.TRASH_FILE
    assert "Xóa file" in dialog.confirm_button.text()
    dialog.keep_file_option.setChecked(True)
    assert dialog.mode() is RemovalMode.REMOVE_FROM_LIBRARY
    dialog.deleteLater()


def test_the_dialog_says_how_many_books_and_lists_their_titles(qapp):
    dialog = _dialog(qapp, total=2)
    assert "2" in dialog.windowTitle() and "Sách A" in dialog.items_label.text() and "Sách B" in dialog.items_label.text()
    dialog.deleteLater()


def test_ask_removal_returns_the_chosen_mode_and_none_when_cancelled(qapp, monkeypatch):
    docs = [{"id": "d1", "title": "Sách A"}]
    monkeypatch.setattr(RemovalChoiceDialog, "exec", lambda self: self.delete_file_option.setChecked(True) or QDialog.Accepted)
    assert ask_removal(None, docs) is RemovalMode.TRASH_FILE
    monkeypatch.setattr(RemovalChoiceDialog, "exec", lambda self: QDialog.Rejected)
    assert ask_removal(None, docs) is None
