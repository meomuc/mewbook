# 03: Đăng ký và quản lý Thiết bị

**What to build:** Người dùng đăng ký từng máy đọc với một cái tên riêng, chọn loại máy và thư mục đích. Khi cắm một máy đã đăng ký thì ứng dụng tự nhận ra; máy lạ thì hỏi có phải máy mới không. Demo được với bản truyền tải thư mục/ổ đĩa.

**Blocked by:** 02 (Gom việc gửi sách vào một giao diện truyền tải thiết bị).

**Status:** ready-for-agent

- [ ] Bảng Thiết bị mới được thêm bằng migration có số thứ tự, chỉ chạy sau bước sao lưu thư viện.
- [ ] Đăng ký một Thiết bị với tên, loại máy (hồ sơ thiết bị có sẵn) và thư mục đích; đổi tên; bỏ đăng ký.
- [ ] Có màn hình quản lý Thiết bị hiện danh sách các máy đã đăng ký.
- [ ] Cắm một máy đã đăng ký thì được nhận ra tự động qua danh tính của kết nối.
- [ ] Cắm một máy lạ thì ứng dụng hỏi "Đây có phải máy mới không?" và cho đặt tên; không tự tạo Thiết bị khi chưa hỏi.
- [ ] Test dùng bản giả của giao diện truyền tải; nâng cấp thư viện tạo đúng bảng mới.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
