"""Gợi ý dọn tên tác giả: suggestions are applied only on request and only in the library."""
from PySide6.QtWidgets import QMessageBox

from smartdoc.domain.author_names import looks_like_uploader_handle
from smartdoc.presentation.author_cleanup_dialog import AuthorCleanupDialog


def _add(ctx, doc_id, author):
    ctx.db.add_or_update_document(doc_id, {"title": doc_id, "author": author, "file_path": f"{doc_id}.pdf", "created_at": 1.0})


def _yes(monkeypatch, answer=QMessageBox.Yes):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: answer))


def test_handles_are_told_apart_from_names():
    assert looks_like_uploader_handle("CongThuc88")
    assert looks_like_uploader_handle("sachvui.com")
    assert looks_like_uploader_handle("thuvienEbook")
    assert not looks_like_uploader_handle("Osho")
    assert not looks_like_uploader_handle("Nguyễn Nhật Ánh")
    assert not looks_like_uploader_handle("J.K. Rowling")
    assert not looks_like_uploader_handle("")


def test_merging_accent_variants_renames_the_smaller_spelling(qapp, app_context, monkeypatch):
    for i in range(3):
        _add(app_context, f"a{i}", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    dialog = AuthorCleanupDialog(app_context)
    assert dialog.list.count() == 1
    assert "Gộp" in dialog.list.item(0).text()
    _yes(monkeypatch)

    assert dialog.apply_current()

    assert app_context.db.get_document("b")["author"] == "Nguyễn Nhật Ánh"
    assert dialog.list.item(0).text().startswith("Không có gợi ý")  # nothing left to suggest


def test_answering_no_changes_nothing(qapp, app_context, monkeypatch):
    _add(app_context, "a", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    dialog = AuthorCleanupDialog(app_context)
    _yes(monkeypatch, QMessageBox.No)

    assert not dialog.apply_current()

    assert app_context.db.get_document("b")["author"] == "Nguyen Nhat Anh"


def test_a_username_can_be_set_to_unknown(qapp, app_context, monkeypatch):
    for i in range(11):
        _add(app_context, f"u{i}", "CongThuc88")
    dialog = AuthorCleanupDialog(app_context)
    assert dialog.apply_button.text() == "Đặt là “Không rõ”"
    _yes(monkeypatch)

    dialog.apply_current()

    assert app_context.db.get_document("u0")["author"] == "Unknown"


def test_the_authors_menu_offers_the_cleanup(qapp, app_context, monkeypatch):
    from smartdoc.domain.library_filter import AUTHORS, TAGS
    from smartdoc.presentation.facet_panel import FacetPanel

    panel = FacetPanel(app_context)
    seen = {}
    monkeypatch.setattr(FacetPanel, "_exec_menu", lambda self, menu, pos: seen.setdefault("texts", [a.text() for a in menu.actions()]) and None)

    panel._show_section_menu(AUTHORS, panel.sections[AUTHORS].menu_button)
    assert any("dọn tên tác giả" in text for text in seen["texts"])

    seen.clear()
    panel._show_section_menu(TAGS, panel.sections[TAGS].menu_button)
    assert not any("dọn tên tác giả" in text for text in seen["texts"])
