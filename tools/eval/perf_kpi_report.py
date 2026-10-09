# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dev-only: tổng hợp các dòng PERF trong mewbook.log thành báo cáo KPI theo từng tác vụ
(count, mean, P50, P95, P99) và đề xuất ngưỡng theo dữ liệu thực tế (P95 = "watch", P99 = "alert")
-- không hardcode số "chậm" là bao nhiêu giây, vì điều đó phụ thuộc máy/thư viện người dùng.

KHÔNG đóng gói vào bản cài đặt (packaging/MewBook.spec không tham chiếu thư mục tools/).

Usage:
    python tools/eval/perf_kpi_report.py --log path/to/mewbook.log [--out report.json]
    # Không truyền --log: tự tìm %APPDATA%/SmartDocLibrary/logs/mewbook.log* trên máy này
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(REPO_SRC))

_LINE_RE = re.compile(r"PERF (op=\S+(?: \S+=\S+)*)")
_FIELD_RE = re.compile(r"(\w+)=(\S+)")


def parse_perf_lines(text: str) -> list[dict[str, str]]:
    records = []
    for match in _LINE_RE.finditer(text):
        records.append(dict(_FIELD_RE.findall(match.group(1))))
    return records


def percentile(values: list[float], pct: float) -> float:
    if len(values) < 2:
        return values[0]
    cut_points = statistics.quantiles(values, n=100)
    return cut_points[min(int(pct) - 1, len(cut_points) - 1)]


def summarize(records: list[dict[str, str]]) -> dict[str, dict]:
    by_op: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if "op" in r and "duration_ms" in r:
            by_op[r["op"]].append(float(r["duration_ms"]))
    report = {}
    for op, durations in sorted(by_op.items()):
        durations.sort()
        report[op] = {
            "count": len(durations),
            "mean_ms": round(statistics.fmean(durations)),
            "p50_ms": round(percentile(durations, 50)),
            "p95_ms": round(percentile(durations, 95)),
            "p99_ms": round(percentile(durations, 99)),
            "min_ms": round(durations[0]),
            "max_ms": round(durations[-1]),
            "suggested_watch_threshold_ms": round(percentile(durations, 95)),
            "suggested_alert_threshold_ms": round(percentile(durations, 99)),
        }
    return report


def _default_log_paths() -> list[Path]:
    import os

    from smartdoc.core.diagnostics import LOG_FILE_NAME, log_dir  # noqa: E402

    app_data = Path(os.environ.get("APPDATA", "")) / "SmartDocLibrary"
    directory = log_dir(app_data)
    return sorted(directory.glob(f"{LOG_FILE_NAME}*")) if directory.is_dir() else []


_OP_LABEL: dict[str, str] = {
    "import": "Nhập sách",
    "classify": "Phân loại thông minh",
    "format_conversion": "Chuyển đổi định dạng",
    "metadata_batch": "Cập nhật thông tin hàng loạt",
    "ai_summary": "Tóm tắt AI",
    "gather": "Gom sách",
    "duplicate_finder_hash": "Tìm trùng — băm file",
    "duplicate_finder_fuzzy": "Tìm trùng — so sánh mờ",
    "webpage_to_pdf_fetch": "Lưu web→PDF: tải trang",
    "webpage_to_pdf_render": "Lưu web→PDF: tạo PDF",
}

_SMALL_SAMPLE_WARN = 10  # fewer samples than this → warn P95/P99 are unreliable


def _fmt(ms: float) -> str:
    """Format milliseconds as a compact human-readable duration."""
    if ms < 1_000:
        return f"{round(ms)}ms"
    if ms < 60_000:
        return f"{ms / 1_000:.1f}s"
    minutes, seconds = divmod(ms / 1_000, 60)
    return f"{int(minutes)}m{int(seconds):02d}s"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", help="Đường dẫn file log (lặp lại để gộp nhiều file)")
    parser.add_argument("--out", help="Ghi báo cáo JSON ra file này")
    args = parser.parse_args()

    paths = [Path(p) for p in args.log] if args.log else _default_log_paths()
    if not paths:
        print("Không tìm thấy file log nào. Dùng --log <path>.", file=sys.stderr)
        sys.exit(1)

    records: list[dict[str, str]] = []
    for path in paths:
        try:
            records.extend(parse_perf_lines(path.read_text(encoding="utf-8", errors="replace")))
        except OSError as exc:
            print(f"Không đọc được {path}: {exc}", file=sys.stderr)

    report = summarize(records)
    if not report:
        print("Không tìm thấy dòng PERF nào trong log đã cho.")
        return

    col = max(len(_OP_LABEL.get(op, op)) for op in report) + 2
    print(f"\n{'Tác vụ':<{col}}  {'Số lần':>6}  {'TB':>7}  {'Nhanh':>7}  {'Chậm':>7}  "
          f"{'P50 (điển hình)':>16}  {'P95 (hiếm chậm)':>16}  {'P99 (ngoại lệ)':>15}")
    print("-" * (col + 6 + 7 * 4 + 16 * 2 + 15 + 14))
    for op, s in report.items():
        label = _OP_LABEL.get(op, op)
        warn = " ⚠" if s["count"] < _SMALL_SAMPLE_WARN else ""
        print(f"{label:<{col}}  {s['count']:>6}{warn}  {_fmt(s['mean_ms']):>7}  "
              f"{_fmt(s['min_ms']):>7}  {_fmt(s['max_ms']):>7}  "
              f"{_fmt(s['p50_ms']):>16}  {_fmt(s['p95_ms']):>16}  {_fmt(s['p99_ms']):>15}")

    small = [_OP_LABEL.get(op, op) for op, s in report.items() if s["count"] < _SMALL_SAMPLE_WARN]
    if small:
        print(f"\n⚠  Ít mẫu (< {_SMALL_SAMPLE_WARN} lần chạy): {', '.join(small)}")
        print("   P95/P99 chưa đáng tin — cần thêm dữ liệu trước khi dùng làm ngưỡng KPI.")

    print("\nGhi chú:")
    print("  P50 = 50% lần chạy nhanh hơn giá trị này  (thời gian điển hình người dùng trải nghiệm)")
    print("  P95 = ngưỡng đề xuất 'cần chú ý'           (1/20 lần chạy sẽ chậm hơn)")
    print("  P99 = ngưỡng đề xuất 'cần điều tra'         (1/100 lần chạy sẽ chậm hơn)")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nĐã ghi {args.out}")


if __name__ == "__main__":
    main()
