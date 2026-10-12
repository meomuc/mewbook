# 04: Lọc trùng dùng hai lựa chọn, không còn xóa cứng

**What to build:** Công cụ lọc trùng cho cùng hai lựa chọn xóa như phần còn lại của ứng dụng. Gỡ một bản trùng không còn làm mất hashtag, tác giả và thông tin tra cứu của nó.

**Blocked by:** 03 ("Xóa file" là lựa chọn thứ hai, kèm nâng cấp dữ liệu cũ).

**Status:** ready-for-agent

**Category:** bug

- [ ] Công cụ lọc trùng có hai lựa chọn Xóa khỏi thư viện và Xóa file, với cùng ý nghĩa như ở hộp thoại xóa chính.
- [ ] Không còn đường nào xóa cứng bản ghi theo yêu cầu người dùng từ công cụ này.
- [ ] Sách bị gỡ qua lọc trùng nằm trong Thùng rác, giữ nguyên hashtag, tác giả và lịch sử metadata.
- [ ] Sách đã vào Thùng rác không còn bị công cụ lọc trùng đếm là bản trùng.
- [ ] Test hồi quy thất bại trước khi sửa (xóa cứng mất dữ liệu) và đạt sau khi sửa.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
