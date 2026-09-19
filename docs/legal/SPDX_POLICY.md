# Chính sách SPDX cho tệp mã nguồn (S0-05, A6)

Quyết định của chủ dự án (O4, 2026-09-19): mã của MewBook phát hành theo **`AGPL-3.0-or-later`**. Văn bản giấy phép nằm ở `LICENSE` (bản nguyên văn từ gnu.org, 661 dòng); `pyproject.toml` khai `license = "AGPL-3.0-or-later"` và `license-files = ["LICENSE"]` (wheel đã kiểm: `License-Expression` và `licenses/LICENSE` có mặt).

## 1. Quy tắc cho tệp mới

Mọi tệp **mã** mới có dòng đầu tiên là:

```
# SPDX-License-Identifier: AGPL-3.0-or-later
```

| Loại tệp | Cách ghi |
|---|---|
| Python (`.py`) | Dòng 1 là chú thích ở trên, **trước** docstring đầu module (docstring vẫn là câu lệnh đầu tiên nên không ảnh hưởng `__doc__` hay `from __future__`) |
| SQL (`.sql`) | `-- SPDX-License-Identifier: AGPL-3.0-or-later` |
| PowerShell (`.ps1`), YAML, TOML, cấu hình có chú thích `#` | Như Python |
| Inno Setup (`.iss`) | `; SPDX-License-Identifier: AGPL-3.0-or-later` |
| Tệp không có chú thích (JSON, ảnh, dữ liệu mô hình) | Không ghi; được `LICENSE` bao trùm. Riêng ảnh và mô hình: xem mục 3 |

Không thêm dòng `SPDX-FileCopyrightText` cho tới khi luật sư chốt cách viết thông báo bản quyền (câu 6 trong `LAWYER_QUESTIONS.md`).

## 2. Tệp đã có

Không thêm tiêu đề hàng loạt trong lượt này (tránh một commit đổi mọi tệp). Chủ dự án quyết định một trong hai: (a) thêm khi sửa tệp đó, hoặc (b) một commit riêng cho toàn bộ `src/`, `tests/`, `packaging/`. Đề xuất (a); `LICENSE` và `pyproject.toml` đã đủ để giấy phép có hiệu lực cho cả kho.

## 3. Ngoại lệ và lưu ý

- **Mã của bên thứ ba** chép vào kho: giữ nguyên tiêu đề giấy phép của họ, ghi vào `THIRD_PARTY_NOTICES.md`, và chỉ nhận nếu tương thích AGPL-3.0 (`LICENSE_INVENTORY.md`). Không gắn nhãn `or-later` lên mã không phải của dự án.
- **Ảnh linh vật, logo, biểu tượng, mô hình phân loại:** chưa có quyết định giấy phép riêng. Nguồn gốc ảnh (O12) và nguồn huấn luyện mô hình (S0-04, câu 11) còn mở; đến khi rõ thì không tuyên bố giấy phép nào ngoài `LICENSE` cho chúng.
- **Tài liệu (`docs/`, README):** chưa quy định (tùy chọn: cùng giấy phép, hoặc CC BY-SA). Chủ dự án quyết định ở S0-11.
- **`-or-later` và các phụ thuộc:** `mobi` là `GPL-3.0-only` và PyMuPDF chỉ ghi "GNU AFFERO GPL 3.0" không kèm "only/or later". Mã của MewBook vẫn cấp giấy phép `or-later`, nhưng **bản phân phối hợp nhất** (exe có `mobi`) thực tế chỉ dùng được theo phiên bản 3 của GPL/AGPL: người nhận không thể chọn một phiên bản mới hơn cho toàn bộ. Điểm này đã nằm trong câu hỏi luật sư 3b và 4; không cần đổi quyết định O4.

## 3b. Quy tắc `CLAUDE.md` (A6) — đã áp dụng 2026-09-19 theo phê duyệt chung của chủ dự án

Thêm vào mục 3 (Code Style & Conventions):

```diff
+- Licence: the code is `AGPL-3.0-or-later` (`LICENSE`). Every **new** source file starts with `# SPDX-License-Identifier: AGPL-3.0-or-later` (SQL: `--`), before the module docstring; see `docs/legal/SPDX_POLICY.md`. Don't add a dependency whose licence is incompatible with AGPL-3.0 (see `docs/legal/LICENSE_INVENTORY.md`).
```

Dòng cũ ở mục 4 về kiểm tra giấy phép phụ thuộc được giữ nguyên (hai dòng bổ sung nhau).

## 4. Đóng gói (S0-05, đã áp dụng)

Đã làm ngày 2026-09-19 (commit `S0-05: installer shows LICENSE ...`) và kiểm bằng bản dựng thử `build.ps1 -SkipTests`:

- `packaging/MewBook.iss`: trang giấy phép của trình cài đặt hiển thị `..\LICENSE` (AGPL-3.0-or-later).
- `packaging/build.ps1`: không còn sinh `packaging/EULA.txt`.
- `packaging/MewBook.spec`: đóng gói `LICENSE`, `THIRD_PARTY_NOTICES.md` và (S0-06) `*.dist-info` của mọi phụ thuộc, nên giấy phép của chúng đi kèm bản dựng. Bản dựng thử có 32 thư mục `dist-info`; chỉ `loguru` và `sklearn_crfsuite` không có tệp giấy phép (đã ghi ở `LICENSE_INVENTORY.md` mục 5.7).
- README, CLAUDE.md và CHANGELOG đã sửa cho khớp.
- Hộp thoại EULA/Quyền riêng tư trong ứng dụng (`presentation/eula_dialog.py`) **không đổi**: nó vẫn là thông báo quyền riêng tư, chờ S2-06 (bản nháp Privacy/Terms). Hộp thoại Giới thiệu đã hiển thị AGPL (S0-06).
