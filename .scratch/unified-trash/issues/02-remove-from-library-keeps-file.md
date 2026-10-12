# 02: "Xóa khỏi thư viện" giữ nguyên file, sách vào Thùng rác

**What to build:** Khi người dùng chọn Xóa khỏi thư viện, sách biến mất khỏi Thư viện và xuất hiện trong chế độ xem Thùng rác với loại xóa "Xóa khỏi thư viện", còn file vật lý đứng nguyên chỗ cũ. Demo được: xóa một sách, file vẫn ở thư mục gốc, sách thấy trong Thùng rác.

**Blocked by:** 01 (Gom mọi đường xóa về một cửa vào).

**Status:** ready-for-agent

- [ ] Xóa khỏi thư viện không di chuyển, đổi tên hay xóa file trên đĩa (có test kiểm tra file còn nguyên chỗ cũ).
- [ ] Sách đã xóa không xuất hiện trong danh sách chính, tìm kiếm, số đếm bộ lọc và các công cụ hàng loạt.
- [ ] Sách hiện trong chế độ xem Thùng rác với cột Tình trạng xóa là "Xóa khỏi thư viện" và vị trí gốc của file.
- [ ] Đường dẫn của file vào danh sách loại trừ nhập lại, và bộ theo dõi thư mục không nhập lại file đó.
- [ ] Loại xóa được lưu bằng một cột mới chỉ thêm (không đổi hay xóa cột cũ); thư viện cũ nâng cấp tại chỗ.
- [ ] Test hồi quy thất bại trước khi sửa (nút cũ chuyển file đi) và đạt sau khi sửa.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
