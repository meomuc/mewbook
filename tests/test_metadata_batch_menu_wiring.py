# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task B3: the "Cập nhật thông tin sách hàng loạt…" tool action opens the dialog scoped to the list currently
being viewed (library_view.classification_scope), not a separate query -- and reuses one open dialog instead of
stacking a second."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRect

from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.metadata_batch_dialog import MetadataBatchUpdateDialog


@pytest.fixture
def window(qapp, app_context, monkeypatch):
    monkeypatch.setattr("smartdoc.presentation.dialog_size._usable_area", lambda _w: QRect(0, 0, 3000, 2000))
    win = MainWindow(app_context)
    yield win
    win.hide()
    win.deleteLater()


def test_the_action_opens_a_dialog_scoped_to_the_current_library_view(qapp, window, app_context):
    app_context.db.add_or_update_document("d1", {"title": "T", "author": "A", "file_path": "d1.pdf", "created_at": 1.0})

    window._on_open_metadata_batch_update()

    dialog = window._metadata_batch_dialog
    assert isinstance(dialog, MetadataBatchUpdateDialog)
    # Bound methods compare equal (same instance + function) even though a fresh access creates a new object,
    # so this is `==`, not `is`.
    assert dialog._current_scope == window.library_view.classification_scope
    assert "1" in dialog.preview_label.text()
    dialog.close()


def test_a_second_call_while_one_is_open_reuses_it_instead_of_opening_another(qapp, window):
    window._on_open_metadata_batch_update()
    first = window._metadata_batch_dialog
    first.show()

    window._on_open_metadata_batch_update()

    assert window._metadata_batch_dialog is first
    first.close()
