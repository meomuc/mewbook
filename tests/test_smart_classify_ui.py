import time

import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox

from _smart_helpers import COOKING_WORDS, PROGRAMMING_WORDS, WORKER_SETTINGS, add_book, make_toy_model, thread_executor, write_epub
from smartdoc.application.smart_classifier import ClassifyScope, ScopePreview, SmartClassifyService
from smartdoc.core.event_bus import (
    FacetFilterChangedEvent,
    ImportBatchCompletedEvent,
    SmartClassifyFinishedEvent,
)
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.settings_dialog import SettingsDialog
from smartdoc.presentation.smart_classify_bar import SmartClassifyBar, summarize
from smartdoc.presentation.smart_classify_dialogs import SmartClassifyOfferDialog, SmartClassifyScopeDialog


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


# -- Dialogs --------------------------------------------------------------------


def test_offer_dialog_is_one_compact_popup_carrying_the_import_summary(qapp):
    dialog = SmartClassifyOfferDialog(12, "Thêm thành công: 12")
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Thêm thành công: 12" in texts
    assert "12" in texts
    assert not dialog.remember_checkbox.isChecked()


def test_offer_dialog_reports_the_choice(qapp):
    dialog = SmartClassifyOfferDialog(3)
    dialog.remember_checkbox.setChecked(True)
    dialog.classify_button.click()
    assert dialog.wants_classification() and dialog.remember_choice()

    skipped = SmartClassifyOfferDialog(3)
    skipped.skip_button.click()
    assert not skipped.wants_classification()


def test_scope_dialog_shows_counts_and_disables_start_when_nothing_is_pending(qapp):
    dialog = SmartClassifyScopeDialog(
        "Bộ sưu tập: A", lambda again: ScopePreview(total=100, pending=100 if again else 60, already_categorised=30, already_looked_at=10)
    )
    assert dialog.start_button.isEnabled()
    assert "60" in dialog.counts_label.text()
    dialog.reclassify_checkbox.setChecked(True)
    assert dialog.reclassify()
    assert "100" in dialog.counts_label.text().split("<br>")[0]
    assert "Bộ sưu tập: A" in dialog.scope_label.text()

    empty = SmartClassifyScopeDialog("x", lambda again: ScopePreview(total=5, pending=0, already_categorised=5))
    assert not empty.start_button.isEnabled()


def test_scope_dialog_names_its_subject(qapp):
    dialog = SmartClassifyScopeDialog("2 tài liệu", lambda again: ScopePreview(total=2, pending=2), subject="các tài liệu đã chọn")
    assert "các tài liệu đã chọn" in dialog.scope_label.text()
    assert "danh sách đang xem" not in dialog.scope_label.text()


# -- The bar above the list -------------------------------------------------------


def test_summaries_are_readable_one_liners():
    assert "80" in summarize(finished_event()) and summarize(finished_event()).startswith("✅")
    assert summarize(finished_event(cancelled=True)).startswith("⏹")
    assert "lỗi" in summarize(finished_event(error="lỗi gì đó"))
    assert "Không có" in summarize(finished_event(total=0, tagged=0, skipped=7))
    assert "Văn học" in summarize(finished_event(by_group=(("Văn học", 50),)))


def test_bar_follows_a_job_from_start_to_finish(qapp, context, service, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    bar = SmartClassifyBar(context, service, lambda: ClassifyScope(description="tất cả"))
    bar.show()
    assert bar.classify_button.isEnabled() and not bar.progress.isVisible()

    assert bar.start(ClassifyScope(doc_ids=("code",)))
    assert not bar.classify_button.isEnabled() and bar.stop_button.isVisible()
    assert service.wait(timeout=30)
    deadline = time.time() + 5
    while time.time() < deadline and not bar.undo_button.isVisible():
        qapp.processEvents()
        time.sleep(0.02)
    assert bar.classify_button.isEnabled()
    assert bar.undo_button.isVisible() and not bar.stop_button.isVisible()
    assert "✅" in bar.status_label.full_text()

    bar.dismiss_button.click()
    assert not bar.undo_button.isVisible()


def test_a_long_result_line_does_not_widen_the_window(qapp, context, service):
    bar = SmartClassifyBar(context, service, lambda: ClassifyScope())
    before = bar.minimumSizeHint().width()
    bar._show_finished(finished_event(by_group=tuple((f"Nhóm rất dài số {i}" * 3, 9) for i in range(3))))
    assert bar.minimumSizeHint().width() <= before + 200
    assert "Nhiều nhất" in bar.status_label.full_text()
    assert bar.status_label.toolTip() == bar.status_label.full_text()


def test_bar_undo_takes_the_tags_back(qapp, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    bar = SmartClassifyBar(context, service, lambda: ClassifyScope())
    bar.show()
    bar.start(ClassifyScope(doc_ids=("code",)))
    assert service.wait(timeout=30)
    deadline = time.time() + 5
    while time.time() < deadline and not bar.undo_button.isVisible():
        qapp.processEvents()
        time.sleep(0.02)
    assert context.db.get_document("code")["tags"]
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    bar.undo_button.click()
    assert not context.db.get_document("code")["tags"]


def test_bar_explains_when_there_is_no_model(qapp, context, service, monkeypatch):
    service.model_path = lambda: None
    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda parent, title, text, *a: shown.append(text)))
    bar = SmartClassifyBar(context, service, lambda: ClassifyScope())
    bar.classify_button.click()
    assert shown and "train.py" in shown[0]


def test_bar_asks_before_starting_and_respects_cancel(qapp, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    bar = SmartClassifyBar(context, service, lambda: ClassifyScope(description="tất cả"))
    monkeypatch.setattr(SmartClassifyScopeDialog, "exec", lambda self: QDialog.Rejected)
    bar.classify_button.click()
    assert not service.running
    assert context.db.get_document("code")["tags"] in ("", None)

    monkeypatch.setattr(SmartClassifyScopeDialog, "exec", lambda self: QDialog.Accepted)
    bar.classify_button.click()
    assert service.wait(timeout=30)
    assert context.db.get_document("code")["tags"]


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
        return next((a for a in menu.actions() if "Phân loại thông minh" in a.text()), None)

    monkeypatch.setattr(LibraryListWidget, "_exec_menu", pick_classify)
    widget._show_context_menu(position)
    assert requested and sorted(requested[0]) == ["d0", "d1"]


# -- Main window: the popup after adding files ----------------------------------------


@pytest.fixture
def window(qapp, context, service):
    win = MainWindow(context, smart_classifier=service)
    yield win
    win.hide()


def batch_event(doc_ids, success=None):
    return ImportBatchCompletedEvent(batch_id="b", success=len(doc_ids) if success is None else success, duplicate=0, failed=0, doc_ids=tuple(doc_ids))


def test_window_puts_the_classify_bar_above_the_list(window):
    layout = window.library_view.parentWidget().layout()
    assert layout.indexOf(window.smart_bar) < layout.indexOf(window.library_view)


def test_asking_mode_offers_the_popup_and_classifies_on_yes(window, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    shown = []

    def fake_exec(self):
        shown.append(self)
        self.classify_button.click()
        return QDialog.Accepted

    monkeypatch.setattr(SmartClassifyOfferDialog, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: pytest.fail("plain summary shown")))
    window._show_import_summary(batch_event(["code"]))
    assert len(shown) == 1
    assert service.wait(timeout=30)
    assert context.db.get_document("code")["tags"]
    assert context.config.config.smart_classify_on_import == "ask"  # not remembered unless ticked


def test_declining_does_not_classify_and_can_be_remembered(window, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))

    def fake_exec(self):
        self.remember_checkbox.setChecked(True)
        self.skip_button.click()
        return QDialog.Rejected

    monkeypatch.setattr(SmartClassifyOfferDialog, "exec", fake_exec)
    window._show_import_summary(batch_event(["code"]))
    assert not service.running
    assert context.db.get_document("code")["tags"] in ("", None)
    assert context.config.config.smart_classify_on_import == "never"


def test_always_mode_classifies_without_a_question(window, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    context.config.config.smart_classify_on_import = "always"
    monkeypatch.setattr(SmartClassifyOfferDialog, "exec", lambda self: pytest.fail("asked although set to always"))
    info = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info.append(a)))
    window._show_import_summary(batch_event(["code"]))
    assert info  # the import result is still reported
    assert service.wait(timeout=30)
    assert context.db.get_document("code")["tags"]


@pytest.mark.parametrize("mode,doc_ids", [("never", ["code"]), ("ask", [])])
def test_no_popup_when_disabled_or_nothing_new(window, context, service, monkeypatch, mode, doc_ids):
    context.config.config.smart_classify_on_import = mode
    monkeypatch.setattr(SmartClassifyOfferDialog, "exec", lambda self: pytest.fail("offered"))
    info = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info.append(a)))
    window._show_import_summary(batch_event(doc_ids))
    assert info and not service.running


def test_no_popup_without_a_usable_model(window, context, service, monkeypatch):
    service.model_path = lambda: None
    monkeypatch.setattr(SmartClassifyOfferDialog, "exec", lambda self: pytest.fail("offered without a model"))
    info = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info.append(a)))
    window._show_import_summary(batch_event(["x"]))
    assert info


def test_selection_request_opens_the_scope_dialog_for_those_documents(window, context, service, tmp_path, monkeypatch):
    add_book(context, "code", write_epub(tmp_path / "c.epub", PROGRAMMING_WORDS))
    seen = []

    def fake_exec(self):
        seen.append(self.scope_label.text())
        return QDialog.Accepted

    monkeypatch.setattr(SmartClassifyScopeDialog, "exec", fake_exec)
    window._on_classify_selected(["code"])
    assert seen and "các tài liệu đã chọn" in seen[0]
    assert service.wait(timeout=30)
    assert context.db.get_document("code")["tags"]


def test_closing_the_window_stops_the_classifier(window, service):
    window.closeEvent(type("E", (), {"accept": lambda self: None})())
    assert not service.running


# -- Settings ---------------------------------------------------------------------------


def test_settings_tab_saves_the_classification_choices(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert dialog.smart_on_import_combo.currentData() == "ask"
    dialog.smart_on_import_combo.setCurrentIndex(dialog.smart_on_import_combo.findData("always"))
    dialog.smart_max_words_spin.setValue(4500)
    dialog.smart_workers_spin.setValue(3)
    dialog._on_save()
    config = app_context.config.config
    assert (config.smart_classify_on_import, config.smart_classify_max_words, config.smart_classify_max_workers) == ("always", 4500, 3)


def test_settings_tab_shows_which_model_is_in_use(qapp, app_context):
    dialog = SettingsDialog(app_context)
    assert "classifier_model" in dialog._smart_classify_model_text()
