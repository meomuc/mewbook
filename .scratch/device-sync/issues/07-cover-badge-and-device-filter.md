# 07: Biểu tượng trên bìa và bộ lọc theo máy

**What to build:** Người dùng nhìn danh sách sách là biết cuốn nào đang nằm trên máy đọc, và lọc được các sách đã gửi sang một máy cụ thể.

**Blocked by:** 06 (Kiểm tra sách còn trên máy).

**Status:** ready-for-agent

- [ ] Bìa sách có một biểu tượng nhỏ kèm số máy mà sách đang còn nằm trên; không có biểu tượng khi sách chưa nằm trên máy nào.
- [ ] Biểu tượng không che bìa sách khi có nhiều máy (chỉ một biểu tượng kèm số).
- [ ] Số máy chỉ tính các máy mà trạng thái là còn trên máy.
- [ ] Có bộ lọc "đã gửi sang máy X" cho từng Thiết bị đã đăng ký.
- [ ] Số đếm bộ lọc đúng và cập nhật khi đăng ký, bỏ đăng ký hay kiểm tra lại máy.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
