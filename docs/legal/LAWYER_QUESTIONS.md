# Câu hỏi gửi luật sư (chuẩn bị cho S0-12)

Danh sách này gộp 9 câu chuẩn ở `docs/handoff/05_LEGAL_OPEN_SOURCE_CHECKLIST.md` mục 3 với các câu phát sinh từ kiểm kê (`LICENSE_INVENTORY.md`) và ghi chú của chủ dự án. Đây là bản chuẩn bị, **không phải kết luận pháp lý**.

## A. Phát sinh từ kiểm kê phụ thuộc

1. **QtPdf / QtPdfWidgets có thuộc LGPL không?** Ứng dụng dùng `PySide6.QtPdf` và `QtPdfWidgets` (trình đọc PDF). Metadata gói PySide6 khai `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` cho cả bộ, nhưng chưa đối chiếu với trang giấy phép chính thức của Qt cho riêng module này (và các thành phần bên thứ ba bên trong như PDFium). Nếu QtPdf chỉ có GPL/thương mại thì ảnh hưởng thế nào tới phân phối?
2. **`pyvi` (MIT): phần dữ liệu mô hình đi kèm có ràng buộc gì không?** Gói khai MIT, cho phép dùng, sửa và tích hợp, kể cả thương mại, chỉ cần giữ thông báo bản quyền của tác giả trong bản phân phối (đã có trong `THIRD_PARTY_NOTICES.md`). Còn lại một điểm kỹ thuật chưa xác minh: nguồn và giấy phép của **ngữ liệu dùng để huấn luyện mô hình CRF** được đóng gói cùng gói này.
3. **PyMuPDF (AGPL-3.0) và tính lây của AGPL.** Nhúng PyMuPDF rồi phân phối ra cộng đồng buộc toàn bộ ứng dụng phát hành mã nguồn dưới AGPL-3.0; đóng mã nguồn `.exe` mà vẫn dùng PyMuPDF (không mua giấy phép thương mại của Artifex) là vi phạm giấy phép. Hướng D1 (mở toàn bộ mã nguồn theo AGPL-3.0) đã đáp ứng điều này. Câu hỏi: (a) xác nhận nghĩa vụ cụ thể của bản phát hành (mã nguồn tương ứng, thông báo, cách trao mã cho người nhận bản `.exe`), (b) metadata của PyMuPDF chỉ ghi "GNU AFFERO GPL 3.0", chưa nói "only" hay "or later": ảnh hưởng gì tới lựa chọn `AGPL-3.0-only` hay `-or-later` (O4)?
4. **Kết hợp GPL-3.0-only (`mobi`) với AGPL-3.0.** Theo văn bản, điều 13 của cả hai cho phép kết hợp. Luật sư xác nhận, và cho ý kiến về nội dung thông báo cần đặt trong ứng dụng.
5. **PyInstaller bootloader:** xác nhận ngoại lệ của bootloader áp dụng cho bản phát hành (giấy phép GPL-2.0-or-later kèm ngoại lệ).

## B. Phát sinh từ kiểm tra mã

6. **Thông báo bản quyền hiện tại** (`APP_COPYRIGHT = "© 2026 Anhtiensinh. Bảo lưu mọi quyền."`) mâu thuẫn với AGPL: cách viết đúng để giữ quyền tác giả mà không tuyên bố "bảo lưu mọi quyền".
7. **Mã QR ngân hàng cá nhân trong kho mã công khai:** mã ủng hộ hiển thị tên và số tài khoản cá nhân của chủ dự án và nằm trong lịch sử git công khai. Có rủi ro pháp lý hay riêng tư nào cần cân nhắc (ví dụ lộ thông tin cá nhân, nghĩa vụ thuế với tiền ủng hộ)?
8. **Văn bản EULA/Quyền riêng tư hiện có** thiếu mô tả về định danh ẩn danh (băm token) và nickname gửi lên máy chủ đánh giá. Nội dung tối thiểu của thông báo riêng tư cần gì?
9. **Lịch sử git:** công việc 1.0.0 vừa được commit (commit `ad06b01`) và có `library`-derived model phân loại. Nếu chủ dự án muốn công khai, nên viết lại lịch sử hay tạo kho mới sạch? (Chủ dự án quyết định; Claude Code không tự làm.)
10. **Nguồn gốc ảnh linh vật và logo** (nghi do công cụ tạo ảnh AI tạo ra): điều khoản công cụ, khả năng bảo hộ bản quyền, và có nên đăng ký nhãn hiệu (O11, O12).

## C. 9 câu chuẩn từ checklist (`05` mục 3)

1. Mã MewBook dưới AGPL-3.0 có tương thích với toàn bộ phụ thuộc trong `LICENSE_INVENTORY.md` không?
2. Gọi `ebook-convert` (GPL) như tiến trình riêng: có nghĩa vụ nào khác không?
3. Nên đăng ký nhãn hiệu "MewBook/Mèo Mực" không? Thủ tục ở Việt Nam?
4. Đối tác tặng kèm bộ cài trên thiết bị hoặc liên kết tải: nghĩa vụ cung cấp mã nguồn của họ?
5. Điều khoản sử dụng và chính sách riêng tư cho dịch vụ review ẩn danh: nội dung tối thiểu, quyền người dùng, trách nhiệm với nội dung người dùng tạo.
6. Nghĩa vụ bảo vệ dữ liệu cá nhân (băm danh tính, nickname, IP ở máy chủ) và yêu cầu đăng ký/thông báo.
7. Nếu bí mật/dữ liệu cá nhân nằm trong lịch sử git: rủi ro và cách xử lý.
8. Rủi ro dùng dữ liệu từ Tiki, Apple Books, Google Books trong ứng dụng miễn phí phân phối rộng.
9. CLA hay DCO khi nhận đóng góp cộng đồng mà chủ dự án muốn giữ quyền quản trị giấy phép.

## D. Từ kiểm toán mô hình phân loại (S0-04)

11. **Nguồn gốc kho huấn luyện của mô hình đi kèm.** Mô hình chỉ chứa thống kê từ (không có văn bản sách) nhưng được huấn luyện từ thư viện cá nhân của chủ dự án, và từ vựng có dấu vết chân trang/nguồn phát hành của các trang ebook (xem `MODEL_VOCAB_AUDIT.md` mục 2.3), tức một phần sách huấn luyện có thể đến từ nguồn không rõ giấy phép. Việc phân phối một mô hình học từ đó có rủi ro bản quyền không? Có nên chuyển sang mô hình huấn luyện từ bộ mẫu công khai/phạm vi công cộng trước khi phát hành?

## E. Từ chính sách DRM (S0-09)

12. **Chính sách "không hỗ trợ DRM" và rủi ro pháp lý khi công khai.** `DRM_POLICY.md` chỉ cho phép *phát hiện để từ chối*, không gỡ hay vượt DRM, và không nhúng, đóng gói hay liên kết tới công cụ gỡ DRM. Câu hỏi: (a) chính sách này có đủ để tránh trách nhiệm theo luật Việt Nam và theo các quy định chống vượt biện pháp bảo vệ kỹ thuật (ví dụ DMCA §1201 khi kho mã nằm trên nền tảng của Mỹ) không; (b) việc gọi `ebook-convert` của Calibre như tiến trình riêng, không cài plugin nào, có thể bị coi là hỗ trợ vượt DRM khi người dùng tự cài plugin bên ngoài không; (c) chép nguyên trạng một file có DRM lên thiết bị của chính người dùng có vấn đề gì không.
