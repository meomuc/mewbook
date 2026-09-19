# Yêu cầu thiết kế giao diện (theme) cho Mèo Mực / MewBook

> Gửi kèm file này cho Claude Design. Mỗi theme bạn thiết kế phải tuân thủ
> các yêu cầu dưới đây thì mới cắm được vào ứng dụng mà không phải sửa code
> chức năng.

## 1. Bối cảnh sản phẩm

- **Mèo Mực (MewBook)** là ứng dụng desktop **Windows** quản lý thư viện
  ebook/tài liệu (PDF, EPUB, MOBI, AZW3). Ứng dụng quét file tại chỗ, đọc
  metadata và ảnh bìa, rồi cho tìm kiếm, lọc, gắn bộ sưu tập, đọc sách, tóm
  tắt bằng AI và đánh giá cộng đồng.
- Người dùng là người Việt: **mọi chữ trên giao diện là tiếng Việt có
  dấu**. Font phải hiển thị đầy đủ dấu (ví dụ "Đắc nhân tâm", "Nguyễn Nhật
  Ánh"). Tên sách có thể dài 60 ký tự trở lên.
- Công nghệ: **Qt 6 / PySide6 (Qt Widgets + Qt Style Sheets)**, không phải
  web. Xem ràng buộc kỹ thuật ở mục 5 trước khi đề xuất hiệu ứng.
- Đã có 3 theme: *Editorial Light* (sáng, kiểu tờ báo), *Walnut Library*
  (kệ sách gỗ, bìa lớn), *Midnight Ink* (khung tối, vùng sách sáng, sidebar
  dạng thanh icon). Theme mới phải khác biệt rõ với cả 3.

## 2. Mỗi theme là gì (thứ bạn thực sự thiết kế)

Một theme gồm ba phần, **không có gì khác**:

**(a) Bảng màu token.** Mọi màu là **hex `#rrggbb`**. Riêng `border` được
phép dùng `rgba(r,g,b,a)`.

| Token | Dùng cho | Đi cặp với chữ |
|---|---|---|
| `background` | Nền cửa sổ, menu bar | `sidebar_text` |
| `surface` | Hộp thoại, menu, tooltip, ô nhập liệu, nút thường | `sidebar_text` |
| `header_bg` | Thanh trên cùng (logo, ô tìm kiếm, nút chế độ xem, sắp xếp) | `sidebar_text` |
| `content_bg` | Nền lưới bìa sách và bảng danh sách | `text` |
| `text` | Chữ trong vùng sách (tên sách, tác giả, ô của bảng) | nền `content_bg` |
| `sidebar_bg` / `sidebar_text` | Thanh bên (bộ sưu tập, bộ lọc) | |
| `panel_bg` / `panel_text` | Panel chi tiết bên phải (bìa lớn, metadata, tóm tắt AI) | |
| `muted_text` | Chữ phụ: số đếm, ngày, gợi ý, tiêu đề mục viết hoa | trên `sidebar_bg` **và** `panel_bg` |
| `border` | Đường kẻ mảnh phân cách | |
| `accent` / `accent_text` | Nút chính, chip đang chọn, liên kết, viền focus | |
| `selected_bg` / `selected_border` / `selected_text` | Mục đang chọn (dải màu + sọc trái + chữ) | |
| `cover_gradients` | 6–10 cặp màu (đầu, cuối) cho **bìa giả** của sách không có ảnh bìa | chữ trắng in trên bìa |
| `cover_spine` | Dải gáy sách bên trái bìa giả, dạng (r,g,b,alpha 0–255) | |

Lưu ý: `text` luôn đi với `content_bg`, còn `sidebar_text` đi với
`background`/`surface`/`header_bg`. Nếu khung tối mà vùng sách sáng (như
Midnight Ink) thì `text` tối, `sidebar_text` sáng. Hãy ghi rõ theme của bạn
thuộc kiểu nào.

**(b) Tùy chọn bố cục**, chỉ chọn trong các giá trị có sẵn:

| Tùy chọn | Giá trị |
|---|---|
| `layout_mode` | `detail_panel` (3 cột: sidebar, sách, panel chi tiết bên phải) hoặc `action_bar` (2 cột, thêm thanh thao tác ngang đáy cửa sổ khi chọn sách) |
| `icon_rail_sidebar` | `true`: sidebar thu thành thanh icon rộng 80px, bấm mở flyout. `false`: sidebar đầy đủ rộng 240px |
| `sidebar_style` | `plain`: dòng "tên … số lượng". `iconic`: dòng cao hơn, có icon nét mảnh, số lượng dạng "viên thuốc" khi được chọn |
| `library_heading` | Tiêu đề mục sidebar, ví dụ "Bộ sưu tập" hoặc "Thư viện" |
| `all_items_label` | Nhãn dòng "tất cả", ví dụ "Tất cả tài liệu" hoặc "Tất cả" |
| `header_add_button` | Có nút "＋ Thêm mới" trên header hay không |
| `show_cover_size_slider` | Hiện thanh trượt cỡ bìa trên header hay không |
| `show_filter_chips` | Hiện chip lọc định dạng (Tất cả / PDF / EPUB… / ★ Sẽ đọc) cạnh ô tìm kiếm hay không |
| `default_cover_width` | Độ rộng bìa mặc định trong lưới, 60–240px. Tỉ lệ bìa cố định **1 : 1.42** |

**(c) Tùy chọn phong cách** (có từ bản 1.1, đã dùng cho 4 theme "mood").
Không bắt buộc; bỏ trống thì theme giữ kiểu mặc định:

| Tùy chọn | Giá trị |
|---|---|
| `font_families` | Danh sách font dự phòng, ví dụ `["Segoe UI", "Arial"]` |
| `font_weight` / `card_title_weight` | 100–900 (300 = mảnh) |
| `letter_spacing` | Phần trăm, 100 = bình thường |
| `label_style` | `normal` hoặc `code` (`// bộ_sưu_tập`) |
| `cover_radius` / `control_radius` / `panel_radius` | px |
| `cover_shadow` | `soft`, `warm` hoặc `none` |
| `cover_border_color` | hex hoặc bỏ trống |
| `cover_flat` / `cover_jacket_text` / `cover_text_color` | Bìa giả phẳng hay gradient; có in tên sách lên bìa không; màu chữ trên bìa |
| `card_selection` / `card_outline_width` | `outline` hoặc `glow`; độ dày viền |
| `selection_style` | `stripe`, `fill`, `outline` hoặc `underline` |
| `action_style` | `default`, `link`, `bracket` hoặc `soft` |
| `search_style` / `search_placeholder` | `box`, `pill` hoặc `underline`; chữ gợi ý |
| `add_button_label` / `brand_prefix` / `brand_caps` | Nhãn nút thêm; ký hiệu trước tên; tên viết hoa giãn chữ |
| `titlebar_text` | Thanh tiêu đề kiểu hệ điều hành cũ (bỏ trống = không có) |
| `grain_overlay` | Lớp hạt phim phủ cửa sổ |
| `motion_ms` / `text_glow` | Thời gian chuyển động hover/chọn (0 = tức thì); phát sáng nhẹ quanh chữ |
| `grid_layout` / `page_margin` / `card_gutter` | `uniform` hoặc `featured` (sách đầu trang hiện lớn); lề ngoài; khoảng cách thẻ |

Nếu thiết kế của bạn cần một kiểu bố cục **không có** trong bảng này (ví dụ
sidebar bên phải, hay kiểu kệ sách ngang), hãy đề xuất nó thành **một tùy
chọn mới có tên và các giá trị rõ ràng**, mô tả hành vi, và coi đó là việc
phát triển thêm. Không thiết kế lén bố cục mới bên trong một theme.

## 3. Yêu cầu bắt buộc

1. **Độ tương phản theo WCAG 2.x** (ứng dụng tự kiểm tra, theme không đạt
   sẽ bị từ chối):
   - Chữ thường ≥ **4.5 : 1**, áp dụng cho các cặp: `text`/`content_bg`,
     `sidebar_text`/`sidebar_bg`, `sidebar_text`/`header_bg`,
     `sidebar_text`/`surface`, `sidebar_text`/`background`,
     `panel_text`/`panel_bg`, `selected_text`/`selected_bg`.
   - Nhãn nút và chữ phụ ≥ **3 : 1**, áp dụng cho: `accent_text`/`accent`,
     `muted_text`/`sidebar_bg`, `muted_text`/`panel_bg`.
   - Ghi tỉ lệ tương phản thực tế của từng cặp vào bảng token bạn giao.
2. **Không đổi chức năng, chữ hay luồng thao tác.** Giữ nguyên mọi nút, menu
   và nhãn tiếng Việt hiện có. Theme chỉ đổi cách chúng trông.
3. **Sao đánh giá luôn màu vàng `#f5b301`, sao rỗng màu `#b0b0b0`.** Hai màu
   này dùng chung mọi theme. Hãy đảm bảo chúng vẫn đọc được trên
   `surface`/`content_bg` của bạn; nếu không, báo lại cho tôi.
4. **Trạng thái đầy đủ:** thường, di chuột, được chọn, chọn nhiều, vô hiệu,
   focus bàn phím, trống (thư viện chưa có sách), đang tải.
5. **Cả hai chế độ xem sách:** lưới bìa (thẻ gồm bìa, tên 2 dòng, tác giả 1
   dòng, ngôi sao "Sẽ đọc" ở góc) và danh sách dạng bảng (bìa nhỏ 32×46,
   cột Tiêu đề co giãn lấp đầy, các cột Tác giả / Định dạng / Dung lượng /
   Đánh giá TB / Ngày thêm).
6. **Bìa giả phải đẹp:** nhiều sách không có ảnh bìa, nên bìa giả (nền
   gradient, tên và tác giả in trên bìa, dải gáy) sẽ xuất hiện rất nhiều.
7. **Cỡ chữ và font:** thiết kế ở cỡ **10pt cho giao diện** và **13pt cho nội
   dung** (người dùng tự chỉnh được). Chỉ dùng font có sẵn trên Windows 10/11
   (Segoe UI, Cambria, Georgia, Times New Roman, Consolas…). Nếu muốn dùng
   font khác, nó phải miễn phí và cho phép nhúng vào phần mềm thương mại
   (ví dụ SIL OFL), và phải nêu tên font kèm giấy phép.
8. **Hỗ trợ màn hình DPI 100% / 150% / 200%**, cửa sổ nhỏ nhất 1024×640.

## 4. Các màn hình cần mockup (mỗi theme)

1. Cửa sổ chính, **lưới bìa**, có một sách đang được chọn (kèm panel chi
   tiết **hoặc** thanh thao tác, tùy `layout_mode`).
2. Cửa sổ chính, **danh sách dạng bảng**, có nhiều dòng được chọn.
3. Sidebar ở trạng thái đang chọn một bộ sưu tập (hoặc flyout mở ra nếu là
   thanh icon).
4. Hộp thoại **Đánh giá**: điểm trung bình kèm sao, danh sách đánh giá với
   sao vàng, nhãn "Bạn" cho bài của chính mình, ngày, "(đã sửa)", và form
   viết đánh giá.
5. Hộp thoại **Tóm tắt AI**: ô nội dung gửi đi, chọn "Kiểu tóm tắt" / "Độ
   dài" / "Ngôn ngữ", ô kết quả, nút "✨ Tạo tóm tắt" và "💾 Lưu tóm tắt".
6. Hộp thoại **Tìm ảnh bìa**: lưới ảnh kết quả, nhãn nguồn, "khớp NN%".
7. **Cài đặt** (một tab bất kỳ) và **một menu đang mở**.
8. Trạng thái **thư viện trống**.

## 5. Ràng buộc kỹ thuật của Qt (đừng thiết kế thứ không làm được)

- Làm được: màu nền và chữ, viền (kể cả bo góc), padding, gradient tuyến
  tính, icon PNG/SVG, đổ bóng **chỉ ở bìa sách** (vẽ tay), thanh cuộn mảnh.
- **Không làm được hoặc rất tốn kém:** làm mờ nền (blur, acrylic, glass),
  hiệu ứng trong suốt nhìn xuyên cửa sổ, animation phức tạp, đổ bóng cho
  mọi widget, font biến thiên, CSS grid/flex. Nếu bắt buộc phải dùng hiệu
  ứng nào trong số này, đánh dấu là "tùy chọn, có thể bỏ".
- Icon: giao file **SVG nét đơn**, không dùng emoji thay icon trong thiết kế
  mới. Cỡ 16/20/24px, nét 1.5px, màu lấy theo token để đổi theme được.

## 6. Định dạng bàn giao (bắt buộc)

Với mỗi theme, giao:

1. **Tên theme** (tiếng Anh, 1–3 từ) và **khóa** viết thường không dấu, ví
   dụ `sakura_paper`.
2. **Khối token** đúng cấu trúc sau, đủ mọi trường:

```json
{
  "key": "sakura_paper",
  "display_name": "Sakura Paper",
  "background": "#......", "surface": "#......", "header_bg": "#......",
  "content_bg": "#......", "text": "#......",
  "sidebar_bg": "#......", "sidebar_text": "#......",
  "panel_bg": "#......", "panel_text": "#......",
  "muted_text": "#......", "border": "rgba(0,0,0,.12)",
  "accent": "#......", "accent_text": "#......",
  "selected_bg": "#......", "selected_border": "#......", "selected_text": "#......",
  "cover_gradients": [["#......", "#......"], ["#......", "#......"]],
  "cover_spine": [0, 0, 0, 55],
  "default_cover_width": 120,
  "layout_mode": "detail_panel",
  "icon_rail_sidebar": false,
  "sidebar_style": "plain",
  "library_heading": "Bộ sưu tập",
  "all_items_label": "Tất cả tài liệu",
  "header_add_button": false,
  "show_cover_size_slider": true,
  "show_filter_chips": false
}
```

3. **Bảng tương phản** cho 10 cặp màu ở mục 3.1 (tỉ lệ đạt được).
4. **Mockup PNG** cho 8 màn hình ở mục 4, ở cỡ 1440×900.
5. **Ghi chú chi tiết** cho những thứ không suy ra được từ token: bo góc
   (px), padding thẻ sách, độ dày viền được chọn, kiểu thanh cuộn, và kiểu
   icon.
6. Nếu có: **đề xuất tùy chọn bố cục mới** (xem cuối mục 2) và **file font,
   icon** kèm giấy phép.

Ngoài bảng token, **không** giao code Python, QSS hay CSS. Tôi sẽ tự cài
theme vào ứng dụng; ứng dụng tự kiểm tra từng theme (màu hợp lệ, tùy chọn
hợp lệ, độ tương phản) và tự dựng thử cửa sổ chính ở theme đó.
