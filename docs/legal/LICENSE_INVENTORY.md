# Kiểm kê giấy phép (S0-01)

- **Ngày:** 2026-09-19 · **Phiên bản ứng dụng:** 1.0.0 (`src/smartdoc/__init__.py`)
- **Nguồn dữ liệu:** `uv tree --no-dev --frozen` (cây phụ thuộc chạy thật), metadata cài đặt (`importlib.metadata`, trường `License-Expression`/`License`/`Classifier`) và file giấy phép trong `*.dist-info`, `packaging/MewBook.spec` (tài nguyên đóng gói), mã nguồn (`from PySide6.…`).
- **Đây không phải tư vấn pháp lý.** Cột "AGPL-3.0" là đánh giá kỹ thuật dựa trên văn bản giấy phép; luật sư xác nhận (`05_LEGAL_OPEN_SOURCE_CHECKLIST.md` mục 3).
- Chú giải cột AGPL-3.0: **Có** = giấy phép cho phép kết hợp vào tác phẩm AGPL-3.0 · **Có (điều kiện)** = được, kèm nghĩa vụ đáng lưu ý · **Chưa rõ** = cần xác minh thêm (đã nêu thành câu hỏi ở mục 5).

## 1. Phụ thuộc chạy thật (đóng gói vào bản cài)

| Gói | Phiên bản | Giấy phép (theo metadata) | Vai trò | AGPL-3.0 | Ghi chú |
|---|---|---|---|---|---|
| **PyMuPDF** | 1.28.2 | "Dual Licensed – GNU AFFERO GPL 3.0 or Artifex Commercial License" | Đọc PDF, trích bìa/văn bản | Có (chọn nhánh AGPL) | Metadata không nói rõ "only" hay "or later". Nhánh thương mại **không** dùng. Nhánh AGPL buộc cả ứng dụng phát hành dưới AGPL (đúng hướng D1) |
| **mobi** | 0.4.1 | `GPL-3.0-only` (LICENSE là GPLv3 nguyên văn) | Giải nén MOBI/AZW3 cho trình đọc | Có (điều kiện) | GPLv3 và AGPLv3 cho phép kết hợp (điều 13 của cả hai). Kết quả: tác phẩm gộp chịu AGPL-3.0; phần `mobi` vẫn là GPL-3.0-only. Liên quan lựa chọn SPDX ở O4 |
| **PySide6** (+ `pyside6-essentials`, `pyside6-addons`, `shiboken6`) | 6.11.2 | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | Toàn bộ giao diện Qt | Có (điều kiện) | Dùng theo LGPL-3.0: liên kết động, người dùng thay được thư viện Qt (bản one-folder của PyInstaller thỏa), giữ thông báo và văn bản giấy phép. Metadata còn có `LicenseRef-Qt-Commercial` (không dùng) |
| Pillow | 12.3.0 | `MIT-CMU` (kiểu HPND) | Xử lý ảnh bìa | Có | Giấy phép cho phép |
| cryptography | 50.0.1 | `Apache-2.0 OR BSD-3-Clause` | Mã hóa khóa API (`SecretStore`) | Có | Chọn nhánh BSD-3-Clause hoặc Apache-2.0 đều được |
| cffi | 2.1.1 | `MIT-0` | (phụ thuộc của cryptography) | Có | |
| pycparser | 3.0 | `BSD-3-Clause` | (phụ thuộc của cffi) | Có | |
| requests | 2.34.2 | `Apache-2.0` | Gọi API bìa/AI/review | Có | Apache-2.0 tương thích một chiều với GPLv3/AGPLv3 |
| urllib3 | 2.8.0 | `MIT` | | Có | |
| certifi | 2026.7.22 | `MPL-2.0` | Gói chứng chỉ CA | Có | MPL-2.0 điều 3.3 cho phép kết hợp với AGPL. Giữ nguyên file MPL |
| charset-normalizer | 3.5.1 | `MIT` | | Có | |
| idna | 3.19 | `BSD-3-Clause` | | Có | |
| watchdog | 6.0.0 | `Apache-2.0` | Theo dõi thư mục | Có | |
| pyvi | 0.1.1 | `MIT` | Tách từ tiếng Việt (chỉ tiến trình phân loại) | Có | Kèm mô hình CRF đóng gói qua `collect_data_files('pyvi')`: **nguồn dữ liệu huấn luyện chưa xác minh** (mục 5, câu 2) |
| scikit-learn | 1.9.1 | `BSD-3-Clause` | (phụ thuộc pyvi) | Có | |
| sklearn-crfsuite | 0.5.0 | `MIT` | (phụ thuộc pyvi) | Có | Metadata không kèm file LICENSE (0 file); xác minh nếu cần in nguyên văn |
| python-crfsuite | 0.9.12 | `MIT` | (phụ thuộc pyvi) | Có | Bản wheel có thể nhúng mã C (CRFsuite/liblbfgs): chưa đối chiếu, xem file giấy phép trong dist-info |
| NumPy | 2.5.3 | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | (phụ thuộc pyvi) | Có | |
| SciPy | 1.18.1 | BSD-3-Clause (nhiều thành phần con) | (phụ thuộc pyvi) | Có | Wheel nhúng runtime gfortran/GCC: `GPL-3.0-or-later WITH GCC-exception-3.1` (có ngoại lệ GCC, không lan sang mã khác). Đã thấy trong file giấy phép của gói |
| joblib | 1.6.0 | `BSD-3-Clause` | (phụ thuộc scikit-learn) | Có | |
| cloudpickle | 3.1.2 | `BSD-3-Clause` | (phụ thuộc joblib) | Có | **Chưa có** trong `THIRD_PARTY_NOTICES.md` cũ |
| narwhals | 2.26.0 | `MIT` | (phụ thuộc scikit-learn) | Có | **Chưa có** trong notices cũ |
| threadpoolctl | 3.7.0 | `BSD-3-Clause` | | Có | |
| tabulate | 0.10.0 | `MIT` | (phụ thuộc sklearn-crfsuite) | Có | |
| tqdm | 4.70.1 | `MPL-2.0 AND MIT` | | Có | |
| loguru | 0.7.3 | MIT (theo Classifier; không có `License-Expression`) | (phụ thuộc mobi) | Có | **Chưa có** trong notices cũ. Metadata không kèm file LICENSE (0 file) |
| colorama | 0.4.6 | BSD (theo Classifier) | (phụ thuộc loguru/tqdm) | Có | **Chưa có** trong notices cũ |
| win32-setctime | 1.2.0 | MIT | (phụ thuộc loguru, chỉ Windows) | Có | **Chưa có** trong notices cũ |
| standard-imghdr | 3.13.0 | `PSF-2.0` | (phụ thuộc mobi) | Có | **Chưa có** trong notices cũ. PSF-2.0 tương thích GPL |

**Module Qt thực sự dùng** (`grep` mã nguồn): `QtCore`, `QtGui`, `QtWidgets`, `QtPdf`, `QtPdfWidgets`. Metadata `pyside6-addons` liệt kê `QtPdf`/`QtPdfWidgets` dưới cùng biểu thức giấy phép LGPL/GPL của gói. **Không** dùng module Qt nào được biết là chỉ GPL/thương mại (Charts, Data Visualization…), nhưng câu hỏi "QtPdf có nằm ngoài LGPL không" vẫn nên đối chiếu với trang giấy phép chính thức của Qt (mục 5, câu 1).

## 2. Công cụ build và phát triển (không nằm trong mã ứng dụng, nhưng bản dựng có nhúng một phần)

Giấy phép trong bảng này ghi theo hiểu biết chung, **chưa** đối chiếu với metadata cài đặt (khác mục 1); cần xác minh nếu đưa vào thông báo chính thức.

| Công cụ | Giấy phép | Ghi chú |
|---|---|---|
| PyInstaller ≥ 6.22.3 | GPL-2.0-or-later kèm **ngoại lệ bootloader** (cho phép phân phối app theo giấy phép bất kỳ) | Bootloader được nhúng vào `MewBook.exe`; ngoại lệ áp dụng. Chưa xác minh văn bản ngoại lệ trong bản 6.22.3 (mục 5, câu 3) |
| Inno Setup | Giấy phép riêng của Inno Setup (miễn phí, cho phép dùng thương mại) | Chỉ tạo bộ cài, không nhúng vào app. Cần ghi nguồn trong tài liệu phát hành nếu muốn |
| pytest ≥ 8 | MIT | Chỉ phát triển |
| hatchling | MIT | Chỉ build wheel |
| uv | Apache-2.0 hoặc MIT | Công cụ, không phân phối |
| pgserver 0.1.4 | Apache-2.0 (văn bản `LICENSE` trong gói) | **Tùy chọn**: chỉ để chạy `tests/test_server_sql.py` (PostgreSQL nhúng). Không nằm trong `pyproject.toml`, không đóng gói, không phải phụ thuộc của dự án; cài bằng `uv pip install` khi cần |
| psycopg2-binary 2.9.13 | LGPL kèm ngoại lệ (metadata: "LGPL with exceptions") | Như trên: chỉ để chạy test SQL, không đóng gói |
| Claude Code (CLI) | Sản phẩm của Anthropic, theo điều khoản của họ | Chủ dự án cài trên **máy chạy tác tử** (`tools/triage/`); **không** đóng gói, không phải phụ thuộc của mã. Cờ dùng: `docs/ERROR_OPS_RUNBOOK.md` mục 6 |

## 3. Tài nguyên đóng gói

Theo `packaging/MewBook.spec`, các tài nguyên sau được đóng gói (từ giao diện "Kệ sách" có 5 phông OFL được đóng gói, xem hàng cuối):

| Tài nguyên | Đường dẫn | Nguồn gốc/giấy phép | Trạng thái |
|---|---|---|---|
| Mô hình phân loại | `src/smartdoc/data/classifier_model.json.gz` (+ `.meta.json`) | Do dự án tự huấn luyện (`train.py`) từ **thư viện của tác giả** (9.451 tài liệu) và `taxonomy.json` | Quyền sở hữu: chủ dự án. Kiểm toán từ vựng xong ở S0-04 (`MODEL_VOCAB_AUDIT.md`): rủi ro nhận diện thấp; có đề xuất siết ngưỡng và stoplist chờ duyệt; nguồn dữ liệu huấn luyện thành câu hỏi luật sư |
| Phân loại (taxonomy) | `src/smartdoc/data/taxonomy.json` | Do dự án soạn | Chủ dự án là tác giả. Xác nhận không sao chép nguyên văn từ nguồn ngoài (mục 5, câu 4) |
| Mô hình tách từ | `collect_data_files('pyvi')` | Gói `pyvi` (MIT) | Nguồn dữ liệu huấn luyện của mô hình CRF **chưa rõ** (mục 5, câu 2) |
| Biểu tượng ứng dụng | `presentation/assets/app_icon.ico` | Sinh từ `brand_logo.png` bằng `packaging/process_brand_icon.py` | **Nguồn gốc ảnh chưa xác nhận (O12)** |
| Ảnh linh vật (7 vai trò) | `presentation/assets/brand/*.png` | Sinh từ `Sample theme/cat/` bằng `tools/prepare_brand_assets.py`; chủ dự án xác nhận `logo.png` là logo chính thức (2026-09-24) | Nguồn gốc/điều khoản công cụ tạo ảnh vẫn cần chốt (O12) trước khi công khai kho mã |
| Logo thương hiệu | `presentation/assets/brand_logo.png` | Ảnh mèo do chủ dự án cung cấp; dấu hiệu do công cụ tạo ảnh AI tạo ra (theo `08` mục 8) | **Chưa xác nhận điều khoản công cụ tạo ảnh (O12)**; giấy phép tranh: O11 |
| Mã QR ủng hộ | `presentation/assets/donate_qr.png` (chỉ đóng gói nếu file tồn tại) | Mã ngân hàng cá nhân của tác giả | **Hiện không có trong repo.** Quyết định của chủ dự án có đưa vào kho công khai không |
| Phông chữ (Be Vietnam Pro, Lora, Montserrat, Playfair Display, Oswald) | `presentation/assets/fonts/*.ttf` (kèm `OFL_*.txt`) | Tải từ github.com/google/fonts (thư mục `ofl/`), SIL Open Font License 1.1 | Được phép nhúng và phát hành cùng ứng dụng; giữ nguyên văn giấy phép cạnh phông, không bán phông riêng lẻ, không dùng tên phông đã đăng ký (Reserved Font Name) cho bản sửa |
| Ảnh xem trước theme | thư mục `Sample theme/` | Tên `Gemini_Generated_Image_*` (công cụ tạo ảnh AI) | **Không** đóng gói, chưa theo dõi bởi git. Nếu công khai, cần xác nhận O12 |

## 4. Dịch vụ bên ngoài (không phải phụ thuộc giấy phép, ghi ở đây để đồng bộ với S0-08)

Open Library, Google Books (API và Atom feed), Apple iTunes Search API, Tiki, Google Custom Search, Supabase (dịch vụ review), các nhà cung cấp AI do người dùng tự chọn (OpenAI, Gemini, Anthropic, OpenRouter, Mistral, DeepSeek, Ollama…). Điều khoản từng nguồn: `docs/legal/DATA_SOURCES.md` (S0-08, đã làm; Tiki và Apple Books tắt mặc định). Thêm ở 1.1.0: máy chủ nhận báo lỗi (Supabase) và dịch vụ AI của tác tử phân loại (Anthropic, do chủ dự án chạy; chỉ nhận dữ liệu báo lỗi đã lọc), xem `DATA_SOURCES.md` mục 2.10 và 2.11.

## 5. Câu hỏi còn mở (cho chủ dự án và luật sư)

1. **Qt/QtPdf:** xác nhận trên trang giấy phép chính thức của Qt rằng `QtPdf`/`QtPdfWidgets` (kèm thành phần Chromium/PDFium nếu có) phân phối được theo LGPL-3.0. Metadata của gói PySide6 nói có, nhưng chưa đối chiếu nguồn Qt.
2. **Dữ liệu mô hình CRF của `pyvi`:** gói khai MIT, nhưng nguồn/giấy phép của kho ngữ liệu huấn luyện mô hình đi kèm chưa được ghi. Cần đọc README/kho mã của pyvi.
3. **PyInstaller:** xác nhận văn bản ngoại lệ bootloader trong đúng bản 6.22.3.
4. **`taxonomy.json`:** có sao chép nguyên văn từ hệ phân loại ngoài (ví dụ Dewey, thư viện quốc gia) không?
5. **PyMuPDF "only" hay "or later":** metadata chỉ ghi "GNU AFFERO GPL 3.0". Ảnh hưởng chọn SPDX (O4): `AGPL-3.0-or-later` cho mã của chủ dự án vẫn ổn, nhưng tác phẩm gộp sẽ bị ràng buộc bởi phần "only" của `mobi` (GPL-3.0-only).
6. **Ranh giới GPLv3 ↔ AGPLv3** với `mobi`: luật sư xác nhận cách kết hợp và nội dung thông báo.
7. **`sklearn-crfsuite`, `loguru`:** metadata không kèm file LICENSE; nếu cần in nguyên văn giấy phép trong bản cài, lấy từ kho mã của tác giả gói.
8. **Kiểm tra lại bản dựng thật:** danh sách này lấy từ cây phụ thuộc, chưa đối chiếu với thư mục `dist/MewBook/_internal`. Cần khi làm bản phát hành (thư mục `dist/` đã có nhưng có thể cũ).

## 6. Kết luận kỹ thuật (chờ luật sư)

- Không thấy phụ thuộc nào có giấy phép **loại trừ** việc phân phối ứng dụng dưới AGPL-3.0.
- Hai thành phần buộc hướng AGPL/GPL: PyMuPDF (nhánh AGPL) và `mobi` (GPL-3.0-only). Cả hai phù hợp với quyết định D1.
- Còn 8 điểm chưa rõ ở mục 5. Điểm 1, 2 và 5 nên được xử lý trước khi công khai; các điểm còn lại là bổ sung hồ sơ.
- `THIRD_PARTY_NOTICES.md` cũ thiếu 6 gói (loguru, colorama, win32-setctime, standard-imghdr, cloudpickle, narwhals) và các gói con của PySide6; đã được viết lại cùng lượt này.
