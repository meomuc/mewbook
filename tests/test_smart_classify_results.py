# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list behind each result card of smart classification: grouped, searchable, and the real books of the run."""
from __future__ import annotations

import pytest

from _smart_helpers import COOKING_WORDS, PROGRAMMING_WORDS, WORKER_SETTINGS, add_book, make_toy_model, thread_executor, write_epub
from smartdoc.application.smart_classifier import UNSURE_REASONS, UNSURE_TAG, ClassifyScope, SmartClassifyService, unsure_reason
from smartdoc.core.event_bus import SmartClassifyFinishedEvent
from smartdoc.presentation.smart_classify_results import ClassifyBooksDialog, build_tree


@pytest.fixture
def context(app_context):
    make_toy_model(app_context.config.app_data_dir / "models" / "classifier_model.json.gz")
    return app_context


def _docs(*rows):
    return {doc_id: {"id": doc_id, "title": title, "author": author, "tags": "", "file_path": f"D:/x/{doc_id}.epub", "extension": "epub"}
            for doc_id, title, author in rows}


def _event(**kw):
    return SmartClassifyFinishedEvent(job_id="j", run_id="r", **kw)


def test_the_unsure_reason_names_the_case():
    assert unsure_reason({"reason": "not_enough_evidence", "words": 0}) == "no_text"  # a scan: nothing was read
    assert unsure_reason({"reason": "not_enough_evidence", "words": 200}) == "not_enough_evidence"
    assert unsure_reason({"reason": "periodical", "words": 900}) == "periodical"
    assert unsure_reason({"reason": "mixed_topics", "words": 900}) == "mixed_topics"
    assert unsure_reason({"reason": "low_confidence", "words": 900}) == "low_confidence"
    assert unsure_reason({"reason": "something new", "words": 5}) in UNSURE_REASONS


def test_tagged_books_are_grouped_by_folder_then_hashtag():
    docs = _docs(("a", "Đắc nhân tâm", "DC"), ("b", "Python cơ bản", "X"), ("c", "Cuốn tiểu thuyết", "Y"), ("d", "Sổ tay", "Z"))
    event = _event(tagged_ids=("a", "b", "c", "d"), tagged_items=(("a", "Phát triển bản thân", "Kỹ năng - Tâm lý"),
                   ("b", "Công nghệ thông tin", "Khoa học - Công nghệ"), ("c", "Tiểu thuyết", "Văn học"),
                   ("d", "Phát triển bản thân", "Kỹ năng - Tâm lý")))
    tree = build_tree("tagged", event, docs)
    assert [(n.label, n.count) for n in tree] == [("Khoa học - Công nghệ", 1), ("Kỹ năng - Tâm lý", 2), ("Văn học", 1)]
    skills = tree[1].children[0]
    assert skills.label == "Phát triển bản thân" and [r.title for r in skills.children] == ["Đắc nhân tâm", "Sổ tay"]


def test_unknown_books_are_grouped_by_why_and_failed_ones_by_the_error():
    docs = _docs(("a", "Bản quét", ""), ("b", "Tạp chí", ""), ("c", "Hỏng", ""), ("d", "Hỏng nữa", ""))
    unknown = build_tree("unknown", _event(unknown_ids=("a", "b"), unknown_items=(("a", "no_text"), ("b", "periodical"))), docs)
    assert {n.label for n in unknown} == {UNSURE_REASONS["no_text"], UNSURE_REASONS["periodical"]}
    failed = build_tree("failed", _event(failed_items=(("c", "OSError: locked"), ("d", "OSError: locked"))), docs)
    assert [(n.label, n.count) for n in failed] == [("OSError: locked", 2)]


def test_an_event_without_items_still_lists_its_books():
    docs = _docs(("a", "Một", ""), ("b", "Hai", ""))
    assert build_tree("tagged", _event(tagged_ids=("a", "b")), docs)[0].count == 2


def test_the_dialog_opens_groups_searches_without_accents_and_shows_the_file(qapp):
    docs = _docs(("a", "Đắc nhân tâm", "Dale Carnegie"), ("b", "Python cơ bản", "Nguyễn Văn A"), ("c", "Truyện Kiều", "Nguyễn Du"))
    event = _event(tagged_ids=("a", "b", "c"), tagged_items=(("a", "Phát triển bản thân", "Kỹ năng - Tâm lý"),
                   ("b", "Công nghệ thông tin", "Khoa học - Công nghệ"), ("c", "Cổ văn Việt Nam", "Văn học")))
    dialog = ClassifyBooksDialog(None, title="t", subtitle="s", tree=build_tree("tagged", event, docs), docs=docs)
    assert dialog.tree.topLevelItemCount() == 3 and not dialog.tree.topLevelItem(0).isExpanded()  # headings first
    assert "(1)" in dialog.tree.topLevelItem(0).text(0)
    dialog.expand_button.click()
    assert dialog.tree.topLevelItem(0).isExpanded()

    dialog.search_edit.setText("nguyen")  # two authors, found without accents
    shown = [dialog.tree.topLevelItem(i) for i in range(3) if not dialog.tree.topLevelItem(i).isHidden()]
    assert len(shown) == 2
    dialog.search_edit.setText("")
    assert all(not dialog.tree.topLevelItem(i).isHidden() for i in range(3))

    assert not dialog.open_file_button.isEnabled()
    leaf = dialog.tree.topLevelItem(0).child(0).child(0)
    dialog.tree.setCurrentItem(leaf)
    assert dialog.open_file_button.isEnabled() and "D:/x/b.epub" in dialog.detail_label.text()
    dialog.deleteLater()


def test_a_real_run_records_each_book_with_its_hashtag_and_reason(qapp, context, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS), title="Lập trình")
    add_book(context, "cook", write_epub(tmp_path / "k.epub", COOKING_WORDS), title="Nấu ăn")
    add_book(context, "blank", write_epub(tmp_path / "b.epub", ["lorem", "ipsum"]), title="Chữ vô nghĩa")
    service = SmartClassifyService(context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    seen: list[SmartClassifyFinishedEvent] = []
    context.event_bus.subscribe(SmartClassifyFinishedEvent, seen.append)
    try:
        service.start(ClassifyScope(doc_ids=["code", "cook", "blank"]))
        assert service.wait(timeout=30)
    finally:
        service.stop()
    event = seen[-1]
    assert {(doc_id, tag) for doc_id, tag, _group in event.tagged_items} == {("code", "Công nghệ thông tin"), ("cook", "Ẩm thực - Nấu ăn")}
    assert [doc_id for doc_id, _reason in event.unknown_items] == ["blank"] and event.unknown_items[0][1] in UNSURE_REASONS
    assert set(event.tagged_ids) == {"code", "cook"}  # the old fields still say the same


# -- giving a hashtag from the list ---------------------------------------------------------------------------------------------

def _run_unsure(context, tmp_path):
    add_book(context, "blank", write_epub(tmp_path / "b.epub", ["lorem", "ipsum"]), title="Chữ vô nghĩa")
    add_book(context, "blank2", write_epub(tmp_path / "b2.epub", ["dolor", "sit"]), title="Cũng vô nghĩa")
    service = SmartClassifyService(context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    return service


def test_tag_books_uses_a_category_and_files_it_in_its_folder(context, tmp_path):
    service = _run_unsure(context, tmp_path)
    try:
        tag, count = service.tag_books(["blank", "blank2"], "nấu ăn")  # written any way the taxonomy knows it
        assert (tag, count) == ("Ẩm thực - Nấu ăn", 2)
        assert "Ẩm thực - Nấu ăn" in context.db.get_document("blank")["tags"]
        again = service.tag_books(["blank"], "Ẩm thực - Nấu ăn")
        assert again == ("Ẩm thực - Nấu ăn", 1) and context.db.get_document("blank")["tags"].count("Ẩm thực") == 1  # added once
        custom, n = service.tag_books(["blank"], "  của   tôi ")
        assert custom == "của tôi" and n == 1 and "của tôi" in context.db.get_document("blank")["tags"]
        assert service.tag_books([], "x") == ("", 0) and service.tag_books(["blank"], "  ") == ("", 0)
        assert ("Sức khỏe - Đời sống", "Ẩm thực - Nấu ăn", "cooking") in service.category_choices()
    finally:
        service.stop()


def test_the_dialog_gives_a_hashtag_to_the_selected_books_and_the_column_follows(qapp, context, tmp_path, monkeypatch):
    service = _run_unsure(context, tmp_path)
    docs = {d["id"]: d for d in context.db.get_documents_light(["blank", "blank2"])}
    event = _event(unknown_ids=("blank", "blank2"), unknown_items=(("blank", "no_text"), ("blank2", "no_text")))
    dialog = ClassifyBooksDialog(
        None, title="t", subtitle="s", tree=build_tree("unknown", event, docs), docs=docs, choices=service.category_choices(),
        tagger=service.tag_books, reload=lambda ids: {d["id"]: d for d in context.db.get_documents_light(list(ids))})
    try:
        assert not dialog.tag_button.isEnabled()
        dialog.tree.selectAll()
        assert len(dialog._selected_ids()) == 2 and dialog.tag_button.isEnabled() and "2 cuốn" in dialog.tag_button.text()
        monkeypatch.setattr("smartdoc.presentation.smart_classify_results.QInputDialog.getItem",
                            lambda *a, **k: ("Ẩm thực - Nấu ăn    (Sức khỏe - Đời sống)", True))
        dialog._on_tag()
        leaves = dialog._all_leaves()
        assert len(leaves) == 2 and all("Ẩm thực - Nấu ăn" in leaf.text(2) for leaf in leaves)
        assert "Đã gắn" in dialog.detail_label.text()
        assert all("Ẩm thực - Nấu ăn" in (context.db.get_document(i)["tags"] or "") for i in ("blank", "blank2"))
    finally:
        dialog.deleteLater()
        service.stop()


def test_without_a_tagger_there_is_no_button(qapp):
    docs = _docs(("a", "Một", ""))
    dialog = ClassifyBooksDialog(None, title="t", subtitle="s", tree=build_tree("tagged", _event(tagged_ids=("a",)), docs), docs=docs)
    assert dialog.tag_button is None
    dialog.deleteLater()


def test_the_placeholder_tag_is_swapped_for_a_real_one_once_the_person_decides(context, tmp_path):
    add_book(context, "vague", write_epub(tmp_path / "v.epub", ["zzz", "qqq"]), title="Không rõ")
    service = SmartClassifyService(context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    try:
        service.start(ClassifyScope(doc_ids=["vague"]))
        assert service.wait(timeout=30)
        assert context.db.get_document("vague")["tags"] == UNSURE_TAG
        tag, count = service.tag_books(["vague"], "nấu ăn")
        assert (tag, count) == ("Ẩm thực - Nấu ăn", 1)
        assert context.db.get_document("vague")["tags"] == "Ẩm thực - Nấu ăn"  # the placeholder is gone, not left beside it
    finally:
        service.stop()


# -- Task B2: a book the model leaned to (but not sure enough) is a suggestion to confirm, in the same list ---------------

def test_a_low_confidence_book_with_a_clear_lean_is_a_suggestion_a_vague_one_is_not():
    lean = {"reason": "low_confidence", "words": 900, "best_name": "Ẩm thực - Nấu ăn", "confidence": 0.52}
    assert unsure_reason(lean) == "suggested"
    assert unsure_reason({**lean, "confidence": 0.3}) == "low_confidence"  # too unsure to even suggest
    assert unsure_reason({**lean, "best_name": ""}) == "low_confidence"
    assert unsure_reason({**lean, "reason": "mixed_topics"}) == "mixed_topics"  # a guard's verdict is never turned into a suggestion


def test_suggestions_form_their_own_group_with_the_lean_in_the_note():
    docs = _docs(("a", "Ăn dặm kiểu Nhật", ""), ("b", "Mơ hồ", ""))
    event = _event(unknown_ids=("a", "b"), unknown_items=(("a", "suggested"), ("b", "low_confidence")),
                   unknown_hints=(("a", "Ẩm thực - Nấu ăn", 0.51),))
    tree = {n.label: n for n in build_tree("unknown", event, docs)}
    row = tree[UNSURE_REASONS["suggested"]].children[0]
    assert row.suggestion == "Ẩm thực - Nấu ăn" and "51%" in row.note
    assert tree[UNSURE_REASONS["low_confidence"]].children[0].suggestion == ""


def test_accepting_suggestions_tags_each_book_with_its_own_lean_and_drops_the_placeholder(qapp, context, tmp_path):
    add_book(context, "s1", write_epub(tmp_path / "s1.epub", ["zzz"]), title="Một")
    add_book(context, "s2", write_epub(tmp_path / "s2.epub", ["qqq"]), title="Hai")
    service = SmartClassifyService(context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    try:
        service.start(ClassifyScope(doc_ids=["s1", "s2"]))
        assert service.wait(timeout=30)
        assert context.db.get_document("s1")["tags"] == UNSURE_TAG
        docs = {d["id"]: d for d in context.db.get_documents_light(["s1", "s2"])}
        event = _event(unknown_ids=("s1", "s2"), unknown_items=(("s1", "suggested"), ("s2", "suggested")),
                       unknown_hints=(("s1", "Ẩm thực - Nấu ăn", 0.6), ("s2", "Công nghệ thông tin", 0.7)))
        dialog = ClassifyBooksDialog(
            None, title="t", subtitle="s", tree=build_tree("unknown", event, docs), docs=docs, choices=service.category_choices(),
            tagger=service.tag_books, reload=lambda ids: {d["id"]: d for d in context.db.get_documents_light(list(ids))})
        try:
            assert not dialog.accept_button.isVisibleTo(dialog)
            dialog.tree.expandAll()
            dialog.tree.selectAll()
            assert dialog.accept_button.isVisibleTo(dialog) and "2 cuốn" in dialog.accept_button.text()
            dialog._on_accept_suggestions()
            assert context.db.get_document("s1")["tags"] == "Ẩm thực - Nấu ăn"
            assert context.db.get_document("s2")["tags"] == "Công nghệ thông tin"
            assert "Đã nhận gợi ý cho 2" in dialog.detail_label.text()
        finally:
            dialog.deleteLater()
    finally:
        service.stop()
