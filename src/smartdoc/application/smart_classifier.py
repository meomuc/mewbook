"""Smart classification service: tags documents with a category and files it in
the sidebar tree -- in the background, without getting in the user's way.

What one classification *does* to a document (never to its file):

1. the category's name is added to the document's hashtags (existing tags are
   kept), e.g. "Kiếm hiệp - Tiên hiệp";
2. that hashtag is filed under the category's group in the sidebar's Hashtag
   tree ("Văn học"), creating the folder if needed -- unless the user has
   already put that hashtag in a folder, which is respected.

Both are ordinary library metadata: physical files are never moved, and a whole
run can be undone (:meth:`SmartClassifyService.undo`). A document that already
carries a category tag is left alone, and one the model isn't sure about gets no
tag at all -- but is remembered as "looked at", so it isn't re-read every run.

How it stays out of the way (the spec: "luôn có cảm giác phần mềm chạy rất nhanh"):

- **Nothing runs at startup.** The model, the tokenizer and the training code are
  not loaded until a job starts (and the training code never is: see train.py).
- **Off the GUI process.** Reading books and segmenting Vietnamese happens in a
  separate low-priority process (classify_worker.py) that exits when the job ends,
  returning its memory. The GUI process only plans the job, writes results
  and paints progress.
- **Bounded.** One worker for a small job, at most a couple for a big one; a
  small window of chunks in flight, so cancelling responds within a fraction of
  a second and memory stays flat however large the library is.
- **Gentle on the database and the UI.** Results are written in batches of a few
  dozen documents in one transaction, and the library view is told to refresh
  at most every couple of seconds instead of after every book.
- **Resumable.** Every decision is stored; stopping or crashing mid-way loses
  at most the current batch, and running again picks up where it left off.
- **Crash-proof.** If a malformed file kills the worker, the job continues with a
  fresh one, one book at a time, and the guilty book is skipped.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, BrokenExecutor, Executor, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.application.classify_worker import classify_chunk, init_worker
from smartdoc.core.event_bus import LibraryUpdatedEvent, SmartClassifyFinishedEvent, SmartClassifyProgressEvent
from smartdoc.domain.taxonomy import Taxonomy
from smartdoc.domain.text_classifier import read_model_meta, resolve_model_path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8
"""Books per task sent to the worker: small enough that cancelling is prompt
and progress is smooth, large enough that the process boundary is not the
bottleneck."""
FLUSH_EVERY_ITEMS = 40
FLUSH_EVERY_SECONDS = 1.5
LIBRARY_EVENT_MIN_INTERVAL = 2.0
MAX_WORKER_CRASHES = 6
SMALL_JOB = 150  # below this, one worker is plenty
CRASH_ERROR = "worker crashed"


@dataclass(frozen=True)
class ClassifyScope:
    """Which documents to look at: explicit ids, or "everything the library
    view is currently showing" (a text query + a filter)."""

    doc_ids: tuple[str, ...] | None = None
    fts_query: str = ""
    where_sql: str = ""
    params: tuple = ()
    description: str = ""


@dataclass
class ScopePreview:
    total: int = 0
    """Documents in the scope."""
    pending: int = 0
    """Documents that would actually be read and classified."""
    already_categorised: int = 0
    """Skipped: they already carry a category tag."""
    already_looked_at: int = 0
    """Skipped: classified (or judged unsure) by this model earlier."""


@dataclass
class _Plan:
    jobs: list[dict] = field(default_factory=list)
    old_tags: dict[str, str] = field(default_factory=dict)
    preview: ScopePreview = field(default_factory=ScopePreview)


# Why a book was left for the person to tag, in words for the result page (keys are what `unsure_reason` returns).
# The hashtag "chưa chắc" (unsure) books get automatically, so they show up and can be found in the ordinary library view,
# not only in the result list. A plain tag (no sidebar folder): it is a status, not a genre. Swapped out for the real category
# the moment one is found (see tag_books and the "replace_tag" below), so it never sits on a book next to its real hashtag.
UNSURE_TAG = "Chưa chắc"

UNSURE_REASONS = {
    "no_text": "Không có chữ đọc được (bản quét, có DRM hoặc định dạng không đọc được)",
    "periodical": "Tạp chí, báo: không thuộc thể loại sách nào",
    "mixed_topics": "Nội dung trộn nhiều chủ đề",
    "low_confidence": "Mô hình phân vân giữa nhiều thể loại",
    "not_enough_evidence": "Ít chữ hoặc chưa đủ manh mối",
}


def unsure_reason(result: dict) -> str:
    """One of UNSURE_REASONS' keys for a worker result that got no category."""
    reason = result.get("reason") or ""
    if not result.get("words") and reason in ("", "no_text", "not_enough_evidence", "error"):
        return "no_text"
    return reason if reason in UNSURE_REASONS else "not_enough_evidence"


def default_executor_factory(workers: int, settings: dict) -> Executor:
    # "spawn" everywhere: a forked copy of a running Qt application is not safe,
    # and it's what Windows does anyway.
    return ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn"), initializer=init_worker, initargs=(settings,)
    )


def _shutdown_executor(executor: Executor | None, *, kill: bool) -> None:
    if executor is None:
        return
    processes = list((getattr(executor, "_processes", None) or {}).values())  # private, best effort
    try:
        executor.shutdown(wait=not kill, cancel_futures=True)
    except Exception:
        logger.debug("executor shutdown failed", exc_info=True)
    if kill:
        for process in processes:
            try:
                if process.is_alive():
                    process.terminate()
            except Exception:
                pass


class SmartClassifyService:
    def __init__(
        self,
        context,
        executor_factory: Callable[[int, dict], Executor] | None = None,
        chunk_size: int = CHUNK_SIZE,
        worker_settings: dict | None = None,
    ) -> None:
        self.context = context
        self._executor_factory = executor_factory or default_executor_factory
        self._chunk_size = max(1, chunk_size)
        self._extra_worker_settings = worker_settings or {}
        self._taxonomy: Taxonomy | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._queued: list[str] = []
        self.last_result: SmartClassifyFinishedEvent | None = None

    # -- Model and taxonomy --------------------------------------------------------

    @property
    def taxonomy(self) -> Taxonomy:
        if self._taxonomy is None:
            self._taxonomy = Taxonomy.load(self.context.config.app_data_dir)
        return self._taxonomy

    def reload_taxonomy(self) -> None:
        self._taxonomy = None

    def model_path(self) -> Path | None:
        return resolve_model_path(self.context.config.app_data_dir)

    def model_version(self) -> str:
        """Identifies the model file, so a re-trained model re-opens the
        "looked at, unsure" documents for another try."""
        path = self.model_path()
        if path is None:
            return ""
        try:
            stat = path.stat()
        except OSError:
            return path.name
        return f"{path.name}:{int(stat.st_mtime)}:{stat.st_size}"

    def availability(self) -> tuple[bool, str]:
        """(usable, reason if not) -- shown to the user before offering anything."""
        path = self.model_path()
        if path is None:
            return False, (
                "Chưa có mô hình phân loại. Hãy chạy train.py (xem hướng dẫn trong README) "
                "để tạo mô hình từ thư viện của bạn."
            )
        return True, ""

    def model_notice(self) -> str:
        """A gentle warning when the categories were edited after the model was
        trained (the model can't predict a category it has never seen)."""
        path = self.model_path()
        meta = read_model_meta(path) if path else None
        if not meta or not meta.get("categories"):
            return ""
        known = set(meta["categories"])
        added = [c.name for c in self.taxonomy if c.id not in known]
        if added:
            return f"Có {len(added)} thể loại mới chưa được huấn luyện ({', '.join(added[:3])}...): chạy lại train.py."
        return ""

    # -- Planning --------------------------------------------------------------------

    def _resolve_ids(self, scope: ClassifyScope) -> list[str]:
        if scope.doc_ids is not None:
            return list(dict.fromkeys(scope.doc_ids))
        return self.context.db.list_document_ids_matching(scope.fts_query, scope.where_sql, scope.params)

    def _plan(self, scope: ClassifyScope, reclassify: bool) -> _Plan:
        db, taxonomy = self.context.db, self.taxonomy
        ids = self._resolve_ids(scope)
        plan = _Plan()
        plan.preview.total = len(ids)
        rows = db.get_documents_light(ids)
        records = db.smart_classification_records(ids)
        version = self.model_version()
        for row in rows:
            record = records.get(row["id"])
            tags = row["tags"] or ""
            has_category_tag = bool(taxonomy.categories_in_tags(tags))
            auto_tag = None
            if record and record.get("applied_tag") and record["applied_tag"].casefold() in {
                t.strip().casefold() for t in tags.split(",")
            }:
                auto_tag = record["applied_tag"]
            if has_category_tag and not (reclassify and auto_tag):
                plan.preview.already_categorised += 1  # the user's own categories are respected
                continue
            if not reclassify and record and record.get("model_version") == version:
                plan.preview.already_looked_at += 1
                continue
            plan.jobs.append(
                {
                    "id": row["id"],
                    "title": row["title"] or "",
                    "author": row["author"] or "",
                    "tags": taxonomy.without_category_tags(tags),
                    "path": row["file_path"],
                    "extension": (row["extension"] or "").lower(),
                }
            )
            if auto_tag:
                plan.old_tags[row["id"]] = auto_tag
        plan.jobs.sort(key=lambda job: job["path"] or "")  # neighbouring files on disk: friendlier to the cache
        plan.preview.pending = len(plan.jobs)
        return plan

    def preview(self, scope: ClassifyScope, *, reclassify: bool = False) -> ScopePreview:
        """What a run over `scope` would do, without starting one. Cheap
        enough (light columns only, no file reads) for the GUI thread."""
        return self._plan(scope, reclassify).preview

    def preview_ids(self, scope: ClassifyScope, *, reclassify: bool = False, limit: int = 6) -> list[str]:
        """A few of the books a run would read (for the cover strip of the first step)."""
        return [job["id"] for job in self._plan(scope, reclassify).jobs[:limit]]

    # -- Running ---------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, scope: ClassifyScope, *, reclassify: bool = False) -> str | None:
        """Starts a background job and returns its id, or None if one is
        already running. Progress and completion arrive as
        SmartClassifyProgressEvent / SmartClassifyFinishedEvent."""
        with self._lock:
            if self._thread is not None:
                return None
            self._cancel.clear()
            job_id = uuid.uuid4().hex
            self._thread = threading.Thread(
                target=self._thread_main, args=(job_id, scope, reclassify), name="smart-classify", daemon=True
            )
            self._thread.start()
            return job_id

    def enqueue(self, doc_ids, description: str = "tài liệu mới") -> None:
        """Classify these documents: now if idle, otherwise right after the
        running job. For "the user added documents" flows, where refusing
        because something else is busy would just lose the request."""
        ids = [i for i in doc_ids if i]
        if not ids:
            return
        with self._lock:
            if self._thread is not None:
                self._queued.extend(ids)
                return
        if self.start(ClassifyScope(doc_ids=tuple(ids), description=description)) is None:
            with self._lock:  # a job slipped in between the check and the start
                self._queued.extend(ids)

    def _thread_main(self, job_id: str, scope: ClassifyScope, reclassify: bool) -> None:
        """Runs the requested job, then whatever was queued meanwhile, then exits."""
        job: tuple[str, ClassifyScope, bool] | None = (job_id, scope, reclassify)
        while job is not None:
            try:
                self._run(job[0], uuid.uuid4().hex, job[1], job[2])
            finally:
                with self._lock:
                    if self._cancel.is_set() or not self._queued:
                        self._queued.clear()
                        self._thread = None
                        job = None
                    else:
                        ids, self._queued = list(dict.fromkeys(self._queued)), []
                        job = (uuid.uuid4().hex, ClassifyScope(doc_ids=tuple(ids), description="tài liệu mới"), False)

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Blocks until the current job (if any) has finished, *without*
        cancelling it. Returns False on timeout."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    def stop(self, timeout: float = 10.0) -> None:
        """For application shutdown: cancel and wait for the job thread to
        finish, so nothing is still reading the database as it closes."""
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    def category_choices(self) -> list[tuple[str, str, str]]:
        """(sidebar folder, hashtag, category id) of every category, in the taxonomy's order: what "Gắn hashtag" offers."""
        return [(c.group, c.name, c.id) for c in self.taxonomy]

    def tag_books(self, doc_ids: list[str], label: str) -> tuple[str, int]:
        """The person's own hashtag for these books (from the result list): `label` is a category of the taxonomy (by name or
        alias) or any text they typed. A category files the hashtag under its sidebar folder like an automatic run does; anything
        else is a plain hashtag. It only ever adds (see DatabaseManager.apply_smart_classifications), is recorded as certain
        (confidence 1) under a run of its own, so the book is not looked at again, and it cannot be taken back with the
        classification run's "Hoàn tác". Returns (the hashtag written, how many books got it)."""
        label = " ".join((label or "").split())
        if not label or not doc_ids:
            return "", 0
        category = self.taxonomy.match_label(label)
        tag = category.name if category else label
        item = {"category_id": category.id if category else None, "confidence": 1.0, "tag": tag,
                "group": category.group if category else None}
        # A book the person decides by hand is settled: its UNSURE_TAG placeholder, if it has one, is swapped out for the
        # real hashtag rather than left sitting next to it.
        current = {row["id"]: row.get("tags") or "" for row in self.context.db.get_documents_light(doc_ids)}
        jobs = [{"doc_id": doc_id, **item,
                "replace_tag": UNSURE_TAG if UNSURE_TAG.casefold() in {t.strip().casefold() for t in current.get(doc_id, "").split(",")} else None}
               for doc_id in doc_ids]
        stats = self.context.db.apply_smart_classifications(f"manual-{uuid.uuid4().hex[:12]}", self.model_version(), jobs)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        return tag, stats["tagged"] + stats["already_tagged"]

    def undo(self, run_id: str) -> int:
        """Takes back a run's hashtags (see DatabaseManager.undo_smart_classification)."""
        changed = self.context.db.undo_smart_classification(run_id)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        return changed

    def _choose_workers(self, jobs: int) -> int:
        if jobs < SMALL_JOB:
            return 1
        cap = max(1, min(4, int(self.context.config.config.smart_classify_max_workers or 1)))
        return max(1, min(cap, (os.cpu_count() or 2) // 4))

    def _worker_settings(self, model_path: Path) -> dict:
        settings = {
            "model_path": str(model_path),
            "max_words": self.context.config.config.smart_classify_max_words,
            "app_data_dir": str(self.context.config.app_data_dir),
            "low_priority": True,
        }
        settings.update(self._extra_worker_settings)
        return settings

    def _run(self, job_id: str, run_id: str, scope: ClassifyScope, reclassify: bool) -> None:
        started = time.perf_counter()
        bus = self.context.event_bus
        tally: Counter = Counter()
        by_group: Counter = Counter()
        tagged_ids: list[str] = []
        unknown_ids: list[str] = []
        failed_items: list[tuple[str, str]] = []
        tagged_items: list[tuple[str, str, str]] = []
        unknown_items: list[tuple[str, str]] = []
        recent: deque = deque(maxlen=3)
        titles: dict[str, str] = {}
        error = ""
        executor: Executor | None = None
        killed = False
        total = 0
        try:
            plan = self._plan(scope, reclassify)
            tally["skipped"] = plan.preview.already_categorised + plan.preview.already_looked_at
            total = len(plan.jobs)
            titles = {job["id"]: job["title"] or Path(job["path"] or "").stem for job in plan.jobs}
            if total == 0:
                return
            usable, reason = self.availability()
            if not usable:
                error = reason
                return

            version = self.model_version()
            workers = self._choose_workers(total)
            settings = self._worker_settings(self.model_path())
            bus.publish(SmartClassifyProgressEvent(job_id=job_id, done=0, total=total, phase="starting"))
            executor = self._executor_factory(workers, settings)

            chunks = deque(plan.jobs[i : i + self._chunk_size] for i in range(0, total, self._chunk_size))
            in_flight: dict = {}
            window = workers * 2
            items: list[dict] = []
            done = 0
            crashes = 0
            last_flush = last_library_event = time.monotonic()

            def flush(final: bool = False) -> None:
                nonlocal last_flush, last_library_event
                if not items:
                    return
                self.context.db.apply_smart_classifications(run_id, version, list(items))
                items.clear()
                last_flush = time.monotonic()
                if final or last_flush - last_library_event >= LIBRARY_EVENT_MIN_INTERVAL:
                    last_library_event = last_flush
                    bus.publish(LibraryUpdatedEvent())

            def absorb(results: list[dict]) -> None:
                nonlocal done
                for result in results:
                    done += 1
                    category_id = result.get("category_id")
                    old_tag = plan.old_tags.get(result["id"])
                    title = titles.get(result["id"], "")
                    if category_id:
                        tally["tagged"] += 1
                        by_group[result.get("group", "")] += 1
                        tagged_ids.append(result["id"])
                        tagged_items.append((result["id"], result.get("name") or "", result.get("group") or ""))
                        recent.append((title, result.get("name") or ""))
                        unsure = False
                    else:
                        error_text = result.get("error") or ""
                        unsure = not error_text
                        tally["failed" if error_text else "unknown"] += 1
                        if error_text:
                            failed_items.append((result["id"], error_text))
                        else:
                            unknown_ids.append(result["id"])
                            unknown_items.append((result["id"], unsure_reason(result)))
                        recent.append((title, ""))
                        # A file that could not be read (unplugged drive, OneDrive placeholder,
                        # locked) is not a verdict about the book: leave no record, so the
                        # next run tries it again. A deterministic crash is recorded, or a
                        # hostile file would take the worker down on every run.
                        if (error_text and error_text != CRASH_ERROR) or old_tag:
                            continue  # (with old_tag: a re-run found nothing better; keep what the last run put there)
                    items.append(
                        {
                            "doc_id": result["id"],
                            "category_id": category_id,
                            "confidence": result.get("confidence", 0.0),
                            # A genuine "not sure" gets the UNSURE_TAG hashtag, so it is found in the ordinary library view too,
                            # not only in this run's result list; a read error gets no tag at all (see the comment above).
                            "tag": (result.get("name") or None) if category_id else (UNSURE_TAG if unsure else None),
                            "group": result.get("group") or None,
                            "replace_tag": old_tag if category_id else None,
                        }
                    )

            while (chunks or in_flight) and not self._cancel.is_set():
                while chunks and len(in_flight) < window:
                    chunk = chunks.popleft()
                    in_flight[executor.submit(classify_chunk, chunk)] = chunk
                finished, _ = wait(in_flight, timeout=0.25, return_when=FIRST_COMPLETED)
                for future in finished:
                    chunk = in_flight.pop(future)
                    try:
                        results = future.result()
                    except BrokenExecutor:
                        # A worker died -- a malformed file that crashed the PDF parser, say.
                        # Everything in flight died with it; go serial so the guilty book is
                        # the only one in flight next time it dies.
                        crashes += 1
                        lost = [chunk] + [in_flight.pop(f) for f in list(in_flight)]
                        logger.warning("classification worker crashed (%d/%d)", crashes, MAX_WORKER_CRASHES)
                        # Nothing of the dead process survives, so the report has no stack -- only that it happened.
                        # Scrubbed, queued and asked about like any other error (application/error_reporter.py).
                        self.context.error_reports.capture_worker_crash("The classification worker process ended abnormally")
                        _shutdown_executor(executor, kill=True)
                        if crashes >= MAX_WORKER_CRASHES:
                            error = "Bộ phân loại bị dừng đột ngột nhiều lần; đã ngắt. Xem file nhật ký để biết chi tiết."
                            executor = None
                            chunks.clear()
                            break
                        if window == 1 and len(chunk) == 1:
                            results = [{"id": chunk[0]["id"], "category_id": None, "reason": "error", "error": CRASH_ERROR}]
                            absorb(results)
                            lost = lost[1:]
                        workers, window = 1, 1
                        executor = self._executor_factory(1, settings)
                        for lost_chunk in reversed(lost):
                            for job in reversed(lost_chunk):
                                chunks.appendleft([job])
                        continue
                    except Exception as exc:  # e.g. the chunk could not be pickled
                        logger.exception("classification chunk failed")
                        results = [
                            {"id": job["id"], "category_id": None, "reason": "error", "error": f"{type(exc).__name__}: {exc}"}
                            for job in chunk
                        ]
                    absorb(results)
                    bus.publish(
                        SmartClassifyProgressEvent(
                            job_id=job_id, done=done, total=total, tagged=tally["tagged"],
                            unknown=tally["unknown"], failed=tally["failed"], recent=tuple(recent),
                        )
                    )
                if error:
                    break
                if len(items) >= FLUSH_EVERY_ITEMS or (items and time.monotonic() - last_flush >= FLUSH_EVERY_SECONDS):
                    flush()
            killed = self._cancel.is_set() or bool(error)
            flush(final=True)
        except Exception as exc:
            logger.exception("smart classification job failed")
            error = f"{type(exc).__name__}: {exc}"
            killed = True
        finally:
            _shutdown_executor(executor, kill=killed)
            finished_event = SmartClassifyFinishedEvent(
                job_id=job_id,
                run_id=run_id,
                total=total,
                tagged=tally["tagged"],
                unknown=tally["unknown"],
                failed=tally["failed"],
                skipped=tally["skipped"],
                cancelled=self._cancel.is_set(),
                error=error,
                seconds=time.perf_counter() - started,
                by_group=tuple(by_group.most_common()),
                tagged_ids=tuple(tagged_ids),
                unknown_ids=tuple(unknown_ids),
                failed_items=tuple(failed_items),
                tagged_items=tuple(tagged_items),
                unknown_items=tuple(unknown_items),
            )
            self.last_result = finished_event
            bus.publish(finished_event)


class AutoClassifyOnImport:
    """For "always classify new documents": documents the *file watcher*
    brings in one by one (no batch, so no dialog to hang a question on) are
    collected for a few seconds and then classified as a group."""

    def __init__(self, context, service: SmartClassifyService, delay_seconds: float = 5.0) -> None:
        from smartdoc.core.event_bus import DocumentIndexedEvent

        self.context = context
        self.service = service
        self.delay_seconds = delay_seconds
        self._pending: list[str] = []
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        context.event_bus.subscribe(DocumentIndexedEvent, self._on_indexed)

    def _on_indexed(self, event) -> None:
        if event.batch_id is not None or self.context.config.config.smart_classify_on_import != "always":
            return  # batches are handled where the summary is shown (MainWindow)
        with self._lock:
            self._pending.append(event.doc_id)
            if self._timer is None:
                self._timer = threading.Timer(self.delay_seconds, self._fire)
                self._timer.daemon = True
                self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            ids, self._pending = self._pending, []
        if ids and self.service.availability()[0]:
            self.service.enqueue(ids)

    def stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


if __name__ == "__main__":
    import tempfile
    from concurrent.futures import ThreadPoolExecutor

    from smartdoc.application import classification_trainer as trainer
    from smartdoc.core.app_context import AppContext
    from smartdoc.domain.taxonomy import Taxonomy as _Taxonomy
    from smartdoc.infrastructure.vi_tokenizer import TextProcessor

    def thread_executor(workers: int, settings: dict) -> Executor:
        init_worker(settings)  # in-process, so the demo needs no child process
        return ThreadPoolExecutor(max_workers=1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        context = AppContext.create_in_memory(tmp_path / "appdata")

        # A tiny model that can tell "programming" from "cooking" books.
        taxonomy = _Taxonomy.load_builtin()
        interner = trainer.Interner()
        vocab = {"programming": "python code function compiler software developer database".split(),
                 "cooking": "recipe ingredients chicken sauce oven bake kitchen".split()}
        docs = [
            trainer.TrainingDoc(doc_id=f"{label}{i}", body=trainer.Counts.from_dict(interner, {w: 3.0 for w in words}),
                                label=label, label_source="tag", group_key=f"{label}{i}")
            for label, words in vocab.items() for i in range(12)
        ]
        model_path = context.config.app_data_dir / "models" / "classifier_model.json.gz"
        trainer.train(docs, taxonomy, interner, TextProcessor(segmenter=None),
                      trainer.TrainOptions(synthetic_per_class=0, refit_on_all=False)).model.save(model_path)

        book = tmp_path / "book.epub"
        import zipfile

        with zipfile.ZipFile(book, "w") as zf:
            zf.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="c.opf"/></rootfiles></container>')
            zf.writestr("c.opf", '<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="a"/></spine></package>')
            zf.writestr("a.xhtml", "<html><body><p>" + "python code function compiler software developer database " * 30 + "</p></body></html>")
        context.db.add_or_update_document("d1", {"title": "Learn it", "author": "X", "file_path": str(book), "extension": "epub", "created_at": 1.0})

        events = []
        context.event_bus.subscribe(SmartClassifyFinishedEvent, events.append)
        service = SmartClassifyService(context, executor_factory=thread_executor, worker_settings={"segmenter": "none", "low_priority": False})
        scope = ClassifyScope(doc_ids=("d1",))
        print("preview:", service.preview(scope))
        service.start(scope)
        assert service.wait(timeout=30)
        print("finished:", events[-1])
        print("tags now:", context.db.get_document("d1")["tags"])
        assert events[-1].tagged == 1 and "Công nghệ thông tin" in context.db.get_document("d1")["tags"]
        undone = service.undo(events[-1].run_id)
        assert undone == 1 and context.db.get_document("d1")["tags"] == ""
        print("undo OK")
        context.shutdown()
