"""Context menu behavior: single-selection edit/delete, multi-selection batch
edit/delete. QMenu.exec() and QMessageBox.question() are modal and block on
a real click; QMenu.exec() in particular has no way to be dismissed under
the offscreen Qt platform tests run under and hangs forever if actually
invoked, so tests patch LibraryListWidget._exec_menu (a plain Python seam)
instead of trying to intercept Qt's own exec().
"""
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QMessageBox

from smartdoc.presentation.library_view import LibraryListWidget


class _FakeDialog:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def exec(self) -> int:
        return 1

    def show(self) -> None:
        pass


def _pick_action_containing(text_substring: str):
    def fake_exec_menu(self, menu, _position):
        for action in menu.actions():
            if text_substring in action.text():
                return action
        return None

    return fake_exec_menu


def _select_row(widget: LibraryListWidget, qapp, *rows: int):
    widget.resize(600, 400)
    widget.show()
    qapp.processEvents()

    selection_model = widget.list_view.selectionModel()
    selection_model.clearSelection()
    for row in rows:
        index = widget.model.index(row, 0)
        selection_model.select(index, QItemSelectionModel.Select)
    # NoUpdate: move "current" to the first row without collapsing the
    # multi-row selection just built above (plain setCurrentIndex() does).
    selection_model.setCurrentIndex(widget.model.index(rows[0], 0), QItemSelectionModel.NoUpdate)
    qapp.processEvents()
    return widget.list_view.visualRect(widget.model.index(rows[0], 0)).center()


def _seed_two_docs(app_context):
    app_context.db.add_or_update_document("d1", {"title": "First", "author": "A", "file_path": "a.pdf", "created_at": 1.0})
    app_context.db.add_or_update_document("d2", {"title": "Second", "author": "B", "file_path": "b.pdf", "created_at": 2.0})


def test_single_selection_edit_action_opens_metadata_editor(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    opened_docs = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.MetadataEditorDialog",
        lambda context, doc, parent: opened_docs.append(doc) or _FakeDialog(),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Chỉnh sửa thông tin"))

    widget._show_context_menu(position)

    assert len(opened_docs) == 1
    assert opened_docs[0]["title"] in ("First", "Second")


def test_single_selection_review_action_opens_review_dialog(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    opened_docs = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.ReviewDialog",
        lambda context, doc, parent: opened_docs.append(doc) or _FakeDialog(),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Xem / Viết đánh giá"))

    widget._show_context_menu(position)

    assert len(opened_docs) == 1
    assert opened_docs[0]["title"] in ("First", "Second")


def test_single_selection_delete_confirmed_removes_document(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)
    doc_at_row0 = widget.model.document_at(0)

    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Xóa khỏi thư viện"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    widget._show_context_menu(position)

    remaining_ids = {d["id"] for d in app_context.db.list_all_documents()}
    assert doc_at_row0["id"] not in remaining_ids


def test_single_selection_delete_cancelled_keeps_document(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Xóa khỏi thư viện"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    widget._show_context_menu(position)

    assert len(app_context.db.list_all_documents()) == 2


def test_double_click_opens_reader_window_not_external_open(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)

    opened_docs = []
    opened_externally = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.ReaderWindow",
        lambda context, doc, parent: opened_docs.append(doc) or _FakeDialog(),
    )
    monkeypatch.setattr(widget.file_actions, "open_file", lambda path: opened_externally.append(path))

    widget._open_selected(widget.model.index(0, 0))

    assert len(opened_docs) == 1
    assert opened_externally == []


def test_single_selection_read_action_opens_reader_window(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    opened_docs = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.ReaderWindow",
        lambda context, doc, parent: opened_docs.append(doc) or _FakeDialog(),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Đọc trong ứng dụng"))

    widget._show_context_menu(position)

    assert len(opened_docs) == 1


def test_single_selection_ai_summary_action_opens_ai_summary_dialog(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    opened_docs = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.AISummaryDialog",
        lambda context, doc, parent: opened_docs.append(doc) or _FakeDialog(),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Tóm tắt AI"))

    widget._show_context_menu(position)

    assert len(opened_docs) == 1


def test_multi_selection_batch_edit_opens_batch_dialog_with_both_ids(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0, 1)

    captured_ids = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.BatchEditorDialog",
        lambda context, doc_ids, parent: captured_ids.extend(doc_ids) or _FakeDialog(),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Chỉnh sửa hàng loạt"))

    widget._show_context_menu(position)

    assert set(captured_ids) == {"d1", "d2"}


def test_multi_selection_delete_confirmed_removes_all_selected(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0, 1)

    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Xóa"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    widget._show_context_menu(position)

    assert app_context.db.list_all_documents() == []
