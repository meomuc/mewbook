# MewBook roadmap (public)

The landing page's "Sắp tới Mèo sẽ làm" list is generated from this file by
`website/scripts/update-content.js` on every release build. One item per line:

    - [status] Title | short description | when

`status` is `next` (in development, expected in the next release: shown in its own "Đang phát triển" card),
`planned`, `doing` or `done` (a `done` item is not shown). Text is Vietnamese because the page is.
Keep it honest: no dates unless the work is really scheduled (`when` may be a phase such as "Kế hoạch").

- [planned] Đồng bộ với máy đọc sách: nhớ sách đã chép | Mèo nhớ cuốn nào đã chép sang máy đọc sách nào; hiện biểu tượng máy đọc sách trên bìa, cạnh đánh giá cộng đồng | Kế hoạch
- [planned] Lọc sách đã / chưa chép sang máy đọc sách | Thêm vào bộ lọc "Tình trạng" để thấy ngay sách nào còn chưa mang theo | Kế hoạch
- [planned] Xem sách đang có trên máy đọc sách | Cắm máy, Mèo đọc danh sách file (chỉ đọc, không kéo nội dung về) và đối chiếu với thư viện; sách đã có trên máy tính được đánh dấu biểu tượng máy tính | Kế hoạch
- [planned] Gửi sách tới Kindle | Kiểm chứng trên máy Kindle thật (EPUB, thư mục documents), sau đó cân nhắc gửi không dây qua email Kindle và máy ở chế độ MTP | Kế hoạch
- [done] Sửa mã hóa cũ trong tên sách | Nhận diện và sửa tên sách gõ theo bảng mã cũ (TCVN3/VNI) thành Unicode chuẩn | Kế hoạch
- [done] Giao diện tiếng Anh | Chuyển ngôn ngữ ngay trong Cài đặt | Kế hoạch
- [done] Đồng bộ metadata cộng đồng: thứ tự ưu tiên nguồn | Máy cục bộ trước, rồi đến Cộng đồng MewBook, rồi mới đến nguồn khác trên Internet; xung đột giữa các nguồn luôn cho bạn xem trước và tự chọn nhận hay bỏ | Kế hoạch
- [done] Đồng bộ metadata cộng đồng: minh bạch & trạng thái | Trước khi bật, nói rõ chỉ chia sẻ metadata (không phải file sách) và có thể tắt bất cứ lúc nào; thanh trạng thái có icon riêng báo đang/đã đồng bộ | Kế hoạch
- [done] Lưu trang web thành PDF | Dán link, Mèo lọc bỏ menu/quảng cáo rồi lưu bài viết thành PDF vào thư viện, có nhắc nhở tôn trọng bản quyền trang gốc | Kế hoạch
- [done] Chuyển đổi định dạng tài liệu: hàng loạt | Chọn nhiều sách cùng lúc, đổi định dạng có thanh tiến độ; một file lỗi không làm dừng cả lô | Kế hoạch
- [done] Chuyển đổi định dạng tài liệu: minh bạch chất lượng | Cặp định dạng dễ lệch bố cục (như PDF sang định dạng chỉnh sửa được) sẽ được cảnh báo rõ trước khi đổi | Kế hoạch
