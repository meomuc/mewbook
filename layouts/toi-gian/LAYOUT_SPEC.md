# Kiểu giao diện "Tối giản" (id: toi-gian) — đặc tả cho Claude Code

Kiểu này thay BỐ CỤC và HÌNH KHỐI; mọi chức năng, chữ, hộp thoại, quy tắc an toàn
giữ nguyên như kiểu "Kệ sách". Không nhân đôi logic: tầng Application/Domain dùng
chung, chỉ tầng Presentation có hai bộ widget/delegate (hoặc một bộ đọc `LayoutSpec`).

## 1. Khung chung
- Nền cửa sổ = token `bg` (màu phông nền ngoài). Nội dung nằm trên một TẤM NỀN
  (`panel`) bo góc `sheet_radius` 26 px, cách mép `sheet_margin_x` 22 / `sheet_margin_y` 14,
  bóng mềm (`shadow`) + viền 1 px `line`.
- Thanh tiêu đề cửa sổ và thanh trạng thái nằm NGOÀI tấm nền, nền trong suốt (`rail` = `bg`).
- Mọi nút, ô nhập, chip, dropdown dạng viên thuốc (`control_radius` 999).
  Thẻ bo 18, hộp thoại bo 22, bìa bo 2/3 px.
- Không trang trí gỗ/bảng phấn: `ornaments: ignore` — bỏ qua khối ornaments của theme.
- Nhãn khu vực là CHỮ DỌC (xoay 90°, phông nội dung 14 px) đặt sát bên trái khu vực.
- Tiêu đề lớn phông nội dung 46 px (Trang đầu) / 30 px (Thư viện), độ đậm 500.
- Chữ in hoa giãn chỉ dùng cho chữ "MEWBOOK" ở logo; nhãn nhóm, tiêu đề cột viết thường.

## 2. Thanh trên (72 px, trong tấm nền)
Logo MEWBOOK + "Mèo Mực" · giữa: 4 mục dạng viên thuốc có icon — Trang đầu, Thư viện,
Sẽ đọc, Bộ sưu tập (mục đang mở tô `accent`, chữ `accentink`) · phải: "+ Thêm sách"
(viền), Công cụ (✦: Phân loại thông minh, Dọn tên tác giả, Tìm file trùng, Tìm lại file,
Gửi sang máy đọc), Cài đặt ⚙, ⋯ (Sao lưu, Quyền riêng tư, Giới thiệu).
Dưới 1100 px: ẩn mục "Bộ sưu tập" vào ⋯, "Thêm sách" rút thành "Thêm".

## 3. Trang đầu (MỚI — màn hình mở mặc định của kiểu này) — preview/01, 06, 07
- Trái: tiêu đề "Đọc tiếp & Mới thêm", dòng phụ "7.545 tài liệu, tất cả nằm trên máy bạn",
  ô tìm kiếm chính (viên thuốc, có gợi ý → chip lọc như kiểu Kệ sách; Enter chuyển sang
  màn Thư viện với bộ lọc đó), 3–4 chip lối tắt (hashtag nhiều nhất, định dạng nhiều nhất,
  Chưa phân loại, Sẽ đọc).
- Giữa: BÌA ĐANG ĐỌC (sách mở gần nhất) cao `hero_cover_height` 350, đứng trên THANH KỆ;
  trên bìa: "Đang đọc · trang 57 / 248". Bấm = mở cửa sổ đọc đúng trang. Chưa đọc cuốn
  nào → hiện cuốn mới thêm gần nhất với chữ "Mới thêm".
- Phải: thẻ "Tác giả của tháng" (nền `accent`): tác giả có nhiều tài liệu được thêm/mở
  nhất trong 30 ngày, số tài liệu, "Xem sách" (= Thư viện + chip Tác giả), 3 bìa xếp chồng.
  Thẻ "Đọc gần đây": tên, tác giả, bìa tròn, thanh tiến độ trang, ‹ Đọc tiếp › (‹ › đổi
  sang cuốn đọc trước/sau trong lịch sử). Không có ảnh chân dung tác giả — không tải ảnh
  người từ Internet.
- THANH KỆ: dày `ledge_thickness` 18, thò ra ngoài tấm nền `ledge_overhang` 18 mỗi bên,
  gradient `shelftop`→`shelf`, bóng đổ xuống.
- Dưới kệ: nhãn dọc "Mới thêm tuần này" + 4 mục (bìa 128 + sao + tên + tác giả + nút viền
  "Đọc"); mục thứ 5 nghiêng 6° thò ra mép phải như gợi ý "còn nữa". "Xem cả thư viện" góc
  dưới phải.
- Thư viện trống (preview/06): tiêu đề "Thư viện đang trống", nút Thêm thư mục sách /
  Nhập từ Calibre, tranh cat_read đứng trên kệ, dưới kệ 3 thẻ Bắt đầu.
- 1024×640 (preview/07): bìa 230, ẩn thẻ "Đọc gần đây", 3 mục dưới kệ.

## 4. Thư viện — preview/02 (lưới), 03 (bảng)
- Cột lọc trái 216 px, KHÔNG viền: ô "Lọc nhanh…", nhóm Thư viện / Bộ sưu tập (⚡ theo
  luật) / Tác giả (top 8 + Xem tất cả…) / Hashtag / Định dạng; mục đang chọn = nền
  `accentsoft` viên thuốc. Số đếm khớp bộ lọc, không có lựa chọn dẫn tới rỗng.
- Đầu vùng giữa: "Thư viện" 30 px + "31 / 7.545 tài liệu" · ô tìm · Lưới/Bảng · Sắp xếp.
  Hàng chip "Đang lọc" (nền `surface2`, ×), "Xóa lọc", "Lưu thành bộ sưu tập".
- Lưới: 5 cột ở 1600 px, bìa ~168, dưới bìa: sao, tên (2 dòng), tác giả. Chọn = viền
  `accent` cách 4 px. Nhãn định dạng, sao "Sẽ đọc", "⚠ Không thấy file", bìa giả — như
  kiểu Kệ sách. Không vẽ vạch kệ trong lưới.
- Bảng: dòng 56 px, dòng chọn nền `accentsoft` bo tròn hai đầu, tiêu đề cột chữ thường.
- Panel chi tiết 320 px: thẻ bo 20 nền `surface2` bên trong tấm nền; bìa lớn (Bấm để
  đọc), hàng nút Đọc (chính) + ★ + Đổi bìa + Tìm thông tin + Gửi máy đọc (icon, có
  tooltip), Tiêu đề/Tác giả/Hashtag sửa tại chỗ (viền đứt + bút; đang sửa viền liền),
  thông tin chỉ đọc, Tóm tắt AI, ⟳ làm mới. Dưới 1200 px: panel thành lớp phủ trượt từ phải.
- Màn "Sẽ đọc" và "Bộ sưu tập" = màn Thư viện với bộ lọc tương ứng đã bật.

## 5. Hộp thoại, Cài đặt, cửa sổ đọc, trạng thái
- Mọi hộp thoại giữ NỘI DUNG như bộ thiết kế Kệ sách (Tìm thông tin sách, Đổi ảnh bìa,
  Tìm file trùng, Xác nhận xóa, Phân loại thông minh, Tìm lại file, Đánh giá, Dọn tên tác
  giả, Bộ sưu tập theo luật, Gửi máy đọc); chỉ đổi hình khối: bo 22, tiêu đề 22 px không
  gạch dưới, nút viên thuốc, chân hộp thoại nền trong suốt + vạch trên (preview/04).
- Cài đặt (preview/05): cửa sổ cũng dùng tấm nền; cột trái là danh sách icon + chữ
  (mục chọn nền `accentsoft`). Tab Giao diện có HAI LỚP CHỌN:
  1) Kiểu giao diện: thẻ Kệ sách / Tối giản (hình thu nhỏ vẽ bằng token).
  2) Bảng màu cho kiểu đang chọn: chỉ hiện theme dùng được với kiểu đó, kèm nhãn ngắn.
  Ghi chú liệt kê các theme chỉ dùng ở kiểu kia + liên kết chuyển kiểu.
  Khi đổi kiểu mà theme hiện tại không hợp → tự chuyển sang `default_theme` của kiểu mới
  và nhớ lựa chọn cũ để quay lại. Lưu cặp (layout_id, theme_id) trong cấu hình.
- Cửa sổ đọc: giữ bố cục, bo góc viên thuốc cho thanh công cụ.
- Trạng thái trống/chờ/xong/lỗi: cùng 7 tranh Mèo Mực, đặt giữa tấm nền.
- Thanh trạng thái: giữ ba vùng và luật co giãn; nhãn vùng viết thường; huy hiệu ✓ ○ ✕;
  sao đánh giá dùng `accent` (không phải màu trạng thái).

## 6. Theme dùng được (trong layout.json)
| Theme | Nhãn | Chỉnh riêng khi ở Tối giản |
|---|---|---|
| Japandi Tối Giản (mặc định) | Gần ảnh mẫu nhất | nền kem đào #EFE3D3, tấm nền #FAF7F2, accent caramel #B07A36 + chữ trên accent tối, token `link` #7A531F cho liên kết, warn #7D7A00 để khác caramel |
| Editorial Light | Sáng, mát | nền xám #E7E8EA, tấm nền trắng |
| Zen Dark Mode | Tối, ấm | nền #141613, tấm nền #1F221E |
| Midnight Ink | Tối, lạnh | nền #15181E, tấm nền #20252E |
Theme khác vẫn tự "đăng ký" được sau này bằng khối `layouts.toi-gian` trong theme.json.
