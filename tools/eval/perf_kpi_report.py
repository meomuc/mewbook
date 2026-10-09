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

    for op, stats in report.items():
        print(
            f"{op}: n={stats['count']} mean={stats['mean_ms']}ms "
            f"P50={stats['p50_ms']}ms P95={stats['p95_ms']}ms P99={stats['p99_ms']}ms"
        )
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Đã ghi {args.out}")


if __name__ == "__main__":
    main()
