# 05: Gửi sách sang Boox Note Air4 qua MTP

**What to build:** Người dùng gửi sách từ Thư viện sang Boox Note Air4 cắm bằng cáp dù máy không có ký tự ổ đĩa: máy được nhận ra qua danh tính MTP, đăng ký như mọi Thiết bị, và việc gửi được ghi lại. Demo được trên máy Boox thật.

**Blocked by:** 01 (Khảo sát Boox Note Air4 qua MTP trên máy thật), 04 (Ghi lại sách đã gửi và hiện trong panel chi tiết).

**Status:** ready-for-agent

- [ ] Có bản MTP cho Windows của giao diện truyền tải, dùng thư viện `comtypes` (giấy phép MIT, tương thích AGPL-3.0), chỉ được import bên trong mô-đun này.
- [ ] Giấy phép của thư viện được ghi vào danh mục giấy phép và `THIRD_PARTY_NOTICES.md` trước khi thêm phụ thuộc.
- [ ] Mọi truy cập MTP chạy ở luồng nền, mỗi luồng tự khởi tạo COM; giao diện không bị đơ khi máy chậm.
- [ ] Máy Boox được nhận ra bằng danh tính MTP do khảo sát (ticket 01) xác nhận, và đăng ký như mọi Thiết bị.
- [ ] Gửi sang Boox không ghi đè file đã có, từ chối sách có DRM, và rút máy giữa chừng không làm ứng dụng sập.
- [ ] Hồ sơ máy chỉ chuyển sang đã kiểm chứng sau khi chạy được trên máy thật.
- [ ] Test phần cứng đánh dấu bỏ qua khi không có thiết bị, và không bao giờ bắt buộc trong CI.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`, một ADR cho việc thêm phụ thuộc MTP.
