# N3 — Đo lại toàn bộ B1 sau khi sửa `mixed_topics()` (N2)

**Ngày:** 2026-10-02 · **Thư viện thật:** 8.605 sách · `max_words = 5000` (đọc từ settings thật)
**Cách đo:** `tools/eval/classification_coverage.py` (cùng pipeline Lớp 1 thật, cùng guard), chạy trên toàn bộ 6.350 sách chưa có hashtag thể loại, chia 4 phần chạy song song (kết quả y hệt chạy một mạch). Không đổi ngưỡng nào.

## Kết quả

| | B1 (đính chính) | N3 (sau N2) |
|---|---:|---:|
| Sách có hashtag thể loại, toàn thư viện | 2.255 / 8.605 (26,2%) | **6.844 / 8.605 (79,5%)** |
| Trong 6.350 sách chưa phân loại: nay có thể loại (`reason = model`) | 0 | **4.589 (72,3%)** |
| (a) Không có chữ đọc được | 85 | 72 |
| (b) Dưới ngưỡng tự tin (`low_confidence`) | 1.606 | 1.606 |
| (c) Guard: `periodical` | 66 | 66 |
| (c) Guard: `mixed_topics` | 4.593 | **6** |
| (d) Không có nhóm/ngôn ngữ phù hợp | 0 | 0 |
| (e) Lỗi kỹ thuật đọc file (mã hoá / font cũ) | 0 | 11 |

(Tổng còn lại 1.761 = 1.606 + 72 + 66 + 6 + 11.)

Lưu ý: số "sau" là kết quả đo bằng pipeline, **chưa** được ghi vào `library.db` — cần chạy "Phân loại" thật trong app để hashtag xuất hiện.

## Đối chiếu với các nhánh quyết định

- Không có lớp nguyên nhân mới lộ ra bên dưới `mixed_topics`: (a) giảm nhẹ, (d) vẫn 0, (e) chỉ 11 sách (mã hoá / font cũ). Nhánh "dừng vì (a)/(c)/(d) tăng" **không** kích hoạt.
- 79,5% là **gần đạt** mục tiêu 80–90% mà không hạ ngưỡng, không retrain, không dùng AI.
- Phần còn lại gần như toàn là (b): 1.606/1.761 (91%). Trong 1.673 dự đoán `low_confidence` (gồm cả sách không chữ), 602 có độ tự tin ≥ 0,5 (trung bình 0,43). Ngôn ngữ phần còn lại: 583 không rõ, 416 en, 351 vi, 160 und, 127 fr…
- Đạt 80% cần thêm ~37 sách; đạt 90% cần thêm ~900 sách — chỉ có thể đến từ nhóm (b).

## Đề xuất (chờ chủ dự án xác nhận)

Theo ngưỡng đã đặt: gần đạt mục tiêu → **đề xuất HOÃN B2/B3/B4**. Nếu vẫn muốn đẩy lên ~90%, chỉ B2 (gợi ý "chưa chắc chắn" qua `UNSURE_TAG`/`UNSURE_REASONS` có sẵn, xem `docs/ARCHITECTURE_CLASSIFICATION_UI.md`) là hợp lẽ; B3/B4 chưa cần. Không hạ `min_score`/`min_group_prob`/`min_class_prob`.
