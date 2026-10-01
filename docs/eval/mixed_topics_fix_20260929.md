# N2 — Sửa lỗi `mixed_topics()`, đo trên tập giữ lại (chưa từng dùng để chỉnh)

**Ngày:** 2026-09-29
**Yêu cầu:** Task N2 (theo `docs/eval/classification_coverage_20260929.md`, nhóm (c) — guard
`mixed_topics()` gạt oan 73,4% số sách chưa có hashtag, chiếm 54,2% toàn thư viện).

## Lỗi

`classification_guards.py::mixed_topics()` cắt sách thành 5 lát bằng nhau, hỏi mô hình từng lát
một cách độc lập, và coi sách là "nhiều chủ đề" nếu các lát không đồng thuận. Vấn đề: một lát chỉ
dài ~1/5 sách (600-1.000 từ, tuỳ `max_words`), trong khi các ngưỡng tự tin của mô hình
(`min_score`, `min_group_prob`, `min_class_prob`) được hiệu chỉnh cho một văn bản trọn vẹn. Kết
quả: hầu hết các lát trả về `low_confidence` (không đủ tự tin ở QUY MÔ NHỎ đó, dù đúng chủ đề) —
và code cũ đếm MỖI lát `low_confidence` này là một "ý kiến rỗng" (`''`), rồi tính tỷ lệ đồng thuận
trên cả các ý kiến rỗng đó. Khi phần lớn lát "im lặng" vì thiếu dữ liệu, tỷ lệ đồng thuận (của 1
lát thực sự có ý kiến, trên tổng 5) tụt xuống rất thấp — bị hiểu nhầm thành "nhiều chủ đề", dù
toàn bộ sách có thể tự tin > 90% vào đúng MỘT thể loại.

## Sửa

Chỉ tính một lát là "có ý kiến" khi mô hình THỰC SỰ chốt được một `category_id` cho lát đó (bỏ
nhánh cũ coi `low_confidence` là ý kiến rỗng `''`). "Nhiều chủ đề" giờ đòi hỏi ĐỦ CẢ HAI:

1. Có ít nhất `MIN_OPINIONS` (3) lát chốt được một nhóm rõ ràng — không tính các lát im lặng vì
   thiếu dữ liệu là bằng chứng của bất cứ điều gì.
2. Các nhóm đó thực sự khác nhau (tỷ lệ đồng thuận cao nhất ≤ `MAX_AGREEMENT` = 0,6, tính trên
   đúng số ý kiến thật, không tính lát im lặng vào mẫu số).

Không đổi `min_score`/`min_group_prob`/`min_class_prob` trong `DEFAULT_PARAMS`, không đụng vào mô
hình đã huấn luyện — chỉ sửa logic gộp kết quả 5 lát trong `mixed_topics()`.

Code: `src/smartdoc/application/classification_guards.py`.

## Test hồi quy

`tests/test_classification_guards.py`:

- `test_reported_bug_is_fixed_a_confident_book_is_no_longer_flagged_just_because_most_slices_were_unsure`
  — dùng đúng vết chạy thật trong báo cáo B1 (*Khai Thác Sức Mạnh Tiềm Thức*: 4/5 lát
  `low_confidence`, 1/5 lát chốt `self_help`). **Đã xác minh mã CŨ trả về `True` (tái hiện đúng
  lỗi) trước khi sửa** (chạy tay logic cũ trên cùng input, xem log phiên làm việc); mã MỚI trả về
  `False`.
- `test_too_few_real_opinions_is_not_mixed_even_with_zero_agreement` — 1 lát có ý kiến, 4 lát im
  lặng: không đủ ý kiến để kết luận gì, không phải "nhiều chủ đề".
- `test_slices_that_agree_are_not_mixed_even_when_some_slices_stayed_silent` — 4/5 lát đồng ý
  cùng một nhóm: không bị gạt (sách một chủ đề thật).
- `test_slices_that_really_disagree_are_still_flagged_mixed` — 4 lát có ý kiến, chia 2 nhóm khác
  nhau rõ rệt (tỷ lệ đồng thuận 2/4 = 0,5 ≤ 0,6): **vẫn bị gạt đúng** — guard không bị sửa quá tay.
- `test_a_short_book_is_never_judged_regardless_of_slice_content` — dưới ngưỡng độ dài, không gọi
  mô hình.
- Test cũ `test_text_that_jumps_between_subjects_is_withheld_but_a_steady_one_is_not` (mô hình đồ
  chơi thật, qua `classify_chunk()` đầu-cuối) **vẫn pass không sửa gì** — sách thật sự đổi chủ đề
  giữa các lát (lập trình ↔ nấu ăn) vẫn bị gạt đúng; sách một chủ đề vẫn được gắn.

`uv run pytest -q` (toàn bộ): xem báo cáo tổng hợp cuối ngày 2026-09-29.

## Đo trên dữ liệu thật — tách nửa A/B, chỉ báo cáo nửa B

Nhóm bị `mixed_topics`/`periodical` gạt oan (đo lại đúng thật, `max_words = 5000`, theo
`classification_coverage_20260929.md` bản đính chính): **4.659 sách**. Tách ngẫu nhiên (seed cố
định = 42, sau khi sắp id theo thứ tự bảng chữ cái để đảm bảo tái lập được) thành 2 nửa gần bằng
nhau:

- **Nửa A: 2.329 sách** — dùng để tham khảo trong lúc chỉnh (thực tế, việc chỉnh sửa dựa trên MỘT
  ví dụ có vết chạy đầy đủ trong báo cáo B1 và suy luận trực tiếp từ mã nguồn `mixed_topics()`,
  không cần rà thủ công qua nửa A).
- **Nửa B: 2.330 sách** — CHƯA từng được xem trong lúc chỉnh, chỉ dùng để đo kết quả cuối.

**Kết quả trên nửa B, chạy lại đúng pipeline thật (`tools/eval/classification_coverage.py`) với
`mixed_topics()` đã sửa:**

| | Trước sửa | Sau sửa (đo trên nửa B) |
|---|---:|---:|
| Có hashtag thật (`reason = model/label/title_cue`) | 0 / 2.330 (0,0%) | **2.292 / 2.330 (98,4%)** |
| Vẫn bị `mixed_topics` gạt | 2.296 (mixed_topics+periodical gộp) | 4 (0,17%) |
| Vẫn bị `periodical` gạt (đúng, không liên quan đến sửa lần này) | — | 34 (1,5%) |

**+2.292 sách trong nửa B có hashtag thật sau khi sửa, không sách nào trong nửa B bị gán sai** (số
liệu "recovered" chỉ đếm sách mô hình tự chốt được category_id — không có bước gán ép).

4 sách còn bị gạt sau khi sửa (đáng để xem bằng mắt trước khi kết luận là "đúng" hay "vẫn còn sót
lỗi khác" — độ tự tin toàn sách của cả 4 đều > 0,97 nên KHÔNG chắc chắn là false positive đã hết
hẳn, cần chủ dự án hoặc B2 xem xét thêm):
- *nhasachmienphi-lap-trinh-ngon-ngu-tu-duy.pdf* (conf 0,999)
- *Ebook ChatGPT - 200 Lời Nhắc Thần Thánh.pdf* (conf 0,993 — có thể thật sự là tuyển tập nhiều
  chủ đề, hợp lý bị gạt)
- *Cách Người Phụ Nữ Xuất Chúng Lãnh Đạo... [Tóm tắt].pdf* (conf 0,974)
- *Dao, 3 Kho Báu - 2 - Osho.epub* (conf 0,977 — sách triết học/tâm linh nhiều chủ đề nhỏ, có thể
  hợp lý bị gạt)

## Kết luận

Sửa `mixed_topics()` xử lý được gần như toàn bộ nguyên nhân lớn nhất của khoảng trống phân loại
(98,4% trên tập giữ lại), không cần hạ ngưỡng tự tin, không cần huấn luyện lại mô hình, không cần
Lớp 2 AI. Bước tiếp theo (Task N3): đo lại toàn bộ B1 trên TOÀN thư viện thật với bản sửa này, xem
tỷ lệ bao phủ tổng thể thay đổi ra sao trước khi quyết định có cần B2/B3/B4 nữa hay không.
