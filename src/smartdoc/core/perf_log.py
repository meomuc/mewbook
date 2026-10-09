# SPDX-License-Identifier: AGPL-3.0-or-later
"""Một dòng log có cấu trúc mỗi khi một trong các tác vụ nền chính hoàn tất, để:
(1) tools/eval/perf_kpi_report.py (chỉ dev, không đóng gói bản cài đặt) tổng hợp thành báo cáo KPI;
(2) tự động có mặt trong log khi người dùng gửi báo cáo lỗi thủ công kèm log (đã scrub, xem
application/error_reporter.py::_log_tail + domain/error_scrubber.py::scrub_log_tail -- không cần
thêm gì ở đây để điều đó hoạt động).

Định dạng: một dòng, dễ grep/parse bằng regex: `PERF op=<name> duration_ms=<int> key=value ...`.
Không bao giờ truyền đường dẫn file, tiêu đề sách, tên tác giả làm giá trị field -- chỉ số đếm, id
ngắn, và outcome dạng enum ngắn (scrub_log_tail sẽ vẫn lọc nếu lỡ có, nhưng log này nên "sạch" từ
gốc).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("smartdoc.perf")


def log_perf(op: str, duration_s: float, **fields: object) -> None:
    parts = [f"op={op}", f"duration_ms={round(duration_s * 1000)}"]
    parts.extend(f"{key}={value}" for key, value in fields.items())
    logger.info("PERF %s", " ".join(parts))
