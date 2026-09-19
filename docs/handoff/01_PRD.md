# 01 — PRD: MewBook cộng đồng (mã nguồn mở, gửi sách tới thiết bị)

## 1. Tầm nhìn và mục tiêu

MewBook trở thành trình quản lý thư viện ebook **miễn phí, mã nguồn mở (AGPL-3.0)** cho người đọc tiếng Việt, đủ tin cậy để các công ty bán máy đọc sách tặng kèm.

**Mục tiêu đo được:**

| # | Mục tiêu | Thước đo |
|---|---|---|
| G1 | Mở mã nguồn an toàn, đúng pháp lý | Kết luận luật sư; repo sạch bí mật; giấy phép của mọi phụ thuộc đã kiểm kê |
| G2 | Không mất dữ liệu người dùng khi nâng cấp | Nâng cấp từ 1.0.0 lên bản mới không mất dữ liệu; có bản sao lưu tự động trước migration |
| G3 | Dịch vụ đánh giá cộng đồng vận hành được bởi một người | Ẩn nội dung xấu trong vài phút; ứng dụng vẫn dùng bình thường khi máy chủ không sẵn sàng |
| G4 | Gửi sách tới máy đọc dễ dàng và an toàn | Người dùng gửi một bộ sưu tập lên BOOX thật thành công, kèm xem trước kế hoạch |
| G5 | Chuyển đổi định dạng dùng được, có cảnh báo trung thực | Chuyển đổi các định dạng đã chốt; từ chối file có DRM |

**Không thuộc phạm vi (non-goals):** bán hàng/giấy phép thương mại; gỡ DRM dưới mọi hình thức; đồng bộ đám mây cá nhân; ứng dụng di động; chuyển đổi định dạng bằng thư viện tự viết; Wi-Fi/OPDS, macOS/Linux (để S5 và giai đoạn 2).

## 2. Đối tượng

| ID | Đối tượng | Nhu cầu chính |
|---|---|---|
| P1 | Người đọc | Quản lý thư viện tiếng Việt, tìm nhanh, đưa sách lên máy Boox mà không cần hiểu kỹ thuật |
| P2 | Đối tác (công ty bán máy đọc sách) | Tặng kèm hợp pháp, thêm thiết bị của họ mà không sửa mã lõi, không phải xin phép |
| P3 | Chủ dự án/kiểm duyệt viên (một người) | Kiểm duyệt review nhanh, công cụ đơn giản, rủi ro pháp lý thấp |
| P4 | Người đóng góp (tương lai) | Tài liệu rõ, CI ổn định, quy trình đóng góp |

## 3. Phạm vi theo chặng

| Chặng | Epic | Trọng tâm |
|---|---|---|
| S0 | A | Pháp lý và mở mã nguồn |
| S1 | B | Vận hành: CI, schema versioning, sao lưu, relink, cộng đồng |
| S2 | C | An toàn dịch vụ review |
| S3 | D | Gửi sách tới thiết bị (spike, ổ đĩa/thẻ nhớ, sau đó MTP nếu đạt) |
| S4 | E, F | Chuyển đổi định dạng; chuẩn hóa tiếng Việt; i18n |
| S5 | G | Phân loại có phản hồi, Wi-Fi/OPDS, OCR/ngữ nghĩa tùy chọn, macOS/Linux |

Ký hiệu ưu tiên: **M** = bắt buộc, **S** = nên có, **C** = có thể.

## 4. Yêu cầu chức năng (FR)

### Epic A — Pháp lý và mở mã nguồn (S0)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-LIC-01 | Kiểm kê giấy phép mọi phụ thuộc và tài nguyên đóng gói (dữ liệu, model, icon, font, ảnh xem trước theme); xác nhận tương thích AGPL-3.0 | M |
| FR-LIC-02 | Quét cây làm việc **và toàn bộ lịch sử git** tìm bí mật và dữ liệu cá nhân; báo cáo đã che giá trị | M |
| FR-LIC-03 | Thêm `LICENSE` (AGPL-3.0), metadata giấy phép trong `pyproject.toml`, chính sách SPDX, cập nhật `THIRD_PARTY_NOTICES.md`, thay EULA tự sinh bằng văn bản giấy phép | M |
| FR-LIC-04 | Hộp thoại "Giới thiệu" và trình cài đặt hiển thị giấy phép, liên kết mã nguồn tương ứng với đúng phiên bản; quy trình phát hành đính kèm gói mã nguồn | M |
| FR-LIC-05 | `TRADEMARK.md`, `PARTNERS.md` (hướng dẫn một trang cho đối tác), gom tên/logo vào một điểm cấu hình | M |
| FR-LIC-06 | Chính sách DRM ghi vào tài liệu và `CLAUDE.md`: không hỗ trợ gỡ hoặc vượt DRM | M |
| FR-LIC-07 | Bảng nguồn dữ liệu bên thứ ba (điều khoản, giới hạn, khóa); công tắc bật/tắt từng nguồn ảnh bìa trong Cài đặt; xác minh điều khoản của Tiki | M |
| FR-LIC-08 | Dọn tài liệu: làm mới README Status, bỏ đường dẫn cá nhân, chuyển lịch sử Drive/Firestore/Supabase sang ADR, chốt quy ước đặt tên | S |
| FR-LIC-09 | Kiểm toán từ vựng mô hình phân loại để không lộ cụm từ hiếm/tên riêng từ thư viện của tác giả; đề xuất ngưỡng cắt | S |

### Epic B — Vận hành và độ bền dữ liệu (S1)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-OPS-01 | CI trên Windows: test (offscreen) và kiểm tra dựng exe | M |
| FR-OPS-02 | Schema versioning (`PRAGMA user_version`) và migration có thứ tự cho bảng/cột mới, không đụng logic `_migrate_add_missing_columns` hiện có | M |
| FR-OPS-03 | Tự động sao lưu `library.db` trước khi migration; giữ N bản gần nhất; Cài đặt có Sao lưu ngay/Khôi phục | M |
| FR-OPS-04 | Phát hiện file mất hoặc bị đổi chỗ; hộp thoại "Tìm lại file" để relink hàng loạt theo thư mục gốc mới (so khớp theo `content_hash`, sau đó tên + kích thước) | M |
| FR-OPS-05 | Móc ký mã trong `build.ps1` (bước tùy chọn theo biến môi trường) | S |
| FR-OPS-06 | Kiểm tra cập nhật chỉ thông báo, tùy chọn bật, không gửi định danh (chờ O8) | C |
| FR-OPS-07 | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, mẫu issue/PR, quy trình DCO (chờ O5) | S |
| FR-OPS-08 | Làm ổn định các test phụ thuộc thời gian; xử lý test SVM thiếu numpy bằng cách đánh dấu phù hợp | S |
| FR-OPS-09 | Kiểm kê chỗ dùng API riêng của Windows (báo cáo, chưa tái cấu trúc) | S |

### Epic C — An toàn dịch vụ review (S2)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-REV-01 | Nút "Báo cáo" trên mỗi review của người khác (lý do: spam, xúc phạm, sai nội dung, khác) | M |
| FR-REV-02 | Phía máy chủ: tự ẩn review khi đủ số người báo cáo khác nhau (ngưỡng cấu hình được); người dùng cũ (1.0.0) không thấy review đã ẩn | M |
| FR-REV-03 | Giới hạn tần suất đăng và độ dài nội dung phía máy chủ; chặn theo băm danh tính | M |
| FR-REV-04 | Công tắc từ xa (kill-switch) và thông báo: ứng dụng đọc cờ cấu hình, tạm dừng tính năng hoặc hiện thông báo | M |
| FR-REV-05 | Suy giảm êm: máy chủ không truy cập được thì báo "tạm thời không khả dụng" và các tính năng khác không bị ảnh hưởng; timeout ngắn, không chặn giao diện | M |
| FR-REV-06 | Sổ tay kiểm duyệt cho một người (`docs/MODERATION_RUNBOOK.md`) | M |
| FR-REV-07 | Bản nháp `PRIVACY` và `TERMS` (đánh dấu cần luật sư duyệt) và liên kết trong ứng dụng | M |
| FR-REV-08 | Tương thích ngược với ứng dụng 1.0.0 đã cài (mọi thay đổi máy chủ chỉ thêm, không phá) | M |

### Epic D — Gửi sách tới thiết bị (S3)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-DEV-01 | Spike đo đạc trên BOOX Note Air 4 và Go 6 (ổ đĩa/thẻ nhớ, MTP); kết quả ghi vào `docs/spikes/` | M |
| FR-DEV-02 | Lớp truyền tải (`transport`) trừu tượng; bản đầu: ổ đĩa/thẻ nhớ; MTP theo kết quả spike | M |
| FR-DEV-03 | Hồ sơ thiết bị dạng dữ liệu JSON (đóng gói sẵn + thư mục người dùng ghi đè, giống mẫu `taxonomy.json`); có hồ sơ cho BOOX Note Air 4, BOOX Go 6, "BOOX/Android chung", "ổ đĩa/thẻ nhớ chung" | M |
| FR-DEV-04 | Phát hiện thiết bị chạy nền, phát `DeviceConnectedEvent`/`DeviceDisconnectedEvent` | M |
| FR-DEV-05 | Kế hoạch gửi có xem trước: sẽ chép, đã có trên thiết bị, định dạng không tương thích, trùng tên, thiếu dung lượng | M |
| FR-DEV-06 | Thực hiện an toàn: chép sang tên tạm rồi đổi tên (khi transport hỗ trợ), kiểm tra kích thước, có thể hủy, không để lại file dở, **không xóa/ghi đè gì trên thiết bị** (ngoại lệ duy nhất: file dở do chính ứng dụng tạo) | M |
| FR-DEV-07 | Lịch sử gửi theo từng thiết bị (bảng `device_transfers`) để nhận biết "đã có trên thiết bị" | M |
| FR-DEV-08 | Điểm vào giao diện: hàng "Thiết bị" ở thanh bên, menu chuột phải "Gửi tới thiết bị", menu Công cụ, gửi cả bộ sưu tập | M |
| FR-DEV-09 | Quy tắc đặt tên file trên thiết bị theo hồ sơ (mẫu, độ dài tối đa, tùy chọn bỏ dấu tiếng Việt) | S |
| FR-DEV-10 | Rút thiết bị giữa chừng không làm ứng dụng lỗi; báo rõ đã chép/chưa chép | M |
| FR-DEV-11 | Gửi qua MTP (chỉ khi spike đạt tiêu chí) | S |

### Epic E — Chuyển đổi định dạng (S4)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-CNV-01 | Chuyển đổi bằng `ebook-convert` của Calibre chạy như **tiến trình riêng**; phát hiện Calibre đã cài (đường dẫn thường gặp, PATH, đường dẫn do người dùng chọn); không đóng gói Calibre | M |
| FR-CNV-02 | Từ chối file có DRM với thông báo rõ; không cài đặt/gọi công cụ gỡ DRM | M |
| FR-CNV-03 | Đầu ra ghi vào thư mục riêng; **không bao giờ ghi đè hoặc sửa file gốc**; tùy chọn thêm bản chuyển đổi vào thư viện (mặc định tắt) | M |
| FR-CNV-04 | Bộ nhớ đệm bản chuyển đổi theo (tài liệu, định dạng đích, băm nguồn) để tái sử dụng | S |
| FR-CNV-05 | Tích hợp với gửi thiết bị: sách không tương thích được gợi ý chuyển đổi trước khi gửi | S |
| FR-CNV-06 | Cảnh báo chất lượng cho chuyển đổi rủi ro (PDF → EPUB); không cung cấp hàng loạt theo mặc định | S |
| FR-CNV-07 | Bộ mẫu kiểm chuẩn tiếng Việt và báo cáo chất lượng (font, dấu, mục lục) | S |

### Epic F — Tiếng Việt và đa ngôn ngữ (S4)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-VN-01 | Chuẩn hóa Unicode NFC cho metadata và tên file trên thiết bị; **không đổi tên file gốc** | M |
| FR-VN-02 | Phát hiện mã hóa cũ (TCVN3, VNI) trong metadata/tên file; chỉ đề xuất, có xem trước rồi mới áp dụng vào cơ sở dữ liệu | S |
| FR-VN-03 | Tách chuỗi giao diện, hỗ trợ tiếng Việt và tiếng Anh; cài đặt ngôn ngữ | S |
| FR-VN-04 | Tiêu chí nghiệm thu tìm kiếm không dấu (nếu chưa đạt thì sửa cấu hình tokenizer) | M |

### Epic G — Chỉ phác thảo (S5)

Vòng phản hồi phân loại (sửa nhóm thành nhãn huấn luyện, hàng đợi xem lại, độ tin cậy, tập kiểm thử độc lập); nhập highlight từ thiết bị; OCR và tìm kiếm ngữ nghĩa tùy chọn (gói tải thêm); Wi-Fi/OPDS; macOS/Linux. Mỗi mục có PRD riêng khi tới lượt.

## 5. Yêu cầu phi chức năng (NFR)

| ID | Yêu cầu |
|---|---|
| NFR-01 | **Không hồi quy khởi động.** Mở cửa sổ chính không chậm hơn ngưỡng đo được ở 15.000 tài liệu (ngưỡng hiện đo 115 ms; ngân sách tăng tối đa đề xuất +10 ms). Bộ phát hiện thiết bị bắt đầu sau khi cửa sổ chính hiển thị, trên luồng nền, ưu tiên thấp |
| NFR-02 | Giao diện không bao giờ bị chặn bởi thao tác thiết bị/chuyển đổi/mạng. Sự kiện tiến độ gộp tối đa khoảng 5 lần/giây |
| NFR-03 | An toàn dữ liệu: file gốc trong thư viện không bị sửa; không xóa/ghi đè trên thiết bị (trừ file dở của chính ta); sao lưu trước migration |
| NFR-04 | Quyền riêng tư: không thêm telemetry; kiểm tra cập nhật (nếu có) không gửi định danh; danh tính ẩn danh của review giữ nguyên thiết kế hiện có |
| NFR-05 | Di động hóa: mã riêng của Windows nằm sau giao diện trừu tượng, tên module `*_windows.py`, nạp muộn theo nền tảng |
| NFR-06 | Kiểm thử được: mọi thao tác thiết bị/chuyển đổi/mạng có bản giả cho CI; test cần phần cứng thật là tùy chọn |
| NFR-07 | Giấy phép: mọi tệp mới theo chính sách SPDX (sau khi O4 chốt); không thêm phụ thuộc chưa kiểm kê |
| NFR-08 | Tương thích ngược: ứng dụng 1.0.0 và `library.db` cũ nâng cấp tại chỗ; máy chủ review tương thích với client cũ |

## 6. User stories và tiêu chí nghiệm thu (Given – When – Then)

**US-01 (P1).** Là người đọc dùng BOOX, tôi muốn gửi một bộ sưu tập lên máy để đọc khi di chuyển, để không phải kéo thả thủ công.
- *Given* máy đã nhận diện và có sách trong bộ sưu tập, *When* tôi chọn "Gửi tới thiết bị", *Then* thấy kế hoạch với số sách sẽ chép, đã có, không tương thích, thiếu chỗ **trước khi** có gì được chép.
- *Given* tôi bấm Bắt đầu, *When* việc chép hoàn tất, *Then* mỗi sách có mặt trên thiết bị đúng kích thước và có dòng trong lịch sử gửi.
- *Given* sách đã được gửi trước đó, *When* tôi gửi lại, *Then* sách được đánh dấu "Đã có" và không bị chép lại.
- *Given* định dạng sách không có trong danh sách của hồ sơ thiết bị, *When* lập kế hoạch, *Then* sách bị đánh dấu không tương thích kèm gợi ý chuyển đổi (khi S4 có mặt).

**US-02 (P1).** Là người đọc, tôi muốn rút cáp giữa chừng mà không hỏng dữ liệu.
- *Given* đang chép, *When* thiết bị bị rút, *Then* ứng dụng hiện thông báo "N sách đã chép xong, M chưa chép", không văng lỗi, không để lại file dở nhìn thấy được trên thiết bị (nếu còn thiết bị để dọn).

**US-03 (P2).** Là đối tác, tôi muốn thêm dòng máy của mình mà không sửa mã.
- *Given* tôi đặt một file hồ sơ hợp lệ vào thư mục hồ sơ người dùng, *When* khởi động ứng dụng, *Then* thiết bị khớp được nhận diện theo hồ sơ đó; hồ sơ sai định dạng bị bỏ qua kèm cảnh báo trong nhật ký, không làm hỏng ứng dụng.

**US-04 (P1).** Là người đọc, tôi muốn chuyển MOBI sang EPUB.
- *Given* Calibre chưa cài, *When* tôi mở hộp thoại chuyển đổi, *Then* thấy hướng dẫn cài và liên kết tới Cài đặt, không lỗi.
- *Given* file có DRM, *When* tôi chuyển đổi, *Then* bị từ chối với thông báo rõ; không có file đầu ra.
- *Given* chuyển đổi thành công, *When* xem thư mục đầu ra, *Then* có bản mới; file gốc không đổi (băm trước/sau giống nhau).

**US-05 (P3).** Là kiểm duyệt viên, tôi muốn ẩn review xấu nhanh.
- *Given* một review nhận đủ báo cáo từ các danh tính khác nhau, *When* ngưỡng đạt, *Then* review không còn xuất hiện với mọi phiên bản ứng dụng, kể cả 1.0.0.
- *Given* tôi làm theo sổ tay kiểm duyệt, *When* ẩn/hiện lại/chặn một danh tính, *Then* kết quả có hiệu lực ngay và có thể hoàn tác.

**US-06 (P1).** Là người dùng cũ, tôi không muốn mất dữ liệu khi nâng cấp.
- *Given* `library.db` của 1.0.0, *When* mở bằng bản mới, *Then* có bản sao lưu trước migration và toàn bộ dữ liệu (tag, đánh giá, bộ sưu tập) còn nguyên.

**US-07 (P1).** Là người dùng có thư viện đã đổi chỗ, tôi muốn tìm lại file.
- *Given* sách bị đánh dấu mất, *When* tôi chọn thư mục gốc mới, *Then* ứng dụng khớp theo `content_hash` rồi theo tên + kích thước, hiện kết quả để xác nhận trước khi cập nhật đường dẫn.

**US-08 (chủ dự án).** Là chủ dự án, tôi muốn biết repo an toàn để công khai.
- *Given* báo cáo quét, *When* xem, *Then* mọi phát hiện được liệt kê với đường dẫn/commit nhưng **không** in giá trị bí mật; nếu có phát hiện thì được ghi rõ "cần thu hồi khóa".

## 7. Sửa đổi `CLAUDE.md` đề xuất (cần chủ dự án duyệt từng mục; Claude Code chỉ đưa bản diff)

| # | Nội dung đề xuất | Lý do |
|---|---|---|
| A1 | Làm rõ quy tắc "không di chuyển/xóa file gốc": **chép** file lên thiết bị theo lệnh người dùng là được phép; ghi lên thiết bị chỉ sau xác nhận; không xóa/ghi đè trên thiết bị trừ file dở của chính ta | Tính năng gửi thiết bị |
| A2 | Thêm quy tắc: không hỗ trợ DRM; không gọi công cụ gỡ DRM; không ghi đè file gốc khi chuyển đổi | Pháp lý (D8) |
| A3 | Mở rộng quy tắc nguồn dữ liệu: mọi nguồn phải có dòng trong `docs/legal/DATA_SOURCES.md` (điều khoản, khóa, giới hạn) | Rủi ro điều khoản |
| A4 | Test cần thiết bị thật phải bỏ qua được, không bao giờ bắt buộc trong CI | NFR-06 |
| A5 | Mô tả khung migration `user_version` là phần bổ sung; `_migrate_add_missing_columns` giữ nguyên quy tắc chỉ append | FR-OPS-02 |
| A6 | Chính sách SPDX cho tệp mới (chờ O4) | Giấy phép |

## 8. Rủi ro chính

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| MTP trên Windows khó/không ổn định | Cao | Spike S3a trước; ổ đĩa/thẻ nhớ làm trước; MTP là S3c có điều kiện |
| `mobi` hoặc phụ thuộc khác không tương thích AGPL-3.0 | Cao | S0-01 kiểm kê; nếu không tương thích thì thay thế hoặc bỏ tính năng, chờ chủ dự án |
| Bí mật hoặc dữ liệu cá nhân trong lịch sử git | Cao | S0-02; chủ dự án thu hồi khóa và quyết định xử lý lịch sử |
| Máy chủ review bị lạm dụng hoặc hết hạn mức | Trung bình | S2: giới hạn, kill-switch, suy giảm êm, sổ tay kiểm duyệt |
| Tiki hoặc nguồn khác chặn/không cho phép | Trung bình | Bảng nguồn, công tắc bật/tắt, xác minh điều khoản |
| Một người phát triển quá tải | Trung bình | Chặng nhỏ, tự động hóa, phạm vi cắt giảm qua các điểm mở |
| Chuyển đổi chất lượng kém (đặc biệt PDF) | Trung bình | Cảnh báo, không hàng loạt, bộ mẫu kiểm chuẩn |
