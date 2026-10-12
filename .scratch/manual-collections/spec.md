Status: ready-for-agent

# Spec: Bộ sưu tập chỉ có thành viên thêm tay

Thuật ngữ theo `CONTEXT.md`: Bộ sưu tập, Sách, Tag / Hashtag, Thư viện.

## Problem Statement

Bộ sưu tập hiện là kiểu lai: vừa có thành viên thêm tay, vừa có quy tắc lọc tính lúc truy vấn. Hai mô hình cùng tồn tại khiến người dùng khó hiểu một sách vì sao nằm trong bộ sưu tập, và khiến mã phải xử lý cả hai nhánh. Người dùng muốn một khái niệm đơn giản: Bộ sưu tập là một nhóm "ảo" do họ tự gom sách vào.

Ngoài ra, một Bộ sưu tập có thể trùng tên với một hashtag mà người dùng không có cách nào nhận ra.

## Solution

Bộ sưu tập chỉ có thành viên do người dùng thêm và bớt tay. Các bộ sưu tập kiểu quy tắc đã tạo trước đây được chốt thành danh sách thành viên tại thời điểm nâng cấp. Khi tên một Bộ sưu tập trùng với một hashtag, ứng dụng chỉ **đánh dấu liên kết** giữa hai thứ để người dùng biết; không thành viên nào được suy ra từ hashtag.

## User Stories

1. Là người dùng, tôi muốn tạo một Bộ sưu tập và tự thêm sách vào đó, để gom sách theo cách của riêng tôi.
2. Là người dùng, tôi muốn thêm nhiều sách đã chọn vào một Bộ sưu tập cùng lúc.
3. Là người dùng, tôi muốn bớt một sách khỏi Bộ sưu tập mà không ảnh hưởng đến file hay hashtag của sách.
4. Là người dùng, tôi muốn một sách thuộc nhiều Bộ sưu tập, để một cuốn xuất hiện ở nhiều nhóm.
5. Là người dùng, tôi muốn đổi tên và xóa một Bộ sưu tập mà không đụng đến sách bên trong.
6. Là người dùng, tôi muốn các Bộ sưu tập tôi đã tạo bằng quy tắc lọc vẫn còn nguyên nội dung sau khi nâng cấp, để không mất công sắp xếp.
7. Là người dùng, tôi muốn biết rằng các Bộ sưu tập đó từ nay không tự cập nhật sách mới, để không ngạc nhiên.
8. Là người dùng, tôi muốn quá trình nâng cấp luôn có bản sao lưu thư viện trước, để có đường lùi nếu có sự cố.
9. Là người dùng, tôi muốn Bộ sưu tập "Sẽ đọc" có sẵn vẫn hoạt động như trước.
10. Là người dùng, tôi muốn thấy dấu liên kết khi một Bộ sưu tập trùng tên với một hashtag, để nhận ra sự trùng lặp.
11. Là người dùng, tôi muốn dấu liên kết không làm thay đổi thành viên, để gắn hashtag cho một sách không tự đưa nó vào Bộ sưu tập.
12. Là người dùng, tôi muốn sách đã xóa vào Thùng rác giữ nguyên tư cách thành viên, để khôi phục xong sách về đúng các nhóm cũ.
13. Là người dùng, tôi muốn khi sách bị xóa hẳn thì nó cũng biến mất khỏi mọi Bộ sưu tập.
14. Là người dùng, tôi muốn số lượng sách trong mỗi Bộ sưu tập ở thanh bên luôn đúng.

## Implementation Decisions

- Bộ sưu tập chỉ còn một mô hình: tập thành viên do người dùng quản lý. Giao diện tạo và sửa quy tắc lọc bị gỡ bỏ. Việc đánh giá quy tắc lúc truy vấn không còn được dùng cho bộ sưu tập.
- Thành viên tiếp tục được lưu ở bảng thành viên riêng. **Không** lưu Bộ sưu tập thành một tag ẩn trong cột hashtag của sách, để không ảnh hưởng tìm kiếm toàn văn, đếm bộ lọc và bộ phân loại.
- Nâng cấp là một **migration có số thứ tự**, chạy sau bước sao lưu thư viện (không sao lưu thì không chạy). Với mỗi Bộ sưu tập kiểu quy tắc, migration tính quy tắc tại thời điểm nâng cấp, thêm các sách khớp vào danh sách thành viên (hợp với thành viên thêm tay có sẵn), rồi coi bộ sưu tập là thủ công. Cột lưu quy tắc không bị xóa hay đổi. Migration phải chạy an toàn nếu bị chạy lại.
- Dấu liên kết hiển thị khi tên Bộ sưu tập trùng một hashtag theo cùng cách so sánh tên mà ứng dụng dùng cho hashtag (không phân biệt hoa thường theo chuẩn hiện có). Dấu này xuất hiện trong danh sách Bộ sưu tập và danh sách hashtag, và chỉ có tính thông tin.
- Thành viên của sách trong Thùng rác được giữ; hết hạn thì xóa cùng bản ghi (thống nhất với spec Thùng rác).
- Chuỗi giao diện bằng tiếng Việt (có bản tiếng Anh), một mục trong `CHANGELOG.md`.

## Testing Decisions

- Test tốt kiểm tra kết quả quan sát được sau nâng cấp (danh sách thành viên), không kiểm tra cách tính nội bộ.
- Seam: nâng cấp `DatabaseManager` từ một thư viện mẫu cũ lên phiên bản mới. Prior art: `tests/test_schema_migrations.py`, và `tests/test_smart_collections.py` cho dữ liệu bộ sưu tập quy tắc.
- Các hành vi cần test: bộ sưu tập quy tắc thành danh sách thành viên đúng bằng kết quả quy tắc lúc nâng cấp, cộng thành viên thủ công; chạy lại migration không thêm trùng; bộ sưu tập thủ công và "Sẽ đọc" không đổi; sách vẫn thuộc nhiều bộ sưu tập; dấu liên kết xuất hiện khi trùng tên hashtag và gắn hashtag mới không đổi thành viên; sách vào Thùng rác giữ thành viên và hết hạn thì mất.

## Out of Scope

- Tự động thêm sách vào Bộ sưu tập khi bộ phân loại gắn hashtag trùng tên.
- Quy tắc lọc cho Bộ sưu tập dưới bất kỳ hình thức nào.
- Xóa cột lưu quy tắc khỏi schema.
- Đồng bộ Bộ sưu tập giữa các máy hoặc lên cloud.

## Further Notes

- Cách nói "tag ẩn" của người dùng được hiểu là khái niệm; quyết định lưu trữ là giữ bảng thành viên riêng. Nếu sau này muốn đưa Bộ sưu tập vào cột hashtag thì đó là một thay đổi lớn cần ADR riêng.
