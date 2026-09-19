# SPDX-License-Identifier: AGPL-3.0-or-later
"""The error report model (E-02/E-03): what a report holds, how errors are grouped, how a payload is validated."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

from smartdoc.domain import error_report as r

ACCOUNT = "Nguyễn Văn Ánh"
TITLE = "Đắc nhân tâm"
HOME = rf"C:\Users\{ACCOUNT}"
CONTEXT = r.ReportContext(
    app_version="1.1.0", build_id="0123abc", channel="release", os="Windows 11 (10.0.26200) AMD64", locale="vi",
    theme_id="broadsheet", install_hash="a" * 64, consent_version=1, library_size_bucket="1k-10k",
)


def _raise_in(filename: str, function: str = "explode", message: str = "boom", exc: type[BaseException] = ValueError, depth: int = 1):
    """An exception whose innermost frame lives in a (fake) file called `filename`, like code installed anywhere."""
    calls = "\n".join(f"def {function}{i}():\n    {function}{i - 1}()\n" for i in range(1, depth)) if depth > 1 else ""
    source = f"def {function}0():\n    raise exc({message!r})\n{calls}"
    namespace = {"exc": exc}
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102 -- test helper building a traceback
    try:
        namespace[f"{function}{depth - 1}"]()
    except BaseException as caught:  # noqa: BLE001
        return caught
    raise AssertionError("no exception was raised")


def _report(exc: BaseException, **kwargs) -> r.ErrorReport:
    return r.build_from_exception(type(exc), exc, exc.__traceback__, context=CONTEXT, **kwargs)


# --- building from an exception ---------------------------------------------------------------------------------------------

def test_a_report_holds_frames_with_relative_paths_and_no_local_values():
    secret_title = TITLE  # a local variable in the failing frame: its value must never be reported

    def fail():
        local_book = secret_title  # noqa: F841 -- present only to prove locals are not collected
        raise KeyError("missing")

    try:
        fail()
    except KeyError as exc:
        report = _report(exc)
    text = json.dumps(report.to_payload(), ensure_ascii=False)
    assert TITLE not in text and "local_book" not in text and "secret_title" not in text
    assert report.exception_type == "KeyError" and all(f.path == "<PATH>" or f.path.startswith(("smartdoc", "site-packages", "stdlib"))
                                                       for f in report.stack_frames)


def test_frames_of_the_app_are_kept_relative_to_the_package_whatever_the_install_folder():
    exc = _raise_in(rf"{HOME}\src\smartdoc\application\import_queue.py", "process", depth=2)
    report = _report(exc)
    innermost = report.stack_frames[-1]
    assert innermost.path == "smartdoc/application/import_queue.py"
    assert innermost.function == "process0" and innermost.line == 2
    assert report.feature_area == "import"
    assert ACCOUNT not in json.dumps(report.to_payload(), ensure_ascii=False)


def test_the_message_is_scrubbed_and_the_report_is_valid():
    message = rf"Không mở được {HOME}\Documents\Sách hay\{TITLE}.epub cho {ACCOUNT}"
    exc = _raise_in(rf"{HOME}\smartdoc\smartdoc\app.py", message=message, exc=OSError)
    report = _report(exc, private_terms=[ACCOUNT, TITLE], user_dirs=[HOME])
    assert report.message_scrubbed == "Không mở được <USER_DIR>/<PATH> cho <PRIVATE>"
    assert r.validate_payload(report.to_payload()) == []
    assert report.exception_type == "OSError" and report.feature_area == "startup"


def test_an_exception_whose_str_fails_still_makes_a_report():
    class Odd(Exception):
        def __str__(self) -> str:
            raise RuntimeError("no text for you")

    report = _report(_raise_in("x.py", exc=Odd))
    assert report.message_scrubbed == "<unprintable message>"
    assert report.exception_type.endswith("Odd")


@pytest.mark.parametrize(
    ("module_path", "area"),
    [
        ("smartdoc/application/import_queue.py", "import"),
        ("smartdoc/infrastructure/pdf_extractor.py", "import"),
        ("smartdoc/application/smart_classifier.py", "classification"),
        ("smartdoc/application/classify_worker.py", "classification"),
        ("smartdoc/presentation/reader_window.py", "reader"),
        ("smartdoc/application/cover_search.py", "cover_search"),
        ("smartdoc/application/metadata_lookup.py", "cover_search"),
        ("smartdoc/application/ai_summary.py", "ai_summary"),
        ("smartdoc/application/cloud_reviews.py", "review"),
        ("smartdoc/presentation/review_dialog.py", "review"),
        ("smartdoc/app.py", "startup"),
        ("smartdoc/presentation/library_view.py", "ui"),
        ("smartdoc/domain/models.py", "other"),
        ("requests/adapters.py", "other"),
    ],
)
def test_the_feature_area_comes_from_the_innermost_app_frame(module_path, area):
    frames = (r.StackFrame(module_path, "f", 1), r.StackFrame("requests/adapters.py", "send", 3))  # a library call inside it
    if module_path.startswith("requests"):
        frames = (r.StackFrame(module_path, "f", 1),)
    assert r.infer_feature_area(frames) == area


def test_a_declared_feature_area_wins_over_the_inferred_one():
    exc = _raise_in(r"C:\x\smartdoc\presentation\library_view.py")
    assert _report(exc, feature_area="review").feature_area == "review"
    assert _report(exc, feature_area="nonsense").feature_area == "ui"  # an unknown declaration is ignored


def test_exception_type_names():
    class Local(Exception):
        pass

    assert r.exception_type_name(ValueError) == "ValueError"
    assert r.exception_type_name(Local).endswith("Local") and "<" not in r.exception_type_name(Local)
    assert r.exception_type_name(json.JSONDecodeError) == "json.decoder.JSONDecodeError"
    assert r.exception_type_name(None) == "UnknownError"


# --- fingerprints -----------------------------------------------------------------------------------------------------------------

def _frames(*items):
    return tuple(r.StackFrame(path, function, line) for path, function, line in items)


def test_the_stable_fingerprint_ignores_line_numbers_but_the_exact_one_does_not():
    a = _frames(("smartdoc/app.py", "main", 10), ("smartdoc/application/x.py", "run", 20))
    b = _frames(("smartdoc/app.py", "main", 11), ("smartdoc/application/x.py", "run", 25))  # the same code, shifted
    assert r.fingerprints("ValueError", a)[0] == r.fingerprints("ValueError", b)[0]
    assert r.fingerprints("ValueError", a)[1] != r.fingerprints("ValueError", b)[1]


def test_the_fingerprints_depend_on_the_exception_type_and_the_function():
    a = _frames(("smartdoc/app.py", "main", 10))
    assert r.fingerprints("ValueError", a)[0] != r.fingerprints("KeyError", a)[0]
    assert r.fingerprints("ValueError", a)[0] != r.fingerprints("ValueError", _frames(("smartdoc/app.py", "other", 10)))[0]


def test_only_the_five_innermost_frames_count():
    deep = _frames(*[("smartdoc/a.py", f"f{i}", i) for i in range(8)])
    same_inner = (r.StackFrame("smartdoc/other.py", "different_outer", 1), *deep[-5:])
    assert r.fingerprints("E", deep)[0] == r.fingerprints("E", same_inner)[0]
    assert r.fingerprints("E", deep)[0] != r.fingerprints("E", deep[1:-1])[0]


def test_the_message_never_changes_the_fingerprint():
    exc1 = _raise_in(r"C:\a\smartdoc\app.py", message=f"file {TITLE}.epub")
    exc2 = _raise_in(r"D:\b\smartdoc\app.py", message="another")
    assert _report(exc1).fingerprint_stable == _report(exc2).fingerprint_stable


def test_a_report_without_frames_is_grouped_by_area_and_process():
    stable = lambda area, process: r.fingerprints("BrokenExecutor", (), feature_area=area, process_kind=process)[0]  # noqa: E731
    assert stable("classification", "classify_worker") == stable("classification", "classify_worker")
    assert stable("classification", "classify_worker") != stable("import", "classify_worker")


# --- payload and validation -----------------------------------------------------------------------------------------------------

def _good() -> dict:
    exc = _raise_in(r"C:\a\smartdoc\app.py")
    return _report(exc).to_payload()


def test_a_payload_round_trips_and_the_json_is_canonical():
    payload = _good()
    report = r.ErrorReport.from_payload(payload)
    assert report.to_payload() == payload
    text = r.payload_json(payload)
    assert json.loads(text) == payload and ": " not in text and ", " not in text  # compact
    assert list(json.loads(text)) == sorted(json.loads(text))  # sorted keys: the same report is the same bytes


def test_optional_fields_are_left_out_when_empty():
    payload = _good()
    copy_ = dict(payload)
    ctx = r.ReportContext("1.1.0", "dev", "dev", "Windows", "vi", "broadsheet", "b" * 64, 1)
    bare = r.build_synthetic("BrokenExecutor", "died", context=ctx, source="worker", process_kind="classify_worker",
                             feature_area="classification").to_payload()
    assert "user_note" not in bare and "log_tail" not in bare and "library_size_bucket" not in bare
    assert copy_["library_size_bucket"] == "1k-10k"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("report_id", "not-a-uuid"),
        ("app_version", "one.two.three"),
        ("build_id", "XYZ"),
        ("channel", "beta"),
        ("locale", "Vietnamese"),
        ("theme_id", "Has Space"),
        ("feature_area", "everything"),
        ("process_kind", "thread"),
        ("source", "telepathy"),
        ("exception_type", "has space"),
        ("message_scrubbed", "x" * 501),
        ("fingerprint_stable", "abc"),
        ("install_hash", "g" * 64),
        ("occurred_at", "yesterday"),
        ("consent_version", "1"),
        ("consent_version", True),
        ("library_size_bucket", "huge"),
        ("user_note", "n" * 1001),
        ("log_tail", "l" * 10_001),
        ("stack_frames", "none"),
        ("stack_frames", [{"path": "a", "function": "f"}]),
        ("stack_frames", [{"path": "a", "function": "f", "line": -1}]),
        ("stack_frames", [{"path": "a", "function": "f", "line": 1}] * 51),
        ("schema", 2),
    ],
)
def test_a_payload_that_breaks_a_rule_is_refused(field, value):
    payload = _good()
    payload[field] = value
    assert r.validate_payload(payload) != []
    with pytest.raises(r.ErrorReportFormatError):
        r.ErrorReport.from_payload(payload)


def test_an_unknown_field_or_a_missing_one_is_refused():
    payload = _good()
    assert r.validate_payload({**payload, "title_of_book": "x"}) != []
    for key in ("report_id", "fingerprint_stable", "stack_frames", "install_hash"):
        broken = copy.deepcopy(payload)
        del broken[key]
        assert r.validate_payload(broken) != []
    assert r.validate_payload("nope") == ["payload: not an object"]


def test_a_payload_over_16_kib_is_refused_and_fit_to_limit_trims_the_log_first():
    ctx = CONTEXT
    long_log = "\n".join(f"2026-09-19 10:00:00,000 INFO [t] smartdoc.x: {'line ' * 30} {i}" for i in range(50))
    report = r.build_synthetic("ManualReport", "m", context=ctx, source="manual", log_tail=long_log, user_note="n" * 900)
    payload = report.to_payload()
    assert r.payload_size(payload) <= r.MAX_PAYLOAD_BYTES and r.validate_payload(payload) == []
    padded = dict(payload, log_tail="x" * 10_000, user_note="y" * 1000, message_scrubbed="m" * 500,
                  stack_frames=[{"path": "p" * 200, "function": "f" * 100, "line": 1}] * 50)
    assert r.payload_size(padded) > r.MAX_PAYLOAD_BYTES
    assert any("larger" in problem for problem in r.validate_payload(padded))


def test_fit_to_limit_keeps_the_innermost_frames_and_the_fingerprints():
    frames = tuple(r.StackFrame("p" * 190, "f" * 90 + str(i), i) for i in range(40))
    stable, exact = r.fingerprints("E", frames)
    report = r.ErrorReport(
        report_id=r.new_report_id(), occurred_at="2026-09-19T10:00Z", source="crash", process_kind="gui",
        feature_area="other", exception_type="E", stack_frames=frames, message_scrubbed="m" * 500,
        fingerprint_stable=stable, fingerprint_exact=exact, context=CONTEXT, user_note="n" * 1000, log_tail="l\n" * 4000,
    )
    fitted = r.fit_to_limit(report)
    assert r.payload_size(fitted.to_payload()) <= r.MAX_PAYLOAD_BYTES
    assert fitted.stack_frames[-1] == frames[-1] and len(fitted.stack_frames) >= r.FINGERPRINT_FRAMES
    assert (fitted.fingerprint_stable, fitted.fingerprint_exact) == (stable, exact)


def test_a_worker_crash_and_a_manual_report_are_built_without_a_traceback():
    worker = r.build_synthetic("BrokenExecutor", "worker ended", context=CONTEXT, source="worker",
                               process_kind="classify_worker", feature_area="classification")
    assert worker.stack_frames == () and worker.process_kind == "classify_worker" and r.validate_payload(worker.to_payload()) == []
    manual = r.build_synthetic("ManualReport", f"lỗi với {TITLE}", context=CONTEXT, source="manual",
                               user_note=f"Tôi là {ACCOUNT}, mở {TITLE}.epub", log_tail="",
                               private_terms=[ACCOUNT, TITLE], user_dirs=[HOME])
    text = json.dumps(manual.to_payload(), ensure_ascii=False)
    assert TITLE not in text and ACCOUNT not in text and manual.user_note == "Tôi là <PRIVATE>, mở <PRIVATE>.epub"


def test_the_time_is_utc_and_rounded_to_the_minute():
    moment = datetime(2026, 9, 19, 17, 5, 59, tzinfo=timezone.utc)
    assert r.occurred_now(moment) == "2026-09-19T17:05Z"
    exc = _raise_in("x.py")
    assert _report(exc, now=moment).occurred_at == "2026-09-19T17:05Z"
