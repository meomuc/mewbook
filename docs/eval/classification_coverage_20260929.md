# B1 — Chẩn đoán độ bao phủ phân loại thông minh (dữ liệu thật)

**Ngày:** 2026-09-29
**Yêu cầu:** Phần B, Task B1 — chạy chẩn đoán trên thư viện thật, gộp mọi sách không có hashtag
vào đúng 1 trong 5 nhóm nguyên nhân, với số liệu thật. **Dừng ở đây, chờ chủ dự án xem báo cáo
này trước khi làm B2 trở đi** — cách sửa phụ thuộc vào nguyên nhân nào chiếm tỷ trọng lớn nhất,
và số liệu bên dưới cho thấy nguyên nhân lớn nhất không nằm trong 5 nhóm đã liệt kê ban đầu.

## Tóm tắt (đọc trước)

- Thư viện thật (`%APPDATA%\SmartDocLibrary\library.db`, copy sang `database/library.db` để
  chẩn đoán, không commit — xem `.gitignore`): **8.605 sách**, hiện có hashtag/thể loại: **2.255
  (26,2%)**.
- **73,8% (6.350 sách) chưa có hashtag.** Đã chạy lại đúng pipeline Lớp 1 thật (không mô phỏng)
  trên toàn bộ 6.350 sách này bằng cách đọc file thật trên đĩa.
- Nguyên nhân lớn nhất **không phải** "không đủ bằng chứng" hay "ngoài 48 thể loại" — mà là
  **một lỗi cụ thể, đã xác minh, trong cơ chế chống nhầm "sách nhiều chủ đề" (`mixed_topics`)**:
  nó đang gạt bỏ **70% số sách trong nhóm chưa có hashtag (4.445/6.350 = 51,7% toàn thư viện)**,
  trong đó **95,1%** trường hợp mô hình vốn đã tự tin ≥ 90% vào đúng MỘT thể loại trước khi bị
  cơ chế này gạt.
- Ngoài ra phát hiện thêm (không thuộc 5 nhóm a-e, nhưng quan trọng): **206 sách (3,2%)** thực
  ra ĐÃ phân loại được nếu chạy lại "Phân loại" ngay bây giờ — dữ liệu trong DB chỉ đơn giản là
  chưa được cập nhật lại, không phải khoảng trống thật.

## Phương pháp

- Nguồn dữ liệu: bản sao thật của `library.db` (945 MB, 8.605 sách), copy từ máy chủ dự án vào
  `database/library.db` (thư mục mới, nằm trong `.gitignore` qua `*.db`, không commit).
- **Không mô phỏng, không dựng dữ liệu giả.** Script chẩn đoán
  (`tools/eval/classification_coverage.py`, đã commit để B5 dùng lại) gọi **đúng** các hàm sản
  xuất thật: `application/classification_features.FeatureExtractor.extract()` (đọc file thật
  trên đĩa — epub/pdf/mobi, qua `TextSampler`), `domain/text_classifier.TextClassifierModel`
  (model thật đang chạy, `classifier_model.json.gz`, không có model do người dùng tự train),
  và 3 guard thật trong `application/classification_guards.py` (`periodical_cue`,
  `mixed_topics`, `label_verdict`/`title_cue_verdict`) — logic giống hệt
  `classify_worker.classify_chunk()`, chỉ khác một điểm: **giữ lại lý do lỗi trích xuất gốc**
  ngay cả khi đó là lỗi "cuối cùng" (permanent) — `classify_chunk()` cố ý xoá lý do đó trong sản
  phẩm thật (để không thử lại vô ích mỗi lần chạy), nhưng B1 cần lý do gốc để phân nhóm trung
  thực, không cần hành vi UI.
- Diện chẩn đoán: mọi sách **chưa có hashtag thể loại thật sự** trong `documents.tags` — không
  chỉ dựa vào cột `smart_classification.category_id IS NULL` (có 63 sách tuy cột đó NULL nhưng
  đã có hashtag thể loại gắn tay, nên KHÔNG tính vào nhóm này).
- Thời gian chạy: 6.350 sách trong 587 giây (~9,8 phút), đọc file thật, phân đoạn tiếng Việt
  bằng `pyvi` (segmenter "auto", giống sản phẩm thật).

## Số liệu tổng quan

| | Số sách | % trên 8.605 |
|---|---:|---:|
| Tổng thư viện | 8.605 | 100% |
| Đã có hashtag (mô hình gắn hoặc gắn tay) | 2.255 | 26,2% |
| **Chưa có hashtag (diện chẩn đoán B1)** | **6.350** | **73,8%** |

## Phân nhóm nguyên nhân (trên 6.350 sách chưa có hashtag)

| Nhóm | Số sách | % trong nhóm chưa-có-hashtag | % toàn thư viện |
|---|---:|---:|---:|
| (a) Không trích được chữ | 85 | 1,3% | 1,0% |
| (b) Có chữ, dưới ngưỡng tự tin | 1.614 | 25,4% | 18,8% |
| (c) Có chữ, mô hình chạy, nhưng bị **guard gạt bỏ** (không phải "không hợp thể loại nào") | 4.445 | 70,0% | 51,7% |
| (d) Ngoài ngôn ngữ/thể loại mô hình học | 0 | 0,0% | 0,0% |
| (e) Lỗi kỹ thuật khác | 0 | 0,0% | 0,0% |
| *(phát hiện thêm, ngoài 5 nhóm)* Dữ liệu DB cũ — chạy lại là có hashtag ngay | 206 | 3,2% | 2,4% |
| **Tổng** | **6.350** | **100%** | 73,8% |

### (a) Không trích được chữ — 85 sách (1,3%)

Tiêu chí: `parts.body_words == 0` (không phải chỉ dựa vào `reason`, vì lỗi "cuối cùng" như "no
text layer" không luôn đi kèm `reason == "no_text"` — model vẫn có thể "đoán" từ tiêu đề/tác giả
và trả về `low_confidence`/`not_enough_evidence` dù thân sách trống rỗng).

| Lý do trích xuất | Số sách |
|---|---:|
| `no text layer` (PDF scan, không có lớp chữ) | 53 |
| Trống, không báo lỗi (file mở được nhưng không có chữ — bìa/ảnh scan không raise exception) | 21 |
| `unreadable text (encrypted or wrongly encoded)` | 6 |
| `unreadable text (legacy font encoding?)` | 3 |
| `unreadable text` | 2 |

Theo định dạng: PDF 75, EPUB 8, MOBI 2 — hợp lý vì PDF scan ảnh là nguyên nhân "không có chữ"
phổ biến nhất.

Ví dụ cụ thể: *196 thế cờ sau 4 nước đi* (PDF, no text layer), *33 Bài Thực Hành Theo Phương
Pháp Shichida...* (PDF, no text layer), 2 file đặt tên "BOOK COVER-pdf" (PDF, trống — rõ ràng
chỉ là ảnh bìa được lưu nhầm dạng PDF, không phải sách).

Nhóm này nhỏ và đúng như dự đoán ban đầu — **không phải vấn đề chính**.

### (b) Có chữ, dưới ngưỡng tự tin — 1.614 sách (25,4%)

Phân phối độ tự tin thật (`confidence` của thể loại tốt nhất, trên toàn bộ ~3.000 từ đầu sách):

- min 0,049 · p25 0,213 · **median 0,376** · p75 0,592 · max 0,898
- **553 sách (34%) có confidence ≥ 0,5** — "suýt đạt ngưỡng", ứng viên tốt cho B2 (gợi ý "chưa
  chắc chắn" để người dùng xác nhận nhanh).
- 365 sách (23%) có confidence < 0,2 — thực sự mơ hồ, khó cải thiện chỉ bằng hạ ngưỡng.

Ví dụ "suýt đạt" (0,5–0,65): *Ăn Dặm Kiểu Nhật* (0,60, gợi ý `textbook`), *Đất Nước Tôi Và Thế
Giới* (0,61, gợi ý `memoir_essay`), *Không gia đình* (0,52, gợi ý `children`), *Lén Nhặt Chuyện
Đời* (0,55, gợi ý `novel`).

Đây **đúng là nhóm (b) như spec dự đoán** — nhưng chỉ chiếm 1/4 khoảng trống, không phải nguyên
nhân chính.

### (c) Có chữ, mô hình CHẠY VÀ RA KẾT QUẢ RẤT TỰ TIN — nhưng bị guard gạt bỏ — 4.445 sách (70,0%)

Đây là phát hiện chính của B1. Đây **không phải** trường hợp "không có thể loại nào trong 48 thể
loại hợp lý" như giả định ban đầu của nhóm (c) — số liệu cho thấy điều ngược lại:

- Trong 4.445 sách này, **4.379 bị gạt vì `mixed_topics`** (cơ chế chống nhầm "sách nhiều chủ
  đề" — được thiết kế ban đầu để tránh gắn nhầm tạp chí/tuyển tập), chỉ 66 bị gạt vì
  `periodical` (đúng mục đích thiết kế — số báo/tạp chí).
- **100% các sách bị `mixed_topics` gạt có ≥ 1.250 từ thân sách** (đúng bằng
  `MIN_WORDS_TO_JUDGE_TOPICS` trong `classification_guards.py:39` — ngưỡng kích hoạt cơ chế
  cắt lát) — tức là mọi sách đủ dài đều có nguy cơ dính guard này, không riêng gì sách thật sự
  đa chủ đề.
- **Trước khi bị gạt, độ tự tin của mô hình trên TOÀN BỘ sách là median 0,999, p25 0,991 — và
  4.228/4.445 sách (95,1%) đạt confidence ≥ 0,9.** Đây là mức tự tin rất cao, không phải mơ hồ.

**Đã xác minh bằng vết chạy cụ thể** (`mixed_topics()`, `classification_guards.py:89-107`), ví
dụ sách *Khai Thác Sức Mạnh Tiềm Thức*:

```
Toàn bộ 3.000 từ đầu sách -> self_help, confidence 0.969 (rất tự tin, đáng lẽ gắn được)

Cắt thành 5 lát 600 từ để kiểm tra "có lạc chủ đề không":
  lát 0: matched=177  reason=low_confidence  conf=0.843
  lát 1: matched=186  reason=model           conf=0.933  -> nhóm "Kỹ năng - Tâm lý"
  lát 2: matched=153  reason=low_confidence  conf=0.253
  lát 3: matched=161  reason=low_confidence  conf=0.811
  lát 4: matched=142  reason=low_confidence  conf=0.282

groups thu được: ['', 'Kỹ năng - Tâm lý', '', '', '']
=> mixed_topics() trả về True (bị coi là "nhiều chủ đề") — SAI.
```

**Nguyên nhân gốc:** các ngưỡng tự tin (`min_score`, `min_group_prob`, `min_class_prob` trong
`DEFAULT_PARAMS`, `text_classifier.py:56-64`) được hiệu chỉnh cho một văn bản ~3.000 từ. Khi
`mixed_topics()` cắt sách thành 5 lát chỉ ~600 từ mỗi lát để "hỏi ý kiến" riêng từng lát
(`classification_guards.py:97-98`), gần như lát nào cũng không đủ tự tin để tự nó vượt ngưỡng
(dù xác suất riêng có thể đạt 0,8+ như lát 0 và lát 3 ở trên) — kết quả là hầu hết lát trả về
`low_confidence` (đóng góp chuỗi rỗng `''` vào `groups`, dòng 104), không phải vì các lát *bất
đồng* về chủ đề, mà vì *từng lát riêng lẻ không đủ dài để chắc chắn*. Khi chỉ 1/5 lát (hoặc ít
hơn `MIN_OPINIONS`) đưa ra được một nhóm rõ ràng, tỷ lệ đồng thuận 1/5 = 0,2 ≤ `MAX_AGREEMENT`
(0,6) khiến hàm kết luận "nhiều chủ đề" — trong khi thực tế đúng ra phải là "không đủ dữ liệu để
kết luận gì cả", và nên **giữ nguyên kết quả tự tin của toàn bộ sách** thay vì gạt bỏ nó.

Ví dụ khác đã bị gạt oan (đều đang mất hashtag dù mô hình rất tự tin về TOÀN sách):
- *479-chien-tranh-tien-te*: gợi ý `war_military`, conf toàn sách 1,0
- *890514371-Tribe-of-Mentors-Tap-1-Doc-Thu*: gợi ý `self_help`, conf 0,98
- *Bí Ẩn Nút Chai Pha Lê*: gợi ý `crime_mystery`, conf 0,73
- *Candle Making Alchemy & Home-Based Business...*: gợi ý `marketing_sales`, conf 0,99

Sách tiếng nước ngoài dễ dính hơn (3.780/4.445 = 85% không phải tiếng Việt, so với 71% trong
toàn bộ diện chẩn đoán) — không phải vì mô hình "không hiểu" ngôn ngữ đó (xem mục (d) — 0 sách),
mà đơn giản vì sách tiếng Anh/Pháp trong thư viện này thường dài hơn 1.250 từ ngay từ đầu, nên dễ
chạm ngưỡng kích hoạt `mixed_topics` hơn.

**Đây là nguyên nhân lớn nhất, và là một lỗi cụ thể có thể sửa được — không phải giới hạn vốn có
của mô hình.** Việc sửa (nếu chủ dự án đồng ý) không cần huấn luyện lại mô hình hay hạ ngưỡng tự
tin — chỉ cần sửa logic `mixed_topics()` để phân biệt "các lát bất đồng ý kiến" với "các lát
không đủ dữ liệu để có ý kiến" (ví dụ: chỉ kết luận "nhiều chủ đề" khi có ≥ `MIN_OPINIONS` lát
**đưa ra được nhóm rõ ràng và các nhóm đó thực sự khác nhau**, thay vì coi "im lặng" của đa số
lát là bằng chứng của "nhiều chủ đề").

### (d) Ngoài ngôn ngữ/thể loại mô hình học — 0 sách (0,0%)

Không có sách nào rơi vào `not_enough_evidence` (quá ít từ vựng quen thuộc) mà vẫn có thân sách
(`body_words > 0`) — toàn bộ trường hợp `not_enough_evidence` quan sát được đều đi kèm
`body_words == 0`, nên đã được tính vào nhóm (a) thay vì (d).

Đối chiếu ngôn ngữ trên toàn diện chẩn đoán: tiếng Việt 739 (11,6%), tiếng khác (chủ yếu Anh,
Pháp) 4.508 (71,0%), không rõ/trống 1.103 (17,4%) — **ngôn ngữ không phải rào cản** như giả định
ban đầu; sách tiếng Anh/Pháp vẫn được mô hình chạy và cho kết quả (thường tự tin, như thấy ở mục
(c)), chỉ là kết quả đó bị gạt bởi lỗi `mixed_topics`, hoặc dưới ngưỡng như bất kỳ sách nào khác.

### (e) Lỗi kỹ thuật khác — 0 sách (0,0%)

Không có lỗi ngoại lệ (exception) nào xảy ra khi chạy lại toàn bộ 6.350 sách qua pipeline thật.

### Phát hiện thêm: 206 sách (3,2%) — dữ liệu DB cũ, không phải khoảng trống thật

206 sách có `smart_classification.category_id = NULL` trong DB, nhưng khi chạy lại đúng pipeline
thật ngay bây giờ thì **có** kết quả tự tin (`reason` = `model`/`label`/`title_cue`, ví dụ *Binh
Pháp* -> `war_military` (1,0), *Telesales thực chiến* -> `marketing_sales` (0,99), *ebook 7 thói
quen của bạn trẻ thành đạt* -> `self_help` (1,0)). Đây không phải lỗ hổng cần sửa thuật toán —
chỉ đơn giản là lần chạy "Phân loại" gần nhất chưa xử lý lại các sách này (có thể do được thêm
vào thư viện sau lần chạy đó, hoặc bị lỗi tạm thời lúc đó). **Chạy lại tính năng "Phân loại" có
sẵn sẽ lấy được ngay 206 hashtag miễn phí**, không cần chờ B2-B4.

## Kết luận & đề xuất hướng đi cho B2 trở đi

Số liệu thật cho thấy bức tranh khác đáng kể so với giả định ban đầu của Phần B:

1. **Không phải vấn đề ngưỡng tự tin quá cao** (nhóm b chỉ 25,4% khoảng trống) — B2 (gợi ý "chưa
   chắc chắn" cho nhóm b) vẫn đáng làm, nhưng chỉ giải quyết được ~1/4 vấn đề.
2. **Không phải vấn đề thiếu thể loại hoặc ngoài ngôn ngữ đã học** (nhóm c thật sự theo định
   nghĩa gốc, và nhóm d, đều gần như 0) — B3 (mở rộng taxonomy, huấn luyện lại) **có lẽ chưa cần
   thiết** dựa trên dữ liệu này; nên cân nhắc hoãn cho đến khi thấy bằng chứng khác.
3. **Vấn đề chính là một lỗi cụ thể trong `mixed_topics()`** (70% khoảng trống, 51,7% toàn thư
   viện) — sửa đúng chỗ này có khả năng tăng độ bao phủ nhiều hơn hẳn B2+B3+B4 cộng lại, mà
   **không cần** hạ ngưỡng tự tin hay gọi thêm AI Lớp 2 (Ollama) — vì bằng chứng cho thấy mô hình
   Lớp 1 vốn đã tự tin đúng, chỉ là guard đang gạt bỏ oan.
4. 206 sách (3,2%) có thể lấy lại hashtag ngay lập tức chỉ bằng cách chạy lại "Phân loại" hiện
   có — không tốn công sức mới.

**Đây là quyết định của chủ dự án, không phải việc tôi tự ý làm:** B1 chỉ dừng ở báo cáo. Nếu
chủ dự án đồng ý, đề xuất thứ tự ưu tiên khác với thứ tự B2→B3→B4 gốc:
- Sửa lỗi `mixed_topics()` trước (tác động lớn nhất, rủi ro thấp nhất — chỉ là sửa logic một
  guard, không đụng đến mô hình đã huấn luyện), đo lại theo đúng phương pháp B1 trên tập kiểm
  tra độc lập trước/sau.
- Sau đó mới làm B2 (gợi ý "chưa chắc chắn" cho nhóm b thật sự, sau khi nhóm c đã được sửa và số
  liệu nhóm b được đo lại cho chính xác).
- B3 (mở rộng taxonomy) và B4 (Lớp 2 AI) tạm hoãn, chờ đo lại sau khi sửa `mixed_topics()` xem
  khoảng trống còn lại là bao nhiêu và thuộc nhóm nào.

## Khả năng tái lập

`tools/eval/classification_coverage.py` (đã commit) — chạy lại đúng phương pháp này trên bất kỳ
`library.db` nào:

```
python tools/eval/classification_coverage.py --db path/to/library.db --app-data path/to/SmartDocLibrary --out results.json
```

Dữ liệu thô (`results.json`, chứa tiêu đề/tác giả/đường dẫn file thật của thư viện cá nhân) và
bản sao `database/library.db` dùng để chạy báo cáo này **không được commit** (riêng tư, đã nằm
trong `.gitignore`) — báo cáo này chỉ trích một số ví dụ minh hoạ cần thiết theo yêu cầu của
spec ("ví dụ cụ thể theo từng nhóm"), không phải toàn bộ dữ liệu.
