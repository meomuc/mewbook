# 06: Kiểm tra sách còn trên máy

**What to build:** Người dùng biết sách đã gửi còn trên máy hay không: ứng dụng tự kiểm tra khi cắm máy đã đăng ký, và có nút "Kiểm tra máy" để kiểm tra lại. Sách không còn trên máy chỉ được đánh dấu trên Thiết bị đó, Thư viện không bị đổi.

**Blocked by:** 04 (Ghi lại sách đã gửi và hiện trong panel chi tiết).

**Status:** ready-for-agent

**Category:** enhancement

- [ ] Việc kiểm tra so tên và kích thước đã ghi lúc gửi với danh sách file hiện có trên máy.
- [ ] Kết quả gồm ba trạng thái: còn trên máy, không còn trên máy, chưa kiểm tra; kèm thời điểm kiểm tra gần nhất.
- [ ] File đổi tên trên máy được coi là "không còn trên máy".
- [ ] Sách không còn trên máy không làm đổi trạng thái của Sách trong Thư viện (có test).
- [ ] Việc kiểm tra chỉ chạy khi máy đang cắm và khi người dùng yêu cầu, không quét liên tục; chạy ở luồng nền.
- [ ] Panel chi tiết hiện trạng thái và thời điểm kiểm tra của từng Thiết bị.
- [ ] Ứng dụng không bao giờ xóa hay sửa file nào trên máy trong quá trình kiểm tra.
- [ ] Chuỗi giao diện tiếng Việt và tiếng Anh, một mục trong `CHANGELOG.md`.
