# Thiết kế lại bộ lọc (bộ sưu tập · tác giả · hashtag · định dạng)

Trạng thái: **đã cài đặt cả 3 giai đoạn.** Số liệu lấy từ thư viện thật của người dùng (7545 sách), đọc trên bản sao.

Khác với đề xuất ban đầu (có chủ đích):
- **Không tạo bảng phụ `document_tags`/`document_authors`.** Việc tách/chuẩn hóa tác giả và hashtag chạy bằng hai hàm SQL `mb_has_author`/`mb_has_tag` (đăng ký trên kết nối) và một bộ nhớ đệm các dòng `(id, author, tags, extension)` trong `FacetCounter`, xóa mỗi khi thư viện đổi. Không cần đồng bộ bảng phụ với mọi nơi ghi `documents`; đo trên 7.545 sách: mỗi lần nhấp cập nhật danh sách + số đếm ≈ 50–110 ms.
- **Ô tích khi rê chuột thay bằng** phím Ctrl/Shift, mục "Thêm vào lựa chọn" trong menu chuột phải và dòng gợi ý dưới sidebar.
- **Thư mục nhóm** hiển thị thành chip/hàng 📂 ở đầu mỗi mục (chọn cả nhóm bằng một cú nhấp), các mục thành viên vẫn hiện bình thường.
- **Bộ sưu tập từ bộ lọc**: điều kiện dẹt AND/OR của `SmartRule` không biểu diễn được "(A hoặc B) và C", ô tìm hoặc bộ sưu tập lồng nhau; các trường hợp đó lưu **danh sách cố định** các sách đang hiển thị và hộp thoại nói rõ trước khi lưu. Thêm toán tử `has_author`/`has_tag` (khớp cả người/cả thẻ) cho `SmartRule`.
- **Gợi ý dọn tên tác giả** (menu "⋯" của mục Tác giả → "🧹 Gợi ý dọn tên tác giả..."): đề xuất gộp các tên chỉ khác dấu ("Nguyen Nhat Anh" / "Nguyễn Nhật Ánh") và đánh dấu tên người đăng như "CongThuc88" (369 sách trên thư viện thật) để đặt thành "Không rõ". Chỉ áp dụng khi bấm nút và xác nhận; chỉ đổi dữ liệu trong thư viện, không đụng file sách. Không gộp tự động theo dấu vì "Hạ Thu"/"Hà Thu" có thể là hai người.

## 1. Bất cập hiện tại

### 1.1 Hành vi khó đoán
| # | Vấn đề | Nơi xảy ra |
|---|---|---|
| 1 | **Nhấp một lần = thêm vào lựa chọn (OR), nhấp đúp = chỉ cái này.** Muốn "xem tác giả này" phải nhấp đúp; Qt bắn click rồi mới double-click nên danh sách nạp lại hai lần và nhấp nháy. Người dùng đa số mong nhấp = chuyển tới. | `filter_sidebar._on_item_clicked/_on_item_double_clicked`, `sidebar._on_collection_clicked` |
| 2 | **Không thấy đang lọc theo cái gì.** Khi danh sách ngắn bất thường, phải dò từng mục trong sidebar. Không có thanh "đang lọc", không có nút "Xóa lọc". | toàn bộ |
| 3 | **Bộ lọc "vô hình".** Bấm "Xem tài liệu của tác giả" ở panel chi tiết đặt `author_names`, nhưng sidebar dựng lại `_selected` chỉ từ `authors` → sidebar hiển thị *không chọn gì* trong khi thư viện đang lọc. | `filter_sidebar._on_bridged_event` |
| 4 | **Các nơi ghi đè lẫn nhau.** Thanh chip định dạng (theme Kệ Sách Gỗ) chỉ gửi `extensions` nên xóa luôn lựa chọn tác giả/hashtag; chọn hashtag ở panel chi tiết thì xóa bộ sưu tập; "Tất cả tài liệu" xóa facet nhưng **không** xóa ô tìm kiếm. Mỗi nơi một luật. | `filter_chips`, `detail_panel`, `sidebar._show_everything` |
| 5 | Ba sự kiện (`SearchRequested`, `FacetFilterChanged`, `CollectionSelected`) mỗi cái mang một phần trạng thái; thư viện tự ghép lại từ ba mảnh, các widget khác phải đoán. | `event_bus`, `library_view._build_combined_where` |

### 1.2 Danh sách không dùng nổi với dữ liệu thật
- **Tác giả: 3.102 mục, trong đó 2.282 mục chỉ có 1 sách.** Danh sách dài như cuộn phim, không có ô tìm trong danh sách, không "xem thêm".
- **Trùng lặp do cách viết: 72 nhóm tên.** "nhiều tác giả" (165) / "Nhiều Tác Giả" (23) / "NHIỀU TÁC GIẢ" (3)…; "Nguyễn nhật Ánh" (34) và "Nguyễn Nhật Ánh" (1); "NHÃ CA" và "Nhã Ca". Mỗi biến thể là một mục riêng nên đếm sai.
- **Đồng tác giả không lọc được từ sidebar:** 98 chuỗi kiểu "A, B, C" là *một* mục. (Panel chi tiết thì tách ra được → hai nơi hiểu "tác giả" khác nhau.)
- **Giá trị rác lên đầu bảng:** "Unknown" (302), "nhiều tác giả" (165+), "CongThuc88" (369, tên người đăng chứ không phải tác giả).
- **Số đếm luôn là toàn thư viện**, không phản ánh bộ lọc đang bật. Chọn hashtag "Lịch sử" rồi bấm một tác giả bất kỳ thường ra **0 kết quả**, vì danh sách tác giả vẫn liệt kê cả những người không có sách Lịch sử.
- **1.963/7.545 sách không có hashtag nào** nhưng không có mục "Chưa phân loại" để tới đó.
- Hashtag thực chất là *thể loại* do trình phân loại gán (57 mục, top: Tiểu thuyết 1.334, Truyện ngắn 1.195…) nhưng trộn cùng khái niệm "hashtag" do người dùng tự gõ.

### 1.3 Kỹ thuật / hiệu năng
- Mỗi lần nhấp: `tree.clear()` và dựng lại **toàn bộ** cây (3.102 tác giả) + duyệt Python toàn bộ cột `tags` → giật, mất vị trí cuộn (đã có mẹo khôi phục cuộn), và là lý do lịch sử dùng cờ `_publishing_own_event` để tránh dựng lại lồng nhau.
- Thư mục nhóm (`facet_groups`) chỉ truy cập được qua menu chuột phải nhiều tầng; người dùng khó biết có tính năng này (đang có 9 nhóm).
- Sidebar là hai widget khác kiểu (`QListWidget` cho bộ sưu tập, `QTreeWidget` cho facet) với hai kiểu chọn khác nhau, dù cùng "lọc thư viện".
- Bộ sưu tập rule-based không thể tạo từ bộ lọc đang xem; phải mở hộp thoại riêng và dựng lại điều kiện bằng tay.

## 2. Nguyên tắc thiết kế
1. **Một nguồn sự thật duy nhất** cho "đang lọc gì".
2. **Luôn nhìn thấy** đang lọc gì và còn bao nhiêu kết quả, và **xóa được bằng một cú nhấp**.
3. **Nhấp = làm đúng điều người ta nghĩ** (chuyển tới mục đó); gộp nhiều mục là thao tác *có chủ đích* (Ctrl/Shift hoặc ô tích).
4. **Không bao giờ dẫn tới kết quả 0** bằng cách nhấp vào mục do sidebar đưa ra: số đếm phản ánh bộ lọc hiện tại, mục 0 bị ẩn/mờ.
5. **Danh sách dài phải tìm được**: chỉ hiện top-N, phần còn lại qua ô gõ tìm.
6. **Dữ liệu bẩn được làm sạch ở lớp hiển thị**, không sửa file/metadata của người dùng.

## 3. Thiết kế

### 3.1 Mô hình lọc thống nhất
```python
@dataclass(frozen=True)
class LibraryFilter:
    query: str = ""
    collections: tuple[str, ...] = ()     # OR trong nhóm
    formats: tuple[str, ...] = ()          # OR
    authors: tuple[str, ...] = ()          # khóa chuẩn hóa của *người* (đã tách đồng tác giả), OR
    tags: tuple[str, ...] = ()             # OR
    def is_empty(self) -> bool: ...
    def with_value(self, category, value, *, mode="replace"|"add"|"toggle") -> "LibraryFilter": ...
    def without(self, category, value=None) -> "LibraryFilter": ...
```
Luật kết hợp duy nhất, hiển thị được cho người dùng: **OR trong một nhóm, AND giữa các nhóm.**
`FilterService` (trong `AppContext`) giữ giá trị hiện tại và phát **một** sự kiện `FilterChangedEvent(filter)`. Ô tìm, sidebar, thanh chip, panel chi tiết, thư viện, thanh trạng thái đều đọc/ghi qua service này. Ba sự kiện cũ vẫn được phát bởi một bộ chuyển đổi trong giai đoạn chuyển tiếp để không vỡ code/test đang dùng.

### 3.2 Thanh "Đang lọc" phía trên danh sách
`Tác giả: Nhã Ca ✕  ·  Hashtag: Lịch sử ✕  ·  “tìm: sài gòn” ✕      **127 / 7.545 tài liệu**   [Xóa lọc]`
- Ẩn hoàn toàn khi không lọc gì (không chiếm chỗ).
- Mỗi chip có ✕ bỏ riêng; chip của bộ lọc từ panel chi tiết cũng hiện ở đây (sửa lỗi 3).
- `Esc` khi tiêu điểm ở danh sách = Xóa lọc.

### 3.3 Cách chọn
| Thao tác | Kết quả |
|---|---|
| Nhấp một mục | **Chuyển tới mục đó** trong nhóm của nó (thay các mục cùng nhóm, giữ nguyên các nhóm khác → thu hẹp dần) |
| Nhấp lại mục đang chọn | Bỏ chọn |
| **Ctrl/Shift + nhấp**, hoặc nhấp vào **ô tích** hiện khi rê chuột | Thêm/bớt mục (OR) |
| Nhấp "Tất cả tài liệu" | Xóa **mọi** thứ, kể cả ô tìm |
| Bỏ nhấp đúp | Không còn ý nghĩa riêng → hết nhấp nháy |

### 3.4 Sidebar mới (một widget, các mục có thể thu gọn, nhớ trạng thái)
```
🔍 Lọc nhanh…  (gõ tên tác giả / hashtag / bộ sưu tập)
─────────────
BỘ SƯU TẬP           ＋
  ★ Sẽ đọc        6
  HRB             1   …
THỂ LOẠI / HASHTAG
  (chip có số) Tiểu thuyết 1.334  Truyện ngắn 1.195  …   [Chưa phân loại 1.963]
TÁC GIẢ
  Thích Nhất Hạnh 85   Cổ Long 79   Osho 75  … (top 8)
  Xem tất cả 3.102… →   (khung tìm + A–Z)
ĐỊNH DẠNG
  [EPUB 6.391] [PDF 1.087] [MOBI 41] [AZW3 26]
```
- **Định dạng và hashtag là chip xếp dòng** (ít giá trị, muốn thấy hết cùng lúc), **tác giả là danh sách có tìm** (nhiều giá trị).
- **Số đếm là số kết quả nếu chọn mục đó, với bộ lọc hiện tại** (bỏ chính nhóm đang xét ra khỏi điều kiện để anh vẫn thấy các lựa chọn anh em). Mục 0 bị ẩn (hoặc mờ đi nếu đang được chọn).
- **"Lọc nhanh"** gợi ý xuyên nhóm ("Nhã Ca — Tác giả (12)", "Lịch sử — Hashtag (231)", "HRB — Bộ sưu tập") và thêm chip tương ứng. Cùng nguồn gợi ý cho ô tìm chính: gõ `nhã ca` hiện dòng "Lọc theo tác giả Nhã Ca".
- Nhóm thư mục hiện có (`facet_groups`) vẫn dùng, hiển thị thành một mục thu gọn được trong phần Tác giả/Hashtag; thao tác tạo/chuyển nhóm chuyển thành kéo-thả + menu chuột phải ngắn gọn.
- Theme "Mực Đêm" (thanh biểu tượng thu gọn) và "Kệ Sách Gỗ" (thanh chip trên đầu) dùng **cùng** `FilterService`, chỉ khác cách trình bày.

### 3.5 Làm sạch danh sách tác giả (chỉ ở lớp hiển thị)
- **Khóa chuẩn hóa:** NFC + `casefold` + gộp khoảng trắng/gạch nối. "NHÃ CA" = "Nhã Ca", "Nguyễn nhật Ánh" = "Nguyễn Nhật Ánh". Nhãn hiển thị = biến thể có nhiều sách nhất.
  *Không* gộp theo bỏ dấu (sẽ nhập nhằng "Hạ Thu"/"Hà Thu") — chỉ gợi ý gộp thủ công sau.
- **Tách đồng tác giả** bằng `split_author_names` sẵn có: sách "A, B" tính cho cả A và B. Vì vậy lọc từ sidebar và từ panel chi tiết cho cùng kết quả.
- **Giá trị "không rõ" gom một mục cuối danh sách:** Unknown, rỗng, "nhiều tác giả", "khuyết danh/vô danh" → "Không rõ / Nhiều tác giả". Không nằm trong top.
- **Tên người đăng** (như "CongThuc88") là dữ liệu nguồn chứ không phải lỗi hiển thị: chỉ nêu trong danh sách dọn dẹp ở Giai đoạn 3 (gợi ý "tên này giống tên người tải lên, 369 sách — gán lại?").

### 3.6 "Lưu bộ lọc này thành bộ sưu tập"
Nút trên thanh Đang lọc, hiện khi có ≥1 chip: tạo `VirtualCollection` với các rule tương ứng (`author contains`, `tags contains`, `extension eq`) — dùng sẵn `smart_collections`. Bộ sưu tập rule-based cập nhật theo thư viện, người dùng không phải nhập tay điều kiện.

## 4. Truy vấn & hiệu năng
- `FacetCounter.counts(category, filter)` → một truy vấn cho mỗi nhóm chạy **trên tập kết quả hiện tại** (`WHERE` của các nhóm *khác*), kết quả cache theo (filter, phiên bản thư viện).
- Tách hashtag/tác giả bằng SQLite `json_each` hoặc bảng phụ `document_tags`, `document_authors` (chỉ *thêm*, dựng từ dữ liệu có sẵn khi khởi động, cập nhật cùng `add_or_update_document`/`apply_metadata`). Cột `tags`/`author` giữ nguyên là nguồn sự thật để không phá `library.db` cũ.
- Cập nhật **tăng dần** (ẩn/hiện/đổi số của mục có sẵn), không `clear()` cây → hết giật, hết mất vị trí cuộn, bỏ cờ `_publishing_own_event`.
- Mục tiêu: nhấp → danh sách + số đếm cập nhật < 100 ms với 7.500 sách.

## 5. Kế hoạch theo giai đoạn
**Giai đoạn 1 — Nền móng và sửa lỗi hành vi** (giá trị cao nhất, rủi ro thấp)
- `LibraryFilter` + `FilterService` + `FilterChangedEvent` (bộ chuyển đổi cho ba sự kiện cũ).
- Thanh **Đang lọc** + nút Xóa lọc + Esc.
- Luật chọn mới (nhấp = chuyển tới; Ctrl/ô tích = thêm); bỏ nhấp đúp; sửa lỗi 3, 4, 5 (mục 1.1).
- Panel chi tiết và thanh chip định dạng đi qua service.

**Giai đoạn 2 — Sidebar mới**
- Một widget, các mục thu gọn; định dạng/hashtag dạng chip; tác giả top-N + "Xem tất cả" có tìm.
- Số đếm theo bộ lọc hiện tại, ẩn mục 0; mục "Chưa phân loại".
- Khóa chuẩn hóa tác giả, tách đồng tác giả, gom "Không rõ".

**Giai đoạn 3 — Thông minh**
- Ô "Lọc nhanh" và gợi ý trong ô tìm chính.
- "Lưu bộ lọc thành bộ sưu tập".
- Gợi ý gộp tên tác giả / dọn dẹp tên người đăng.

## 6. Tương thích và rủi ro
- **Dữ liệu:** không đổi/xóa cột hiện có; thêm bảng phụ theo đúng luật "chỉ thêm" của `_migrate_add_missing_columns`. Không sửa file của người dùng.
- **Test hiện có:** `test_filter_sidebar.py`, `test_sidebar.py`, `test_library_view*.py`, `test_detail_panel.py` mô tả hành vi *cũ* (nhấp đúp, chọn nhiều bằng nhấp đơn). Giai đoạn 1–2 sẽ viết lại các test đó theo luật mới; đây là thay đổi hành vi có chủ đích, ghi rõ trong CHANGELOG.
- **Thay đổi thói quen:** người đang quen "nhấp đơn = cộng dồn" sẽ thấy khác. Giảm nhẹ: gợi ý ngắn ở lần chạy đầu ("Giữ Ctrl để chọn nhiều") và ô tích hiện khi rê chuột.
- **Theme:** mọi màu/kiểu mới đi qua `ThemeColors` (không rẽ nhánh theo tên theme) và được `test_theme_contract.py` kiểm tra.
- Giao diện kiểu rail (Mực Đêm) và kiểu chip (Kệ Sách Gỗ) cần thử trực quan ở từng theme.
