> Loads only when Claude works under `themes/`. Moved out of the root CLAUDE.md, section 5.

## 5. Theme (giao diện màu) — chuẩn gói theme v1

Mọi theme của MewBook là DỮ LIỆU, không phải mã. Mỗi theme nằm trong
`themes/<id>/theme.json` (+ `fonts/`, `preview/` nếu có) và tuân theo
`themes/_schema/theme.schema.json`. Không viết mã màu trực tiếp trong widget,
QSS hay delegate: mọi màu lấy từ ThemeManager.

### Các kiểu trang trí (ornaments) — cài một lần, dùng chung
| Khối        | Kiểu         | Ý nghĩa khi vẽ |
|-------------|--------------|----------------|
| shelf       | flat         | vạch kệ gradient shelftop → shelf, dày `thickness` (mặc định 6) |
| shelf       | wood         | như flat nhưng có dải sáng ở mặt trên (28%), thân shelf, mép dưới `edge`, vân gỗ `grain` mờ chạy ngang |
| shelf       | glass        | vạch mờ trong suốt 60% + đường sáng 1px ở trên |
| shelf       | brackets     | 2 ke đỡ 7×11 px màu `bracket_color`, cách hai đầu kệ 18 px |
| frame       | wood         | nhãn nhóm thanh bên, header panel chi tiết, tiêu đề cột Cài đặt: nền gradient `light`→`dark`, viền `dark`, chữ `ink` |
| notice      | chalkboard   | thẻ thông báo (tóm tắt nhập, có bản mới, dải mất file): nền `bg`, chữ `ink`, viền dày 7 px màu `frame` |
| cover_frame | wood / line  | khung quanh bìa lớn ở panel chi tiết, dày `width` px |
| backdrop    | karst / terraces / hills-flowers / pines / dunes / aurora / leaves / leaf-pile | hình phong cảnh mờ sau lưới sách (chuẩn 1.2/1.3, xem bên dưới); cài trong `ornaments.paint_backdrop` |
Thiếu khối nào = dùng kiểu mặc định phẳng. Kiểu không nhận ra = bỏ qua + cảnh báo, không làm vỡ giao diện.

### Quy tắc không được phá (validator kiểm tra tự động)
- ink, ink2 trên bg/rail/panel/surface/surface2 ≥ 4.5:1; ink trên accentsoft ≥ 4.5:1.
- accentink trên accent ≥ 4.5:1; accent (liên kết) trên panel/surface ≥ 4.5:1; accent trên bg ≥ 3:1.
- ok, warn, err trên panel/surface/rail ≥ 3:1; ok/warn/err/accent khác nhau ΔE ≥ 20.
- `dark` phải khớp độ sáng thật của bg.
- Phông kèm gói phải có giấy phép OFL hoặc Apache 2.0 và đủ dấu tiếng Việt.
- Trạng thái luôn có hình dạng/chữ đi kèm, không bao giờ chỉ bằng màu.

### Test bắt buộc: tests/test_themes.py
- Mọi `themes/*/theme.json` qua validate_theme (mã thoát 0).
- ThemeManager nạp được từng theme, sinh QSS không còn `$token` nào chưa thay.
- Đổi theme lúc chạy phát `themeChanged` và các delegate vẽ lại.

### Trong mã (đã cài; đừng làm lại)
- `presentation/theme_manager.py`: quét `themes/*/theme.json`, chỉ nạp gói qua `validate_theme.check` (gói lỗi bị bỏ và ghi log),
  `available_themes()` sinh thẻ trong Cài đặt, `ornament(block)` đưa tham số trang trí cho widget.
- `presentation/ornaments.py`: MỘT nơi cài mọi kiểu trang trí (shelf, frame, notice, cover_frame). Kiểu mới thêm ở đây,
  kèm test trong `tests/test_themes.py`.
- `AppConfig.theme` lưu khóa cũ cho 7 theme gốc (`woodshelf`...) và `id` cho theme thêm sau; id không còn gói thì dùng giao diện mặc định.
- `presentation/theme.py::colors_for()` cho widget còn đọc `ThemeColors`: theme mới nhận cấu trúc mặc định + màu của gói.
- Gói theme nằm ở thư mục gốc `themes/` và được `packaging/MewBook.spec` đưa vào bản dựng (trừ `incoming/`).
- Màu chữ mờ `ink3` phải đạt 4.5:1 (test hợp đồng theme của dự án), chặt hơn cảnh báo 3:1 của validator.

## Hình phong cảnh (ornaments.backdrop) — chuẩn 1.2

Theme 1.2 có thể khai báo `ornaments.backdrop`: một hình phong cảnh MỜ vẽ sau lưng vùng
nội dung (lưới kệ sách / bảng), giúp theme có "cảnh" mà không làm rối chữ.

- Kiểu có sẵn (hình mẫu chuẩn trong themes/_schema/backdrops/<style>.svg, viewBox 1200×300,
  2 lớp: lớp xa fill-opacity .55, lớp gần 1): karst (núi đá vôi trên nước), terraces
  (ruộng bậc thang), hills-flowers (đồi hoa), pines (rừng thông), dunes (đồi cát),
  aurora (cực quang — position top).
- Vẽ: trong paintEvent của viewport vùng nội dung, TRƯỚC khi vẽ kệ/bìa. Dựng QPainterPath
  một lần từ path trong SVG (hoặc QSvgRenderer), co giãn theo chiều ngang (không giữ tỉ lệ),
  cao = height_pct % chiều cao viewport, bám đáy (bottom) hoặc đỉnh (top).
  Lớp gần tô `color`, lớp xa tô `color2` (thiếu thì dùng color), nhân `opacity` của theme.
- CỐ ĐỊNH theo khung nhìn, không cuộn theo sách; không động (không hiệu ứng chạy).
- Cache pixmap theo (kích thước viewport, theme id); vẽ lại khi đổi cỡ cửa sổ / đổi theme.
- Kiểu "Kệ sách": vẽ. Kiểu "Tối giản": layout.json đặt ornaments = ignore → không vẽ.
- Validator 1.2 đảm bảo: hình thật mờ (tương phản với nền ≤ 1.35:1) và chữ ink/ink2 đặt
  trên phần hình vẫn ≥ 4.5:1.
- Có tùy chọn trong Cài đặt › Giao diện: "Hiện hình phong cảnh của theme" (mặc định bật).

## Chuẩn 1.3 — thêm hai hình nền lá thu

- `leaves`: lá thu rơi rải rác (lá sấu thuôn + lá phong 5 thùy), dày ở phía trên, thưa dần
  xuống dưới. Thường dùng với position = top, height_pct 45–60.
- `leaf-pile`: thảm lá rụng, dày ở đáy. Dùng với position = bottom.
Hình mẫu: themes/_schema/backdrops/leaves.svg, leaf-pile.svg (cùng quy ước 2 lớp như 1.2).
Hình đứng yên, KHÔNG làm hiệu ứng lá rơi chuyển động (giữ tinh thần yên tĩnh, không tốn CPU).

Mã: `presentation/ornaments.py::paint_backdrop` (hình mẫu đọc từ `themes/_schema/backdrops/*.svg`, cache pixmap theo cỡ), vẽ ở `shelf_view.paintEvent` trước kệ/bìa; `AppConfig.show_backdrop` + `ThemeManager.show_backdrop` là tùy chọn Cài đặt › Giao diện.

