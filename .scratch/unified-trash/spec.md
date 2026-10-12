Status: ready-for-agent

# Spec: Thùng rác hợp nhất và hai loại xóa

Thuật ngữ theo `CONTEXT.md`: Sách, Thư viện, Xóa khỏi thư viện, Xóa file, Thùng rác, Thư mục thùng rác, Tình trạng file.

## Problem Statement

Người dùng quản lý ebook trong MewBook nhưng không điều khiển được điều gì xảy ra với file khi xóa sách:

- Nút "Xóa khỏi thư viện" hiện **chuyển luôn file vật lý** vào thùng rác của ứng dụng. Tên nút nói một đằng, hành vi làm một nẻo.
- Trong công cụ lọc trùng, lựa chọn "gỡ khỏi thư viện" **xóa cứng** bản ghi: mất hashtag, tác giả, thông tin tra cứu và lịch sử metadata, không khôi phục được.
- Không có chỗ nào để xem lại những sách đã gỡ khỏi thư viện mà file vẫn còn nguyên trên đĩa. Bộ lọc Tình trạng file chỉ có "Thiếu file" và "File quá nhỏ".
- Thư mục chứa file đã xóa là một thư mục cố định của ứng dụng, người dùng không chọn được nơi đặt.
- Một file đã gỡ khỏi thư viện nhưng còn nằm trong thư mục được theo dõi có thể bị tự nhập lại.

## Solution

Chỉ có **một Thùng rác**, nằm trong bộ lọc Tình trạng file và là nơi duy nhất hiện sách đã xóa. Có hai loại xóa, mỗi mục trong Thùng rác ghi rõ là loại nào:

- **Xóa khỏi thư viện**: Sách vào Thùng rác, file vật lý đứng nguyên chỗ cũ.
- **Xóa file**: Sách vào Thùng rác và file vật lý chuyển sang Thư mục thùng rác do người dùng chọn trong Cài đặt.

Cả hai loại đều khôi phục được và đều hết hạn sau cùng số ngày. Hết hạn thì bản ghi bị xóa hẳn, và file cũng bị xóa nếu là Xóa file. Mọi nơi xóa sách (xóa trực tiếp, lọc trùng) đều dùng đúng hai lựa chọn này.

## User Stories

1. Là người dùng, tôi muốn "Xóa khỏi thư viện" không đụng tới file trên đĩa, để tôi gỡ sách khỏi danh sách mà không làm mất file.
2. Là người dùng, tôi muốn "Xóa file" chuyển file vào thư mục thùng rác tôi đã chọn, để tôi xóa được cả file mà vẫn có đường lùi.
3. Là người dùng, tôi muốn thấy hai lựa chọn này khi xóa một sách, để tôi biết rõ điều sắp xảy ra.
4. Là người dùng, tôi muốn thấy hai lựa chọn này khi xóa nhiều sách cùng lúc, để thao tác hàng loạt cũng rõ ràng.
5. Là người dùng, tôi muốn công cụ lọc trùng cho cùng hai lựa chọn đó, để tôi dọn bản trùng mà không mất hashtag và thông tin đã nhập.
6. Là người dùng, tôi muốn mọi sách đã xóa nằm trong một Thùng rác duy nhất ở Tình trạng file, để không phải tìm ở nhiều nơi.
7. Là người dùng, tôi muốn sách đã xóa biến mất khỏi danh sách chính, tìm kiếm, bộ lọc, số đếm và mọi công cụ, để thư viện chỉ chứa sách tôi đang dùng.
8. Là người dùng, tôi muốn mỗi mục trong Thùng rác có cột "Tình trạng xóa" (Xóa khỏi thư viện / Xóa file và thư viện), để phân biệt hai loại.
9. Là người dùng, tôi muốn mỗi mục có cột đường dẫn hiện tại của file, để biết file đang ở đâu.
10. Là người dùng, tôi muốn bấm vào đường dẫn để mở thư mục chứa file với file đó được chọn, để đến thẳng file.
11. Là người dùng, tôi muốn được báo rõ khi file không còn ở đường dẫn đó, thay vì một cửa sổ trống.
12. Là người dùng, tôi muốn mỗi mục hiển thị ngày xóa và số ngày còn lại trước khi hết hạn, để biết còn bao lâu để đổi ý.
13. Là người dùng, tôi muốn khôi phục một sách "Xóa khỏi thư viện", để nó hiện lại ngay với đủ hashtag, tác giả, bộ sưu tập và thông tin cũ.
14. Là người dùng, tôi muốn khôi phục một sách "Xóa file", để file về đúng chỗ cũ và sách hiện lại như trước.
15. Là người dùng, tôi muốn việc khôi phục không bao giờ ghi đè một file khác đang nằm ở chỗ cũ, để không mất dữ liệu.
16. Là người dùng, tôi muốn chọn thư mục thùng rác trong Cài đặt, ví dụ trên ổ khác, để khỏi đầy ổ hệ thống.
17. Là người dùng, tôi muốn có sẵn một thư mục thùng rác mặc định, để dùng được ngay mà không phải cấu hình.
18. Là người dùng, tôi muốn đổi thư mục thùng rác mà không làm hỏng các mục đã có, để file cũ vẫn khôi phục được.
19. Là người dùng, tôi muốn đặt số ngày giữ trong Thùng rác, để tự quyết định thời gian chờ.
20. Là người dùng, tôi muốn đặt số ngày bằng 0 để không bao giờ hết hạn, để tôi tự dọn khi muốn.
21. Là người dùng, tôi muốn mục hết hạn bị xóa hẳn bản ghi, và file cũng bị xóa nếu là Xóa file, để Thùng rác tự dọn.
22. Là người dùng, tôi muốn file của mục "Xóa khỏi thư viện" không bao giờ bị xóa khi mục hết hạn, để file gốc của tôi luôn an toàn.
23. Là người dùng, tôi muốn có nút "Xóa hẳn" cho từng mục và cho cả Thùng rác, để tôi dọn ngay không phải chờ.
24. Là người dùng, tôi muốn được hỏi xác nhận trước khi "Xóa hẳn", và lời nhắc nói rõ file có bị xóa hay không.
25. Là người dùng, tôi muốn file đã gỡ khỏi thư viện không bị tự nhập lại bởi bộ theo dõi thư mục, kể cả sau khi mục hết hạn.
26. Là người dùng, tôi muốn khi khôi phục, file lại được phép nhập như bình thường.
27. Là người dùng, tôi muốn nếu việc chuyển file thất bại thì sách ở lại thư viện nguyên vẹn và tôi được báo lý do, để không có trạng thái nửa vời.
28. Là người dùng, tôi muốn các sách tôi đã đưa vào thùng rác theo cách cũ vẫn thấy và khôi phục được sau khi nâng cấp, được hiểu là loại Xóa file.
29. Là người dùng, tôi muốn panel chi tiết của một sách đã xóa cho biết loại xóa và vị trí file, để hiểu tình trạng của nó.
30. Là người dùng, tôi muốn chức năng hiện có "Sách đã xóa…" trong menu Công cụ mở đúng Thùng rác này, để chỉ có một cửa vào.

## Implementation Decisions

- Mỗi Sách đã xóa mang một thuộc tính **loại xóa** với hai giá trị: "Xóa khỏi thư viện" và "Xóa file và thư viện". Thuộc tính này là cột mới thêm vào bảng sách theo cách chỉ thêm cột (không đổi, không xóa cột cũ).
- Sách trong Thùng rác giữ nguyên mọi thuộc tính: hashtag, tác giả, thành viên bộ sưu tập, văn bản tìm kiếm, bìa, lịch sử metadata. Sách đã xóa bị loại khỏi mọi truy vấn của Thư viện, kể cả số đếm bộ lọc, các công cụ hàng loạt và công cụ lọc trùng, và chỉ xuất hiện trong chế độ xem Thùng rác.
- "Xóa khỏi thư viện" không thực hiện thao tác nào trên file. Đường dẫn hiển thị là vị trí gốc.
- "Xóa file" chuyển file vào Thư mục thùng rác, không ghi đè bất kỳ file nào đã có ở đó. Nếu chuyển thất bại, sách giữ nguyên trong Thư viện và có thông báo lỗi. Đây là hành vi hiện có và được giữ.
- Khôi phục "Xóa khỏi thư viện": chỉ đưa sách trở lại Thư viện. Khôi phục "Xóa file": đưa file về đường dẫn cũ rồi đưa sách trở lại, không ghi đè file khác. Mỗi mục lưu đường dẫn đầy đủ của riêng nó, nên đổi Thư mục thùng rác chỉ ảnh hưởng các lần xóa sau.
- Hết hạn dùng một cài đặt số ngày duy nhất (hiện có: mặc định 30, 0 là không hết hạn, tối đa 365), áp dụng cho cả hai loại. Hết hạn xóa hẳn bản ghi cùng mọi dữ liệu liên quan (thành viên bộ sưu tập, kết quả phân loại, lịch sử metadata, tiến độ đọc), và xóa file nếu loại là Xóa file. Với loại Xóa khỏi thư viện, file không bao giờ bị đụng tới.
- Đường dẫn của mọi sách đã xóa được đưa vào danh sách loại trừ nhập lại, và **vẫn nằm trong danh sách đó vĩnh viễn** kể cả sau khi hết hạn. Khôi phục thì gỡ đường dẫn khỏi danh sách. Muốn nhập lại file sau khi hết hạn, người dùng thêm thủ công.
- Chế độ xem Thùng rác là một bảng có các cột: tên sách, Tình trạng xóa, đường dẫn hiện tại (bấm mở đúng file trong trình quản lý file), ngày xóa, số ngày còn lại. Hành động: Khôi phục, Xóa hẳn, Dọn Thùng rác. Bộ lọc Tình trạng file có thêm một giá trị "Thùng rác" dẫn tới chế độ xem này.
- Cài đặt Thư mục thùng rác: người dùng chọn thư mục; mặc định là thư mục thùng rác cố định hiện có của ứng dụng.
- Công cụ lọc trùng chuyển từ xóa cứng sang cùng hai lựa chọn. Không còn đường nào xóa cứng bản ghi theo yêu cầu người dùng, ngoại trừ "Xóa hẳn" và hết hạn.
- Các sách đã nằm trong thùng rác theo cách cũ được nâng cấp thành loại "Xóa file và thư viện", vì file của chúng đang nằm trong thùng rác. Việc này đi qua cơ chế nâng cấp schema hiện có và không sửa migration đã phát hành.
- Nút "Xóa khỏi thư viện" hiện tại phải ngừng chuyển file. Nhãn nút và hộp thoại xác nhận phản ánh đúng hành vi mới.
- Chuỗi giao diện bằng tiếng Việt (có bản tiếng Anh), có một mục trong `CHANGELOG.md`, và có một ADR ghi lại quyết định "một Thùng rác hợp nhất, hai loại xóa".
- Sau mỗi thao tác phát một sự kiện cập nhật thư viện như hiện nay để các widget tự truy vấn lại.

## Testing Decisions

- Test tốt chỉ kiểm tra hành vi quan sát được: file còn hay mất ở đâu, sách có trong truy vấn Thư viện hay không, mục có trong Thùng rác hay không. Không kiểm tra tên hàm nội bộ hay thứ tự gọi.
- Seam duy nhất: dịch vụ thùng rác qua `app_context` (cùng fixture `library` như test hiện có), kiểm tra kết quả bằng truy vấn tài liệu với bộ lọc Tình trạng file. Prior art: `tests/test_trash_service.py`, kể cả test hộp thoại thùng rác ở đó.
- Các hành vi cần có test: xóa khỏi thư viện để nguyên file; xóa file chuyển file và không ghi đè; khôi phục cả hai loại giữ nguyên hashtag và bộ sưu tập; hết hạn xóa bản ghi cả hai loại và chỉ xóa file với Xóa file; số ngày 0 là không hết hạn; đường dẫn bị loại trừ nhập lại sau hết hạn và được gỡ khi khôi phục; sách đã xóa không xuất hiện trong truy vấn Thư viện lẫn số đếm bộ lọc; công cụ lọc trùng không còn xóa cứng; nâng cấp thư viện có mục thùng rác kiểu cũ thành loại Xóa file (cùng kiểu với `tests/test_schema_migrations.py` và `tests/test_duplicate_finder_dialog.py`).
- Mỗi lỗi sửa kèm một test hồi quy phải thất bại trước khi sửa (quy định của dự án), nhất là lỗi nút "Xóa khỏi thư viện" đang chuyển file.

## Out of Scope

- Chức năng "Dọn sách thiếu file" (quên các sách mà file đã mất): hiện xóa cứng bản ghi, giữ nguyên trong spec này.
- Dùng Thùng rác của Windows (Recycle Bin).
- Hoàn tác hàng loạt nhiều lần xóa.
- Đồng bộ trạng thái xóa lên cloud hoặc sang máy đọc sách.
- Màn hình quản lý danh sách loại trừ nhập lại.

## Further Notes

- Giả định cần bạn xác nhận khi review: đổi Thư mục thùng rác không di chuyển các file đang nằm ở thư mục cũ.
- Khi khôi phục "Xóa file" mà thư mục gốc không còn tồn tại, cách xử lý (tạo lại thư mục hay báo lỗi) chưa được chốt. Đề xuất: tạo lại thư mục rồi khôi phục, nếu không được thì báo lỗi.
- Chưa quyết định `.scratch/` có được commit vào git hay không.
