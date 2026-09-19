# Tên gọi trong dự án (S0-11, O7)

Sản phẩm có **tên hiển thị** khác với **tên kỹ thuật** của mã. Quyết định O7: **giữ nguyên tên kỹ thuật cũ**, vì đổi chúng làm hỏng dữ liệu và bản cài của người dùng hiện có.

| Vai trò | Tên | Có được đổi không |
|---|---|---|
| Tên sản phẩm (kỹ thuật, tiếng Anh) | **MewBook** (`APP_NAME`) | Đổi ở một chỗ: `src/smartdoc/__init__.py` |
| Tên hiển thị (giao diện tiếng Việt) | **Mèo Mực** (`APP_DISPLAY_NAME`) | Như trên |
| Nhà phát hành | `APP_PUBLISHER` | Như trên |
| Gói Python và thư mục mã | `smartdoc` (`src/smartdoc/`) | **Không.** Đổi thì mọi `import` và lệnh chạy đổi theo |
| Tên phân phối trên PyPI/wheel | `smartdoc-library` (`pyproject.toml`) | Không cần thiết, giữ |
| Lệnh chạy | `smartdoc` (`[project.scripts]`), `run.bat` | Giữ |
| Thư mục dữ liệu người dùng | `%APPDATA%\SmartDocLibrary\` (`APP_DIR_NAME` trong `core/config.py`) | **Không.** Chứa `library.db`, `settings.json`, `identity.dat`, ảnh bìa, nhật ký; đổi tên thì người dùng cũ mất thư viện |
| Tệp nhật ký | `mewbook.log` | Giữ |
| Tệp chạy và bộ cài | `MewBook.exe`, `MewBook-Setup-X.Y.Z.exe` (`packaging/`) | Chỉ bản sửa đổi mới cần đổi (`TRADEMARK.md`) |
| `AppId` của trình cài đặt | GUID trong `packaging/MewBook.iss` | **Không bao giờ** với bản gốc: đổi thì Windows coi là sản phẩm khác và không nâng cấp tại chỗ. Bản sửa đổi/fork nên đổi để khỏi ghi đè bản gốc |

## Tại sao có hai tên cũ (`smartdoc`, `SmartDocLibrary`)

Dự án bắt đầu với tên "SmartDoc Library" rồi đổi thương hiệu thành MewBook / Mèo Mực (2026-09-18, xem `CHANGELOG.md`). Tên kỹ thuật được giữ để bản đã cài cập nhật tại chỗ và mã hiện có không phải sửa hàng loạt. Người đọc mã sẽ thấy `smartdoc` ở khắp nơi; đó là chủ ý.

## Quy tắc cho mã mới

- Chuỗi hiển thị cho người dùng lấy từ `APP_NAME`, `APP_DISPLAY_NAME`, `APP_PUBLISHER`; **không viết cứng** "MewBook" hay "Mèo Mực" trong mã (`tests/test_brand_constants.py` sẽ báo lỗi).
- Tên hình ảnh (logo, biểu tượng) lấy qua `presentation/resources.py`.
- Thương hiệu và điều kiện dùng tên/logo: `TRADEMARK.md`. Đồng thương hiệu với đối tác đang **hoãn** (D9).
