# 03 — Đặc tả UI/UX

## 1. Nguyên tắc chung

- Chuỗi giao diện bằng **tiếng Việt** (bình luận trong mã bằng tiếng Anh). Sang S4 các chuỗi mới đi qua cơ chế dịch; từ S3 trở đi nên gom chuỗi dễ trích xuất.
- **Không rẽ nhánh theo khóa theme.** Màu, bo góc, font, phong cách lấy từ `ThemeColors` (thêm tùy chọn khi cần); mọi theme phải qua `test_theme_contract.py` (kể cả tương phản WCAG). Widget mới đặt `color` cùng với `background` trong stylesheet.
- **Không chặn giao diện:** thao tác thiết bị/chuyển đổi/mạng chạy nền; luôn có trạng thái đang xử lý, nút Hủy, và trạng thái lỗi rõ.
- **Xem trước rồi mới làm** cho mọi thao tác ghi ra ngoài thư viện (gửi thiết bị, chuyển đổi, áp dụng chuẩn hóa).
- Không dùng ngôn ngữ kỹ thuật (MTP, VID/PID) trong thông báo cho người dùng; chi tiết kỹ thuật chỉ có ở nhật ký và nút "Sao chép thông tin hỗ trợ".
- Kiểm tra hiển thị thật bằng nền tảng thật (bỏ `QT_QPA_PLATFORM=offscreen`) khi làm giao diện.

## 2. Điểm vào

| Điểm vào | Hành động |
|---|---|
| Thanh bên → mục **Thiết bị** | Danh sách thiết bị đang kết nối; nhấn hàng thiết bị → mở hộp thoại gửi cho thiết bị đó |
| Chuột phải tài liệu (một hoặc nhiều) | **Gửi tới thiết bị ▸** (danh sách thiết bị; nếu chưa có thì mục bị làm mờ kèm gợi ý) |
| Chuột phải một bộ sưu tập | **Gửi bộ sưu tập tới thiết bị…** |
| Menu **Công cụ** | Gửi tới thiết bị…, Chuyển đổi định dạng…, Tìm lại file thiếu…, Sao lưu thư viện… |
| Trong hộp thoại review | Nút **⚑ Báo cáo** trên review của người khác |
| **Cài đặt** | Thêm các thẻ: Thiết bị, Chuyển đổi, Nguồn dữ liệu, Sao lưu (và Cập nhật nếu O8 được duyệt) |

## 3. Thanh bên: mục Thiết bị

- Mỗi thiết bị một hàng: biểu tượng, tên (ví dụ "BOOX Go 6"), kiểu kết nối (Thẻ nhớ / Cáp USB), dung lượng trống.
- **Trạng thái rỗng:** "Chưa thấy thiết bị nào. Cắm cáp USB (chế độ truyền file) hoặc cắm thẻ nhớ vào máy tính."
- Thiết bị lạ chưa có hồ sơ: hàng hiển thị "Thiết bị chưa nhận diện" và nhấn vào sẽ mở bước chọn hồ sơ (danh sách hồ sơ + "Ổ đĩa/thẻ nhớ chung").
- Hàng cập nhật khi cắm/rút; mục biến mất mềm, không nhảy vị trí cuộn của cây thanh bên (giữ nguyên hành vi hiện có của cây facet).

## 4. Hộp thoại "Gửi tới thiết bị"

**Bố cục:**
1. Đầu: tên thiết bị, kiểu kết nối, dung lượng trống, **thư mục đích** (chọn được, nhớ theo thiết bị).
2. Thân: bảng kế hoạch — cột: ☑ | Tựa sách | Tác giả | Định dạng | Kích thước | Trạng thái. Có bộ lọc theo trạng thái.
3. Tùy chọn: "Bỏ dấu tiếng Việt trong tên file" (mặc định theo hồ sơ), "Khi trùng tên: bỏ qua / thêm hậu tố".
4. Dòng tóm tắt: "Sẽ chép N sách (X MB). Còn trống Y MB."
5. Chân: **[Bắt đầu]**, **[Hủy]**, và (khi có sách không tương thích và S4 đã có) **[Chuyển đổi các sách không tương thích…]**.

**Trạng thái của mỗi dòng (chip màu, kèm chữ, không chỉ dựa vào màu):**

| Trạng thái | Chữ hiển thị | Ghi chú |
|---|---|---|
| will_copy | Sẽ chép | Mặc định được chọn |
| already_on_device | Đã có trên thiết bị | Mặc định bỏ chọn |
| incompatible_format | Định dạng không tương thích | Kèm gợi ý chuyển đổi khi có |
| name_conflict | Trùng tên | Theo tùy chọn |
| insufficient_space | Không đủ chỗ | Bị khóa chọn; tóm tắt cảnh báo |

**Máy trạng thái của hộp thoại:** `Idle` → `Planning` → `PlanReady` → `Transferring` → (`Cancelling`) → `Done` | `Failed` | `DeviceLost`.
- `Planning`: thanh tiến độ không xác định, giao diện vẫn tương tác được để hủy.
- `Transferring`: thanh tiến độ tổng (số sách, dung lượng), tên file hiện tại, tốc độ, **[Hủy]** ("Hủy sẽ dừng sau file đang chép; không để lại file dở"). Cập nhật tiến độ gộp, không làm chậm giao diện.
- `DeviceLost`: "Thiết bị đã bị ngắt kết nối. Đã chép N sách, chưa chép M sách." + [Xem chi tiết] [Đóng]. Không hộp thoại lỗi chồng chéo.
- `Done`: tóm tắt "Đã chép N sách, bỏ qua M, lỗi K" + danh sách lỗi (nếu có) + [Sao chép nhật ký] [Đóng].

## 5. Hộp thoại "Chuyển đổi định dạng" (S4)

- Danh sách sách nguồn (định dạng hiện tại), chọn **định dạng đích** (chỉ liệt kê những đích hợp lệ cho nguồn).
- Thư mục đầu ra (nhớ lần trước). Ô chọn "Thêm bản chuyển đổi vào thư viện" (mặc định **tắt**).
- Cảnh báo theo ngữ cảnh: PDF → EPUB: "Chất lượng có thể thấp với sách quét hoặc bố cục phức tạp."
- **Chưa cài Calibre:** khối hướng dẫn + nút "Mở Cài đặt". Không hiện lỗi kỹ thuật.
- **File có DRM:** dòng bị từ chối "Sách này có bảo vệ bản quyền (DRM) nên không thể chuyển đổi."
- Tiến độ theo từng sách, hủy được, tổng kết cuối.

## 6. Review: báo cáo và công tắc từ xa (S2)

- Mỗi review của người khác có **⚑ Báo cáo**; nhấn → chọn lý do (Spam / Xúc phạm / Sai nội dung / Khác) → xác nhận → thông báo "Cảm ơn bạn. Chúng tôi sẽ xem xét."
- Không hiện nút báo cáo trên review của chính mình (đã đánh dấu "Bạn").
- Nếu cờ `reviews_enabled` tắt: dải thông báo "Tính năng đánh giá đang tạm dừng." + nội dung `banner_message` nếu có; nút gửi bị vô hiệu.
- Máy chủ không truy cập được: "Dịch vụ đánh giá tạm thời không khả dụng. Các tính năng khác vẫn hoạt động bình thường."
- Mã lỗi từ máy chủ (vượt hạn mức, bị chặn, quá dài) → thông báo tiếng Việt tương ứng, không lộ chi tiết kỹ thuật.
- Đường dẫn tới Điều khoản và Chính sách riêng tư ở chân hộp thoại review.

## 7. Tìm lại file (S1)

- Sidebar hoặc thanh trạng thái hiện chỉ báo "N sách không tìm thấy file" khi có `LibraryFilesMissingEvent`.
- Hộp thoại: chọn thư mục gốc mới → ứng dụng lập bảng đề xuất (khớp theo băm nội dung, rồi theo tên + kích thước) → người dùng xem, bỏ chọn, xác nhận → cập nhật đường dẫn trong DB. Không có gì thay đổi trước bước xác nhận.

## 8. Cài đặt (thẻ mới)

| Thẻ | Nội dung |
|---|---|
| Thiết bị | Bật/tắt tự phát hiện thiết bị; mở thư mục hồ sơ người dùng; mặc định quy tắc tên file |
| Chuyển đổi | Đường dẫn Calibre (Kiểm tra), thư mục đầu ra, thêm vào thư viện |
| Nguồn dữ liệu | Danh sách nguồn ảnh bìa với công tắc bật/tắt và liên kết điều khoản |
| Sao lưu | Sao lưu ngay, Khôi phục, số bản giữ lại |
| Giới thiệu (hộp thoại) | Giấy phép AGPL-3.0, liên kết mã nguồn đúng phiên bản, thông báo bên thứ ba, ghi chú thương hiệu |

## 9. Chuỗi tiếng Việt chính (bản gốc để Claude Code dùng và tinh chỉnh)

| Ngữ cảnh | Chuỗi |
|---|---|
| Menu | "Gửi tới thiết bị", "Chuyển đổi định dạng…", "Tìm lại file thiếu…", "Sao lưu thư viện…" |
| Thiết bị rỗng | "Chưa thấy thiết bị nào. Cắm cáp USB (chế độ truyền file) hoặc cắm thẻ nhớ vào máy tính." |
| Kế hoạch | "Sẽ chép {n} sách ({size}). Còn trống {free}." |
| Đã có | "Đã có trên thiết bị" |
| Không tương thích | "Định dạng không tương thích" |
| Hủy | "Hủy sẽ dừng sau file đang chép." |
| Mất thiết bị | "Thiết bị đã bị ngắt kết nối. Đã chép {done} sách, chưa chép {left} sách." |
| DRM | "Sách này có bảo vệ bản quyền (DRM) nên không thể chuyển đổi." |
| Chưa cài Calibre | "Cần cài Calibre để chuyển đổi định dạng. Sau khi cài, chọn đường dẫn trong Cài đặt." |
| Báo cáo | "Cảm ơn bạn. Chúng tôi sẽ xem xét đánh giá này." |
| Review tạm dừng | "Tính năng đánh giá đang tạm dừng." |
| Review không truy cập được | "Dịch vụ đánh giá tạm thời không khả dụng. Các tính năng khác vẫn hoạt động bình thường." |
| Backup | "Đã sao lưu thư viện trước khi nâng cấp." |
| Relink | "{n} sách không tìm thấy file. Tìm lại?" |

## 10. Khả năng tiếp cận và bàn phím

- Mọi chức năng dùng được bằng bàn phím (Tab/Enter/Esc); focus rõ.
- Trạng thái không chỉ dựa vào màu; có chữ hoặc biểu tượng.
- Kích thước font theo cài đặt hiện có; không cố định pixel cho văn bản.
