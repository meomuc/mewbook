"""Shared building blocks for the smart-classification tests: a tiny trained
model, EPUBs to read, and an in-process stand-in for the worker process pool
(so no test needs to spawn a real child)."""
from __future__ import annotations

import zipfile
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path

from smartdoc.application import classification_trainer as trainer
from smartdoc.application.classify_worker import init_worker
from smartdoc.domain.taxonomy import Taxonomy
from smartdoc.infrastructure.vi_tokenizer import TextProcessor

PROGRAMMING_WORDS = "python code function compiler software developer database".split()
COOKING_WORDS = "recipe ingredients chicken sauce oven bake kitchen".split()

WORKER_SETTINGS = {"segmenter": "none", "low_priority": False}


def thread_executor(workers: int, settings: dict) -> Executor:
    init_worker(settings)  # in this process, so no child has to be spawned
    return ThreadPoolExecutor(max_workers=1)


def make_toy_model(path: Path) -> Path:
    """A model that tells "programming" books from "cooking" ones, saved at `path`."""
    taxonomy = Taxonomy.load_builtin()
    interner = trainer.Interner()
    vocab = {"programming": PROGRAMMING_WORDS, "cooking": COOKING_WORDS}
    docs = [
        trainer.TrainingDoc(
            doc_id=f"{label}{i}",
            body=trainer.Counts.from_dict(interner, {w: 3.0 for w in words}),
            label=label,
            label_source="tag",
            group_key=f"{label}{i}",
        )
        for label, words in vocab.items()
        for i in range(12)
    ]
    result = trainer.train(
        docs, taxonomy, interner, TextProcessor(segmenter=None), trainer.TrainOptions(synthetic_per_class=0, refit_on_all=False)
    )
    result.model.save(path)
    return path


def write_epub(path: Path, words: list[str], *, repeat: int = 30, subject: str | None = None) -> Path:
    subject_xml = f"<dc:subject>{subject}</dc:subject>" if subject else ""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="c.opf"/></rootfiles></container>',
        )
        zf.writestr(
            "c.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<metadata>{subject_xml}</metadata>"
            '<manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="a"/></spine></package>',
        )
        zf.writestr("a.xhtml", "<html><body><p>" + (" ".join(words) + " ") * repeat + "</p></body></html>")
    return path


def add_book(context, doc_id: str, path: Path, *, title: str = "Sách thử", tags: str = "") -> None:
    context.db.add_or_update_document(
        doc_id,
        {"title": title, "author": "X", "file_path": str(path), "extension": "epub", "tags": tags, "created_at": 1.0},
    )
