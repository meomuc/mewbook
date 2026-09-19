# Kiểm toán mô hình phân loại đi kèm ứng dụng (S0-04)

- **Ngày:** 2026-09-19 · **Đối tượng:** `src/smartdoc/data/classifier_model.json.gz` (+ `.meta.json`), thuật toán linear-SVM, tokenizer `pyvi`, `train.py`.
- **Câu hỏi:** từ vựng của mô hình có chứa cụm từ hiếm hoặc tên riêng làm nhận diện được thư viện của tác giả không? Nên đặt ngưỡng tần suất tối thiểu nào khi huấn luyện?
- **Phạm vi hành động:** tài liệu này **chỉ báo cáo và đề xuất**. **Không đổi mô hình, `train.py` hay bộ huấn luyện.** Việc đổi thuộc quyết định của chủ dự án (mục 6).
- **Che giá trị:** không liệt kê từ vựng cụ thể; token mẫu chỉ hiển thị dạng `x***(độ dài)`. Số liệu là tổng hợp.

## 1. Cách kiểm tra

1. Đọc mô hình: 60.000 đặc trưng (`features`), `idf`, `postings` (mỗi đặc trưng một danh sách [lớp, trọng số]), 48 lớp. Đặc trưng là token đã bỏ dấu, chữ thường, chỉ gồm `a–z`, `0–9`, `_` (`_` nối âm tiết của từ ghép do `pyvi`); **không có** đường dẫn, email hay URL nguyên văn.
2. **Khôi phục tần suất tài liệu (df)** từ `idf = ln((N+1)/(df+1)) + 1`. Đơn vị `N = 14.774` **dòng huấn luyện** (suy ra từ `idf` lớn nhất của token chưa từng thấy). 98,9% giá trị df khôi phục ra số nguyên trong sai số làm tròn, nên phép suy ngược đáng tin.
3. **Đối chiếu với thư viện thật** (`library.db`, mở chỉ đọc; 7.545 tài liệu): token hóa cột tác giả, tiêu đề, hashtag bằng đúng `TextProcessor` của ứng dụng rồi so với từ vựng. Chỉ in số đếm.
4. Ước lượng **thiệt hại nếu cắt** bằng tổng |trọng số| trong `postings` của các đặc trưng bị cắt (đại lượng thay thế cho ảnh hưởng tới dự đoán, xem giới hạn ở mục 5).

## 2. Kết quả

### 2.1 Hình dạng từ vựng

| Nhóm | Số đặc trưng | Tỷ lệ | Có trong `postings` | Phần trọng số |
|---|---|---|---|---|
| df > 50 dòng | 18.907 | 31,5% | 18.255 | 73,7% |
| df 11–50 | 36.985 | 61,6% | 25.686 | 23,6% |
| df 6–10 | 3.785 | 6,3% | 1.990 | 1,6% |
| df 4–5 | 48 | 0,08% | 45 | 0,18% |
| df 3 | 42 | 0,07% | 37 | 0,10% |
| df 2 | 27 | 0,05% | 26 | 0,07% |
| df 0–1 (từ khóa khởi tạo của `taxonomy.json` hoặc gần như chưa thấy) | 206 | 0,34% | 200 | 0,74% |
| **Tổng** | **60.000** | | 46.239 (23% đặc trưng không có trọng số, chỉ dùng đếm "bằng chứng" và `idf`) | 100% |

**Kết luận:** từ vựng chủ yếu là từ thông dụng. Chỉ **323 đặc trưng (0,54%)** có df ≤ 5, và chúng chỉ mang **1,1% trọng số**.

### 2.2 Dấu vết thư viện của tác giả

| Mối quan tâm | Kết quả | Mức |
|---|---|---|
| Token của **tiêu đề** trong thư viện có trong từ vựng | 5.601 / 13.555 token tiêu đề. Chỉ **51 token hiếm (df ≤ 5)**, 48 trong số đó có trọng số | Thấp–Trung bình |
| Token của **tên tác giả** | 2.333 / 5.634 token tác giả có trong từ vựng, nhưng phần lớn là âm tiết tên thông dụng (91 token df 6–10, 1 token df ≤ 5, còn lại df ≥ 11). **Chỉ 9** token dạng "họ tên đầy đủ" (≥ 3 âm tiết ghép) | Thấp |
| **Hashtag riêng** của người dùng | 209 / 210 token hashtag có trong từ vựng; **28 token df ≤ 5** (có thể là nhãn cá nhân) | Trung bình |
| Từ hiếm dạng dài | 30 token ≥ 20 ký tự với df ≤ 10 | Thấp |
| Token có chữ số, đường dẫn, email, URL | **Không có** token chứa chữ số hay dấu chấm/`@`/`/`. Có token chứa ký tự nối `_` là do từ ghép | Không có rủi ro |
| Định danh của chủ dự án (tên tác giả ứng dụng, tên tài khoản, tên công khai) | Không có token nào là định danh riêng; chỉ có một từ ghép thông dụng chứa một âm tiết trùng (df ≈ 243), không nhận diện được cá nhân | Thấp |

### 2.3 Phát hiện phụ: dấu vết nguồn phát hành sách điện tử (không phải dữ liệu cá nhân)

Từ vựng chứa **token do tên trang/nhóm phát hành ebook, chân trang và đoạn chèn tự động** trong nội dung sách: nhiều token nhắc trang web, mạng xã hội, email, blog, ứng dụng nhắn tin (df từ khoảng 13 đến 191), **hai tên trang/nhóm ebook rất phổ biến (df ≈ 680 và ≈ 980)**, cùng hàng chục token kiểu `ebook`, `copyright`, `download`, tên định dạng. Điều này cho thấy:
1. **Chất lượng:** mô hình học "nguồn phát hành" như một tín hiệu thể loại (tương quan giả); nên loại các token này.
2. **Nguồn gốc dữ liệu huấn luyện:** phần thư viện dùng để huấn luyện có nhiều bản sách từ các nguồn đó. Bản thân mô hình chỉ chứa thống kê từ, không chứa văn bản sách, nhưng câu hỏi nguồn gốc/bản quyền của kho huấn luyện nên đưa cho luật sư (đã thêm vào `LAWYER_QUESTIONS.md`).

### 2.4 Siêu dữ liệu đi kèm (`.meta.json`)

Ghi `trained_docs = 9.451`, số sách theo từng thể loại (từ 1 đến 2.310), `trained_at`, độ chính xác giữ lại. Đây là **thống kê tổng hợp** về thành phần thư viện của tác giả (ví dụ số truyện ngắn, tiểu thuyết); 5 trong 47 lớp có ≤ 3 sách. **Rủi ro thấp**, nhưng lộ quy mô và cơ cấu thư viện. Có thể làm tròn hoặc bỏ `per_class` nếu muốn.

### 2.5 Điểm đáng chú ý về `min_df` (đã sửa ngày 2026-09-19)

> **Đính chính.** Bản đầu của mục này (S0-04) nói df đếm theo *dòng huấn luyện* vì "mỗi sách dùng hai lần (có và không có nhãn nhúng)". Khi đọc mã để làm S0-04b, tôi thấy điều đó **không đúng**: `build_model_svm` đếm df theo *tài liệu* (`df.update(doc.token_ids())`, một tập token cho cả sách gộp cả hai dạng). Con số 14.774 là số **tài liệu** (sách có nhãn 9.451 cộng sách không nhãn dùng làm nền), không phải số dòng.

Điểm yếu thật của `min_df = 2` là **cùng một cuốn sách ở nhiều định dạng** (EPUB và PDF của một tên sách) là hai tài liệu chung một `group_key`, nên một token chỉ thuộc **một** cuốn vẫn đạt df = 2 và lọt vào từ vựng. Ngoài ra tên tác giả, tiêu đề và hashtag riêng đi vào từ vựng chỉ với hai bản sao. Đó là gốc của 323 đặc trưng hiếm ở 2.1. Hướng sửa ở mục 4 vẫn đúng, chỉ cần đếm theo `group_key` chứ không theo dòng.

## 3. Đánh giá rủi ro tổng thể

| Khía cạnh | Đánh giá |
|---|---|
| Lộ thông tin cá nhân trực tiếp (đường dẫn, email, tên người dùng, khóa) | **Không thấy** |
| Nhận diện được thư viện qua từ hiếm/tên riêng | **Thấp**: dưới 0,6% đặc trưng có df ≤ 5, chúng gần như không mang trọng số; tên tác giả đầy đủ chỉ 9 token |
| Nhãn cá nhân (hashtag riêng) | **Trung bình nhỏ**: 28 token hiếm |
| Chất lượng mô hình (tín hiệu nguồn phát hành) | Có vấn đề nhẹ, nên xử lý |
| Nguồn gốc dữ liệu huấn luyện | **Câu hỏi cho luật sư** |

## 4. Đề xuất ngưỡng và thay đổi (chờ chủ dự án duyệt)

Ước lượng dùng đại lượng thay thế ở mục 1.4, tính trên mô hình hiện có (chưa huấn luyện lại):

| Ngưỡng df tối thiểu (tính theo dòng huấn luyện; 1 sách ≈ 1,56 dòng) | Đặc trưng bị cắt | Trọng số bị cắt | Token tác giả bị cắt | Token tiêu đề bị cắt |
|---|---|---|---|---|
| 3 | 68 | 0,20% | 0 | 25 |
| 5 | 136 | 0,43% | 0 | 45 |
| 8 | 216 | 0,70% | 2 | 69 |
| **10** | **243** | **0,76%** | 7 | 78 |
| 20 | 24.478 | 11,4% | 670 | 819 |

(Các mốc 3–10 không tính token gieo từ `taxonomy.json`, được giữ nguyên. Mốc 20 là **không** khuyến nghị: mất 11% trọng số.)

**Đề xuất (theo thứ tự ưu tiên):**
1. **Tính df theo cuốn sách, không theo dòng**, và đặt `min_df ≥ 5` sách cho mọi token ngoài `taxonomy.json` (tương đương df ≥ ~8 dòng). Ước lượng mất ≲ 0,7% trọng số, loại khoảng 216 đặc trưng gồm gần hết token hiếm.
2. **Ngưỡng cao hơn cho token chỉ đến từ tác giả/tiêu đề/hashtag riêng** (không đến từ nội dung): ≥ 10 sách, để một tên riêng hay nhãn cá nhân không thể vào mô hình chỉ vì xuất hiện ở vài cuốn.
3. **Danh sách loại trừ (stoplist)** cho token chân trang/nguồn phát hành: tên trang và nhóm ebook, "email/blog/mạng xã hội", "copyright", "download", tên định dạng… (ước lượng vài trăm đặc trưng nếu tính cả biến thể). Vừa giảm tín hiệu giả vừa bỏ dấu vết nguồn. Danh sách duy trì bởi chủ dự án, kèm test.
4. **Không đưa** hashtag riêng (không thuộc `taxonomy.json`) vào đặc trưng, hoặc áp cùng ngưỡng như (2).
5. **Meta:** làm tròn số sách theo lớp (ví dụ ≥ 10) hoặc bỏ `per_class`; giữ `evaluation`.
6. **Dài hạn (tùy chọn):** huấn luyện mô hình đi kèm bằng bộ mẫu công khai (`train.py --dataset`, thư mục theo thể loại, sách phạm vi công cộng) để nguồn gốc rõ ràng; mô hình cá nhân vẫn có thể tạo riêng cho từng người dùng (đã hỗ trợ, `%APPDATA%\…\models\`).

## 5. Giới hạn của kiểm toán này

- Đại lượng "trọng số bị cắt" là **ước lượng đầu vào**, không phải độ chính xác. **Đo tác động thật cần huấn luyện lại** với `uv run python train.py --dry-run` (đọc lại toàn bộ sách trong thư viện, mất nhiều phút, không ghi mô hình) trên mô hình đã sửa, so với `evaluation` hiện tại (accuracy 71,2%, precision 85,1%, phủ 56,4% trên 1.689 sách giữ lại).
- df suy ngược từ `idf` (làm tròn 4 chữ số) đủ chính xác cho df nhỏ; chỉ dùng cho phân nhóm.
- Đối chiếu tên/tiêu đề dùng thư viện **hiện tại** của tác giả, không phải ảnh chụp lúc huấn luyện.
- Chưa kiểm token từ nội dung sách xem có trích cụm từ nhận diện (ví dụ tên riêng hiếm trong một cuốn), vì token nội dung rất khó phân biệt với từ thông dụng khi chỉ có df; đề xuất 1–2 giải quyết phần này bằng ngưỡng.

## 6. Quyết định cần chủ dự án

| # | Câu hỏi | Đề xuất |
|---|---|---|
| 1 | Có áp dụng đề xuất 1–4 và huấn luyện lại mô hình đi kèm không? | **Có.** Làm thành task riêng (S0-04b): sửa `TrainOptions` (df theo sách, ngưỡng tác giả/tiêu đề), thêm stoplist và test; chạy `--dry-run` để đo, rồi mới `--output builtin` khi chủ dự án duyệt số đo |
| 2 | Chấp nhận giảm độ chính xác tối đa bao nhiêu? | Ví dụ ≤ 1 điểm phần trăm accuracy, precision giữ ≥ 85% |
| 3 | Có làm tròn/bỏ `per_class` trong meta không? | Làm tròn |
| 4 | Có muốn chuyển sang mô hình huấn luyện từ bộ mẫu công khai (đề xuất 6) không? | Để sau, không chặn 1.1.0 |
| 5 | Mô hình cũ nằm trong lịch sử git (commit `ad06b01`). Đổi mô hình chỉ có tác dụng nếu lịch sử được xử lý | Gắn với quyết định lịch sử (`SECRET_SCAN_REPORT.md` mục 4, đề xuất hướng A: kho công khai mới) |

## 7. Kết quả S0-04b: mô hình đi kèm đã được huấn luyện lại (2026-09-19)

Chủ dự án duyệt (2026-09-19): huấn luyện lại với ngưỡng chất lượng (giảm độ chính xác tối đa 1 điểm phần trăm, precision giữ ≥ 85%). Đã làm:

- `classification_trainer.py`: df đếm theo **cuốn sách** (`group_key`), thêm `min_books` và `min_books_private` (mặc định 2 và 0, nên mô hình cá nhân của người dùng không đổi); bản phát hành dùng `RELEASE_MIN_BOOKS = 5` và `RELEASE_MIN_BOOKS_PRIVATE = 10` (token chỉ đến từ tiêu đề/tác giả/thẻ, không có trong nội dung của ít nhất 5 sách, cần 10 sách). `python train.py --release` áp dụng chúng.
- `classification_stoplist.py`: danh sách loại trừ token chân trang/nguồn phát hành (website, mạng xã hội, email, tên nhóm ebook, Project Gutenberg, bản quyền...). Danh sách được ưu tiên hơn cả từ khóa taxonomy (bốn từ khóa `ebook`, `ebook_song`, `facebook`, `facebook_ads` bị loại).
- Meta: số sách theo lớp làm tròn **lên** bội số của 10.
- Test: `tests/test_classification_trainer.py` (bản sao nhiều định dạng đếm một lần, ngưỡng bản phát hành, ngưỡng cho token riêng, danh sách loại trừ, làm tròn meta).

**Đo** trên cùng một tập giữ lại (1.095 sách, không có nhãn nhúng). Hai lần chạy cho kết quả hơi khác nhau vì huấn luyện không hoàn toàn tất định, nên ghi cả hai:

| Mô hình | Đặc trưng | Accuracy | Đúng thư mục | Macro-F1 | Trả lời / precision |
|---|---|---|---|---|---|
| Đang đi kèm trước đó (`meta.evaluation`) | 60.000 | 71,2% | | | 56,4% / 85,1% |
| Cũ, chạy lại lần 1 | 60.000 | 70,9% | 91,1% | 61,8% | 56,5% / 85,1% |
| Cũ, chạy lại lần 2 | 60.000 | 70,1% | 91,1% | 61,9% | 60,8% / 85,1% |
| **Bản phát hành, lần 1** | 51.046 | 70,5% | 91,3% | 62,0% | 56,3% / 85,1% |
| **Bản phát hành, lần 2 (được ghi vào kho)** | 51.046 | **70,3%** | 91,1% | 60,0% | 55,9% / **85,5%** |

Kết luận: so với mô hình cũ đang đi kèm, accuracy giảm 0,9 điểm (71,2% xuống 70,3%), nằm trong ngưỡng 1 điểm, và dao động giữa các lần chạy (0,8 điểm) cùng cỡ với chênh lệch; precision 85,5% đạt ≥ 85%; macro-F1 lần ghi giảm khoảng 2 điểm (nhóm nhỏ). Không có gì cho thấy mô hình mới kém đáng kể.

**Kiểm tra mô hình đã ghi:** 51.046 đặc trưng; **không còn token nào trong danh sách loại trừ**; không có token ngoài taxonomy nào có df dưới 5 sách (425 đặc trưng df thấp đều là từ khóa taxonomy, công khai); `per_class` toàn bội số của 10, nhỏ nhất 10; `trained_docs` 5.755.

**Còn lại (chưa làm):** nội dung sách trong thư viện huấn luyện vẫn có thể đến từ nguồn không rõ giấy phép (câu 11 gửi luật sư): mô hình chỉ chứa thống kê từ, không chứa văn bản. Bộ mẫu công khai/phạm vi công cộng (đề xuất 6) để sau 1.0.
