"""Gợi ý dọn tên tác giả: suggestions are applied only on request and only in the library."""
from smartdoc.domain.author_names import looks_like_uploader_handle
from smartdoc.presentation.author_cleanup_dialog import AuthorCleanupDialog


def _add(ctx, doc_id, author):
    ctx.db.add_or_update_document(doc_id, {"title": doc_id, "author": author, "file_path": f"{doc_id}.pdf", "created_at": 1.0})


def test_handles_are_told_apart_from_names():
    assert looks_like_uploader_handle("CongThuc88")
    assert looks_like_uploader_handle("sachvui.com")
    assert looks_like_uploader_handle("thuvienEbook")
    assert not looks_like_uploader_handle("Osho")
    assert not looks_like_uploader_handle("Nguyễn Nhật Ánh")
    assert not looks_like_uploader_handle("J.K. Rowling")
    assert not looks_like_uploader_handle("")


def _confirm(monkeypatch, answer=True):
    from smartdoc.presentation import author_cleanup_dialog as module

    asked = {}

    def fake(parent, **kwargs):
        asked.update(kwargs)
        return answer

    monkeypatch.setattr(module, "confirm_danger", fake)
    return asked


def test_merging_accent_variants_renames_the_smaller_spelling(qapp, app_context, monkeypatch):
    for i in range(3):
        _add(app_context, f"a{i}", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    dialog = AuthorCleanupDialog(app_context)
    assert len(dialog._cards) == 1
    assert dialog.apply_button.text() == "Áp dụng 1 thay đổi"
    asked = _confirm(monkeypatch)

    assert dialog.apply_selected()

    assert app_context.db.get_document("b")["author"] == "Nguyễn Nhật Ánh"
    assert "4 sách" in asked["message"] and not dialog._cards  # nothing left to suggest
    assert not dialog.empty_label.isHidden()
    dialog.deleteLater()


def test_the_target_name_of_a_merge_can_be_edited(qapp, app_context, monkeypatch):
    for i in range(3):
        _add(app_context, f"a{i}", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    dialog = AuthorCleanupDialog(app_context)
    dialog._cards[0].name_edit.setText("Nguyễn N. Ánh")
    _confirm(monkeypatch)

    dialog.apply_selected()

    assert {app_context.db.get_document(i)["author"] for i in ("a0", "b")} == {"Nguyễn N. Ánh"}
    dialog.deleteLater()


def test_answering_no_changes_nothing(qapp, app_context, monkeypatch):
    _add(app_context, "a", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    dialog = AuthorCleanupDialog(app_context)
    _confirm(monkeypatch, False)

    assert not dialog.apply_selected()

    assert app_context.db.get_document("b")["author"] == "Nguyen Nhat Anh"
    dialog.deleteLater()


def test_an_unticked_card_is_left_alone(qapp, app_context, monkeypatch):
    _add(app_context, "a", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    dialog = AuthorCleanupDialog(app_context)
    dialog._cards[0].check.setChecked(False)
    assert not dialog.apply_button.isEnabled()
    _confirm(monkeypatch)
    assert not dialog.apply_selected()
    assert app_context.db.get_document("b")["author"] == "Nguyen Nhat Anh"
    dialog.deleteLater()


def test_a_username_can_be_set_to_unknown(qapp, app_context, monkeypatch):
    for i in range(11):
        _add(app_context, f"u{i}", "CongThuc88")
    dialog = AuthorCleanupDialog(app_context)
    assert not dialog._cards[0].name_edit.isEnabled()
    _confirm(monkeypatch)

    dialog.apply_selected()

    assert app_context.db.get_document("u0")["author"] == "Unknown"
    dialog.deleteLater()


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
