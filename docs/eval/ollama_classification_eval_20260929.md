# Đánh giá mô hình Ollama cho Lớp 2 phân loại (Task D3) — 2026-09-29

Đo 3 mô hình Ollama trên bộ 29 sách mẫu, để đề xuất một mô hình mặc định khuyến nghị cho
"Trình thiết lập AI" (Phần G). **Đây là số liệu thật, đo trên máy thật, không phải nhận xét
chung chung** — nhưng mẫu còn nhỏ (29 sách, trong đó chỉ 6 tiếng Việt), xem mục "Giới hạn"
trước khi coi kết quả là kết luận cuối cùng.

**Quyết định cần chủ dự án duyệt: đề xuất `qwen2.5:7b` làm mô hình mặc định khuyến nghị**
(xem mục "Đề xuất" cuối file) — **chưa gắn cứng vào code**, đúng yêu cầu D3.

## 1. Bộ sách mẫu — vì sao không dùng thư viện thật

Ban đầu D3 giả định dùng lại "bộ 25-30 sách mẫu đã thiết kế ở phần tóm tắt", nhưng tìm khắp
`docs/`, `src/`, `tools/` không thấy bộ này hay bất kỳ hạ tầng eval nào cho AI Tóm tắt — có
thể chưa từng được làm ở đợt trước. Máy này cũng không có `library.db` thật (không có ở
`%APPDATA%`/`%LOCALAPPDATA%`, chỉ có một file 110KB dữ liệu giả của test đóng gói ở
`C:\build\appdata_e2e\`). Đã hỏi chủ dự án và được xác nhận: **dùng sách công khai/miễn phí
bản quyền** thay vì thư viện cá nhân.

Bộ sách mẫu (`tools/eval/corpus.json`, dựng bằng `tools/eval/build_corpus.py`, chạy lại được
bất cứ lúc nào — script tự tải lại từ nguồn, không có gì "đóng gói cứng"):

- **23 sách tiếng Anh** từ [Project Gutenberg](https://www.gutenberg.org) (hết hạn bản
  quyền tại Mỹ).
- **6 sách tiếng Việt** từ [Wikisource tiếng Việt](https://vi.wikisource.org) (Ngô Tất Tố,
  Nam Cao, Nguyễn Đình Chiểu, Tản Đà, Thạch Lam đều đã mất trên 50 năm — hết hạn bản quyền
  theo Luật SHTT Việt Nam; truyện dân gian "Tấm Cám" không có tác giả). Phần tiếng Việt
  quan trọng riêng vì tiêu chí chọn mô hình của D3 là "hỗ trợ tiếng Việt tốt" — không thể
  đánh giá điều đó chỉ bằng văn bản tiếng Anh.
- Mỗi sách trích một đoạn ~1500 ký tự (đúng bằng `classify_worker.LAYER2_EXCERPT_CHARS` —
  đúng lượng chữ Lớp 2 thật sẽ thấy), cộng tiêu đề/tác giả, gửi y hệt cách
  `application/classify_layer2.py` sẽ gửi.
- Nhãn "đúng" là thể loại không thể bàn cãi hợp lý (Kiêu hãnh và Định kiến → tiểu thuyết,
  Nguồn gốc muôn loài → khoa học tự nhiên...) — sách chỉ được chọn vào bộ khi việc gán nhãn
  không gây tranh cãi.
- **27/48 thể loại của Taxonomy có sách mẫu.** 21 thể loại còn lại — hầu hết nhóm nghề
  nghiệp/kinh doanh hiện đại (quản trị, marketing, khởi nghiệp, lập trình, AI, y học, pháp
  luật, giáo trình, từ điển, ngoại ngữ...) và `wuxia`, `math`, `cooking` — không có sách công
  khai phù hợp rõ ràng nên bỏ trống thay vì gán ép một sách không thật sự đúng thể loại.

## 2. Ba mô hình đã thử

| Mô hình | Dung lượng thật (`ollama list`) | Ghi chú |
|---|---|---|
| `qwen2.5:14b` | 8.99 GB | Đã cài sẵn trên máy trước khi làm D3 |
| `qwen2.5:7b` | 4.68 GB | Tải thêm để so sánh |
| `llama3.2:3b` | 2.02 GB | Tải thêm để so sánh, đại diện nhóm "rất nhỏ" |

Máy đo: có GPU NVIDIA RTX A2000 (4GB VRAM) — thời gian ở máy không có GPU rời sẽ chậm hơn.
Mỗi lệnh gọi dùng `format` JSON schema ép `category_ids` chỉ được chọn trong đúng 48 id hợp
lệ (xem `application/ollama_classifier.py`), giống hệt lúc chạy thật.

## 3. Kết quả

"Đúng" = nhãn thật nằm trong tối đa 3 id mô hình trả về (đúng như Lớp 2 thật cho phép, xem
`classify_layer2.py`); "Đúng vị trí 1" = nhãn thật là id ĐẦU TIÊN — khắt khe hơn, gần với
việc chỉ hiện một gợi ý duy nhất trong "Cần xem lại".

| Mô hình | Đúng (top-3) | Đúng vị trí 1 | Đúng — tiếng Việt (n=6) | Đúng — tiếng Anh (n=23) | Lỗi | Giây/sách (trung bình / trung vị) |
|---|---|---|---|---|---|---|
| `qwen2.5:14b` | 51.7% (15/29) | 51.7% | 33.3% (2/6) | 56.5% (13/23) | 0 | 8.73 / 6.68 |
| **`qwen2.5:7b`** | **82.8% (24/29)** | 44.8% | **83.3% (5/6)** | 82.6% (19/23) | 0 | 4.18 / 3.97 |
| `llama3.2:3b` | 34.5% (10/29) | 6.9% | 66.7% (4/6) | 26.1% (6/23) | 0 | 3.08 / 2.98 |

(`qwen2.5:14b` có 2 lỗi kết nối tạm thời ở lần chạy đầu — Ollama từ chối kết nối giữa lúc
chạy, có lẽ do máy đang tải mô hình 14B nặng nhất cùng GPU 4GB VRAM hạn chế; thử lại thủ
công riêng 2 sách đó ngay sau thì cả hai đều trả lời đúng. Bảng trên đã tính cả hai là đúng
và 0 lỗi, đúng với thực tế sau khi thử lại — nhưng đây cũng là một tín hiệu thật: mô hình
14B trên máy 4GB VRAM có thể không ổn định bằng mô hình nhỏ hơn.)

### Phát hiện đáng chú ý: mô hình to hơn KHÔNG chính xác hơn ở đây

`qwen2.5:14b` (to nhất, 9GB) chính xác **thấp hơn hẳn** `qwen2.5:7b` (nhỏ hơn một nửa, 4.7GB)
— ngược trực giác "to hơn là tốt hơn". Nhìn vào từng sách sai thì thấy nguyên nhân khá rõ:
với sách tiếng Việt "cổ" (chữ có gạch nối kiểu xưa: "Vũ-đại", "nông-nỗi"), `qwen2.5:14b` gần
như luôn trả lời "Cổ văn Việt Nam" (`vn_classics`) bất kể sách đó thật ra là tiểu thuyết,
truyện ngắn, thơ hay tùy bút — như thể nó bắt được "tín hiệu bề mặt: chữ Việt kiểu cũ" mà bỏ
qua thể loại cụ thể. `qwen2.5:7b` phân biệt tốt hơn nhiều trên đúng những sách đó:

| Sách | Nhãn thật | `qwen2.5:14b` trả lời | `qwen2.5:7b` trả lời |
|---|---|---|---|
| Tắt đèn (ch. I) | Tiểu thuyết | *Cổ văn Việt Nam* (sai) | Tiểu thuyết (đúng) |
| Vịnh bức địa đồ rách | Thơ | *Cổ văn Việt Nam* (sai) | Thơ (đúng) |
| Hà Nội băm sáu phố phường | Hồi ký - Tùy bút | *Cổ văn Việt Nam* (sai) | Hồi ký - Tùy bút (đúng) |
| Chí Phèo | Truyện ngắn | Cổ văn Việt Nam, Tiểu thuyết (sai) | Cổ văn Việt Nam, Tiểu thuyết, Hồi ký (sai, nhưng vẫn không phải chỉ 1 nhãn cứng) |

Với sách tiếng Anh, phần lớn câu `qwen2.5:14b` trả "sai" thực ra là lựa chọn hợp lý khác
(Wuthering Heights → "Tiểu thuyết" thay vì "Ngôn tình"; The Art of War → "Lịch sử" thay vì
"Chiến tranh - Quân sự"; Relativity/Origin of Species → "Khoa học" (`science`, một id hợp lệ
khác trong Taxonomy) thay vì id khoa học chuyên biệt hơn) — cho thấy nhãn "đúng" duy nhất của
bộ eval này có phần khắt khe hơn thực tế, và một phần "sai" của 14B không hẳn là mô hình kém,
mà là ranh giới thể loại vốn mờ. Nhưng riêng khoản overuse "Cổ văn Việt Nam" thì là một điểm
yếu thật, không phải do nhãn khắt khe.

`llama3.2:3b` (3B, nhỏ nhất) cho thấy giới hạn rõ ràng của việc đi quá nhỏ: rất hay trả lời
"không đủ căn cứ" (`insufficient_evidence`) ngay cả với sách rất dễ (Kiêu hãnh và Định kiến,
Alice ở xứ sở thần tiên, Nguồn gốc muôn loài...), và khi có trả lời thì nhiều lần chọn nhầm
hẳn sang thể loại không liên quan (Dracula → "Truyện cổ tích"; Chiến tranh giữa các thế giới
→ "Lịch sử"; thậm chí gán "Kiếm hiệp - Tiên hiệp" cho Wuthering Heights và The Art of War) —
"Đúng vị trí 1" chỉ 6.9% cho thấy ngay cả lúc đúng, nhãn đúng cũng hiếm khi được đặt lên đầu.
Độ chính xác tiếng Việt (66.7%) cao hơn tiếng Anh (26.1%) của riêng mô hình này nhiều khả
năng chỉ là ngẫu nhiên do mẫu quá nhỏ (n=6), không phải bằng chứng 3B giỏi tiếng Việt hơn
tiếng Anh.

## 4. Giới hạn của lần đo này

- **Mẫu nhỏ**: 29 sách, 6 sách tiếng Việt — một khoảng tin cậy thống kê rất rộng. Số liệu đủ
  để thấy CHÊNH LỆCH LỚN (7B rõ ràng hơn hẳn hai mô hình kia) nhưng không đủ để phân biệt hai
  mô hình có kết quả gần nhau.
- **Một nhãn "đúng" duy nhất mỗi sách** trong khi nhiều sách thật ra hợp lý ở 2 thể loại —
  bảng "Đúng (top-3)" giảm bớt vấn đề này (Lớp 2 thật cũng cho phép tới 3 gợi ý) nhưng không
  loại bỏ hoàn toàn.
- **Không đo trên sách có DRM/quét ảnh** (không trích được `excerpt`) — Lớp 2 thật sẽ gặp
  loại sách này (chính là một phần lý do Lớp 1 xếp "chưa chắc"), nhưng eval này không có ví
  dụ cho trường hợp "sách trống trơn, chỉ có tiêu đề/tác giả".
- **21/48 thể loại không có sách mẫu** (mục 1) — không nói được gì về độ chính xác của mô
  hình trên các thể loại đó.
- **Không đo dùng nhiều lần liên tiếp/máy khác** — mỗi mô hình chỉ chạy một lượt; thời gian
  đặc biệt phụ thuộc phần cứng (GPU 4GB ở đây).

## 5. Đề xuất — CHỜ CHỦ DỰ ÁN DUYỆT

Đề xuất **`qwen2.5:7b`** làm mô hình mặc định khuyến nghị trong "Trình thiết lập AI" (Phần
G): chính xác nhất trong 3 mô hình đã thử ở mọi mặt cắt (tổng thể, tiếng Việt, tiếng Anh),
nhanh hơn `qwen2.5:14b`, dung lượng vừa phải (4.68GB — tải được trong thời gian hợp lý), và
0 lỗi kết nối suốt lượt chạy.

**Chưa gắn cứng vào code** (`ollama_classifier.DEFAULT_LAYER2_MODEL` hiện vẫn là
`"qwen2.5"`, chưa đổi) — theo đúng AC của D3: "DỪNG chờ tôi duyệt mô hình khuyến nghị trước
khi gắn cứng vào Trình thiết lập AI".

Nếu chủ dự án duyệt, việc còn lại: đổi `DEFAULT_LAYER2_MODEL` thành `"qwen2.5:7b"` (không
đổi `"qwen2.5"` cho AI Tóm tắt — đó là lựa chọn khác, dùng model theo `ai_model`/
`AppConfig.ai_model`, không liên quan đến `smart_classify_layer2_model`), và đưa vào danh
sách mô hình khuyến nghị của Trình thiết lập AI (Phần G) cùng dung lượng ước tính (~4.7GB)
để hiện cảnh báo dung lượng trước khi tải, đúng AC của G1.

## Cách chạy lại

```
uv run python tools/eval/build_corpus.py                                   # dựng lại corpus.json (tải lại từ Gutenberg/Wikisource)
uv run python tools/eval/run_layer2_eval.py qwen2.5:14b qwen2.5:7b llama3.2:3b   # ollama phải đang chạy, các mô hình đã "ollama pull"
```

Kết quả chi tiết từng sách: `tools/eval/results.json`.
