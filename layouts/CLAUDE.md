> Loads only when Claude works under `layouts/`. Moved out of the root CLAUDE.md, section 6.

## 6. Kiểu giao diện (layout) — chuẩn gói v1.1

MewBook có HAI LỚP chọn giao diện: KIỂU GIAO DIỆN (bố cục, hình khối) và THEME (màu, phông — dữ liệu). Cấu hình lưu cặp
`AppConfig.layout` + `AppConfig.theme` (và `theme_by_layout`, theme đã dùng cho từng kiểu để đổi qua lại không mất lựa chọn).

### Tổ hợp màu
token cuối = `theme.tokens` ← `layout.themes[theme].tokens` ← `theme.layouts[layout].tokens`. Theme dùng được với một kiểu nếu có
trong `layout.themes` HOẶC tự khai báo `layouts.<id>.supported = true`. Token `link` (1.1) thiếu thì dùng `accent`.
Mã: `presentation/layouts.py` (không Qt), `ThemeManager.apply(app, theme, layout)`, `ThemeManager.metric()/tokens()`.
`ornaments: ignore` → `ThemeManager.ornament()` trả `{}`.

### Gói kiểu = dữ liệu + mã
Gói `layout.json` chỉ là số đo và màu; HÌNH DẠNG cửa sổ là mã cài một lần ở tầng Presentation theo `LAYOUT_SPEC.md`. Một kiểu
chỉ được đưa ra Cài đặt và áp dụng khi id của nó nằm trong `layouts.IMPLEMENTED_LAYOUTS` (thêm id ở CÙNG thay đổi cài hình dạng; lớp cửa sổ đăng ký ở `presentation/window_shapes.py`, test giữ hai bảng khớp nhau). `ke-sach` → `MainWindow`, `toi-gian` → `SheetMainWindow`.
Chưa cài thì gói vẫn được kiểm và ghép màu nhưng bị ẩn, để không có kiểu "chỉ đổi màu".

