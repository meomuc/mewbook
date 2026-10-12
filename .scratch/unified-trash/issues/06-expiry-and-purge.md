# 06: Hết hạn và "Xóa hẳn"

**What to build:** Các mục trong Thùng rác tự hết hạn sau số ngày người dùng đặt, và người dùng có thể dọn ngay bằng "Xóa hẳn". Hết hạn xóa bản ghi và, với Xóa file, cả file; file của mục "Xóa khỏi thư viện" không bao giờ bị đụng tới.

**Blocked by:** 03 ("Xóa file" là lựa chọn thứ hai, kèm nâng cấp dữ liệu cũ).

**Status:** ready-for-agent

- [ ] Một cài đặt số ngày duy nhất áp dụng cho cả hai loại; 0 nghĩa là không bao giờ hết hạn; tối đa 365 ngày.
- [ ] Mục hết hạn bị xóa hẳn bản ghi cùng mọi dữ liệu liên quan, gồm thành viên bộ sưu tập, kết quả phân loại, lịch sử metadata và tiến độ đọc.
- [ ] Mục loại Xóa file hết hạn thì file trong Thư mục thùng rác cũng bị xóa.
- [ ] Mục loại Xóa khỏi thư viện hết hạn thì file gốc vẫn còn nguyên (có test).
- [ ] Đường dẫn của sách hết hạn vẫn nằm trong danh sách loại trừ nhập lại, bộ theo dõi không nhập lại file.
- [ ] Nút "Xóa hẳn" cho từng mục và cho cả Thùng rác, có hộp xác nhận nói rõ file có bị xóa hay không.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
