# Đặc tả: Tìm kiếm & cập nhật metadata sách

Trạng thái: **Giai đoạn 1 đã cài đặt** (các mục 1–5 và 7, trừ phần kho cộng đồng; xem §11 "Ghi chú cài đặt" ở cuối file). Giai đoạn 2 (kho cộng đồng, chia sẻ) và 3 chưa làm. Đã chốt với chủ dự án:
1. "Cơ sở dữ liệu" = thư viện cục bộ **+ kho cộng đồng trên Supabase**.
2. "Cập nhật" = chỉ mục trong app **và ghi vào file gốc** (EPUB/PDF).
3. Chia sẻ **chỉ văn bản metadata**, không bao giờ chia sẻ ảnh bìa.

## 1. Luồng tra cứu (dừng sớm khi độ tin cậy ≥ 90%)

| Tầng | Nguồn | Khóa | Ghi chú |
|---|---|---|---|
| 0 | Chính file | ISBN trong OPF / trang đầu PDF | dùng extractor sẵn có |
| 1 | Thư viện cục bộ | `fingerprint`, ISBN, tiêu đề+tác giả chuẩn hóa | bản sao khác của cùng sách; dùng `normalize_text` của `cover_search` |
| 2 | Kho cộng đồng (Supabase) | `fingerprint` → ISBN → tiêu đề+tác giả | khớp fingerprint = đúng nội dung sách |
| 3 | Internet | Open Library, Google Books (API + feed), Apple Books, Tiki | tái dùng hạ tầng `cover_search`: song song, chấm điểm, ngưỡng, cache |

Nút "Tìm thêm trên internet" luôn có. Mỗi nguồn hỏng độc lập, không làm hỏng cả tìm kiếm.

## 2. Định danh sách: `fingerprint` (quan trọng)

`content_hash` hiện tại là SHA-256 **toàn bộ file**. Ghi metadata vào file làm nó **đổi** (đã kiểm chứng), làm hỏng
duplicate finder và khiến hai người có cùng sách nhưng khác metadata có hash khác nhau. Vì vậy thêm cột
`fingerprint` = hash **không phụ thuộc metadata**, dùng làm khóa cộng đồng:

- **EPUB:** SHA-256 của (tên + nội dung) mọi entry zip, sắp xếp theo tên, **trừ** `*.opf`, `mimetype`, `META-INF/*`.
- **PDF:** SHA-256 của `page_count` + `page.read_contents()` của tối đa 10 trang đầu.
- MOBI/AZW3: fingerprint = `content_hash` (không ghi được, nên không đổi).
- Đã kiểm chứng: sau khi ghi metadata, fingerprint giữ nguyên còn hash toàn file đổi.
- Sau mỗi lần ghi vào file: cập nhật lại `content_hash`, `file_size`, `updated_at` trong chỉ mục.

## 3. Schema cục bộ (chỉ **thêm** cột, theo `_migrate_add_missing_columns`)

`documents`: `fingerprint TEXT`, `publisher TEXT`, `pub_year INTEGER`, `language TEXT`, `isbn TEXT`, `series TEXT`,
`description TEXT`, `locked_fields TEXT` (JSON: các trường người dùng tự sửa, không bị đề xuất ghi đè).

Bảng mới `metadata_history` (hoàn tác + nguồn gốc): `id, doc_id, run_id, field, old_value, new_value, source,
confidence, applied_at, written_to_file (0/1)`.

Bảng mới `metadata_outbox` (hàng đợi chia sẻ khi offline): `id, fingerprint, payload_json, created_at, sent_at`.

## 4. Xác nhận trước khi cập nhật

Hộp thoại "Đề xuất metadata" (mẫu `CoverSearchDialog` + `MetadataEditorDialog`):
- Bảng *Hiện tại | Đề xuất | Nguồn | Độ khớp %*, ô tick từng trường; danh sách nhiều ứng viên để chọn.
- Mặc định tick: trường **trống**, hoặc đề xuất ≥ 90%. Trường xung đột với dữ liệu hiện có: **bỏ tick**. Trường trong `locked_fields`: không đề xuất.
- Hai ô riêng: "Cập nhật chỉ mục thư viện" (luôn bật) và "**Ghi vào file gốc**" (xem §5).
- **Không bao giờ tự ghi.** Chỉ ghi khi bấm "Áp dụng". Mỗi lần áp dụng tạo một `run_id` để **Hoàn tác** (khôi phục cả chỉ mục lẫn file từ bản sao lưu).
- Hàng loạt: chọn nhiều sách → tra cứu nền → "hộp thư đề xuất"; nút "Chấp nhận tất cả ≥ 90%" và duyệt từng cuốn.

## 5. Ghi vào file gốc (giao thức an toàn — BẮT BUỘC)

Chỉ EPUB và PDF. MOBI/AZW3 và PDF mã hóa: chỉ cập nhật chỉ mục, báo rõ lý do.

1. Chỉ ghi khi người dùng tick ô "Ghi vào file gốc" trong lần áp dụng đó (mặc định tắt; có thể đổi mặc định trong Cài đặt).
2. **Sao lưu trước**: `<thư mục dữ liệu app>/backups/<doc_id>/<run_id>.<ext>` (giữ N bản gần nhất, có tùy chọn dung lượng tối đa). Không ghi nếu sao lưu thất bại.
3. **Ghi vào file tạm** cùng thư mục, kiểm tra mở lại được và đọc đúng metadata + fingerprint không đổi, rồi mới `os.replace` sang file gốc. Lỗi ở bất kỳ bước nào → giữ nguyên file gốc, báo lỗi.
4. Từ chối ghi khi: file chỉ đọc, đang mở trong trình đọc của app (đóng trước), PDF mã hóa/DRM, đường dẫn không tồn tại. Cảnh báo nếu file nằm trong thư mục đồng bộ (OneDrive) đang đồng bộ.
5. **EPUB:** viết lại zip, giữ nguyên `mimetype` là entry đầu, không nén; chỉ sửa các phần tử `dc:*` trong OPF (giữ nguyên phần còn lại, kể cả `meta` khác). **PDF:** `set_metadata` + lưu **incremental** (`saveIncr`), không viết lại nội dung.
6. **Chặn vòng lặp file watcher:** ghi vào file sẽ phát sự kiện `modified`. Đăng ký đường dẫn đang tự ghi trong một tập "bỏ qua sự kiện" cho tới khi hết thời gian debounce, rồi cập nhật chỉ mục trực tiếp.
7. Ghi `written_to_file=1` vào `metadata_history` để hoàn tác biết khôi phục file.

## 6. Chia sẻ lên kho cộng đồng (opt-in)

- Chế độ (Cài đặt): **Không chia sẻ (mặc định)** / Hỏi từng lần / Luôn chia sẻ metadata đã xác nhận.
- **Chia sẻ:** `fingerprint`, ISBN, tiêu đề, tác giả, nhà xuất bản, năm, ngôn ngữ, bộ sách, mô tả ngắn, nguồn gốc từng trường, phiên bản app.
- **KHÔNG chia sẻ:** ảnh bìa (kể cả URL), đường dẫn/tên file, danh sách thư viện, tags/bộ sưu tập cá nhân, tóm tắt AI, đánh giá.
- Chỉ chia sẻ trường **người dùng đã xác nhận/chỉnh sửa**, không chia sẻ đề xuất chưa duyệt.
- **Cờ cấp phép theo nguồn** (`shareable` trong mỗi nguồn): trường lấy nguyên từ nguồn không cho phép phân phối lại (mặc định coi Google Books, Apple Books là **không**) chỉ được chia sẻ nếu người dùng **đã tự sửa** giá trị. Open Library (dữ liệu mở) được phép. *Cần chủ dự án rà lại điều khoản từng nguồn trước khi bật.*
- Màn hình **xem trước** ("Sẽ chia sẻ những gì") trước khi gửi; xem danh sách và **rút lại** đóng góp của mình.
- Gửi qua outbox: offline thì xếp hàng, có mạng thì tự gửi.

### Máy chủ (Supabase) — file mới `src/smartdoc/application/sql/002_book_metadata.sql`

Không sửa `001_*.sql`. Theo mẫu `submit_review` (ghi **chỉ qua RPC**, thu hồi INSERT trực tiếp của khóa anon):
- `book_metadata_contributions(id, fingerprint, isbn, fields jsonb, user_hash, created_at, withdrawn_at)`; một người một đóng góp cho mỗi fingerprint (upsert).
- `book_metadata_votes(contribution_id, user_hash, vote)` cho "Xác nhận đúng" / "Báo sai".
- View `book_metadata_consensus`: chọn từng trường theo đồng thuận (nhiều người trùng + phiếu), trả về `confidence`.
- Hàm `submit_book_metadata(...)`: kiểm tra độ dài trường, giới hạn tần suất theo `user_hash`, băm token bí mật phía server (như `submit_review`). RLS: đọc công khai, không ghi trực tiếp.
- Tra cứu cộng đồng: `GET` view theo `fingerprint`, rồi theo `isbn`; cache cục bộ 24 giờ.

## 7. Kiến trúc mã (theo quy ước CLAUDE.md)

- `application/metadata_lookup.py`: `MetadataLookupService` (chuỗi tầng §1), giao diện nguồn `MetadataSource` (cờ `shareable`), `MetadataCandidate` (kèm điểm), lỗi `MetadataLookupError`.
- `application/metadata_writer.py`: `MetadataWriter` (giao thức §5), lỗi `MetadataWriteError`.
- `application/metadata_sharing.py`: outbox + client Supabase (plain `requests`), lỗi `MetadataSharingError`.
- `infrastructure/fingerprint.py`: `fingerprint_file(path)`.
- `presentation/metadata_suggest_dialog.py`, `presentation/metadata_inbox_dialog.py`; mục "Tìm metadata" trong menu chuột phải và nút "Tìm thông tin" trong `MetadataEditorDialog`.
- Sự kiện mới (frozen dataclass, qua `QtEventBridge`): `MetadataSuggestionsReadyEvent`, `MetadataAppliedEvent`.
- Cài đặt: bật/tắt & thứ tự nguồn, ngưỡng độ tin cậy, tự tra cứu khi nhập (**chỉ tạo đề xuất**), mặc định "ghi vào file", dung lượng sao lưu, chế độ chia sẻ.

## 8. Lộ trình

| Giai đoạn | Nội dung |
|---|---|
| **1** | cột schema mới + `fingerprint` (điền cho sách cũ ở nền) + tầng 0/1/3 + hộp thoại xác nhận + `metadata_history`/hoàn tác + **ghi file có sao lưu** |
| **2** | `002_book_metadata.sql` + tầng 2 (đọc cộng đồng) + chia sẻ (opt-in, outbox, xem trước, rút lại) |
| **3** | hộp thư đề xuất hàng loạt, bỏ phiếu/báo sai, tự tra cứu khi nhập |

## 9. Kiểm thử bắt buộc

- `fingerprint` ổn định khi ghi metadata (EPUB và PDF), đổi khi nội dung đổi.
- Ghi file: file gốc nguyên vẹn khi lỗi ở từng bước (sao lưu hỏng, ghi tạm hỏng, kiểm tra sau ghi hỏng); từ chối file chỉ đọc/PDF mã hóa; `mimetype` vẫn là entry đầu của EPUB; tiếng Việt có dấu đọc lại đúng.
- Hoàn tác khôi phục đúng cả chỉ mục và file.
- Watcher không nhập lại file vừa tự ghi.
- Trường `locked_fields` không bị đề xuất ghi đè; đề xuất không bao giờ tự áp dụng.
- Chia sẻ: payload **không chứa** ảnh bìa, đường dẫn, tags; chế độ "Không chia sẻ" không gửi gì; trường từ nguồn `shareable=False` chỉ gửi khi người dùng đã sửa.

## 10. Việc phải làm ngoài mã

- ~~Cập nhật câu "Original ebook files are never touched" ở `README.md` và `packaging/MewBook.iss`~~ — đã kiểm tra: cả hai nói về **gỡ cài đặt** (bộ gỡ không đụng file sách), vẫn đúng, không cần đổi.
- Cập nhật EULA / Chính sách quyền riêng tư (chia sẻ dữ liệu cộng đồng, ghi vào file) và `CHANGELOG.md` (bản MINOR).
- Rà điều khoản cấp phép của từng nguồn dữ liệu (§6) trước khi bật chia sẻ lại.
- Đặt/khởi tạo dự án Supabase riêng cho kho metadata (hoặc dùng chung dự án đánh giá) và chạy `002_*.sql`.

## 11. Ghi chú cài đặt (Giai đoạn 1)

Đã làm: `infrastructure/fingerprint.py` (+ điền nền cho sách cũ: `application/fingerprint_backfill.py`), cột mới và bảng
`metadata_history` trong `database.py`, `application/metadata_lookup.py` (tầng 0/1/3), `application/metadata_writer.py`
(giao thức §5), `application/metadata_applier.py` (áp dụng + hoàn tác), `core/self_writes.py` (watcher bỏ qua file tự ghi),
`presentation/metadata_suggest_dialog.py`, menu chuột phải "Tìm metadata...", nút "Tìm thông tin..." trong trình sửa, khóa
trường tự sửa (`locked_fields`), dòng thông tin trong panel chi tiết, và 2 cài đặt (mặc định tick "Ghi vào file gốc", số bản sao lưu).

Khác với đặc tả ban đầu:
- Nguồn internet: Open Library, Google Books (API rồi feed), Apple Books. **Không có Tiki** (chỉ trả tên sách, không có trường metadata).
- Tầng 2 (cộng đồng) và chia sẻ: chưa có; `MetadataCandidate.shareable` đã ghi sẵn cờ cấp phép theo nguồn cho Giai đoạn 2.
- Không thêm `MetadataAppliedEvent`: dùng `DocumentUpdatedEvent` + `LibraryUpdatedEvent` sẵn có.
- Dừng sớm: chỉ tầng 1 (thư viện) đủ tin cậy (≥ 90%) mới bỏ qua internet; dữ liệu trong file (tầng 0) không tự dừng vì thường là rác.
- Chưa có chế độ hàng loạt / "hộp thư đề xuất" và tự tra cứu khi nhập (Giai đoạn 3).
- PDF chỉ ghi được Tiêu đề và Tác giả (Info dictionary); các trường còn lại chỉ lưu trong thư viện. EPUB ghi được cả 8 trường.
- File đang mở trong chương trình khác (kể cả trình đọc của app) làm `os.replace` thất bại: hiện lỗi rõ ràng, file gốc nguyên vẹn.
- Sao lưu ở `<thư mục dữ liệu app>/backups/<doc_id>/<run_id>.<đuôi>`; hoàn tác chỉ áp dụng cho lần cập nhật **gần nhất** của mỗi sách.
