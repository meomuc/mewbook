# Nguồn dữ liệu bên thứ ba (S0-08)

Ngày xác minh: **2026-09-19**, bằng cách tải các trang tài liệu/điều khoản công khai và gọi thử từng điểm cuối một lần. Đây là bản ghi kỹ thuật để chủ dự án và luật sư xem, **không phải kết luận pháp lý**. Các dòng "chưa rõ" được đưa vào `LAWYER_QUESTIONS.md` (câu 8 mục C và câu 13). Điều khoản có thể đổi; cần xem lại trước mỗi bản phát hành (`RELEASE_CHECKLIST.md`).

Nguyên tắc của dự án (`CLAUDE.md`): chỉ dùng API chính thức hoặc API công khai không cần khóa; không thu thập (scrape) trang web, đặc biệt không google.com. Mọi lời gọi chạy **từ máy người dùng**, không qua máy chủ của dự án. Người dùng tắt được từng nguồn ở Cài đặt → Ảnh bìa (`disabled_cover_sources`); nguồn bị tắt không bị gọi ở bất kỳ đường nào (tìm ảnh bìa, tìm lại chỉ theo tên sách, tra cứu metadata).

## 1. Tóm tắt

| Nguồn | Dùng để | Khóa | Tình trạng | Mặc định |
|---|---|---|---|---|
| Open Library | ảnh bìa, metadata | không | **Được phép, có điều kiện** | Bật |
| Google Books API (v1) | ảnh bìa, metadata | tùy chọn (của người dùng) | **Được phép, có điều kiện** | Bật |
| Google Books, nguồn cấp Atom cũ | dự phòng khi API v1 hết hạn mức | không | **Chưa rõ** (API cũ, không còn tài liệu) | Bật (cùng công tắc "Google Books") |
| Apple Books (iTunes Search API) | ảnh bìa, metadata | không | **Chưa rõ / rủi ro** (điều khoản giới hạn mục đích dùng ảnh) | **Tắt** (quyết định 2026-09-19) |
| Tiki (`tiki.vn/api/v2/products`) | ảnh bìa sách tiếng Việt | không | **Chưa rõ** (API nội bộ, không có điều khoản công bố) | **Tắt** |
| Google Custom Search JSON API | ảnh bìa từ toàn web | khóa + cx của người dùng | Được phép cho khách hàng **hiện có**; **đã đóng với khách hàng mới** | Tắt (cần khóa) |
| Nhà cung cấp AI (OpenAI, Anthropic, Gemini, DeepSeek, Groq, Mistral, OpenRouter, Ollama) | tóm tắt sách | khóa của người dùng | Theo điều khoản từng nhà cung cấp; **nội dung sách rời khỏi máy** | Tắt (cần khóa) |
| Supabase (dịch vụ đánh giá) | đánh giá cộng đồng | khóa anon (công khai theo thiết kế) | Do chủ dự án vận hành; xem S2 | Tắt (cần cấu hình) |
| Nguồn thông tin bản phát hành (kiểm tra cập nhật) | báo có bản mới | không | Trang phát hành của chính dự án; chỉ đọc số phiên bản | **Tắt** (người dùng bật; cần `APP_UPDATE_FEED_URL`) |

## 2. Chi tiết từng nguồn

### 2.1 Open Library

- **Điểm cuối:** `https://openlibrary.org/search.json` và `https://covers.openlibrary.org/b/id/{cover_id}-L.jpg` (ảnh theo Cover ID). Mã: `application/cover_search.py`, `application/metadata_lookup.py`.
- **Tài liệu và điều khoản:** trang "Usage Guidelines" của `openlibrary.org/developers/api` và `openlibrary.org/dev/docs/api/covers`.
- **Điều kiện đọc được (đã tải ngày 2026-09-19):**
  - API phục vụ tìm kiếm sách theo thời gian thực cho người dùng và "không nhằm làm kho dữ liệu cho dịch vụ bên thứ ba". **Nên:** yêu cầu có ích và theo thời gian thực thay mặt người dùng, lưu đệm phản hồi, **nhận diện ứng dụng bằng `User-Agent` kèm email**. **Không nên:** thu thập trang HTML (dùng API), phân tán lưu lượng qua từ 5 IP trở lên. Cần dữ liệu hàng loạt thì dùng bản dữ liệu tải xuống hằng tháng.
  - Ảnh bìa: truy cập bằng khóa **khác** Cover ID/OLID bị giới hạn 100 yêu cầu/IP/5 phút (quá thì trả `403`). MewBook dùng Cover ID nên không nằm trong giới hạn đó.
  - Đề nghị ghi công: một liên kết thân thiện về Open Library ở trang chi tiết sách hoặc trang Giới thiệu/chân trang.
- **Khớp hiện trạng:** MewBook gửi một truy vấn khi người dùng bấm tìm; có bộ đệm 30 phút (`_CACHE_TTL_SECONDS`); `User-Agent` là `MewBook/1.0 (ebook manager; cover lookup)` **chưa có email**.
- **Việc cần làm:** (a) chủ dự án cung cấp một email/URL liên hệ để đưa vào `User-Agent`; (b) thêm dòng ghi công Open Library vào hộp thoại Giới thiệu (đề xuất, chưa làm).
- **Dữ liệu chia sẻ tiếp:** mã đang coi dữ liệu Open Library là chia sẻ được (`_SHAREABLE`). Giấy phép dữ liệu cụ thể của Open Library chưa được đối chiếu ở lượt này.

### 2.2 Google Books API v1

- **Điểm cuối:** `https://www.googleapis.com/books/v1/volumes`. Khóa API là tùy chọn (dùng khóa Google của người dùng nếu có, nhằm có hạn mức riêng).
- **Điều khoản:** "Terms of Service" của Google Books APIs, cộng Google APIs Terms of Service (`developers.google.com/books/terms`).
- **Điều kiện đọc được:** không được thu phí người dùng cho việc dùng ứng dụng nếu chưa có thỏa thuận riêng hay văn bản cho phép của Google; phải gỡ nội dung bị cho là vi phạm theo yêu cầu của Google hoặc khi luật đòi hỏi, và cung cấp thông tin liên hệ cho chủ quyền; phải thông báo người dùng rằng nội dung họ gửi qua Books API (kể cả tên/biệt danh) có thể được công khai trên dịch vụ Google.
- **Khớp hiện trạng:** MewBook miễn phí (quyên góp là tự nguyện, không phải phí dùng); MewBook chỉ **đọc** dữ liệu, không gửi nội dung người dùng lên Books API, nên điều khoản về nội dung gửi lên không phát sinh. Hạn mức miễn phí không khóa nhỏ và hay hết; mã đã xử lý (thử lại, rồi dùng nguồn cấp cũ ở mục 2.3).
- **Việc cần làm:** cần một đường liên hệ để chủ quyền yêu cầu gỡ (`CONTRIBUTING.md`/`SECURITY.md` ở S1-07). Dữ liệu Google được coi **không** chia sẻ tiếp (`_SHAREABLE = False`) là đúng thận trọng.

### 2.3 Google Books, nguồn cấp Atom cũ (dự phòng)

- **Điểm cuối:** `https://www.google.com/books/feeds/volumes` (giao thức GData cũ). Thử ngày 2026-09-19 vẫn trả `200` và XML Atom.
- **Tình trạng:** trong các trang tài liệu Books API đã tải không thấy nguồn cấp này được mô tả hay có điều khoản riêng. Đây là bộ nhận dữ liệu đọc bằng máy chứ không phải thu thập HTML, nhưng nằm trên tên miền google.com và **không còn tài liệu**, nên đối chiếu với quy tắc "không scrape google.com" là chưa rõ.
- **Đề xuất:** giữ như dự phòng nhưng để chủ dự án/luật sư quyết định; nếu bị cho là rủi ro thì gỡ nhánh dự phòng này khỏi `cover_search.py` và `metadata_lookup.py`. Hiện chưa có công tắc riêng, công tắc "Google Books" tắt cả hai.

### 2.4 Apple Books (iTunes Search API)

- **Điểm cuối:** `https://itunes.apple.com/search` (`media=ebook`), kể cả kho Việt Nam khi tên sách trông như tiếng Việt.
- **Tài liệu:** trang Search API của Apple (`performance-partners.apple.com/search-api`).
- **Điều kiện đọc được:** giới hạn khoảng **20 lời gọi/phút** (có thể đổi); trang lớn nên lưu đệm; nội dung khuyến mại trong API, gồm ảnh bìa album/ứng dụng, chỉ được dùng **để quảng bá nội dung của cửa hàng, không phải để giải trí**.
- **Khớp hiện trạng:** MewBook dùng ảnh bìa từ Apple làm ảnh bìa sách trong thư viện riêng của người dùng, tức không phải để quảng bá cửa hàng Apple. Đây là điểm **chưa rõ / có rủi ro**. Giới hạn 20 lời gọi/phút vẫn đúng với cách dùng hiện tại (mỗi lần tìm vài lời gọi, có lưu đệm), trừ khi người dùng chạy tra cứu hàng loạt.
- **Quyết định của chủ dự án (2026-09-19): tắt mặc định** (`disabled_cover_sources = ["Tiki", "Apple Books"]`); người dùng bật lại ở Cài đặt → Ảnh bìa và thấy dòng ghi chú lý do. Câu hỏi luật sư 13 vẫn mở. Hệ quả: chất lượng tìm ảnh bìa sách tiếng Việt giảm cho tới khi người dùng tự bật.

### 2.5 Tiki

- **Điểm cuối:** `https://tiki.vn/api/v2/products` (JSON). Chỉ gọi khi tên sách hoặc tác giả có dấu hiệu tiếng Việt.
- **Tình trạng:** đây là API nội bộ của cửa hàng tiki.vn (đang trả `200` và JSON, thử ngày 2026-09-19). **Không thấy tài liệu API công khai hay điều khoản cho phép bên thứ ba dùng.** `tiki.vn/robots.txt` không nhắc tới `/api` (chỉ liệt kê các đường dẫn rác) nhưng robots.txt không phải giấy phép. Trang điều khoản/quy chế của Tiki không đọc được bằng công cụ dùng ở đây (trang trợ giúp là ứng dụng JavaScript), nên **điều khoản chưa được xác minh**.
- **Quyết định thực hiện:** theo checklist mục 2.6 ("nếu không rõ thì để tắt mặc định hoặc gỡ"), **Tiki tắt mặc định** (`disabled_cover_sources = ["Tiki"]`). Người dùng vẫn bật lại được ở Cài đặt và thấy dòng ghi chú lý do.
- **Việc còn lại:** chủ dự án hoặc luật sư đọc điều khoản của Tiki; nếu không cho phép thì gỡ hẳn nhánh Tiki khỏi mã.

### 2.6 Google Custom Search JSON API (Google Images)

- **Điểm cuối:** `https://www.googleapis.com/customsearch/v1`, tìm ảnh, cần khóa API và mã công cụ tìm kiếm (cx) của **chính người dùng**. Không thu thập google.com.
- **Điều kiện đọc được (trang tổng quan, 2026-09-19):** 100 truy vấn miễn phí/ngày, thêm thì 5 USD/1000 truy vấn, tối đa 10.000/ngày; **API đã đóng với khách hàng mới**; khách hàng hiện có vẫn dùng được (chi tiết thời hạn xem trên trang của Google).
- **Hệ quả:** tính năng chỉ hữu ích với người đã có sẵn khóa. Cài đặt đã có dòng lưu ý; hướng dẫn cài đặt trong Cài đặt vẫn mô tả cách tạo mới, nên cần rà soát lại (đề xuất, chưa làm).

### 2.7 Nhà cung cấp AI

- **Điểm cuối:** `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.deepseek.com`, `api.groq.com`, `api.mistral.ai`, `openrouter.ai`, và Ollama chạy trên máy (`localhost`). Mã: `application/ai_summary.py`.
- **Khóa:** của người dùng, lưu mã hóa (`SecretStore`); dự án không gửi hay chuyển tiếp khóa của mình.
- **Dữ liệu rời khỏi máy:** phần **nội dung yêu cầu** hiện trong ô "nội dung gửi" của hộp thoại Tóm tắt AI (người dùng xem và sửa được trước khi gửi); mã không cắt ngắn nội dung đó. Nội dung gồm tiêu đề, tác giả, thẻ và, nếu đã trích xuất, **trích đoạn nội dung sách** (`build_request_content`). Điều này cần được nói rõ trong thông báo quyền riêng tư (phần 3 của hộp thoại hiện có nhắc khóa API; S2-06 sẽ rà soát).
- **Điều khoản:** mỗi nhà cung cấp có điều khoản riêng, người dùng là bên ký với nhà cung cấp. Không có nhà cung cấp nào được bật mặc định.

### 2.8 Supabase (đánh giá cộng đồng)

- **Điểm cuối:** dự án Supabase do chủ dự án tạo (URL do người dùng nhập ở Cài đặt).
- **Dữ liệu gửi đi:** mã tài liệu (`doc_id`), biệt danh, điểm, nhận xét, và mã định danh ẩn danh (băm ở máy chủ). Tệp sách không được gửi. Đặc tả: `docs/handoff/09_ERROR_REPORTING_SPEC.md` và S2.
- **Việc cần làm:** bản nháp Privacy/Terms (S2-06); phần này không thuộc S0-08.

### 2.9 Kiểm tra bản mới (tùy chọn, S1-05)

- **Điểm cuối:** `APP_UPDATE_FEED_URL` trong `smartdoc/__init__.py`, một JSON "bản phát hành mới nhất" kiểu GitHub (`tag_name`, `html_url`). **Đang để trống** cho tới khi kho công khai tồn tại; khi trống, giao diện nói chưa cấu hình và không làm gì.
- **Khi nào:** chỉ khi người dùng bật ở Cài đặt → Cập nhật (mặc định tắt), tối đa mỗi ngày một lần khi khởi động, hoặc bấm "Kiểm tra ngay".
- **Gửi gì:** một yêu cầu GET với `User-Agent: MewBook/<phiên bản>`. **Không** gửi mã cài đặt ẩn danh, thông tin thư viện hay cookie (có test kiểm tra). Máy chủ thấy địa chỉ IP và số phiên bản.
- **Làm gì với kết quả:** chỉ báo "Có bản mới X" và mở trang phát hành (chỉ liên kết `https://`) khi người dùng bấm. Không tải, không cài.

## 3. Dữ liệu nào rời khỏi máy, theo nguồn

| Nguồn | Gửi đi |
|---|---|
| Open Library, Google Books, Apple Books, Tiki | Tên sách và tác giả (đã làm sạch), ISBN nếu có; địa chỉ IP của người dùng (như mọi lời gọi HTTP) |
| Google Custom Search | Tên sách, tác giả, khóa API và cx của người dùng |
| Nhà cung cấp AI | Nội dung yêu cầu người dùng đã duyệt (có thể chứa trích đoạn sách), khóa API |
| Supabase | Mã tài liệu, biệt danh, điểm, nhận xét, mã ẩn danh |
| Kiểm tra bản mới (nếu bật) | Chỉ địa chỉ IP và số phiên bản MewBook |

Không nguồn nào nhận tệp sách nguyên vẹn.

## 4. Quyết định và việc còn lại

Đã quyết định (2026-09-19): Apple Books **tắt mặc định** (mục 2.4); Tiki tắt mặc định và **giữ** trong mã; nhánh Atom cũ của Google Books **giữ** làm dự phòng (mục 2.3, 2.5). Luật sư xem lại ở câu 13.

Còn lại:

1. Cung cấp email/URL liên hệ cho `User-Agent` (Open Library yêu cầu).
2. Thêm dòng ghi công Open Library vào hộp thoại Giới thiệu.
