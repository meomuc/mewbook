import time

import pytest
from PySide6.QtCore import QItemSelectionModel

from _smart_helpers import COOKING_WORDS, PROGRAMMING_WORDS, WORKER_SETTINGS, add_book, make_toy_model, thread_executor, write_epub
from smartdoc.application.smart_classifier import ClassifyScope, SmartClassifyService
from smartdoc.core.event_bus import (
    ImportBatchCompletedEvent,
    SmartClassifyFinishedEvent,
    SmartClassifyProgressEvent,
)
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.smart_classify_wizard import STEP_RESULT, STEP_RUNNING, STEP_SCOPE, SmartClassifyWizard


@pytest.fixture
def context(app_context):
    make_toy_model(app_context.config.app_data_dir / "models" / "classifier_model.json.gz")
    return app_context


@pytest.fixture
def service(context):
    svc = SmartClassifyService(context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    yield svc
    svc.stop()


def finished_event(**kwargs):
    defaults = dict(job_id="j", run_id="r", total=100, tagged=80, unknown=15, failed=1, skipped=4)
    return SmartClassifyFinishedEvent(**{**defaults, **kwargs})


# -- The three-step dialog --------------------------------------------------------


def _wizard(context, service, scope=None, selected=None):
    return SmartClassifyWizard(context, service, lambda: scope or ClassifyScope(description="Tất cả tài liệu"),
                               selected_scope=selected)


def _pump(qapp, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def test_step_one_shows_three_cards_with_counts_and_a_start_button(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    add_book(context, "food", write_epub(tmp_path / "f.epub", COOKING_WORDS), tags="bếp")
    wizard = _wizard(context, service)

    assert [o.key for o in wizard.options] == ["filter", "unclassified", "all"]
    assert wizard.step_bar.step == STEP_SCOPE
    assert wizard.cards["filter"].count_label.text() == "2 sách"
    assert wizard.selected_option().key == "filter"
    assert wizard.start_button.text() == "Bắt đầu với 2 sách" and wizard.start_button.isEnabled()
    wizard.cards["all"].radio.setChecked(True)
    assert wizard.selected_option().key == "all" and not wizard.cards["filter"].radio.isChecked()
    wizard.deleteLater()


def test_a_selection_from_the_list_replaces_the_first_card(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    selected = ClassifyScope(doc_ids=("code",), description="1 sách đã chọn")
    wizard = _wizard(context, service, selected=selected)
    assert wizard.options[0].key == "selected" and wizard.cards["selected"].count_label.text() == "1 sách"
    wizard.deleteLater()


def test_cards_with_nothing_to_do_are_switched_off(qapp, context, service):
    wizard = _wizard(context, service)
    assert not wizard.start_button.isEnabled()
    assert all(not card.radio.isEnabled() for card in wizard.cards.values())
    wizard.deleteLater()


def test_the_dialog_explains_when_there_is_no_model(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    service.model_path = lambda: None
    wizard = _wizard(context, service)
    assert not wizard.start_button.isEnabled()
    assert "train.py" in wizard._notice
    wizard.deleteLater()


def test_a_run_goes_through_the_steps_and_lists_its_books(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS), title="Lập trình Python")
    wizard = _wizard(context, service)
    wizard.show()

    wizard.start_button.click()
    assert wizard.step_bar.step in (STEP_RUNNING, STEP_RESULT)
    assert service.wait(timeout=30)
    assert _pump(qapp, lambda: wizard.step_bar.step == STEP_RESULT)

    assert wizard.tagged_count.text() == "1" and not wizard.tagged_link.isHidden()
    assert wizard.tagged_link.text() == "Xem 1 sách"
    assert wizard.undo_button.isEnabled() and not wizard.done_button.isHidden()
    assert context.db.get_document("code")["tags"]
    wizard.deleteLater()


def test_undo_takes_back_only_this_runs_tags(qapp, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    wizard = _wizard(context, service)
    wizard.show()
    wizard.start_button.click()
    assert service.wait(timeout=30)
    assert _pump(qapp, lambda: wizard.step_bar.step == STEP_RESULT)
    monkeypatch.setattr(wizard, "_confirm_undo", lambda tagged: True)

    wizard.undo_button.click()

    assert not context.db.get_document("code")["tags"]
    assert "Đã hoàn tác" in wizard.result_title.text() and not wizard.undo_button.isEnabled()
    wizard.deleteLater()


def test_declining_the_undo_keeps_the_tags(qapp, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    wizard = _wizard(context, service)
    wizard.show()
    wizard.start_button.click()
    assert service.wait(timeout=30)
    assert _pump(qapp, lambda: wizard.step_bar.step == STEP_RESULT)
    monkeypatch.setattr(wizard, "_confirm_undo", lambda tagged: False)
    wizard.undo_button.click()
    assert context.db.get_document("code")["tags"]
    wizard.deleteLater()


def test_the_running_step_shows_progress_and_the_last_three_books(qapp, context, service):
    wizard = _wizard(context, service)
    wizard._set_step(STEP_RUNNING)
    wizard._started_at = time.monotonic() - 30
    wizard._show_progress(140, 318, "running", (("Tủ rack", "Mạng"), ("Sống chậm", "Kỹ năng"), ("Dự án", "")))
    assert wizard.progress.maximum() == 318 and wizard.progress.value() == 140
    assert "140" in wizard.done_label.text() and wizard.eta_label.text().startswith("còn ")
    assert wizard.recent_labels[0].text().startswith("✓ Tủ rack") and "chưa chắc" in wizard.recent_labels[2].text()
    assert not wizard.stop_button.isHidden() and not wizard.background_button.isHidden()
    wizard.deleteLater()


def test_running_in_the_background_hides_the_dialog_and_reports_at_the_end(qapp, context, service):
    wizard = _wizard(context, service)
    wizard.show()
    wizard._set_step(STEP_RUNNING)
    said = []
    wizard.background_finished.connect(said.append)
    wizard.background_button.click()
    assert not wizard.isVisible()
    wizard._show_result(finished_event(tagged=281, unknown=30, failed=7))
    assert said and "281" in said[0] and "30" in said[0]
    wizard.deleteLater()


def test_the_result_page_names_errors_and_offers_the_lists(qapp, context, service):
    context.db.add_or_update_document("bad", {"title": "Hỏng", "author": "A", "file_path": "x.pdf", "created_at": 1.0})
    wizard = _wizard(context, service)
    wizard._show_result(finished_event(tagged=0, unknown=0, failed=1, failed_items=(("bad", "worker crashed"),)))
    assert wizard.failed_count.text() == "1" and wizard.failed_link.text() == "Xem lý do"
    assert wizard.tagged_link.isHidden() and not wizard.undo_button.isEnabled()
    wizard.deleteLater()


def test_an_error_result_says_so(qapp, context, service):
    wizard = _wizard(context, service)
    wizard._show_result(finished_event(total=0, tagged=0, unknown=0, failed=0, error="Chưa có mô hình"))
    assert wizard.result_title.text() == "Chưa phân loại được" and "Chưa có mô hình" in wizard.result_subtitle.text()
    wizard.deleteLater()


def test_a_finished_event_from_a_job_elsewhere_is_ignored_on_step_one(qapp, context, service):
    wizard = _wizard(context, service)
    wizard._on_event(finished_event())
    assert wizard.step_bar.step == STEP_SCOPE
    wizard.deleteLater()


def test_the_service_reports_recent_books_and_the_ids_of_each_outcome(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS), title="Lập trình Python")
    events = []
    context.event_bus.subscribe(SmartClassifyProgressEvent, events.append)
    finished = []
    context.event_bus.subscribe(SmartClassifyFinishedEvent, finished.append)
    service.start(ClassifyScope(doc_ids=("code",)))
    assert service.wait(timeout=30)
    assert finished[0].tagged_ids == ("code",) and finished[0].unknown_ids == () and finished[0].failed_items == ()
    assert any(e.recent and e.recent[-1][0] == "Lập trình Python" for e in events)
    assert service.preview_ids(ClassifyScope(doc_ids=("code",)), reclassify=True, limit=3) == ["code"]


# -- The library list: what "the list I am looking at" means ------------------------


def test_scope_follows_the_search_and_sidebar_selection(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS), title="Lập trình Python", tags="python")
    add_book(context, "food", write_epub(tmp_path / "f.epub", COOKING_WORDS), title="Nấu ăn", tags="bếp")
    widget = LibraryListWidget(context)

    everything = widget.classification_scope()
    assert everything.description == "Tất cả tài liệu"
    assert service.preview(everything).total == 2

    context.filters.select("tags", "python")
    qapp.processEvents()
    assert widget.library_filter.tags == ("python",)
    scoped = widget.classification_scope()
    assert "python" in scoped.description
    assert service.preview(scoped).total == 1  # only the list being viewed, not the whole library


def test_scope_description_names_the_selected_collection(qapp, context):
    collection = VirtualCollection(name="Sách hay")
    collection_id = collection.id
    context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at)
    widget = LibraryListWidget(context)
    context.filters.select("collections", collection_id)
    assert "Sách hay" in widget.classification_scope().description
    for i in range(6):
        context.filters.select("tags", f"t{i}", "add")
    assert "(+3)" in widget._describe_current_list()


def test_context_menu_offers_classification_for_the_selection(qapp, context, monkeypatch):
    for i, title in enumerate(("First", "Second")):
        context.db.add_or_update_document(f"d{i}", {"title": title, "author": "A", "file_path": f"{i}.pdf", "created_at": float(i)})
    widget = LibraryListWidget(context)
    widget.resize(600, 400)
    widget.show()
    qapp.processEvents()
    selection = widget.list_view.selectionModel()
    for row in (0, 1):
        selection.select(widget.model.index(row, 0), QItemSelectionModel.Select)
    selection.setCurrentIndex(widget.model.index(0, 0), QItemSelectionModel.NoUpdate)
    qapp.processEvents()
    position = widget.list_view.visualRect(widget.model.index(0, 0)).center()

    requested = []
    widget.smart_classify_requested.connect(requested.append)

    def pick_classify(self, menu, _position):
        return next((a for a in menu.actions() if "Tự động phân loại" in a.text()), None)

    monkeypatch.setattr(LibraryListWidget, "_exec_menu", pick_classify)
    widget._show_context_menu(position)
    assert requested and sorted(requested[0]) == ["d0", "d1"]


# -- Main window: the card after adding files ----------------------------------------


@pytest.fixture
def window(qapp, context, service):
    win = MainWindow(context, smart_classifier=service)
    yield win
    win.hide()


def batch_event(doc_ids, success=None):
    return ImportBatchCompletedEvent(batch_id="b", success=len(doc_ids) if success is None else success, duplicate=0, failed=0, doc_ids=tuple(doc_ids))


def test_the_window_opens_the_dialog_and_reuses_a_running_one(window, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    wizard = window.open_smart_classify()
    assert wizard.isVisible() and window.classify_wizard is wizard
    wizard.hide()
    service.start(ClassifyScope(doc_ids=("code",)))
    assert window.open_smart_classify() is wizard  # a job is running: the same dialog comes back
    service.wait(timeout=30)
    wizard.hide()


def test_reopening_after_background_shows_result_page(qapp, window, context, service, tmp_path):
    """Bug A regression: after 'Chạy nền' + job finishes, re-opening the wizard must show STEP_RESULT."""
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    wizard = window.open_smart_classify()
    wizard.show()
    wizard.start_button.click()
    assert service.wait(timeout=30)
    assert _pump(qapp, lambda: wizard.step_bar.step == STEP_RESULT)
    wizard.hide()
    # Re-opening must reuse the same wizard at STEP_RESULT, not a new blank one.
    reopened = window.open_smart_classify()
    assert reopened is wizard
    assert reopened.step_bar.step == STEP_RESULT
    assert not reopened.done_button.isHidden()
    wizard.deleteLater()
    window.classify_wizard = None


def test_wizard_shows_result_when_job_finished_before_init(qapp, context, service, tmp_path):
    """Bug B regression: race where job finishes before wizard subscribes → _show_result path works."""
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    service.start(ClassifyScope(doc_ids=("code",)))
    assert service.wait(timeout=30)
    assert not service.running and service.last_result is not None
    # Simulate the race: wizard opens with _job_was_running=True but service.running=False.
    # The __init__ fallback branch calls _show_result(service.last_result) directly.
    wizard = SmartClassifyWizard(context, service, lambda: ClassifyScope(description="Tất cả"))
    wizard._job_was_running = True
    # Trigger the same path the __init__ fallback uses.
    wizard._show_result(service.last_result)
    assert wizard.step_bar.step == STEP_RESULT
    assert not wizard.done_button.isHidden()
    wizard.deleteLater()


def test_a_selection_from_the_list_opens_the_dialog_on_those_books(window, context, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    window._on_classify_selected(["code"])
    assert window.classify_wizard.options[0].key == "selected"
    window.classify_wizard.hide()


def test_asking_mode_offers_the_question_on_the_card_and_classifies_on_yes(window, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    card = window.import_card
    card.show_summary(batch_event(["code"]))
    assert card.mode == "summary" and not card.classify_button.isHidden()
    assert "1 sách mới" in card.question_label.text()

    card.classify_button.click()
    assert service.wait(timeout=30)
    assert context.db.get_document("code")["tags"]
    assert card.isHidden()


def test_declining_with_de_sau_does_not_classify(window, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    card = window.import_card
    card.show_summary(batch_event(["code"]))

    card.later_button.click()

    assert not service.running
    assert context.db.get_document("code")["tags"] in ("", None)
    assert card.isHidden()


def test_always_mode_classifies_without_a_question(window, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    context.config.config.smart_classify_on_import = "always"
    card = window.import_card
    card.show_summary(batch_event(["code"]))
    assert card.classify_button.isHidden() and not card.added_label.isHidden()  # the result is still reported
    assert service.wait(timeout=30)
    assert context.db.get_document("code")["tags"]


@pytest.mark.parametrize("mode,doc_ids", [("never", ["code"]), ("ask", [])])
def test_no_question_when_disabled_or_nothing_new(window, context, service, mode, doc_ids):
    context.config.config.smart_classify_on_import = mode
    card = window.import_card
    card.show_summary(ImportBatchCompletedEvent(batch_id="b", success=len(doc_ids), duplicate=1, failed=0,
                                                doc_ids=tuple(doc_ids)))
    assert card.classify_button.isHidden() and not service.running


def test_no_question_without_a_usable_model(window, context, service):
    service.model_path = lambda: None
    card = window.import_card
    card.show_summary(batch_event(["x"]))
    assert card.classify_button.isHidden()
