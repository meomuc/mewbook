from smartdoc.application import classify_layer2
from smartdoc.application.classify_layer2 import Layer2ClassifyService, Layer2Outcome, review_candidates
from smartdoc.application.ollama_classifier import OLLAMA_UNREACHABLE_REASON, Layer2Suggestion


def _job(doc_id, category_id=None, **overrides):
    base = {"id": doc_id, "title": "T", "author": "A", "tags": "", "category_id": category_id, "reason": "low_confidence"}
    base.update(overrides)
    return base


def _ollama_reachable(monkeypatch, reachable: bool = True) -> None:
    """Task D2's preflight (Layer2ClassifyService.availability) calls the real
    application.ai_summary.probe_ollama, which would otherwise try a real network
    connection in every test -- pinned here instead of depending on whatever is or
    isn't listening on localhost:11434 on the machine running the suite."""
    monkeypatch.setattr(classify_layer2, "probe_ollama", lambda base_url: reachable)


def test_review_candidates_keeps_only_unsure_books():
    jobs = [_job("confident", category_id="novel"), _job("unsure", category_id=None)]
    candidates = review_candidates(jobs)
    assert [c.doc_id for c in candidates] == ["unsure"]


def test_disabled_layer2_makes_zero_calls(app_context, monkeypatch):
    _ollama_reachable(monkeypatch)
    app_context.config.config.smart_classify_layer2_enabled = False
    calls = []

    def spy_caller(job, taxonomy, base_url, model):
        calls.append(job.doc_id)
        return Layer2Suggestion()

    service = Layer2ClassifyService(app_context, caller=spy_caller)
    outcomes = service.review([_job("a", category_id=None), _job("b", category_id=None)])

    assert outcomes == []
    assert calls == []  # not one HTTP call, even though both books are "chưa chắc"


def test_enabled_layer2_calls_only_unsure_books(app_context, monkeypatch):
    _ollama_reachable(monkeypatch)
    app_context.config.config.smart_classify_layer2_enabled = True
    calls = []

    def spy_caller(job, taxonomy, base_url, model):
        calls.append(job.doc_id)
        return Layer2Suggestion(category_ids=("novel",), confidence=0.8, insufficient_evidence=False)

    service = Layer2ClassifyService(app_context, caller=spy_caller)
    outcomes = service.review(
        [
            _job("confident", category_id="novel"),  # Lớp 1 already tagged it -- must not be sent
            _job("unsure1", category_id=None),
            _job("unsure2", category_id=None),
        ]
    )

    assert calls == ["unsure1", "unsure2"]  # the confidently-tagged book was skipped
    assert {o.doc_id for o in outcomes} == {"unsure1", "unsure2"}
    assert all(o.category_ids == ("novel",) for o in outcomes)


def test_no_unsure_books_means_no_calls_even_when_enabled(app_context, monkeypatch):
    _ollama_reachable(monkeypatch)
    app_context.config.config.smart_classify_layer2_enabled = True
    calls = []

    def spy_caller(job, taxonomy, base_url, model):
        calls.append(job.doc_id)
        return Layer2Suggestion()

    service = Layer2ClassifyService(app_context, caller=spy_caller)
    outcomes = service.review([_job("confident", category_id="novel")])

    assert outcomes == []
    assert calls == []


def test_a_failed_ollama_call_is_recorded_as_an_error_outcome_not_raised(app_context, monkeypatch):
    from smartdoc.application.ollama_classifier import OllamaClassificationError

    _ollama_reachable(monkeypatch)
    app_context.config.config.smart_classify_layer2_enabled = True

    def failing_caller(job, taxonomy, base_url, model):
        raise OllamaClassificationError("Ollama: lỗi khác, không phải mất kết nối")

    service = Layer2ClassifyService(app_context, caller=failing_caller)
    outcomes = service.review([_job("unsure", category_id=None)])

    assert len(outcomes) == 1
    assert outcomes[0] == Layer2Outcome(doc_id="unsure", error="Ollama: lỗi khác, không phải mất kết nối")


# -- Task D2: reusing the one "is Ollama running" check, checked once per batch -----------------------------


def test_ollama_unreachable_is_checked_once_not_per_book(app_context, monkeypatch):
    """D2's AC: Ollama turned off mid-run -> the next run reports a clear error, doesn't hang, doesn't crash --
    and does so from ONE quick check rather than one slow connection attempt per unsure book."""
    probe_calls = []

    def fake_probe(base_url):
        probe_calls.append(base_url)
        return False

    monkeypatch.setattr(classify_layer2, "probe_ollama", fake_probe)
    app_context.config.config.smart_classify_layer2_enabled = True
    caller_calls = []

    def spy_caller(job, taxonomy, base_url, model):
        caller_calls.append(job.doc_id)  # must never be reached when Ollama is unreachable
        return Layer2Suggestion()

    service = Layer2ClassifyService(app_context, caller=spy_caller)
    outcomes = service.review([_job("a", category_id=None), _job("b", category_id=None), _job("c", category_id=None)])

    assert len(probe_calls) == 1  # one reachability check for the whole batch, not three
    assert caller_calls == []  # no per-book Ollama call was attempted at all
    assert {o.doc_id for o in outcomes} == {"a", "b", "c"}
    assert all(o.error == OLLAMA_UNREACHABLE_REASON for o in outcomes)


def test_ollama_unreachable_reason_is_still_recorded_on_the_document(app_context, monkeypatch):
    _ollama_reachable(monkeypatch, reachable=False)
    app_context.config.config.smart_classify_layer2_enabled = True
    app_context.db.add_or_update_document(
        "d", {"title": "Sách", "author": "A", "file_path": "/d.epub", "tags": "", "created_at": 1.0}
    )
    app_context.db.apply_smart_classifications("r1", "v1", [{"doc_id": "d", "category_id": None, "confidence": 0.1}])

    Layer2ClassifyService(app_context, caller=lambda *a: Layer2Suggestion()).review([_job("d", category_id=None)])

    record = app_context.db.smart_classification_records(["d"])["d"]
    assert record["layer2_error"] == OLLAMA_UNREACHABLE_REASON


def test_availability_reflects_probe_ollama(app_context, monkeypatch):
    _ollama_reachable(monkeypatch, reachable=True)
    assert Layer2ClassifyService(app_context).availability() == (True, "")

    _ollama_reachable(monkeypatch, reachable=False)
    usable, reason = Layer2ClassifyService(app_context).availability()
    assert not usable and reason == OLLAMA_UNREACHABLE_REASON


def test_model_and_base_url_fall_back_to_defaults(app_context):
    from smartdoc.application.ai_summary import OLLAMA_DEFAULT_BASE_URL
    from smartdoc.application.ollama_classifier import DEFAULT_LAYER2_MODEL

    service = Layer2ClassifyService(app_context)
    assert service.model() == DEFAULT_LAYER2_MODEL
    assert service.base_url() == OLLAMA_DEFAULT_BASE_URL


def test_model_and_base_url_are_configurable(app_context):
    app_context.config.config.smart_classify_layer2_model = "llama3.1"
    app_context.config.config.ai_base_url = "http://192.168.1.20:11434"

    service = Layer2ClassifyService(app_context)
    assert service.model() == "llama3.1"
    assert service.base_url() == "http://192.168.1.20:11434"
