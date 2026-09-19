# Thương hiệu MewBook / Mèo Mực

> **Bản nháp, cần luật sư duyệt** (`docs/legal/LAWYER_QUESTIONS.md`, câu 10 và câu 3 mục C). Điều khoản về tranh và logo còn chờ chủ dự án xác nhận nguồn gốc (O12) và giấy phép (O11).
>
> *English summary:* the code is free software under AGPL-3.0-or-later; the **name "MewBook" / "Mèo Mực", the logo and the mascot artwork are not licensed by the AGPL**. You may redistribute the **unmodified** app under its name and logo. If you change the software, rename it and drop the logo and mascot. Partners: see `PARTNERS.md`.

## 1. Phạm vi

- **Mã nguồn** của MewBook theo giấy phép `AGPL-3.0-or-later` (`LICENSE`): bạn được dùng, sửa và phân phối lại theo giấy phép đó.
- **Tên và hình ảnh** không thuộc giấy phép đó, gồm: tên **"MewBook"**, tên **"Mèo Mực"**, logo, biểu tượng ứng dụng và tranh linh vật (mèo). AGPL-3.0 cho phép tác giả không cấp quyền nhãn hiệu (điều 7(e)); dự án dùng quyền đó.
- Tại thời điểm viết, tài liệu dự án **không ghi nhận** việc đăng ký nhãn hiệu; chủ dự án xác nhận trước khi công bố. Việc đăng ký (nếu có) là câu hỏi mở cho luật sư.

## 2. Được làm mà không cần xin phép

1. **Phân phối lại bản gốc nguyên vẹn** (bộ cài hoặc mã nguồn không sửa từ trang phát hành chính thức), giữ nguyên tên, logo, `LICENSE`, `THIRD_PARTY_NOTICES.md` và thông báo bản quyền.
2. **Nhắc tên để nói về phần mềm**: bài viết, hướng dẫn, đánh giá, "tương thích với MewBook", liên kết tới trang chính thức.
3. **Dùng tên trong ảnh chụp màn hình và tài liệu hướng dẫn** của bản gốc.

## 3. Bản sửa đổi

Nếu bạn sửa mã (thêm tính năng, đổi giao diện, đóng gói khác), bạn được phát hành theo AGPL-3.0-or-later nhưng **phải**:

- **Đổi tên** (không dùng "MewBook", "Mèo Mực" hay tên dễ nhầm), đổi tên gói hiển thị, tên tệp cài đặt và tên trong thuộc tính exe;
- **không dùng logo, biểu tượng và tranh linh vật**; dùng hình của bạn;
- ghi rõ đây là bản khác, ví dụ "dựa trên MewBook", kèm liên kết tới dự án gốc;
- giữ thông báo bản quyền và giấy phép của dự án, và cung cấp mã nguồn tương ứng theo AGPL-3.0.

Việc đổi tên hiển thị dùng các hằng số ở `src/smartdoc/__init__.py` (`APP_NAME`, `APP_DISPLAY_NAME`, `APP_PUBLISHER`, ...) và các tệp hình ở `src/smartdoc/presentation/assets/`; không cần sửa từng widget. Bản sửa đổi cũng nên đổi `AppId` trong trình cài đặt để không ghi đè bản gốc.

## 4. Đối tác (nhà sản xuất hoặc bán thiết bị đọc sách)

Đối tác được phân phối bản gốc nguyên vẹn hoặc tặng kèm bộ cài/liên kết tải, dùng tên và logo **nguyên bản** như mục 2, với điều kiện ở `PARTNERS.md`. Họ **không** được:

- ám chỉ rằng dự án bảo trợ, chứng nhận hoặc hỗ trợ sản phẩm hay dịch vụ của họ nếu chưa có thỏa thuận bằng văn bản;
- đổi logo hay tranh linh vật, hoặc dùng chúng cho sản phẩm khác.

**Đồng thương hiệu** (giao diện mang thương hiệu của đối tác) chưa được hỗ trợ và chưa có chính sách (quyết định D9, hoãn); cần thỏa thuận riêng.

## 5. Không được

- Dùng tên, logo hoặc tranh linh vật cho sản phẩm hay dịch vụ khác, hoặc để gây nhầm lẫn về nguồn gốc.
- Đăng ký tên miền, tài khoản hay tên gói phần mềm dễ nhầm là của dự án.
- Sửa logo hay tranh linh vật (cắt, đổi màu, thêm chữ) rồi vẫn gắn với tên MewBook.

## 6. Tranh linh vật và logo

Đề xuất (O11, chờ xác nhận): tranh và logo thuộc bản quyền của chủ dự án; được dùng **nguyên bản** cùng MewBook và trong tài liệu liên quan theo mục 2; không được dùng cho sản phẩm khác hay sửa đổi gây nhầm lẫn. Văn bản riêng cho tranh (`LICENSE-ART.md`) và hồ sơ nguồn gốc (`PROVENANCE.md`) sẽ được viết sau khi O12 (nguồn gốc ảnh, điều khoản của công cụ tạo ảnh) được chủ dự án xác nhận. Cho tới lúc đó, **không** coi các tệp ảnh là được cấp phép dùng lại.

## 7. Liên hệ

Câu hỏi về việc dùng tên và logo: **[chủ dự án điền kênh liên hệ trước khi công bố]**.
