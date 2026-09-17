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


def test_single_selection_copy_action_puts_file_path_on_clipboard(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.set_clipboard_files",
        lambda paths, cut=False: calls.append((paths, cut)),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Sao chép"))

    widget._show_context_menu(position)

    assert calls[0][1] is False
    assert calls[0][0][0] in ("a.pdf", "b.pdf")


def test_single_selection_cut_action_marks_clipboard_as_move(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0)

    calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.set_clipboard_files",
        lambda paths, cut=False: calls.append((paths, cut)),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Cắt"))

    widget._show_context_menu(position)

    assert calls[0][1] is True
    assert calls[0][0][0] in ("a.pdf", "b.pdf")


def test_multi_selection_copy_action_puts_all_file_paths_on_clipboard(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    position = _select_row(widget, qapp, 0, 1)

    calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.set_clipboard_files",
        lambda paths, cut=False: calls.append((paths, cut)),
    )
    monkeypatch.setattr(LibraryListWidget, "_exec_menu", _pick_action_containing("Sao chép"))

    widget._show_context_menu(position)

    assert calls[0][1] is False
    assert set(calls[0][0]) == {"a.pdf", "b.pdf"}


def test_clear_selection_deselects_everything(qapp, app_context):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    _select_row(widget, qapp, 0, 1)
    assert widget.list_view.selectionModel().hasSelection()

    widget.clear_selection()

    assert not widget.list_view.selectionModel().hasSelection()


def test_edit_selected_opens_metadata_editor_for_single_selection(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    _select_row(widget, qapp, 0)

    opened_docs = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.MetadataEditorDialog",
        lambda context, doc, parent: opened_docs.append(doc) or _FakeDialog(),
    )

    widget.edit_selected()

    assert len(opened_docs) == 1


def test_edit_selected_opens_batch_editor_for_multi_selection(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    _select_row(widget, qapp, 0, 1)

    captured_ids = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.BatchEditorDialog",
        lambda context, doc_ids, parent: captured_ids.extend(doc_ids) or _FakeDialog(),
    )

    widget.edit_selected()

    assert set(captured_ids) == {"d1", "d2"}


def test_delete_selected_removes_confirmed_selection(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    _select_row(widget, qapp, 0, 1)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    widget.delete_selected()

    assert app_context.db.list_all_documents() == []


def test_delete_selected_does_nothing_when_nothing_selected(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)

    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(1) or QMessageBox.Yes))

    widget.delete_selected()

    assert asked == []
    assert len(app_context.db.list_all_documents()) == 2


def test_copy_selected_puts_selected_paths_on_clipboard(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    _select_row(widget, qapp, 0, 1)

    calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.set_clipboard_files",
        lambda paths, cut=False: calls.append((paths, cut)),
    )

    widget.copy_selected()

    assert calls[0][1] is False
    assert set(calls[0][0]) == {"a.pdf", "b.pdf"}


def test_cut_selected_marks_clipboard_as_move(qapp, app_context, monkeypatch):
    _seed_two_docs(app_context)
    widget = LibraryListWidget(app_context)
    _select_row(widget, qapp, 0)

    calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.set_clipboard_files",
        lambda paths, cut=False: calls.append((paths, cut)),
    )

    widget.cut_selected()

    assert calls[0][1] is True
    assert calls[0][0][0] in ("a.pdf", "b.pdf")


class _FakeImportManager:
    def __init__(self) -> None:
        self.added_files: list[str] = []
        self.scanned_folders: list[str] = []

    def add_files(self, paths: list[str]) -> int:
        self.added_files.extend(paths)
        return len(paths)

    def scan_folder(self, folder_path: str) -> int:
        self.scanned_folders.append(folder_path)
        return 0


def test_paste_files_imports_files_from_clipboard(qapp, app_context, monkeypatch, tmp_path):
    file_a = tmp_path / "book.pdf"
    file_a.write_text("x")
    import_manager = _FakeImportManager()
    widget = LibraryListWidget(app_context, import_manager=import_manager)
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.get_clipboard_file_paths", lambda: [str(file_a)]
    )

    widget.paste_files()

    assert import_manager.added_files == [str(file_a)]


def test_paste_files_scans_folders_from_clipboard(qapp, app_context, monkeypatch, tmp_path):
    folder = tmp_path / "books"
    folder.mkdir()
    import_manager = _FakeImportManager()
    widget = LibraryListWidget(app_context, import_manager=import_manager)
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.get_clipboard_file_paths", lambda: [str(folder)]
    )

    widget.paste_files()

    assert import_manager.scanned_folders == [str(folder)]


def test_paste_files_does_nothing_without_an_import_manager(qapp, app_context, monkeypatch, tmp_path):
    file_a = tmp_path / "book.pdf"
    file_a.write_text("x")
    widget = LibraryListWidget(app_context)
    monkeypatch.setattr(
        "smartdoc.presentation.library_view.get_clipboard_file_paths", lambda: [str(file_a)]
    )

    widget.paste_files()  # should not raise
