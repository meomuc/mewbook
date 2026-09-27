# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list behind each result card of smart classification: grouped, searchable, and the real books of the run."""
from __future__ import annotations

import pytest

from _smart_helpers import COOKING_WORDS, PROGRAMMING_WORDS, WORKER_SETTINGS, add_book, make_toy_model, thread_executor, write_epub
from smartdoc.application.smart_classifier import UNSURE_REASONS, ClassifyScope, SmartClassifyService, unsure_reason
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
