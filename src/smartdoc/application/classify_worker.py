"""The classification worker: what runs inside the child process.

Everything expensive about smart classification happens here, *not* in the GUI
process -- reading book files, segmenting Vietnamese (pyvi drags in
scikit-learn, ~100 MB), scoring against the model:

- **No shared GIL.** A thread doing this work would still steal time slices
  from the GUI thread (PyMuPDF and the CRF tagger hold the GIL for tens of
  milliseconds at a time), which shows up as scrolling that hitches while a
  classification runs. A separate process cannot do that.
- **Runs at background priority** (Windows "process background mode": CPU, disk
  and memory priority all lowered), so it soaks up idle time and gets out of
  the way the moment the user does something.
- **Gives its memory back.** The service (smart_classifier.py) shuts the process
  down after every job, so the scikit-learn/pyvi footprint is only ever paid
  while classifying -- and only if the library has Vietnamese text.
- **A crash stays contained.** A hostile PDF that takes PyMuPDF down kills this
  process, not the app.

Only plain data crosses the process boundary (dicts of str/float), so nothing
here needs Qt, the database or an AppContext -- keep it that way: the worker's
import cost is the latency before the first result.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from smartdoc.application.classification_guards import (
    LABEL_CONFIDENCE,
    REASON_MIXED_TOPICS,
    REASON_PERIODICAL,
    TITLE_CUE_CONFIDENCE,
    label_verdict,
    mixed_topics,
    periodical_cue,
    title_cue_verdict,
)

logger = logging.getLogger(__name__)

# Per-process state, filled by init_worker().
_STATE: dict = {}

LAYER2_EXCERPT_CHARS = 1500
"""How much of a book's already-extracted text rides back with an *unsure* verdict, for the optional Ollama
second pass (application/classify_layer2.py) to read without opening the file a second time. Small and only
ever attached when Lớp 1 withheld an answer -- a confidently-tagged book (the overwhelming majority of a run)
pays nothing extra to cross the process boundary."""

_WIN_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
_WIN_PROCESS_IO_PRIORITY = 33  # NtSetInformationProcess class
_WIN_IO_PRIORITY_LOW = 1  # 0 very low, 1 low, 2 normal


def lower_process_priority() -> bool:
    """Best effort; never raises (a failure just means normal priority).
    Returns whether the process is now running at a lowered priority."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            # Declaring the types matters: without them ctypes passes the
            # 64-bit "current process" pseudo-handle as a 32-bit int, Windows
            # rejects it, and the call silently does nothing.
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.SetPriorityClass.restype = wintypes.BOOL
            handle = kernel32.GetCurrentProcess()
            # CPU: below normal, so whatever the user is doing always wins a
            # contended core. Disk: "low", so a hard disk isn't thrashed under
            # them. Deliberately NOT Windows' full "background mode"
            # (PROCESS_MODE_BACKGROUND_BEGIN): measured on this workload it made
            # the job ~20x slower -- I/O at "very low" starves behind every other
            # request and the lowest memory priority has the OS trimming the
            # process's working set while it works -- for no benefit to the
            # foreground that plain below-normal doesn't already give.
            lowered = bool(kernel32.SetPriorityClass(handle, _WIN_BELOW_NORMAL_PRIORITY_CLASS))
            try:
                ntdll = ctypes.WinDLL("ntdll")
                ntdll.NtSetInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG]
                io_priority = wintypes.ULONG(_WIN_IO_PRIORITY_LOW)
                ntdll.NtSetInformationProcess(handle, _WIN_PROCESS_IO_PRIORITY, ctypes.byref(io_priority), ctypes.sizeof(io_priority))
            except Exception:
                logger.debug("could not lower I/O priority", exc_info=True)
            return lowered
        os.nice(10)
        return True
    except Exception:
        logger.debug("could not lower process priority", exc_info=True)
        return False


def init_worker(settings: dict) -> None:
    """Process initializer. `settings`: model_path, low_priority, max_words."""
    if settings.get("low_priority", True):
        lower_process_priority()
    _STATE.clear()
    _STATE["settings"] = settings
    try:
        from smartdoc.domain.text_classifier import TextClassifierModel

        model = TextClassifierModel.load(_as_path(settings["model_path"]))
        _STATE["model"] = model
        from smartdoc.domain.taxonomy import Taxonomy

        directory = settings.get("app_data_dir")  # the person's own categories (taxonomy.json) count too
        _STATE["taxonomy"] = Taxonomy.load(_as_path(directory) if directory else None)
        from smartdoc.application.classification_features import FeatureExtractor
        from smartdoc.infrastructure.vi_tokenizer import TextProcessor

        # "none" is for tests: no segmenter, so no scikit-learn import.
        processor = TextProcessor(segmenter=None if settings.get("segmenter") == "none" else "auto")
        _STATE["extractor"] = FeatureExtractor(
            weights=model.feature_weights, max_words=int(settings.get("max_words") or model.max_words), processor=processor,
            front_chars=model.front_chars,
        )
    except Exception as exc:  # reported per document, so the service can show why nothing was classified
        logger.exception("classification worker could not load its model")
        _STATE["error"] = f"{type(exc).__name__}: {exc}"


def _as_path(value):
    from pathlib import Path

    return Path(value)


def classify_chunk(jobs: list[dict]) -> list[dict]:
    """Classifies a few documents. Each job: id, title, author, tags (list of
    the user's non-category tags), path, extension. Never raises -- a document
    that goes wrong is reported with `error` set and no category."""
    from smartdoc.infrastructure.text_sampler import is_final_error  # here, not at the top: the GUI imports this module and must not load the sampler

    results = []
    model = _STATE.get("model")
    extractor = _STATE.get("extractor")
    for job in jobs:
        started = time.perf_counter()
        result = {"id": job["id"], "category_id": None, "name": "", "group": "", "confidence": 0.0, "group_confidence": 0.0,
                  "best_id": None, "reason": "error", "top": [], "words": 0, "error": ""}
        if model is None or extractor is None:
            result["error"] = _STATE.get("error", "worker not initialised")
            results.append(result)
            continue
        try:
            parts = extractor.extract(
                title=job.get("title", ""),
                author=job.get("author", ""),
                tags=job.get("tags", ()),
                path=job.get("path"),
                extension=job.get("extension"),
            )
            cue = periodical_cue(job.get("title", ""), job.get("path"))
            prediction = model.predict(parts.merged(hints=True))
            confidence_override = None
            if cue:  # a magazine / newspaper issue is not one of the book categories: withhold rather than force one
                prediction.category_id, prediction.reason = None, REASON_PERIODICAL
            elif prediction.category_id and mixed_topics(
                    model, lambda text: extractor.processor.weighted_counts([(text, extractor.weights["body"])]), parts.body_text):
                prediction.category_id, prediction.reason = None, REASON_MIXED_TOPICS
            elif not prediction.category_id:
                # The model would not decide (typically a short text: too few words to be sure). The file's own subject labels,
                # then the title, may still name the category outright.
                taxonomy = _STATE.get("taxonomy")
                found = label_verdict(taxonomy, parts.subjects) if taxonomy is not None else None
                confidence_override = LABEL_CONFIDENCE
                if found is None and taxonomy is not None:
                    found, confidence_override = title_cue_verdict(taxonomy, job.get("title", "")), TITLE_CUE_CONFIDENCE
                if found is not None and model.class_by_id(found) is not None:
                    prediction.category_id = found
                    prediction.reason = "label" if confidence_override == LABEL_CONFIDENCE else "title_cue"
                    prediction.confidence = prediction.group_confidence = confidence_override
            info = model.class_by_id(prediction.category_id) if prediction.category_id else None
            leaning = model.class_by_id(prediction.best_id) if prediction.best_id and not prediction.category_id else None
            result["best_name"] = leaning.name if leaning else ""  # what an undecided book leaned to (shown as a suggestion, B2)
            result.update(
                name=info.name if info else "",
                group=info.group if info else "",
                category_id=prediction.category_id,
                confidence=prediction.confidence,
                group_confidence=prediction.group_confidence,
                best_id=prediction.best_id,
                reason=prediction.reason,
                top=prediction.top,
                words=parts.body_words,
                # A book that simply has no text (a scan, DRM, a format we cannot read) is a verdict, not a failure: it is
                # recorded and not retried on every run. A file that could not be opened stays an error, and is retried.
                error=parts.error if not prediction.category_id and not parts.body_words and not is_final_error(parts.error) else "",
            )
            if not prediction.category_id and parts.body_text:
                # Only an *unsure* verdict carries this home (see LAYER2_EXCERPT_CHARS) -- Lớp 2 (D1) is the only
                # reader, and it never runs on a book Lớp 1 already tagged with confidence.
                result["excerpt"] = parts.body_text[:LAYER2_EXCERPT_CHARS]
        except Exception as exc:  # one bad book must not lose the rest of the chunk
            logger.debug("classify failed for %s", job.get("path"), exc_info=True)
            result["error"] = f"{type(exc).__name__}: {exc}"
        result["ms"] = round((time.perf_counter() - started) * 1000, 1)
        results.append(result)
    return results


def segmenter_name() -> str:
    """Which segmenter this process ended up with -- for diagnostics."""
    extractor = _STATE.get("extractor")
    return extractor.processor.segmenter_name if extractor else "unavailable"
