# 02: Gom việc gửi sách vào một giao diện truyền tải thiết bị

**What to build:** Việc gửi sách sang máy đọc đi qua một giao diện truyền tải với đúng ba khả năng: liệt kê thiết bị đang kết nối, liệt kê file trong một thư mục trên máy, và chép một file lên máy. Cách gửi hiện tại (thư mục hoặc ổ đĩa) trở thành một bản cài đặt của giao diện đó, và có thêm một bản giả trong bộ nhớ cho test. Người dùng không thấy khác biệt.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Category:** enhancement

- [ ] Giao diện không có thao tác xóa hay ghi nào ngoài chép file sách lên máy.
- [ ] Hộp thoại gửi hiện tại đi qua giao diện này, hành vi giữ nguyên: không ghi đè file đã có, từ chối sách có DRM, dừng sạch khi rút máy giữa chừng.
- [ ] Có bản giả trong bộ nhớ dùng được trong test, và các test gửi hiện có chạy được trên cả hai bản.
- [ ] Toàn bộ test hiện có vẫn xanh.
