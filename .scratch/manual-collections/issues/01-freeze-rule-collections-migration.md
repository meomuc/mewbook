# 01: Chốt bộ sưu tập quy tắc cũ thành danh sách thành viên

**What to build:** Khi nâng cấp, mỗi Bộ sưu tập kiểu quy tắc được chốt thành một danh sách thành viên cụ thể, để người dùng giữ nguyên nội dung đang thấy. Từ đây truy vấn bộ sưu tập chỉ dựa vào thành viên.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Category:** enhancement

- [ ] Migration có số thứ tự, chỉ chạy sau bước sao lưu thư viện (không sao lưu thì không chạy).
- [ ] Mỗi bộ sưu tập quy tắc có thành viên bằng đúng kết quả quy tắc tại thời điểm nâng cấp, hợp với thành viên thêm tay có sẵn.
- [ ] Chạy lại migration không thêm thành viên trùng.
- [ ] Bộ sưu tập thủ công và "Sẽ đọc" không bị đổi.
- [ ] Cột lưu quy tắc không bị xóa hay đổi; truy vấn bộ sưu tập không còn đánh giá quy tắc lúc truy vấn.
- [ ] Test nâng cấp từ một thư viện mẫu cũ có cả bộ sưu tập quy tắc và thủ công.
- [ ] Một mục trong `CHANGELOG.md` nói rõ bộ sưu tập quy tắc cũ không còn tự cập nhật.
