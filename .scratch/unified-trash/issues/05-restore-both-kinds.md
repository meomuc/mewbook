# 05: Khôi phục cả hai loại

**What to build:** Người dùng khôi phục một mục từ Thùng rác và sách hiện lại trong Thư viện đúng như trước khi xóa. Với Xóa file, file cũng về đúng chỗ cũ.

**Blocked by:** 03 ("Xóa file" là lựa chọn thứ hai, kèm nâng cấp dữ liệu cũ).

**Status:** ready-for-agent

- [ ] Khôi phục mục "Xóa khỏi thư viện": sách hiện lại ngay với đủ hashtag, tác giả, bộ sưu tập và thông tin cũ.
- [ ] Khôi phục mục "Xóa file": file về đường dẫn cũ rồi sách hiện lại.
- [ ] Việc khôi phục không bao giờ ghi đè một file khác đang nằm ở đường dẫn cũ; người dùng được báo rõ.
- [ ] Nếu thư mục gốc không còn tồn tại, thư mục được tạo lại rồi khôi phục; nếu không được thì báo lỗi và mục vẫn nằm trong Thùng rác.
- [ ] Đường dẫn của sách được gỡ khỏi danh sách loại trừ nhập lại khi khôi phục.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
