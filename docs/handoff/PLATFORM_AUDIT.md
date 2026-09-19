# Kiểm kê mã riêng của Windows (S1-09)

Ngày: 2026-09-19. Mục đích: chuẩn bị cho việc chạy trên macOS/Linux (giai đoạn 2 của sản phẩm) **mà không tái cấu trúc bây giờ**. Đây là báo cáo, không có thay đổi mã trong lượt này. Phương pháp: tìm `sys.platform`, `os.startfile`, `ctypes`/`WinDLL`, `%APPDATA%`, `explorer`, `subprocess`, đường dẫn và phông chữ trong `src/`, cộng đọc các tệp đóng gói. Quy tắc kiến trúc (`02_ARCHITECTURE.md` mục 9): mã riêng của một hệ điều hành chỉ nằm trong các mô-đun `*_windows.py`, nạp muộn theo nền tảng.

## 1. Tổng kết

Ứng dụng **gần như đã độc lập nền tảng**: chỉ có ba chỗ mã gọi API Windows, cả ba đã có nhánh cho macOS/Linux hoặc đã có phương án lùi. Phần lớn công việc để hỗ trợ hệ khác nằm ở **đóng gói, thư mục dữ liệu, lưu khóa bí mật và phông chữ/emoji**, không phải logic nghiệp vụ.

| Mức | Số chỗ | Ý nghĩa |
|---|---|---|
| Đã có nhánh đa nền tảng | 3 | `file_actions`, `classify_worker`, `default_app_data_dir` |
| Cần làm khi hỗ trợ hệ khác | 6 | thư mục dữ liệu, khóa bí mật, đóng gói, phông/emoji, so sánh đường dẫn, phát hiện Calibre (S4) |
| Chỉ là dữ liệu/tài liệu Windows | vài | ví dụ đường dẫn trong test và lời mô tả |

## 2. Từng chỗ

| # | Vị trí | Hiện trạng | Việc cần cho macOS/Linux |
|---|---|---|---|
| 1 | `presentation/file_actions.py` (mở file, mở thư mục chứa) | `os.startfile` và `explorer /select,"..."` cho Windows; `open`/`open -R` cho macOS; `xdg-open` cho Linux (trên Linux chỉ mở thư mục cha, không chọn file) | Đã đủ. Nếu tách theo quy tắc `*_windows.py`, chuyển nhánh Windows sang `file_actions_windows.py` (nhỏ, rủi ro thấp) |
| 2 | `application/classify_worker.py` (`lower_process_priority`) | `ctypes.WinDLL("kernel32")`/`ntdll` cho ưu tiên CPU và I/O, có `try/except`; nhánh khác dùng `os.nice(10)` | Đã đủ. `os.nice` không có trên mọi nền tảng nhưng lỗi được nuốt (best effort). Có thể tách phần `ctypes` sang `process_priority_windows.py` |
| 3 | `core/config.py` (`default_app_data_dir`) | `%APPDATA%\SmartDocLibrary`, nếu không có biến thì `~/.smartdoc/SmartDocLibrary` | Cần một điểm duy nhất theo nền tảng: macOS `~/Library/Application Support/`, Linux `$XDG_CONFIG_HOME` hoặc `~/.config/`. Xem thư viện `platformdirs` (MIT; kiểm kê giấy phép theo quy tắc trước khi thêm). **Tên thư mục `SmartDocLibrary` không đổi** (O7, `docs/NAMING.md`); hàm này phải giữ nguyên kết quả trên Windows |
| 4 | `core/secret_store.py` | Khóa Fernet trong `.secret.key` cạnh `settings.json`; không dùng DPAPI. Đã ghi rõ trong docstring rằng đây chỉ chống lộ tình cờ | Không phụ thuộc nền tảng, nên chạy được mọi nơi. Cải thiện tùy chọn: trên POSIX đặt quyền `0600` cho `.secret.key`; dùng kho khóa của hệ điều hành (DPAPI, Keychain, Secret Service) qua một lớp mỏng, có phương án lùi về tệp khóa |
| 5 | `packaging/` (`MewBook.spec`, `MewBook.iss`, `build.ps1`), `run.bat`, `README` | Toàn bộ là Windows: PyInstaller một thư mục, Inno Setup, PowerShell | Cần quy trình riêng: `.app`/DMG (macOS), AppImage hoặc gói `.deb`/Flatpak (Linux). Chưa có việc gì trong mã |
| 6 | `presentation/theme.py`: `MONO_FONT_FAMILIES`, `SANS_LIGHT_FONT_FAMILIES`... | Danh sách phông có "Segoe UI", "Consolas", "Candara", "Calibri" kèm phông thay thế (Helvetica Neue, Arial, Noto Sans...) | Đã có phương án lùi. Hình dạng chữ khác sẽ làm bố cục lệch nhẹ: cần kiểm tra bằng mắt trên từng nền tảng |
| 7 | Emoji trong chuỗi giao diện (📚, ⚠️, 💾...) | Dựa vào phông emoji hệ thống (Segoe UI Emoji trên Windows) | Linux cần phông như Noto Color Emoji (đưa vào tài liệu cài đặt); macOS có sẵn |
| 8 | `infrastructure/database.py`: `find_id_by_path` dùng `COLLATE NOCASE`; `application/relink_service.py`: `casefold()` khi so sánh tên và đường dẫn | Đúng cho hệ tập tin không phân biệt hoa thường (Windows, mặc định macOS) | Trên Linux (phân biệt hoa thường) hai file khác hoa thường có thể bị coi là một. Cần chọn kiểu so sánh theo nền tảng; mức độ rủi ro thấp |
| 9 | `application/import_queue.py`: `doc_id = md5(file_path)` | Đường dẫn là đầu vào của định danh: đổi cách viết đường dẫn (ổ đĩa, dấu gạch) làm đổi id | Thư viện của người dùng không di chuyển được giữa hai hệ điều hành nếu không có bước chuẩn hóa/relink. Đã có relink (S1-04) |
| 10 | Phát hiện Calibre (`ebook-convert`) (S4-03, chưa làm) | Các vị trí cài đặt thường gặp sẽ khác nhau | Thiết kế phát hiện theo nền tảng ngay khi làm S4-03 |
| 11 | Tests | Vài test dùng đường dẫn Windows (`D:\Ebooks`, `C:\Users\someone\...`) làm chuỗi mẫu; `conftest` dùng `QT_QPA_PLATFORM=offscreen` | Phần lớn chỉ là chuỗi; kiểm lại khi có CI trên hệ khác |

## 3. Phụ thuộc

- **PySide6, PyMuPDF, Pillow, watchdog, cryptography, scikit-learn, numpy, scipy**: có wheel cho Windows, macOS và Linux.
- **pyvi, mobi, requests**: thuần Python.
- **PyInstaller**: chạy trên cả ba nhưng phải dựng trên từng hệ (không dựng chéo).
- **Inno Setup**: chỉ Windows.

## 4. Đề xuất cho giai đoạn 2 (chưa làm)

1. Một mô-đun `core/paths.py` trả về thư mục dữ liệu, cấu hình và nhật ký theo nền tảng; `default_app_data_dir` gọi vào đó và **giữ nguyên kết quả trên Windows**.
2. Tách hai đoạn `ctypes` (ưu tiên tiến trình) và nhánh `explorer` thành `*_windows.py` theo quy tắc kiến trúc, nạp muộn.
3. Chạy CI (S1-01) thêm trên Linux để phát hiện sớm phần mã ngầm định Windows; test Qt vẫn `offscreen`.
4. Quyết định cách lưu khóa bí mật (mục 4 trong bảng) trước khi phát hành trên hệ khác.
5. Quy trình đóng gói riêng cho từng hệ, và bản kiểm tra bằng mắt cho phông/emoji.

Không có mục nào trong danh sách này chặn bản 1.x trên Windows.
