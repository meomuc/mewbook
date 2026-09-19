import subprocess
import sys
import threading
import time

import pytest

from _smart_helpers import (
    COOKING_WORDS,
    PROGRAMMING_WORDS,
    WORKER_SETTINGS,
    add_book,
    make_toy_model,
    thread_executor,
    write_epub,
)
from smartdoc.application.smart_classifier import AutoClassifyOnImport, ClassifyScope, SmartClassifyService
from smartdoc.core.event_bus import DocumentIndexedEvent, SmartClassifyFinishedEvent, SmartClassifyProgressEvent


@pytest.fixture
def context(app_context):
    make_toy_model(app_context.config.app_data_dir / "models" / "classifier_model.json.gz")
    return app_context


@pytest.fixture
def service(context):
    svc = SmartClassifyService(context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    yield svc
    svc.stop()


@pytest.fixture
def events(context):
    finished, progress = [], []
    context.event_bus.subscribe(SmartClassifyFinishedEvent, finished.append)
    context.event_bus.subscribe(SmartClassifyProgressEvent, progress.append)
    return finished, progress


def tags_of(context, doc_id):
    return [t.strip() for t in (context.db.get_document(doc_id)["tags"] or "").split(",") if t.strip()]


def library(context, tmp_path):
    add_book(context, "code", write_epub(tmp_path / "code.epub", PROGRAMMING_WORDS), title="Học lập trình")
    add_book(context, "food", write_epub(tmp_path / "food.epub", COOKING_WORDS), title="Món ngon")
    return context


def run(service, scope, **kwargs):
    assert service.start(scope, **kwargs)
    assert service.wait(timeout=60)


def test_nothing_is_running_or_loaded_until_a_job_starts(service):
    assert not service.running
    assert service._taxonomy is None


def test_tags_documents_and_files_the_hashtag_under_its_group(context, service, events, tmp_path):
    library(context, tmp_path)
    finished, progress = events
    run(service, ClassifyScope(description="tất cả"))
    result = finished[-1]
    assert (result.total, result.tagged, result.unknown, result.failed) == (2, 2, 0, 0)
    assert tags_of(context, "code") == ["Công nghệ thông tin"]
    assert tags_of(context, "food") == ["Ẩm thực - Nấu ăn"]
    assert progress and progress[-1].done == 2
    groups = {g["name"] for g in context.db.list_facet_groups("tag")}
    assert {"Khoa học - Công nghệ", "Đời sống"} & groups
    members = {
        row["value"] for row in context.db.connection.execute("SELECT value FROM facet_group_members WHERE category='tag'")
    }
    assert {"Công nghệ thông tin", "Ẩm thực - Nấu ăn"} <= members


def test_existing_tags_are_kept_and_user_categories_are_respected(context, service, events, tmp_path):
    add_book(context, "mine", write_epub(tmp_path / "m.epub", COOKING_WORDS), tags="Truyện cười, yêu thích")
    add_book(context, "plain", write_epub(tmp_path / "p.epub", PROGRAMMING_WORDS), tags="đọc-sau")
    finished, _ = events
    run(service, ClassifyScope(doc_ids=("mine", "plain")))
    assert finished[-1].skipped == 1 and finished[-1].tagged == 1
    assert tags_of(context, "mine") == ["Truyện cười", "yêu thích"]  # already categorised by the user: untouched
    assert tags_of(context, "plain") == ["đọc-sau", "Công nghệ thông tin"]


def test_a_folder_the_user_chose_for_a_hashtag_is_not_overridden(context, service, tmp_path):
    library(context, tmp_path)
    group_id = context.db.create_facet_group("tag", "Bếp của tôi")
    context.db.connection.execute(
        "INSERT INTO facet_group_members (category, value, group_id) VALUES ('tag', 'Ẩm thực - Nấu ăn', ?)", (group_id,)
    )
    context.db.connection.commit()
    run(service, ClassifyScope(doc_ids=("food",)))
    row = context.db.connection.execute(
        "SELECT group_id FROM facet_group_members WHERE category='tag' AND value='Ẩm thực - Nấu ăn'"
    ).fetchone()
    assert row["group_id"] == group_id


def test_documents_the_model_is_unsure_about_get_no_tag_and_are_not_reread(context, service, events, tmp_path):
    add_book(context, "vague", write_epub(tmp_path / "v.epub", ["zzz", "qqq"]), title="Không rõ")
    finished, _ = events
    run(service, ClassifyScope(doc_ids=("vague",)))
    assert finished[-1].tagged == 0 and finished[-1].unknown == 1
    assert tags_of(context, "vague") == []
    assert service.preview(ClassifyScope(doc_ids=("vague",))).already_looked_at == 1
    assert service.preview(ClassifyScope(doc_ids=("vague",)), reclassify=True).pending == 1


def test_preview_counts_what_would_happen(context, service, tmp_path):
    library(context, tmp_path)
    add_book(context, "done", write_epub(tmp_path / "d.epub", COOKING_WORDS), tags="Truyện cười")
    preview = service.preview(ClassifyScope())
    assert (preview.total, preview.pending, preview.already_categorised) == (3, 2, 1)


def test_scope_can_follow_the_current_list_filter(context, service, events, tmp_path):
    library(context, tmp_path)
    finished, _ = events
    run(service, ClassifyScope(where_sql="documents.title LIKE ?", params=("Món%",), description="lọc"))
    assert finished[-1].total == 1
    assert tags_of(context, "food") and not tags_of(context, "code")


def test_undo_removes_only_what_the_run_added(context, service, events, tmp_path):
    add_book(context, "keep", write_epub(tmp_path / "k.epub", PROGRAMMING_WORDS), tags="đọc-sau")
    finished, _ = events
    run(service, ClassifyScope(doc_ids=("keep",)))
    assert "Công nghệ thông tin" in tags_of(context, "keep")
    assert service.undo(finished[-1].run_id) == 1
    assert tags_of(context, "keep") == ["đọc-sau"]
    assert service.preview(ClassifyScope(doc_ids=("keep",))).pending == 1  # forgotten: eligible again


def test_reclassifying_swaps_the_machine_tag_instead_of_stacking_two(context, service, tmp_path):
    add_book(context, "b", write_epub(tmp_path / "b.epub", PROGRAMMING_WORDS))
    run(service, ClassifyScope(doc_ids=("b",)))
    assert tags_of(context, "b") == ["Công nghệ thông tin"]
    write_epub(tmp_path / "b.epub", COOKING_WORDS)  # the file now reads as a cookbook
    run(service, ClassifyScope(doc_ids=("b",)), reclassify=True)
    assert tags_of(context, "b") == ["Ẩm thực - Nấu ăn"]


def test_unreadable_files_are_counted_not_fatal(context, service, events, tmp_path):
    add_book(context, "gone", tmp_path / "missing.epub")
    library(context, tmp_path)
    finished, _ = events
    run(service, ClassifyScope())
    assert finished[-1].failed == 1 and finished[-1].tagged == 2


def test_only_one_job_at_a_time(context, service, tmp_path):
    library(context, tmp_path)
    gate = threading.Event()

    def slow_executor(workers, settings):
        executor = thread_executor(workers, settings)
        real_submit = executor.submit
        executor.submit = lambda fn, *a, **k: real_submit(lambda: (gate.wait(10), fn(*a, **k))[1])
        return executor

    service._executor_factory = slow_executor
    assert service.start(ClassifyScope())
    assert service.running
    assert service.start(ClassifyScope()) is None
    gate.set()
    assert service.wait(timeout=30)
    assert not service.running


def test_cancel_stops_the_job_and_reports_it(context, service, events, tmp_path):
    for i in range(30):
        add_book(context, f"b{i}", write_epub(tmp_path / f"b{i}.epub", PROGRAMMING_WORDS))
    finished, _ = events
    gate = threading.Event()

    def slow_executor(workers, settings):
        executor = thread_executor(workers, settings)
        real_submit = executor.submit
        executor.submit = lambda fn, *a, **k: real_submit(lambda: (gate.wait(0.3), fn(*a, **k))[1])
        return executor

    service._executor_factory = slow_executor
    assert service.start(ClassifyScope())
    time.sleep(0.4)
    service.cancel()
    assert service.wait(timeout=30)
    assert finished[-1].cancelled
    assert finished[-1].tagged < 30


def test_enqueue_runs_now_when_idle_and_after_the_current_job_when_busy(context, service, events, tmp_path):
    library(context, tmp_path)
    finished, _ = events
    service.enqueue(["code"])
    service.enqueue(["food"])  # may land while the first is still running: must not be lost
    deadline = time.time() + 30
    while time.time() < deadline and (service.running or not tags_of(context, "food")):
        time.sleep(0.05)
    assert service.wait(timeout=30)
    assert tags_of(context, "code") and tags_of(context, "food")


def test_no_model_means_unavailable(app_context):
    svc = SmartClassifyService(app_context, executor_factory=thread_executor, worker_settings=WORKER_SETTINGS)
    svc.model_path = lambda: None
    usable, reason = svc.availability()
    assert not usable and "train.py" in reason


def test_a_model_older_than_the_taxonomy_produces_a_notice(context, service):
    assert service.model_notice() == ""
    (context.config.app_data_dir / "taxonomy.json").write_text(
        '{"categories": [{"id": "gardening", "name": "Làm vườn", "group": "Đời sống"}]}', encoding="utf-8"
    )
    service.reload_taxonomy()
    assert "Làm vườn" in service.model_notice()


def test_auto_classify_collects_watcher_documents_when_set_to_always(context, service, tmp_path):
    library(context, tmp_path)
    context.config.config.smart_classify_on_import = "always"
    auto = AutoClassifyOnImport(context, service, delay_seconds=0.1)
    try:
        context.event_bus.publish(DocumentIndexedEvent(doc_id="code", batch_id=None))
        context.event_bus.publish(DocumentIndexedEvent(doc_id="food", batch_id="some-batch"))  # batches are asked about elsewhere
        deadline = time.time() + 15
        while time.time() < deadline and not tags_of(context, "code"):
            time.sleep(0.05)
        assert service.wait(timeout=30)
        assert tags_of(context, "code") and not tags_of(context, "food")
    finally:
        auto.stop()


def test_auto_classify_does_nothing_when_not_set_to_always(context, service, tmp_path):
    library(context, tmp_path)
    auto = AutoClassifyOnImport(context, service, delay_seconds=0.05)
    try:
        context.event_bus.publish(DocumentIndexedEvent(doc_id="code", batch_id=None))
        time.sleep(0.3)
        assert not service.running and not tags_of(context, "code")
    finally:
        auto.stop()


def test_importing_the_app_does_not_load_the_machine_learning_stack():
    """Startup speed: the model, the tokenizer (pyvi -> scikit-learn) and the
    training code must stay out of the GUI process until they are needed."""
    code = (
        "import sys\n"
        "import smartdoc.app, smartdoc.presentation.main_window\n"
        "heavy = [m for m in ('pyvi', 'sklearn', 'scipy', 'numpy', 'smartdoc.application.classification_trainer',"
        " 'smartdoc.infrastructure.vi_tokenizer', 'smartdoc.infrastructure.text_sampler') if m in sys.modules]\n"
        "print('LOADED:' + ','.join(heavy))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("LOADED:"), out.stdout
