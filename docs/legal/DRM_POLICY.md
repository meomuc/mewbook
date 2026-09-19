# Chính sách DRM của MewBook (S0-09)

Trạng thái: **bản đề xuất, chờ chủ dự án duyệt**. Không phải kết luận pháp lý; các điểm pháp lý đã được đưa vào `LAWYER_QUESTIONS.md` (câu 12). Căn cứ: quyết định D8 (có chuyển đổi định dạng), non-goal "gỡ DRM dưới mọi hình thức" (`01_PRD.md`), FR-LIC-06, FR-CNV-02, `02_ARCHITECTURE.md` mục 10, `05_LEGAL_OPEN_SOURCE_CHECKLIST.md` mục 2.5.

## 1. Chính sách

MewBook **không hỗ trợ gỡ hoặc vượt qua DRM** dưới bất kỳ hình thức nào. Cụ thể:

1. Không viết, không nhúng, không đóng gói, không gọi (kể cả gián tiếp qua Calibre hay plugin) công cụ hoặc mã có chức năng gỡ, vượt hoặc suy ra khóa của DRM (Adobe ADEPT, Amazon/Kindle, Apple FairPlay, Kobo, và các hệ tương tự).
2. Không viết hướng dẫn, không đặt liên kết tới hướng dẫn hay công cụ như vậy, trong ứng dụng, tài liệu, issue, hay kênh hỗ trợ.
3. Phần mềm chỉ **phát hiện** DRM để **từ chối** file đó. Phát hiện không đọc nội dung đã mã hóa, không thử khóa, không thử mật khẩu.
4. Chuyển đổi định dạng (S4-03) đọc file gốc ở chế độ chỉ đọc, ghi kết quả ra thư mục riêng, không sửa và không ghi đè file gốc.
5. Đóng góp (pull request) thêm chức năng trái các điều trên sẽ bị từ chối, và sẽ được ghi trong `CONTRIBUTING.md` (S1-07).

Ranh giới cần nói rõ:

- **Phông nhúng bị làm rối:** EPUB có `META-INF/encryption.xml` khai thuật toán làm rối phông (`http://www.idpf.org/2008/embedding`, `http://ns.adobe.com/pdf/enc#RC`) **không phải DRM**. Khi thiết kế phát hiện ở S4-03, không được coi các mục này là DRM (nếu không, sẽ từ chối nhầm nhiều sách hợp lệ).
- **PDF có mật khẩu mở tài liệu** (người dùng tự đặt) là trường hợp riêng: hiện ứng dụng bỏ qua file, không thử mật khẩu. Việc cho phép người dùng nhập mật khẩu của chính họ chưa nằm trong phạm vi và cần quyết định riêng (mục 5, câu hỏi b).

## 2. Hiện trạng trong mã (đã kiểm tra ngày 2026-09-19)

| Vị trí | Hành vi | Đánh giá |
|---|---|---|
| `infrastructure/text_sampler.py` (đọc MOBI) | Đọc trường mã hóa trong bản ghi 0; nếu khác 0 thì đánh dấu lỗi "DRM-protected" và bỏ qua file. Không giải mã | Phù hợp: phát hiện để từ chối |
| `presentation/reader_window.py` (Kindle) | Gọi `mobi.extract`; lỗi (gồm cả file có DRM) thì rơi về trình đọc của hệ điều hành, có `logger.exception` | Phù hợp; không thử vượt qua |
| `infrastructure/pdf_extractor.py`, `page_count.py`, `fingerprint.py`, `application/metadata_writer.py` | PDF `is_encrypted`/`needs_pass` thì bỏ qua (không có trang, không băm, không ghi metadata). Không gọi `authenticate` | Phù hợp; nhưng thông báo cho người dùng chưa phân biệt "có mật khẩu" và "có DRM" |
| Gói `mobi` 0.4.1 (GPL-3.0-only) | Chỉ đọc các trường DRM trong header (`drm_offset`, `drm_count`, ...); tìm từ khóa `drm`, `decrypt` không thấy mã giải mã | Không có mã gỡ DRM trong phụ thuộc (kiểm bằng tìm từ khóa, chưa đọc từng dòng) |
| Chuyển đổi (S4) | Chưa hiện thực | Xem mục 3 |

Không thấy chỗ nào trong mã hiện tại trái chính sách.

## 3. Yêu cầu cho S4-03 (chuyển đổi)

1. **Phát hiện trước khi gọi Calibre**, mức chỉ đọc siêu dữ liệu: MOBI/AZW (trường mã hóa khác 0), EPUB (`META-INF/rights.xml`, hoặc `encryption.xml` có thuật toán ngoài danh sách làm rối phông ở mục 1), PDF (từ điển `Encrypt` có bộ xử lý không chuẩn, ví dụ khai báo DRM của nhà bán). Danh sách chính xác sẽ chốt và có test ở S4-03.
2. Nếu phát hiện DRM: từ chối, không gọi `ebook-convert`, không tạo file đầu ra. Thông báo (theo `03_UI_UX_SPEC.md`): "Sách này có bảo vệ bản quyền (DRM) nên không thể chuyển đổi."
3. Nếu Calibre tự từ chối vì DRM: hiển thị đúng thông báo trên, không gợi ý cách khác.
4. Không đóng gói Calibre; `ebook-convert` chạy như tiến trình riêng; không cài hay khuyên cài plugin nào của Calibre.
5. Test: file mẫu có dấu hiệu DRM (tạo giả bằng cách sửa header/thêm `rights.xml`; không dùng sách có DRM thật) phải bị từ chối và không sinh file đầu ra.

## 4. Đề xuất sửa `CLAUDE.md` (A2) — chờ chủ dự án duyệt, chưa áp dụng

Thêm một dòng vào mục 4 (Guardrails), ngay sau dòng "Don't move or delete users' original ebook files...":

```diff
 - Don't move or delete users' original ebook files. Writing *metadata* into EPUB/PDF is allowed only as specified in `docs/METADATA_LOOKUP_SPEC.md` §5 (explicit per-run opt-in, backup first, temp file + verify + `os.replace`); no other code path may modify them.
+- No DRM support (`docs/legal/DRM_POLICY.md`): never add, call, bundle, document or link a tool or code that removes or bypasses DRM. DRM may only be *detected* in order to refuse the file. Format conversion reads the original read-only, writes elsewhere, and never overwrites the source.
```

Ghi chú tương tác với A1 (gửi thiết bị): A1 cho phép **chép** file lên thiết bị theo lệnh người dùng; A2 không mâu thuẫn, vì chép không sửa file gốc và không đụng DRM. Một file có DRM vẫn có thể được **chép nguyên trạng** lên thiết bị nếu người dùng yêu cầu (đó là chép, không chuyển đổi); nếu bạn muốn chặn cả việc đó, cần nói rõ.

## 5. Quyết định của chủ dự án và việc còn lại

Quyết định ngày 2026-09-19:

- **b. PDF có mật khẩu: giữ nguyên là bỏ qua.** Chưa cho nhập mật khẩu ở 1.x. Ứng dụng không gọi `authenticate` và không thử mật khẩu.
- **c. File có DRM: cho gửi nguyên trạng lên thiết bị (S3).** Đây là *chép*, không chuyển đổi và không sửa file. Giao diện gửi thiết bị nên ghi chú "sách có DRM, không chuyển đổi được" (nội dung do S3b-06 chốt). Câu 12(c) trong `LAWYER_QUESTIONS.md` hỏi luật sư về điểm này.

Còn mở:

- a. Chủ dự án duyệt chính sách ở mục 1 và dòng A2 ở mục 4 (hoặc sửa lời). A2 chưa được áp dụng vào `CLAUDE.md`.
- d. Luật sư xem câu 12 trong `LAWYER_QUESTIONS.md` trước khi công khai.
- Cải thiện nhỏ (đề xuất, chưa làm): thông báo cho người dùng phân biệt "PDF có mật khẩu" với "sách có DRM".
