# MewBook 1.3.0 (chưa phát hành -- bản nháp Tuần 3, chờ bạn duyệt)

**Đây là bản nháp ghi chú phát hành, theo đúng mẫu ở `docs/RELEASE_CHECKLIST.md`. Chưa build, chưa tag, chưa đăng
-- không có lệnh nào trong số đó được chạy.** Số phiên bản `1.3.0` là **đề xuất** (MINOR: chỉ thêm tính năng mới,
tương thích ngược, không có gì phá vỡ dữ liệu/cài đặt cũ) — `__version__` trong `src/smartdoc/__init__.py` **chưa
bị sửa**; đổi số thật sự là việc của lúc phát hành, không phải bây giờ.

## Điểm mới

- **Cập nhật thông tin sách hàng loạt** (menu Công cụ) -- tìm và điền tên sách, tác giả, nhà xuất bản... cho cả
  danh sách đang xem, chạy nền không chặn giao diện, không bao giờ ghi đè thông tin bạn đã tự sửa tay.
- **Gửi sang máy đọc sách: thêm hồ sơ thiết bị** (BOOX Note Air4C, BOOX Go 6, Kindle) -- xem trước kế hoạch trước
  khi chép, không bao giờ ghi đè file cùng tên, rút thiết bị giữa chừng không làm lỗi ứng dụng.
  **Phiên bản thử nghiệm ban đầu:** hồ sơ riêng theo từng máy chưa được kiểm chứng trên phần cứng thật (chưa có
  máy BOOX/Kindle thật để đo — xem `docs/spikes/2026-09-28_ereader_device_transport.md`); chỉ hỗ trợ đường ổ
  đĩa/thẻ nhớ, chưa hỗ trợ MTP.
- **Chuyển đổi định dạng sách** (menu File/Công cụ, menu chuột phải) -- đổi định dạng qua Calibre đã cài sẵn trên
  máy (không đi kèm MewBook), có xem trước kế hoạch, không ghi đè/sửa file gốc, chạy nền và hủy được.
  **Phiên bản thử nghiệm ban đầu:** chỉ hỗ trợ một số cặp định dạng phổ biến (EPUB/MOBI/AZW3 qua lại, TXT→EPUB,
  PDF→EPUB/MOBI/AZW3 có cảnh báo lệch bố cục); cần cài Calibre riêng.
- **Tìm file trùng: thêm cột "Loại file"**, cột "Vị trí file" cắt giữa và kéo đổi độ rộng được.
- Hiệu ứng "đang xử lý" dùng chung (vòng tròn xoay) cho các hộp thoại chạy nền lâu.
- Một số hộp thoại (Tìm thêm thông tin, Tạo/Sửa bộ sưu tập, Giới thiệu, Giấy phép & quyền riêng tư) co giãn đúng
  trên màn hình nhỏ thay vì bị cắt.
- Chữ kết quả (đã cập nhật/đã gửi bao nhiêu sách...) giờ to và đậm hơn chữ nhãn tĩnh xung quanh, đọc được cả khi
  không nhìn màu.

## Đã sửa

- Kết quả thử kết nối AI và ảnh bìa Google trong Cài đặt giờ dùng đúng màu theme đang chọn, đọc rõ ở theme tối.
- Giới hạn kích thước chung của hộp thoại đôi khi không có tác dụng trên màn hình nhỏ.

## Chỉ thiết kế, chưa có tính năng (không nằm trong bản này)

Hai tài liệu thiết kế mới, **không có dòng mã hay thay đổi máy chủ nào**, chờ chủ dự án quyết trước khi làm ở
Tuần 4: `docs/design/COMMUNITY_METADATA_SYNC.md` (đồng bộ thông tin sách với cộng đồng MewBook) và
`docs/design/WEB_TO_PDF.md` (chuyển trang web thành PDF để đọc ngoại tuyến).

## Trước khi nâng cấp

- Sao lưu file `library.db` (nằm trong `%APPDATA%/SmartDocLibrary`) -- thói quen chung, bản này không có thay đổi
  schema nào đòi hỏi việc này riêng.
- Chuyển đổi định dạng cần cài Calibre riêng (miễn phí, calibre-ebook.com) nếu muốn dùng; không có Calibre thì
  tính năng còn lại của MewBook không bị ảnh hưởng gì.

## Tải về

*(điền khi thật sự đóng gói -- chưa có file nào ở bước này)*

## Giấy phép

MewBook là phần mềm mã nguồn mở theo AGPL-3.0. Tranh và logo có giấy phép riêng (xem `LICENSE-ART.md`).

## Báo lỗi

- Nơi báo lỗi: menu Công cụ → Trợ giúp → "Báo lỗi…"

---

## Ghi chú cho người duyệt (không phải nội dung công khai)

- Test: `2238 passed` + các test mới của Tuần 3 (đang chờ kết quả lần chạy cuối cùng, xem báo cáo kèm theo).
- 1 test chập chờn tiền tồn tại không liên quan Tuần 3 (`test_metadata_batch_dialog.py::test_running_reports_progress_and_ends_with_the_result_line`,
  đã nêu ở báo cáo C/D trước) -- **chưa sửa**, nằm ngoài phạm vi Tuần 3.
- `ruff check src tests tools`: sạch, không thêm lỗi mới.
- Chưa chạy mục 5-14 của `RELEASE_CHECKLIST.md` (quét bí mật, dựng bản cài, ký mã, tag, đăng...) -- đây chỉ là
  ghi chú phát hành để bạn duyệt nội dung, không phải quy trình phát hành đầy đủ.
- Việc quyết số phiên bản cuối cùng (1.3.0 hay khác) là của bạn.
