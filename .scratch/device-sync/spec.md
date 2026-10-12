Status: ready-for-agent

# Spec: Quản lý Thiết bị và theo dõi sách đã gửi sang máy đọc

Thuật ngữ theo `CONTEXT.md`: Thiết bị, Sách, Thư viện. Máy đầu tiên: Boox Note Air4 (kết nối MTP, không có ký tự ổ đĩa).

## Problem Statement

Người dùng gửi sách sang máy đọc nhưng ứng dụng không nhớ gì: không biết cuốn nào đã sang máy nào, còn trên máy hay đã bị xóa. Người dùng có nhiều máy đọc nên cần phân biệt từng máy. Ngoài ra Boox Note Air4 kết nối với Windows theo kiểu MTP (không có ký tự ổ đĩa), còn đường gửi hiện tại chỉ chép file vào một thư mục trên ổ đĩa nên không gửi được sang Boox.

## Solution

Người dùng đăng ký từng **Thiết bị** có tên. Mỗi lần gửi, ứng dụng ghi lại sách nào đã sang Thiết bị nào. Ứng dụng kiểm tra được sách còn trên máy hay không, và hiện trạng thái đó trên bìa sách (một biểu tượng kèm số máy) và trong panel chi tiết (từng máy một). Ứng dụng chỉ **đọc** từ máy và chỉ **chép file sách** lên máy; không sửa hay xóa gì khác trên máy. Boox Note Air4 là thiết bị đầu tiên, các dòng khác thêm sau qua hồ sơ thiết bị.

## User Stories

1. Là người dùng, tôi muốn đăng ký một Thiết bị và đặt tên cho nó (ví dụ "Boox của tôi"), để phân biệt các máy.
2. Là người dùng, tôi muốn chọn loại máy từ danh sách hồ sơ thiết bị có sẵn khi đăng ký.
3. Là người dùng, tôi muốn đặt thư mục đích trên mỗi Thiết bị, để sách vào đúng chỗ.
4. Là người dùng, tôi muốn khi cắm một máy đã đăng ký, ứng dụng tự nhận ra máy đó, để không phải chọn lại mỗi lần.
5. Là người dùng, tôi muốn khi cắm một máy lạ, ứng dụng hỏi "Đây có phải máy mới không?" và cho tôi đặt tên, để không có máy trùng lặp.
6. Là người dùng, tôi muốn có màn hình quản lý Thiết bị: danh sách, đổi tên, bỏ đăng ký.
7. Là người dùng, tôi muốn gửi sách sang Boox Note Air4 cắm qua cáp mặc dù máy không có ký tự ổ đĩa.
8. Là người dùng, tôi muốn gửi vẫn không ghi đè một file đã có trên máy.
9. Là người dùng, tôi muốn sách có DRM vẫn bị từ chối khi gửi, như hiện nay.
10. Là người dùng, tôi muốn ứng dụng ghi lại mỗi sách đã gửi sang máy nào, vào lúc nào.
11. Là người dùng, tôi muốn kiểm tra xem các sách đã gửi còn trên máy không, bằng cách bấm "Kiểm tra máy" khi máy đang cắm.
12. Là người dùng, tôi muốn ứng dụng tự kiểm tra khi tôi cắm máy đã đăng ký.
13. Là người dùng, tôi muốn sách không còn trên máy chỉ được đánh dấu "không còn trên máy" trên Thiết bị đó, mà sách trong Thư viện không bị đổi.
14. Là người dùng, tôi muốn trên bìa sách có một biểu tượng nhỏ khi sách đang nằm trên ít nhất một máy, kèm số máy.
15. Là người dùng, tôi muốn trong panel chi tiết thấy từng Thiết bị, trạng thái (còn trên máy / không còn trên máy / chưa kiểm tra) và lần kiểm tra gần nhất.
16. Là người dùng, tôi muốn lọc thư viện theo "đã gửi sang máy X".
17. Là người dùng, tôi muốn gửi sách sang nhiều máy khác nhau, mỗi máy có lịch sử gửi riêng.
18. Là người dùng, tôi muốn bỏ đăng ký một Thiết bị mà không ảnh hưởng đến sách trong Thư viện.
19. Là người dùng, tôi muốn việc gửi và kiểm tra chạy nền, để ứng dụng không bị đơ khi máy chậm.
20. Là người dùng, tôi muốn rút máy giữa chừng không làm ứng dụng sập, chỉ báo dừng sạch như hiện nay.
21. Là người dùng, tôi muốn biết trạng thái của hồ sơ máy là chưa kiểm chứng, để hiểu vì sao có thể có lỗi.
22. Là người dùng, tôi muốn ứng dụng không bao giờ xóa hay sửa file nào trên máy của tôi.

## Implementation Decisions

- Thêm khái niệm **Thiết bị** được lưu bền: tên do người dùng đặt, loại máy (hồ sơ thiết bị), danh tính ổn định lấy từ kết nối (với MTP là danh tính thiết bị do Windows cung cấp, chẳng hạn tên và số serial, cần kiểm chứng trên máy thật; với máy dạng ổ đĩa là nhãn ổ hoặc serial ổ), và thư mục đích.
- Thêm bản ghi **đã gửi** theo cặp (Sách, Thiết bị): thời điểm gửi, tên và kích thước file đã chép, đường dẫn trên máy, trạng thái hiện diện (còn / không còn / chưa kiểm tra) và thời điểm kiểm tra gần nhất.
- Các bảng mới được thêm bằng **migration có số thứ tự**, chạy sau bước sao lưu thư viện.
- **Seam mới**: một giao diện truyền tải thiết bị gồm ba khả năng và chỉ ba: liệt kê thiết bị đang kết nối kèm danh tính; liệt kê file trong một thư mục trên máy (tên, kích thước, ngày sửa); chép một file lên máy. Không có thao tác xóa hay ghi khác. Có hai bản cài đặt: kiểu thư mục/ổ đĩa (đã có) và kiểu **MTP cho Windows** (mới), cùng một bản giả trong bộ nhớ dùng cho test.
- MTP dùng thư viện `comtypes` (giấy phép MIT, tương thích AGPL-3.0). Trước khi thêm phải ghi dòng giấy phép vào danh mục giấy phép và `THIRD_PARTY_NOTICES.md` theo quy định của dự án. Thư viện chỉ được import bên trong mô-đun truyền tải MTP. Mọi truy cập MTP chạy ở luồng nền và khởi tạo COM riêng cho từng luồng.
- Khớp thiết bị khi cắm: so danh tính kết nối với các Thiết bị đã đăng ký; khớp thì dùng, không khớp thì hỏi đăng ký mới. Không tự tạo Thiết bị mới khi chưa hỏi người dùng.
- Kiểm tra hiện diện: so tên và kích thước đã ghi lúc gửi với danh sách file hiện có trên máy. MTP không có hash rẻ, nên đổi tên file trên máy sẽ được coi là "không còn trên máy". Việc kiểm tra chỉ chạy khi máy đang cắm và khi người dùng yêu cầu; không quét liên tục.
- Việc "không còn trên máy" **không bao giờ** tự động đổi trạng thái Sách trong Thư viện.
- Hiển thị: bìa sách có một biểu tượng kèm số máy mà sách đang còn nằm trên; panel chi tiết liệt kê từng Thiết bị.
- Ứng dụng chỉ đọc từ máy và chỉ chép file sách lên máy. Không ghi đè, không xóa, không sửa file trên máy. Hành vi từ chối DRM và không ghi đè hiện có được giữ.
- **Thiết bị đầu tiên Boox Note Air4.** Hồ sơ hiện có `boox-note-air4c` còn ở trạng thái chưa kiểm chứng. Ticket đầu tiên là một khảo sát trên máy thật của chủ dự án: đo chế độ USB, thư mục chứa sách, và thử chép và liệt kê file qua MTP. Kết quả ghi vào tài liệu khảo sát; hồ sơ chỉ được chuyển sang "đã kiểm chứng" sau khi đo. Các ticket gửi sách và kiểm tra hiện diện phụ thuộc vào ticket này.
- Chuỗi giao diện bằng tiếng Việt (có bản tiếng Anh), một mục trong `CHANGELOG.md`, và một ADR cho việc thêm phụ thuộc MTP.

## Testing Decisions

- Test tốt kiểm tra hành vi quan sát được (bản ghi đã gửi, trạng thái hiện diện, biểu tượng trên bìa), không kiểm tra lời gọi COM.
- Seam: giao diện truyền tải thiết bị với bản giả trong bộ nhớ, đi qua `app_context`. Prior art: `tests/test_ereader_dialog.py` (đã dùng thư mục giả), `tests/test_device_profiles.py` và `tests/test_file_actions.py` cho việc chép.
- Các hành vi cần test: đăng ký và đặt tên; khớp tự động máy đã đăng ký và hỏi khi máy lạ; gửi ghi lại bản ghi đã gửi; không ghi đè file có sẵn; sách DRM bị từ chối; kiểm tra phát hiện file bị xóa trên máy; đổi tên trên máy thành "không còn trên máy"; trạng thái Thư viện không đổi khi sách không còn trên máy; nhiều máy cho một sách và số máy trên bìa; bỏ đăng ký không ảnh hưởng Sách; rút máy giữa chừng không sập; nâng cấp tạo các bảng mới.
- Bản MTP thật chỉ có test đánh dấu bỏ qua khi không có thiết bị, và không bao giờ bắt buộc trong CI (quy định của dự án).

## Out of Scope

- Đọc tiến độ đọc, ghi chú hay đánh dấu từ máy (NeoReader không có dữ liệu mà PC đọc được). Đọc từ KOReader và nhập ghi chú NeoReader xuất tay là các spec về sau.
- Ghi bất cứ thứ gì lên máy ngoài việc chép file sách; xóa hay sửa file trên máy.
- Tự động Xóa khỏi thư viện khi sách bị xóa trên máy.
- Các dòng máy khác (Kindle, Kobo, ...) và các kênh khác như Wi-Fi, BooxDrop hay cloud của Boox.
- Hash nội dung để nhận diện sách bị đổi tên trên máy.

## Further Notes

- Câu trả lời Q11 và Q17 của chủ dự án (đồng bộ hai chiều đầy đủ, cho phép ghi ngược) đã được thu hẹp xuống một chiều ở bản đầu, vì NeoReader không có dữ liệu đọc được. Các phần đó là bước tiếp theo, không bị bỏ.
- Hồ sơ hiện có tên `boox-note-air4c` (Air4 C), còn chủ dự án nói máy là "Boox Note Air4". Cần xác nhận hậu tố "C" của máy khi làm ticket khảo sát.
- Giả định cần xác nhận: bỏ đăng ký một Thiết bị cũng xóa các bản ghi đã gửi của nó.
- Hồ sơ `boox-android-generic` được nhắc trong tài liệu handoff nhưng chưa tồn tại.
