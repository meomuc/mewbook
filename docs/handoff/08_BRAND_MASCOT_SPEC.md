# 08 — Nhận diện thương hiệu và linh vật Mèo Mực (Epic I)

- **Chặng:** BR-A (đường ống ảnh và thành phần giao diện, gói trong 1.1.0 sau S0); phần gắn vào từng màn hình đi cùng tính năng tương ứng (S3, S4…).
- **Nguyên tắc chi phối:** *Mèo xuất hiện khi người dùng đang chờ, khi không có gì để hiển thị, khi mọi việc đã xong hoặc khi có lỗi. Mèo không bao giờ xuất hiện khi người dùng đang tập trung làm việc.*
- Tài liệu mô tả thiết kế, không chứa mã thực thi. Đọc cùng `docs/THEME_DESIGN_BRIEF.md` và `test_theme_contract.py` của repo.

## 1. Mục tiêu

1. Biến bộ tranh Mèo Mực thành **hệ nhận diện nhất quán**: một logo cố định, sáu biểu cảm gắn với sáu trạng thái quen thuộc.
2. **Hài hước tinh tế:** một câu đùa nhẹ đi kèm **một hướng dẫn rõ ràng**; không bao giờ đùa trên việc mất dữ liệu hay xác nhận xóa.
3. Dùng được cho cộng đồng và đối tác: mọi thứ đi qua **một bảng khai báo** (manifest) để sau này thay đổi/đồng thương hiệu (D9) mà không sửa mã.
4. Không làm nặng ứng dụng: **tải muộn**, tổng tài nguyên nhỏ, tắt được.

## 2. Thương hiệu tóm tắt

| Mục | Nội dung |
|---|---|
| Tên | **MewBook** (kỹ thuật, tên gói, kho mã) · **Mèo Mực** (tên hiển thị trong ứng dụng); quy ước ghi ở `docs/NAMING.md` (S0-11) |
| Linh vật | Chú mèo cam, luôn thấy **từ phía sau**, đang làm việc gì đó: đọc, tìm, nghĩ, chờ, nghỉ, buồn, gõ code |
| Tính cách | Điềm tĩnh, chăm chỉ, hơi lười biếng dễ thương; không ồn ào, không thúc giục |
| Bảng màu (đo từ `logo.png`, xấp xỉ) | Cam Mực `#DA7E4A` · Cam đậm `#C66A3F` · Nét viền `#3A3941` · Kem giấy `#D9C0A7` · Nâu ấm `#60504E` |
| Phong cách vẽ | Nét viền đậm, màu phẳng, bóng đổ nhẹ, hình khối tròn |
| Khẩu hiệu (chọn 1, **O14**) | (1) "Kệ sách gọn gàng, mèo giữ giúp bạn." · (2) "Sách của bạn, đúng chỗ, đúng máy." · (3) "Đọc thong thả, việc còn lại để mèo lo." |

## 3. Kiểm kê hình ảnh và vấn đề cần xử lý

Kết quả kiểm tra trực tiếp các file (kênh alpha, kích thước, nội dung):

| File | Kích thước | Loại | Nội dung | Vấn đề | Hành động |
|---|---|---|---|---|---|
| `logo.png` | 2048×2048 | Hình cắt rời | Mèo ngồi đọc sách trên tấm thảm xám | **Không có alpha thật**: ô caro xám-trắng vẽ dính vào ảnh (ô ≈ 51 px, màu ≈ `#F8F8F8` và `#C8C8C8`). Có một dấu sao 4 cánh rất mờ ở góc dưới phải (xem O12). Nặng ≈ 5,2 MB | Tách nền, cắt sát, xuất kích thước nhỏ (BR-02); logo chính thức |
| `cat_read.png` | 616×622 | Hình cắt rời | Cùng tranh với logo (nét viền thô hơn) | Trùng tư thế với logo; ô caro dính | **Không đóng gói**; giữ làm tài liệu tham khảo |
| `cat_read_2.png` | 616×556 | Hình cắt rời | Cùng tranh với `cat_read.png`, khác vùng cắt | Trùng lặp | **Không đóng gói** |
| `cat_AI.png` | 642×618 | Hình cắt rời | Mèo chống cằm nhìn mạng nơ-ron và dãy số nhị phân | Ô caro dính; **các vùng trong đồ thị nơ-ron còn ô caro khép kín**; các quầng sáng xanh bán trong suốt đã trộn với ô caro nên không tách sạch | Tách hai lượt (BR-02); quầng sáng phải **vẽ lại hoặc bỏ** (O13) |
| `cat_research.png` | 614×622 | Hình cắt rời | Mèo cầm kính lúp soi tấm bản đồ, ngồi trên chồng sách và cuộn giấy | Ô caro dính | Tách nền tự động được |
| `cat_dev.png` | 646×622 | Hình cắt rời, **bị cắt mép** | Mèo đeo tai nghe gõ code, màn hình, bàn, ghế | Mép phải và mép dưới của cảnh bị cắt bởi khung ảnh; **chữ trên màn hình không đọc được** (chuỗi ký tự vô nghĩa) | Dùng trong **thẻ có bo góc** (không thả nổi); không phóng to quá ≈ 320 px; đề nghị vẽ lại với chữ thật, ví dụ lệnh `uv run smartdoc` (O13) |
| `cat_coffee.png` | 616×666 | **Cảnh có nền** | Mèo ngồi quán cà phê nhìn ra cửa sổ, tách cà phê bốc khói | Không có alpha; còn vài ô caro ở mép ảnh | Cắt lề, đặt trong thẻ bo góc |
| `cat_retire.png` | 616×622 | **Cảnh có nền** | Mèo nằm dang tay chân trên chiếu ngoài vườn, nhìn từ trên xuống | Còn ô caro ở mép trên | Cắt lề, đặt trong thẻ bo góc |
| `cat_sad.png` | 426×422 | **Cảnh có nền** | Mèo cúi đầu ngồi dưới mưa, cây dù cụp bên cạnh | Độ phân giải thấp nhất; kênh alpha có nhưng đục hoàn toàn | Chỉ dùng cỡ nhỏ (≤ 200 px) hoặc xin ảnh gốc tốt hơn (O13) |

**Đã thử nghiệm khả thi:** loại các điểm ảnh gần trắng/xám trung tính (max ≥ 185, độ sắc ≤ 22) liên thông với mép ảnh cho kết quả sạch với `logo.png`, `cat_read`, `cat_dev`; `cat_AI` còn ô caro khép kín và quầng sáng.

**Đã có sẵn trong ứng dụng (từ `CHANGELOG.md`):** `packaging/process_brand_icon.py` (tách nền caro giả bằng độ bão hòa, cắt vuông, phủ mặt nạ bo góc) sinh `app_icon.ico` nhiều cỡ và `brand_logo.png`; tiêu đề thương hiệu ở thanh bên (logo + tên); hộp thoại Giới thiệu; hộp thoại EULA/Quyền riêng tư; `donate_dialog` (mã QR ủng hộ). **Đường ống mới phải mở rộng những thứ này, không viết trùng.**

## 4. Bản đồ áp dụng: hình nào cho chức năng nào

Chọn theo **cảm xúc của trạng thái**, không theo trang trí.

| Biểu cảm | Ảnh | Ý nghĩa |
|---|---|---|
| **Đọc** (thương hiệu, mặc định) | `logo.png` | Bản sắc cố định |
| **Suy nghĩ** | `cat_AI.png` | Máy đang tính toán, học |
| **Tìm kiếm** | `cat_research.png` | Tra cứu, lục kệ |
| **Chờ thong thả** | `cat_coffee.png` | Việc dài đang chạy, đang đợi |
| **Xong, thư giãn** | `cat_retire.png` | Mọi thứ khớp, không còn việc |
| **Buồn, gặp sự cố** | `cat_sad.png` | Lỗi nhẹ, mất kết nối |
| **Kỹ thuật, đóng góp** | `cat_dev.png` | Người làm đang gõ code |

### 4.1 Bảng áp dụng chi tiết

| Ảnh | Chức năng và màn hình | Kích hoạt khi | Cỡ | Lời nhắn (giọng dí dỏm) | Vì sao hợp |
|---|---|---|---|---|---|
| `logo.png` | **Biểu tượng ứng dụng** (`.ico` nhiều cỡ), **hộp thoại Giới thiệu**, ảnh trang bìa trình cài đặt, avatar/ảnh xã hội, đầu README | Luôn (không dùng làm ảnh chào lúc khởi động: nguyên tắc "không tải gì lúc khởi động") | 16–256 px; hero 320 px | "Mèo Mực · MewBook {version}" | Tư thế đọc sách là chính công việc của ứng dụng |
| `logo.png` (biểu cảm "đọc") | **Panel chi tiết khi chưa chọn sách nào**; **lần chạy đầu khi thư viện trống** | Không có sách được chọn; thư viện chưa có gì | 120–160 px | Panel: "Chọn một cuốn để xem chi tiết." · Thư viện trống: "Chưa có sách nào. Thêm một thư mục, mèo sẽ lo phần còn lại." [Thêm thư mục…] | Lời mời bắt đầu, trung tính, thân thiện |
| `cat_research.png` | **Tìm metadata** (tiêu đề hộp thoại, trạng thái đang tra cứu và không có kết quả), **tìm bìa sách** (không có kết quả), **ô tìm kiếm chính không có kết quả**, **Duplicate Finder** khi đang quét | Đang tra cứu; kết quả rỗng | 140–200 px | Đang tra: "Mèo đang lục kệ…" · Rỗng: "Mèo lục cả kệ mà không thấy “{q}”. Thử bỏ dấu hoặc bớt từ khóa?" | Kính lúp và bản đồ là hình ảnh trực quan nhất của "tìm" |
| `cat_AI.png` | **Tóm tắt AI** (đang tạo), **Phân loại thông minh** (hộp thoại xác nhận, đang chạy, kết quả), **Cài đặt → nhà cung cấp AI** (đầu trang) | Đang xử lý bằng mô hình; kết thúc phân loại | 120–180 px | Tóm tắt: "Mèo đang suy nghĩ… thường mất vài giây." · Phân loại xong: "Mèo đã xếp {n} cuốn vào đúng kệ. Không ưng? Bấm Hoàn tác." | Tay chống cằm, mạng nơ-ron: hình ảnh của "đang nghĩ" |
| `cat_coffee.png` | **Tác vụ dài** (quét thư mục lớn, nhập từ Calibre, quét thiết bị chậm qua MTP, chuyển đổi hàng loạt); **màn "Thiết bị" khi chưa thấy thiết bị nào**; **trang Ủng hộ dự án** trong About | Việc chạy quá 3 giây; chưa có thiết bị; người dùng mở trang Ủng hộ | 160–220 px; thu nhỏ khi cửa sổ thấp | Việc dài: "Mèo lo phần việc nặng. Bạn cứ nhâm nhi cà phê." · Chờ thiết bị: "Mèo đang đợi máy đọc ghé chơi. Cắm cáp USB hoặc thẻ nhớ nhé." · Ủng hộ: "Mời mèo một ly cà phê ☕ — dự án miễn phí nhờ cộng đồng." | Tách cà phê là **motif chờ đợi**; cũng là ngôn ngữ quen thuộc của việc ủng hộ |
| `cat_retire.png` | **Đồng bộ đã khớp hết** (Bảng đồng bộ: không còn việc), **kết thúc lô nhập/phân loại/chuyển đổi**, **Duplicate Finder không có bản trùng** | Không còn mục cần xử lý; việc hoàn tất thành công | 160–200 px | Đã khớp: "Xong hết rồi. Mèo đi phơi nắng đây." · Sạch: "Không có bản trùng nào. Thư viện sạch bóng." | Nằm dang tay dưới nắng = "không còn gì phải lo". **Không** dùng cho lời ủng hộ để tránh hiểu nhầm "dự án sắp nghỉ hưu" |
| `cat_sad.png` | **Thiết bị bị ngắt kết nối giữa chừng**, **đồng bộ/gửi thất bại**, **dịch vụ đánh giá tạm thời không khả dụng**, **không có mạng khi tìm bìa**, **hộp thoại lỗi bất ngờ** (crash) | Có lỗi không nghiêm trọng đến dữ liệu, hoặc lỗi bất ngờ | 96–160 px (ảnh gốc nhỏ) | Mất thiết bị: "Thiết bị vừa rút cáp, mèo chưa kịp mở ô. Đã chép {n} sách, chưa chép {m} sách." · Dịch vụ: "Dịch vụ đánh giá đang nghỉ mưa. Các chức năng khác vẫn dùng bình thường." · Crash: "Có lỗi bất ngờ. Nhật ký đã được ghi lại; bấm để sao chép thông tin hỗ trợ." | Trời mưa, cây dù cụp: nhẹ nhàng, có hướng xử lý ngay sau câu đùa |
| `cat_dev.png` | **Giới thiệu → Nhóm phát triển**, **Sao chép thông tin hỗ trợ / nhật ký**, **Hướng dẫn thêm hồ sơ thiết bị** (Cài đặt → Thiết bị), `CONTRIBUTING.md`, `PARTNERS.md` | Người dùng chủ động tìm tới khu vực kỹ thuật/đóng góp | 160–240 px trong thẻ | "Mèo đang gõ code. Bạn có thiết bị mới? Thêm một tệp hồ sơ là được." | Tai nghe và màn hình hợp với vai người làm; mời cộng đồng tham gia mà không ép |

### 4.2 Nơi **không** dùng mèo

- Hộp thoại xác nhận **xóa**, ghi đè, khôi phục sao lưu, thay thế file (nghiêm túc, không tô vẽ).
- Trong luồng đang gõ/chọn (danh sách, biểu mẫu chỉnh sửa metadata, ô tìm kiếm khi có kết quả).
- Lỗi liên quan mất dữ liệu (dùng câu chữ rõ ràng, không đùa).
- Thanh trạng thái nhỏ và tooltip.
- Không quá **một hình mèo mỗi màn hình**.

### 4.3 Nguyên tắc lời nhắn (giọng Mèo Mực)

1. **Ngắn:** tối đa hai câu.
2. **Một nhịp đùa, một hướng dẫn:** câu đầu nhẹ nhàng (mèo làm gì), câu sau nói điều người dùng cần làm hoặc kết quả cụ thể.
3. **Đúng sự thật trước, dễ thương sau:** con số, tên thiết bị, trạng thái luôn chính xác.
4. Không viết hoa toàn bộ, không quá hai biểu tượng cảm xúc, không tiếng lóng khó hiểu.
5. Có **bản trung tính** cho từng câu (dùng khi người dùng chọn giọng "Trung tính"); ví dụ: "Không tìm thấy “{q}”. Thử bỏ dấu hoặc bớt từ khóa." Bảng đôi (dí dỏm/trung tính) nằm trong một module chuỗi duy nhất để S4 (i18n) dịch được.

### 4.4 Hiện trạng cần tôn trọng và cách điều chỉnh

| Hiện có | Điều chỉnh |
|---|---|
| Biểu tượng `.ico` là mèo đọc sách trong khung bo góc viền chuyển màu | Giữ hoặc thay bằng hình cắt rời: **O17**. Với `.ico` ≤ 32 px, khung bo góc thường dễ đọc hơn |
| Tiêu đề thương hiệu ở thanh bên (logo + tên) | Dùng `brand_logo.png` mới xử lý; không thêm hình mèo thứ hai vào cùng màn hình |
| Hộp thoại ủng hộ có mã QR (`donate_dialog`) | Thêm `cat_coffee` phía trên mã QR, lời nhắn "Mời mèo một ly cà phê ☕ — dự án miễn phí nhờ cộng đồng."; không tạo trang ủng hộ thứ hai |
| Dải chữ chạy "donate" ở thanh trạng thái | Đề xuất **chữ tĩnh, tắt được** trong Cài đặt (**O18**), vì chuyển động liên tục làm phiền người đang tập trung |
| Hộp thoại EULA/Quyền riêng tư chặn lần chạy đầu | Viết lại thành thông báo giấy phép AGPL + quyền riêng tư (S0-05). Có thể dùng biểu cảm `logo` cỡ nhỏ; **không** dùng `cat_sad`, không đùa trong văn bản pháp lý |
| Dòng ghi tác giả "Auth:Anhtiensinh" ở thanh trạng thái | Thống nhất với thông báo bản quyền trong Giới thiệu (S0-06) |

## 5. Bộ thành phần giao diện

| Thành phần | Trách nhiệm |
|---|---|
| **`BrandAssets`** (`presentation/brand.py`) | Đọc bảng khai báo, cung cấp ảnh theo **vai trò** và kích thước (kèm hệ số DPI), tải muộn, bộ nhớ đệm có giới hạn; không tải gì khi khởi động |
| **`MascotBanner`** (`presentation/mascot_banner.py`) | Widget dùng lại: [ảnh] + tiêu đề + lời nhắn + nút hành động (tùy chọn); có kiểu **đầy đủ** và **gọn**; tự chuyển sang gọn hoặc ẩn ảnh khi cửa sổ thấp (< 640 px) |
| **Sổ trạng thái** | Bản đồ khóa trạng thái → (vai trò ảnh, khóa chuỗi dí dỏm, khóa chuỗi trung tính) để mọi màn hình dùng chung, tránh rải rác |
| **Bảng khai báo** (`src/smartdoc/data/brand/brand.json`) | Mỗi vai trò: tệp, loại (`cutout`/`scene`), cỡ mặc định, tên hiển thị cho trình đọc màn hình (tiếng Việt), nơi dùng |

- Widget mới đặt `color` cùng `background` trong stylesheet (quy ước hiện có).
- Sự kiện đổi theme làm `MascotBanner` cập nhật khung viền; **không** rẽ nhánh theo khóa theme.
- Mọi lời nhắn đi qua module chuỗi; không viết cứng trong widget.

## 6. Tích hợp giao diện `ThemeColors`

Thêm tùy chọn (mặc định làm hành vi hiện tại **không đổi**, tức chưa hiện mèo):

| Tùy chọn | Ý nghĩa | Giá trị |
|---|---|---|
| `mascot_frame` | Khung cho ảnh | `none` · `card` (thẻ nền có bo góc) · `sticker` (viền trắng dày và bóng nhẹ, cho hình cắt rời) |
| `mascot_card_radius` | Bo góc thẻ | số, lấy từ bán kính theme |
| `mascot_shadow` | Bóng | `none` · `soft` |
| `mascot_dim` | Làm tối ảnh cảnh trên theme tối để không có mảng trắng chói | 0.0–0.15 |

**Gợi ý theo theme** (để Claude Code khởi tạo, chủ dự án tinh chỉnh):

| Theme | Khung | Ghi chú |
|---|---|---|
| Ba theme gốc (sáng) | `card` | Nền thẻ theo `ThemeColors` |
| Không Gian Chữa Lành (Cottagecore) | `card`, bóng mềm | Hợp bảng màu kem và xanh xô thơm |
| Hoài Niệm Kỹ Thuật Số (Lo-Fi Retro-Tech) | `card`, viền cứng | Lời nhắn theo kiểu `// mèo_đang_nghĩ` nếu theme yêu cầu chữ đơn cách; ảnh giữ nguyên |
| Japandi Tối Giản | `card` phẳng, không bóng | Ít hiệu ứng |
| Zen Dark | `card`, `mascot_dim` khoảng 0.10 | Tránh mảng sáng chói trên nền xanh đậm |

- **Chữ luôn do Qt vẽ** (không nướng chữ vào ảnh) và phải đạt tương phản WCAG trên nền thẻ; `test_theme_contract.py` phải kiểm tự động các tùy chọn mới cho mọi theme.
- Hình cắt rời (`logo`, `cat_AI`, `cat_research`, `cat_dev`) dùng `sticker` trên nền tối hoặc nền màu, `none`/`card` trên nền sáng.

## 7. Đường ống xử lý ảnh (BR-A)

**Nguyên tắc:** ảnh gốc là đầu vào, ảnh đóng gói là đầu ra tái tạo được; công cụ xử lý **không nằm trong gói `src/smartdoc`** (không kéo numpy/scipy vào tiến trình giao diện, đúng guardrail hiện có).

**Công cụ xử lý ảnh** (mở rộng `packaging/process_brand_icon.py` hoặc thêm `tools/prepare_brand_assets.py` cạnh nó, Claude Code chọn theo mã hiện có; chạy tay, không đóng gói):
1. **Lượt 1:** loại các điểm ảnh gần trắng/xám trung tính liên thông với mép ảnh (ngưỡng đề xuất: max ≥ 185, chênh kênh ≤ 22), làm mềm mép ≈ 0,8 px.
2. **Lượt 2 (ô caro khép kín):** loại các điểm ảnh trùng **đúng hai màu ô caro** (±6) nằm trong vùng khép kín và không thuộc bảng màu linh vật.
3. Bỏ viền mờ sát mép bằng cách co 1 px vùng nền.
4. **Cắt sát** khung chữ nhật của mèo (kèm lề), loại luôn vùng có dấu sao ở góc.
5. **Cảnh có nền** (`cat_coffee`, `cat_retire`, `cat_sad`): cắt lề vài điểm ảnh để bỏ ô caro ở mép; giữ nền.
6. Xuất `@1x` và `@2x` theo cỡ trong bảng khai báo; tối ưu PNG (bảng màu giới hạn cho cảnh nếu chất lượng đạt).
7. Tạo báo cáo (`docs/brand/asset_report.md`): kích thước, tỉ lệ điểm ảnh trong suốt, **số điểm ảnh ô caro còn sót (phải bằng 0)**, dung lượng.

**Ngân sách đóng gói (đề xuất):** tổng ≤ 1,5 MB; mỗi tệp ≤ 250 KB ở @2x; logo gốc 2048 px giữ ngoài kho mã.

**Ảnh gốc:** để **ngoài** kho mã (hoặc trong thư mục không đóng gói như `assets-src/brand/original/`), ghi nguồn trong `docs/brand/PROVENANCE.md`.

**Biểu tượng ứng dụng:** `process_brand_icon.py` đã sinh `app_icon.ico` từ bản khung bo góc. Quyết định giữ khung hay chuyển sang hình cắt rời của `logo.png` thuộc **O17**. Dù chọn hướng nào, kiểm tra độ đọc ở 16, 24, 32, 48 và 256 px; ở cỡ ≤ 32 px dùng **bản giản lược** (đầu mèo và cuốn sách, bỏ tấm thảm). Giữ `generate_icon.py` làm dự phòng như hiện nay.

**Nội dung đề nghị vẽ thêm (không chặn phát hành):**
1. Mèo ôm sách chạy sang máy đọc (đồng bộ/gửi sách).
2. Mèo đan len biến hai loại sợi thành một (chuyển đổi định dạng).
3. (Tùy chọn) Bộ sticker cho cộng đồng: các biểu cảm trên có viền trắng dày, xuất PNG/WebP cho Zalo/Telegram (chưa cần làm sớm).
Yêu cầu chung cho ảnh mới: cùng phong cách và bảng màu, **nền trong suốt thật** (hoặc nền đơn sắc dễ tách), ≥ 1024 px, nhìn từ phía sau.

## 8. Giấy phép, nguồn gốc và thương hiệu

- **Tranh không thuộc AGPL-3.0.** Đề xuất (O11): tranh và logo thuộc bản quyền chủ dự án; cho phép dùng **nguyên bản** cùng MewBook và trong tài liệu liên quan theo `TRADEMARK.md`; không cho phép dùng cho sản phẩm khác hoặc sửa đổi để gây nhầm lẫn. Viết vào `src/smartdoc/data/brand/LICENSE-ART.md` và nêu trong `LICENSE`/`NOTICE`, `THIRD_PARTY_NOTICES.md`.
- **Nguồn gốc ảnh (O12):** các ảnh có dáng vẻ do công cụ tạo ảnh AI tạo ra (logo có dấu sao 4 cánh rất mờ ở góc dưới phải, giống dấu của công cụ; ô caro "giả trong suốt" là dấu hiệu thường gặp). Chủ dự án cần: (a) xác nhận công cụ đã dùng và **điều khoản dùng thương mại và phân phối mã nguồn mở**; (b) lưu bằng chứng (`PROVENANCE.md`). Cắt sát logo sẽ loại phần góc, nhưng **không thay thế** việc kiểm tra điều khoản.
- **Câu hỏi cho luật sư:** quyền tác giả của ảnh do AI tạo (ở nhiều nơi có thể không được bảo hộ như tác phẩm do người sáng tạo), do đó **bảo hộ nhãn hiệu** cho tên và logo có thể là công cụ chính; điều khoản của công cụ tạo ảnh; điều kiện cho đối tác dùng linh vật.
- **Đồng thương hiệu (D9, hoãn):** vì mọi ảnh đi qua bảng khai báo theo vai trò, đối tác sau này có thể thay bộ tranh mà không sửa mã. Chưa xây cơ chế nạp bộ tranh của đối tác.

## 9. Cài đặt của người dùng

| Cài đặt | Giá trị | Mặc định |
|---|---|---|
| Hình minh họa Mèo Mực | Bật/tắt | Bật |
| Giọng lời nhắn | Dí dỏm / Trung tính | Dí dỏm |

Khi tắt hình: `MascotBanner` chỉ hiện chữ (bản trung tính hoặc dí dỏm theo cài đặt), không để trống. Cài đặt nằm ở Cài đặt → Giao diện.

## 10. Yêu cầu chức năng (FR-BRD)

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FR-BRD-01 | Đường ống ảnh sinh tài nguyên có alpha thật, không sót ô caro, đạt ngân sách kích thước | M |
| FR-BRD-02 | `BrandAssets` và bảng khai báo theo vai trò; tải muộn; không hiển thị gì lúc khởi động | M |
| FR-BRD-03 | `MascotBanner` (đầy đủ/gọn), chuyển gọn/ẩn ảnh khi cửa sổ thấp | M |
| FR-BRD-04 | Tùy chọn `mascot_*` trong `ThemeColors` và kiểm hợp lệ tự động cho mọi theme | M |
| FR-BRD-05 | Logo chính thức làm biểu tượng ứng dụng, About, trình cài đặt | M |
| FR-BRD-06 | Gắn biểu cảm vào các trạng thái theo bản đồ mục 4 (mỗi trạng thái khi tính năng tương ứng có mặt) | S |
| FR-BRD-07 | Cài đặt bật/tắt hình và chọn giọng lời nhắn | M |
| FR-BRD-08 | Dùng lại `donate_dialog` hiện có (thêm `cat_coffee`); dải chữ "donate" ở thanh trạng thái chuyển sang chữ tĩnh, tắt được (O18); không có cửa sổ bật lên đòi ủng hộ ở bất kỳ nơi nào | S |
| FR-BRD-09 | Tên truy cập (accessible name) cho mọi hình; thông tin quan trọng không chỉ truyền bằng hình | M |
| FR-BRD-10 | Tài liệu giấy phép tranh và nguồn gốc (`LICENSE-ART.md`, `PROVENANCE.md`) | M |
| FR-BRD-11 | Ảnh xã hội (1280×640) và banner README; bộ sticker cộng đồng (tùy chọn) | C |
| FR-BRD-12 | Ẩn dụ nhỏ (trứng phục sinh) như nhấn 5 lần vào logo trong About hiện `cat_dev` "đang gõ code, đừng làm phiền" | C |

## 11. Tiêu chí nghiệm thu

| ID | Kịch bản |
|---|---|
| BRD-A1 | *Given* mọi tệp trong `data/brand/`, *When* chạy `test_brand_assets`, *Then* hình cắt rời có alpha thật; hình cảnh không còn điểm ảnh ô caro ở mép; số điểm ảnh ô caro sót bằng 0 |
| BRD-A2 | *Given* bản dựng, *When* kiểm dung lượng, *Then* tổng tài nguyên thương hiệu ≤ 1,5 MB và mỗi tệp ≤ 250 KB |
| BRD-A3 | *Given* khởi động ứng dụng, *When* đo, *Then* không có `QPixmap` thương hiệu nào được tạo trước khi một màn hình cần đến; thời gian mở cửa sổ chính không hồi quy |
| BRD-A4 | *Given* bảy theme, *When* hiển thị `MascotBanner` mọi trạng thái, *Then* chữ đạt tương phản WCAG trên nền thẻ; `test_theme_contract.py` xanh |
| BRD-A5 | *Given* tắt hình minh họa, *When* xem mọi trạng thái, *Then* hình biến mất, lời nhắn còn; đổi sang giọng trung tính thì chữ đổi tương ứng |
| BRD-A6 | *Given* mọi màn hình chính, *When* kiểm, *Then* không quá một hình mèo mỗi màn hình; hộp thoại xóa/ghi đè/khôi phục không có mèo |
| BRD-A7 | *Given* thiết bị bị rút giữa chừng, *When* hiển thị tổng kết, *Then* dùng biểu cảm buồn kèm số sách đã/chưa chép và hành động tiếp theo; không dùng câu đùa về dữ liệu bị mất |
| BRD-A8 | *Given* cửa sổ cao dưới 640 px, *When* hiển thị trạng thái, *Then* `MascotBanner` thu gọn hoặc chỉ hiện chữ |
| BRD-A9 | *Given* hộp thoại Giới thiệu, *When* mở, *Then* thấy logo, phiên bản, giấy phép AGPL-3.0, liên kết mã nguồn đúng phiên bản và ghi chú giấy phép tranh |
| BRD-A10 | *Given* trình đọc màn hình, *When* duyệt, *Then* mỗi hình có tên truy cập tiếng Việt |

## 12. Nhiệm vụ

- [ ] **S0-13 [H]** Chủ dự án xác nhận nguồn gốc, điều khoản công cụ tạo ảnh, giấy phép tranh (O11, O12); chọn khẩu hiệu (O14).
- [ ] **BR-00 [R]** Đọc `packaging/process_brand_icon.py`, `generate_icon.py`, `brand_logo.png`, `app_icon.ico`, tiêu đề thương hiệu ở thanh bên, `donate_dialog.py`, `eula_dialog.py`, hộp thoại Giới thiệu; ghi hiện trạng vào `docs/brand/CURRENT_STATE.md` và cập nhật `DISCREPANCIES.md`.
- [ ] **BR-01 [R]** Đọc `docs/THEME_DESIGN_BRIEF.md`, `ThemeColors`, cách theme hiện có vẽ nhãn thương hiệu (ví dụ dấu 🌿 của Cottagecore) để linh vật bổ sung, không thay thế.
- [ ] **BR-02** Viết `tools/prepare_brand_assets.py` theo mục 7 và sinh tài nguyên; báo cáo `docs/brand/asset_report.md`.
- [ ] **BR-03** Bảng khai báo `brand.json`, `LICENSE-ART.md`, `PROVENANCE.md`.
- [ ] **BR-04 [H][O17]** Biểu tượng ứng dụng: mở rộng `process_brand_icon.py` theo quyết định O17; duyệt bản giản lược ≤ 32 px; hình trang bìa trình cài đặt Inno Setup.
- [ ] **BR-05** `BrandAssets`, `MascotBanner`, sổ trạng thái, module chuỗi hai giọng; test đơn vị.
- [ ] **BR-06** Tùy chọn `mascot_*` trong `ThemeColors`; cập nhật `test_theme_contract.py`; giá trị cho bảy theme.
- [ ] **BR-07** Cài đặt "Hình minh họa" và "Giọng lời nhắn"; hộp thoại Giới thiệu; `donate_dialog` với `cat_coffee`; dải chữ donate tĩnh/tắt được [O18].
- [ ] **BR-08** Gắn vào **màn hình hiện có**: panel chi tiết trống, thư viện trống, không có kết quả tìm kiếm, tìm metadata, tìm bìa, tóm tắt AI, phân loại thông minh, Duplicate Finder, dịch vụ đánh giá không khả dụng, hộp thoại lỗi bất ngờ, tác vụ dài.
- [ ] **BR-09** Gắn vào **màn hình của S3/S3d/S3e** khi tính năng đó được làm: màn Thiết bị (chờ), thông báo mất thiết bị, Bảng đồng bộ (đã khớp), chuyển đổi (S4).
- [ ] **BR-10** Kiểm hiển thị thật trên bảy theme (bỏ `offscreen`), ghi ảnh chụp vào `docs/brand/`.
- [ ] **BR-11 (tùy chọn)** Ảnh xã hội, banner README, sticker.
- [ ] **CHANGELOG.md:** mục `Added` cho từng phần người dùng thấy được.

**Thoát BR-A:** ảnh có alpha thật và báo cáo sạch; About/biểu tượng dùng logo mới; `MascotBanner` chạy trên bảy theme; hình tắt được; không hồi quy khởi động; giấy phép tranh đã ghi rõ.
