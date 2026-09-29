"""Task D1: an *unsure* verdict carries a short excerpt of the book's own text home from
the worker process, so classify_layer2.py can show Ollama something without reading the
file a second time; a confidently-tagged book (the common case) carries none."""
from smartdoc.application.classify_worker import LAYER2_EXCERPT_CHARS, classify_chunk, init_worker

from _smart_helpers import PROGRAMMING_WORDS, WORKER_SETTINGS, make_toy_model, write_epub

UNKNOWN_WORDS = ["zebra", "giraffe", "lion", "tiger", "elephant", "rhino"]


def _job(doc_id, path):
    return {"id": doc_id, "title": "Sách thử", "author": "X", "tags": [], "path": str(path), "extension": "epub"}


def test_unsure_verdict_carries_an_excerpt(tmp_path):
    model_path = make_toy_model(tmp_path / "model.json.gz")
    init_worker({**WORKER_SETTINGS, "model_path": str(model_path)})

    book = write_epub(tmp_path / "book.epub", UNKNOWN_WORDS)
    results = classify_chunk([_job("d1", book)])

    assert results[0]["category_id"] is None
    assert results[0]["excerpt"], "an unsure book should carry a text excerpt for Lớp 2"
    assert len(results[0]["excerpt"]) <= LAYER2_EXCERPT_CHARS


def test_confident_verdict_carries_no_excerpt(tmp_path):
    model_path = make_toy_model(tmp_path / "model.json.gz")
    init_worker({**WORKER_SETTINGS, "model_path": str(model_path)})

    book = write_epub(tmp_path / "book.epub", PROGRAMMING_WORDS)
    results = classify_chunk([_job("d1", book)])

    assert results[0]["category_id"] is not None
    assert "excerpt" not in results[0]  # the common case pays nothing extra crossing the process boundary


def test_no_text_verdict_carries_no_excerpt(tmp_path):
    model_path = make_toy_model(tmp_path / "model.json.gz")
    init_worker({**WORKER_SETTINGS, "model_path": str(model_path)})

    # An extension nothing here can extract text from -- reason "no_text", no body_text to attach.
    job = {"id": "d1", "title": "", "author": "", "tags": [], "path": str(tmp_path / "missing.epub"), "extension": "epub"}
    results = classify_chunk([job])

    assert results[0]["category_id"] is None
    assert "excerpt" not in results[0]
