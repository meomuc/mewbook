# Quy tắc thiết kế giao diện MewBook

Tài liệu này mô tả yêu cầu thiết kế giao diện, chia thành hai lớp: **kiểu giao diện (layout)** và **theme**.
Nó áp dụng các quy ước đã có trong `CLAUDE.md` (§3 và §5), `layouts/CLAUDE.md` và `themes/CLAUDE.md`.
Nếu có chỗ mâu thuẫn, các file đó có hiệu lực trước; phần mâu thuẫn được nêu ở mục "Câu hỏi còn mở".

## 0. Nguyên tắc chung

1. **Phân tách hai lớp.** Layout quyết định *cấu trúc* (cửa sổ nào, vùng nào, trang nào). Theme quyết định *diện mạo*
   (màu, chữ, nền, icon, trang trí). Một theme dùng được với nhiều layout; một layout có nhiều theme.
2. **Layout là mã; theme là dữ liệu.** Hình dạng cửa sổ được cài một lần trong `presentation/window_shapes.py`
   (`ke-sach` → `MainWindow`, `toi-gian` → `SheetMainWindow`). File `layout.json` chỉ chứa số đo và màu.
3. **Không màu cứng, không nhánh theo theme.** Widget không được viết mã màu trực tiếp và không được `if theme == ...`.
   Mọi màu lấy từ ThemeManager.
4. **Chức năng không đổi khi đổi giao diện.** Mọi chức năng (lọc, tìm kiếm, bộ sưu tập, thiết bị, thùng rác,
   cài đặt, đọc file) phải truy cập được trong mọi layout đã cài. Đổi layout chỉ đổi *đường đi tới* chức năng.
5. **Tiếng Việt cho mọi chuỗi giao diện** (`CLAUDE.md` §3); mã tiếng Anh cho chú thích giải thích lý do.
6. **Trạng thái luôn có chữ hoặc hình đi kèm**, không chỉ bằng màu (xem `themes/CLAUDE.md`).
7. **Không làm vỡ giao diện khi thiếu gói.** Theme hoặc layout thiếu dữ liệu thì dùng mặc định; không văng lỗi.

## 1. Layout: thiết kế những gì

Layout là một bộ khung hoàn chỉnh, thay đổi được *cấu trúc của mọi trang* chứ không chỉ một cửa sổ. Một layout mới
phải định nghĩa đủ các phần sau.

### 1.1 Cửa sổ chính và các vùng
- Vị trí và kích thước các vùng: thanh bên (bộ lọc, bộ sưu tập, hashtag), vùng nội dung (lưới, danh sách, bảng),
  panel chi tiết, thanh công cụ, thanh trạng thái, thanh phân trang.
- Chiều rộng tối thiểu của cửa sổ và cách các vùng co lại khi cửa sổ hẹp.
- Thứ tự và nhóm của các nút điều hướng chính (Thư viện, Công cụ, Cài đặt, Thùng rác, Máy đọc sách).

### 1.2 Các trang và hộp thoại phải được thiết kế lại theo layout
Một layout không được chỉ đổi cửa sổ chính. Các trang sau cũng thuộc layout:
- **Thư viện:** lưới thẻ, danh sách bảng, trạng thái rỗng và "không khớp" (`state_view`), dải tiêu đề của kết quả
  hai nhóm (ticket 3).
- **Chi tiết sách:** panel chi tiết, bìa lớn, các ô thông tin, hành động.
- **Cài đặt:** các mục (Giao diện, Ảnh bìa, Sao lưu, Máy đọc sách...) và cách chúng được nhóm.
- **Đọc file:** cửa sổ đọc sách (`reader_window`), thanh điều hướng và thanh công cụ của trình đọc.
- **Hộp thoại quan trọng:** xóa, gửi sang máy đọc, phân loại, tìm metadata. Có thể chọn kiểu hiển thị riêng cho từng
  loại, nhưng phải cùng bộ khung màu và chữ của layout.

### 1.3 Đặc tả kỹ thuật tối thiểu của một layout
- Id duy nhất, thêm vào `layouts.IMPLEMENTED_LAYOUTS` **cùng lúc** với lớp cửa sổ trong `window_shapes.py`.
- `layout.json` khai báo số đo: khoảng đệm, cỡ bìa, chiều cao hàng, bán kính góc, độ cao thanh công cụ.
- Danh sách theme được hỗ trợ (`layout.themes`) và trang trí dùng được (`ornaments`).
- Danh sách **vị trí cho phép** (`layout.slots`): các chỗ mà theme được chọn để đặt chức năng (ví dụ thanh công cụ trên
  hoặc bên trái). Theme chỉ được chọn trong danh sách này.
- Chưa cài hình dạng thì không đưa ra Cài đặt: gói vẫn được kiểm và ghép màu nhưng bị ẩn.

### 1.4 Yêu cầu chất lượng cho mọi layout
- **Phông và cỡ chữ:** dùng thang cỡ chữ của theme (không đặt cỡ cứng trong mã); chữ tiếng Việt có đủ dấu.
- **Phím tắt và điều hướng bàn phím:** mọi thao tác chính có phím tắt; tiêu điểm nhìn thấy được.
- **Khả năng tiếp cận:** nút chỉ có icon phải có nhãn hoặc tooltip; tương phản đạt chuẩn của theme.
- **Cửa sổ nhỏ:** không mất nút; có thể cuộn hoặc gom vào menu, không cắt chữ mà không có dấu hiệu.
- **Trạng thái:** mọi trang có trạng thái rỗng, đang tải, lỗi và thành công (`state_view`, `busy_indicator`).

### 1.5 Kiểm chứng
- Test cấu trúc: `tests/test_layouts.py` (hai bảng khớp nhau, mọi layout nạp được).
- Chụp màn hình trên nền tảng thật (không offscreen, vì offscreen không có font): `tools/ui_screenshots.py`
  chụp ở các cỡ 1440 px và 375 px rồi so với mẫu.
- Nếu không chụp được, báo rõ "chưa xác minh hình ảnh", không tuyên bố đã đúng thiết kế.

## 2. Theme: thiết kế những gì

Theme là dữ liệu: `themes/<id>/theme.json` cộng `fonts/` và `preview/`, theo `themes/_schema/theme.schema.json`.
Theme *không* được thay đổi cấu trúc của trang. Phạm vi của theme gồm sáu nhóm sau.

### 2.1 Màu sắc
- Bộ token: nền (`bg`, `panel`, `surface`, `surface2`, `rail`), chữ (`ink`, `ink2`, `ink3`), nhấn (`accent`,
  `accentink`, `accentsoft`, `link`), trạng thái (`ok`, `warn`, `err`), viền và bóng (`frame`, `under`).
- Quy tắc tương phản bắt buộc (validator): chữ trên nền ≥ 4.5:1; liên kết trên nền ≥ 4.5:1; trạng thái trên nền ≥ 3:1;
  `ok`, `warn`, `err`, `accent` khác nhau ΔE ≥ 20; `dark` khớp độ sáng thật của `bg`.
- Chế độ tối: `theme.json` khai báo màu tối; Windows chọn sáng hoặc tối theo cài đặt hệ thống.

### 2.2 Chữ (phông)
- Ba họ: `ui` (giao diện), `content` (nội dung sách, đọc được lâu), `disp` (tiêu đề, nhãn nhóm).
- Thang cỡ chữ: cỡ cơ bản, bước cỡ, cỡ tiêu đề, cỡ nhãn nhỏ. Các layout chỉ dùng thang này, không đặt cỡ cứng.
- Độ đậm, khoảng cách chữ (letter spacing) và chiều cao dòng (line height) của từng họ.
- Phông kèm theme phải có giấy phép OFL hoặc Apache 2.0 và đủ dấu tiếng Việt.

### 2.3 Hình nền và trang trí
- Nền vùng nội dung (`content_surface`) và nền thanh bên.
- Hình phong cảnh mờ sau lưới (`backdrop`): các kiểu 1.2 và 1.3 (karst, terraces, hills-flowers, pines, dunes,
  aurora, leaves, leaf-pile). Hình cố định theo khung nhìn, không chuyển động.
- Trang trí kệ, khung, thông báo, khung bìa (`shelf`, `frame`, `notice`, `cover_frame`). Kiểu không nhận ra thì bỏ qua và ghi cảnh báo.
- Người dùng có thể tắt hình nền trong Cài đặt › Giao diện.

### 2.4 Icon
- Mỗi theme có **một bộ icon vẽ riêng**, theo phong cách của theme (nét, hình khối, màu). Icon nằm trong
  `themes/<id>/icons/`, theo tên icon chuẩn.
- **Tên icon và vị trí dùng icon do layout quyết định**. Thêm một icon mới (tên mới) là thay đổi mã và phải có ở mọi theme.
- Mọi icon thao tác có nhãn hoặc tooltip đi kèm.

### 2.5 Mật độ và khoảng cách
- Theme khai báo mật độ (thoải mái, vừa, gọn) bằng một hệ số, và layout nhân hệ số đó với các số đo của nó.
  Không sửa số đo trong widget.

### 2.6 Kiểm chứng
- `tests/test_themes.py`: mọi `theme.json` qua validator; ThemeManager nạp được; QSS không còn `$token` chưa thay.
- `tests/test_theme_contract.py`: tương phản WCAG; ngưỡng `ink3` 4.5:1, chặt hơn validator.
- Đổi theme lúc chạy phát `themeChanged`; các delegate và widget vẽ lại.

## 3. Ranh giới giữa layout và theme

| Việc | Thuộc | Lý do |
|---|---|---|
| Màu, chữ, cỡ, khoảng cách | Theme (token và thang) | Là dữ liệu, đổi không cần mã |
| Hình nền, trang trí, kiểu icon | Theme | Là diện mạo |
| Vị trí thanh bên, toolbar, panel | Layout | Là cấu trúc; một theme không được đổi |
| Trang nào có, nút nào có mặt | Layout | Chức năng là cấu trúc |
| Chọn một vị trí trong các vị trí layout đã cho phép (thay đổi vừa phải) | Theme (dữ liệu) | Mục 5, câu 1 |

## 4. Quy trình khi thêm một giao diện

1. Thêm theme: tạo `themes/<id>/theme.json`, phông, ảnh xem trước; `validate_theme` phải đạt; test theme xanh.
2. Thêm layout: viết lớp cửa sổ, đăng ký trong `window_shapes.py` và `IMPLEMENTED_LAYOUTS` cùng lúc; `layout.json`.
3. Chụp màn hình trên máy thật, các cỡ 1440 px và 375 px; so với mẫu; liệt kê điểm lệch.
4. Ghi `CHANGELOG.md` (mục `Added` hoặc `Changed`) và nhật ký theo giao thức.

## 5. Quyết định của chủ dự án

1. **Theme có được chọn vị trí chức năng không?** Được, trong số các vị trí layout cho phép (layout khai báo
   danh sách vị trí). Mức thay đổi vừa phải: theme chỉ đổi vị trí trong phạm vi đó, không được thay đổi cấu trúc
   quá lớn.
2. **Phạm vi layout:** có, layout bao gồm trang Cài đặt và cửa sổ đọc sách (mục 1.2).
3. **Bộ icon:** mỗi theme có một bộ icon vẽ riêng, theo phong cách của theme đó. Tên icon và vị trí dùng icon vẫn do
   layout quyết định (mục 2.4 cần cập nhật theo điểm này).
4. **Thời điểm áp dụng:** đổi layout áp dụng ngay, không cần khởi động lại.

Hệ quả cho các mục trên: mục 2.4 đổi thành "theme có bộ icon riêng"; mục 3 dòng "Chọn một vị trí" nay là
"Theme được chọn trong các vị trí layout cho phép"; mục 1.3 cần thêm "danh sách vị trí cho phép" vào `layout.json`.
