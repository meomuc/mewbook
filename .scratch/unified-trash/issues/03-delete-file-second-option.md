# 03: "Xóa file" là lựa chọn thứ hai, kèm nâng cấp dữ liệu cũ

**What to build:** Hộp thoại xóa (một sách và nhiều sách) có hai lựa chọn rõ ràng: Xóa khỏi thư viện và Xóa file. Xóa file chuyển file vật lý sang Thư mục thùng rác và đưa sách vào Thùng rác với loại "Xóa file và thư viện". Các sách đã nằm trong thùng rác theo cách cũ trở thành loại này sau khi nâng cấp.

**Blocked by:** 02 ("Xóa khỏi thư viện" giữ nguyên file, sách vào Thùng rác).

**Status:** ready-for-agent

- [ ] Hộp thoại xóa một sách và nhiều sách đều hiện hai lựa chọn với mô tả đúng hành vi.
- [ ] Xóa file chuyển file vào Thư mục thùng rác và không bao giờ ghi đè một file đã có ở đó.
- [ ] Nếu việc chuyển file thất bại, sách ở lại Thư viện nguyên vẹn và người dùng được báo lý do.
- [ ] Mục trong Thùng rác có loại "Xóa file và thư viện" và đường dẫn trỏ vào Thư mục thùng rác.
- [ ] Các sách đã vào thùng rác theo cách cũ vẫn thấy và được coi là loại "Xóa file và thư viện" sau khi nâng cấp (test nâng cấp từ thư viện mẫu cũ).
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
