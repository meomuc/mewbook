# 01: Gom mọi đường xóa về một cửa vào

**What to build:** Mọi đường xóa sách (xóa trực tiếp một sách, xóa nhiều sách, công cụ lọc trùng) đi qua một điểm vào duy nhất để quyết định số phận của file và bản ghi. Người dùng không thấy khác biệt nào. Đây là bước chuẩn bị để các ticket sau đổi hành vi ở đúng một chỗ.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Mỗi đường xóa hiện có có một test hồi quy ghi lại hành vi hiện tại, kể cả việc nút "Xóa khỏi thư viện" đang chuyển file (hành vi tạm, sẽ đổi ở ticket 02).
- [ ] Chỉ còn một nơi quyết định số phận file và bản ghi khi xóa.
- [ ] Toàn bộ test hiện có vẫn xanh, không có thay đổi hành vi nhìn thấy được.
