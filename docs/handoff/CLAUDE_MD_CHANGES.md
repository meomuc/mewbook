# Sửa đổi `CLAUDE.md` (S0-10, `01_PRD.md` mục 7)

`CLAUDE.md` là bộ quy tắc ưu tiên cao nhất của kho. Bảng dưới ghi từng sửa đổi A1–A6: đã áp dụng hay còn chờ, và diff đề xuất cho phần chờ. Ngày 2026-09-19 chủ dự án cho phép Claude Code thực hiện phần còn lại của công việc; các sửa đổi **gắn với tính năng đã tồn tại** được áp dụng ngay, các sửa đổi **gắn với tính năng chưa có** được giữ ở đây và áp dụng khi tính năng đó được xây, để `CLAUDE.md` không mô tả quy tắc cho thứ chưa tồn tại.

| # | Nội dung | Trạng thái | Áp dụng khi |
|---|---|---|---|
| A1 | Làm rõ "không di chuyển/xóa file gốc": chép lên thiết bị theo lệnh người dùng được phép | **Chờ** | S3b-07 (gửi tới thiết bị) |
| A2 | Không hỗ trợ DRM; chuyển đổi không ghi đè file gốc | **Đã áp dụng** 2026-09-19 | (`docs/legal/DRM_POLICY.md`) |
| A3 | Mọi nguồn dữ liệu phải có dòng trong `DATA_SOURCES.md`; nguồn không rõ điều khoản thì tắt mặc định | **Đã áp dụng** 2026-09-19 | (`docs/legal/DATA_SOURCES.md`) |
| A4 | Test cần thiết bị thật phải bỏ qua được, không bắt buộc trong CI | **Chờ** | S3b (test thiết bị) và S1-01 (CI) |
| A5 | Khung migration `user_version` là phần bổ sung; `_migrate_add_missing_columns` giữ quy tắc chỉ append | **Chờ** | S1-02 |
| A6 | Chính sách SPDX cho tệp mới | **Đã áp dụng** 2026-09-19 | (`docs/legal/SPDX_POLICY.md`) |

Ngoài A1–A6, một sửa nhỏ để khớp thực tế: dòng cấm commit `packaging/EULA.txt` sinh ra đã bỏ vì `build.ps1` không còn sinh tệp đó (S0-05).

## Diff cho các phần chờ

### A1 (áp dụng cùng S3b-07)

Sửa dòng "Don't move or delete users' original ebook files..." ở mục 4:

```diff
-- Don't move or delete users' original ebook files. Writing *metadata* into EPUB/PDF is allowed only as specified in `docs/METADATA_LOOKUP_SPEC.md` §5 (explicit per-run opt-in, backup first, temp file + verify + `os.replace`); no other code path may modify them.
+- Don't move or delete users' original ebook files. Writing *metadata* into EPUB/PDF is allowed only as specified in `docs/METADATA_LOOKUP_SPEC.md` §5 (explicit per-run opt-in, backup first, temp file + verify + `os.replace`); no other code path may modify them. *Copying* a file to a device or folder is allowed only on an explicit user command and after confirmation; never delete or overwrite anything on a device except our own partial file.
```

### A4 (áp dụng cùng S3b, S1-01)

Thêm vào mục 3, phần Tests:

```diff
 - Tests: `tests/test_<module>.py`, use the `app_context` / `qapp` fixtures (in-memory DB); bug fixes get a regression test that fails before the fix.
+- A test that needs a real device or other hardware must be skippable (`pytest.mark.skipif` / a marker) and is never required in CI.
```

### A5 (áp dụng cùng S1-02)

Thêm vào mục 4, cạnh quy tắc migration:

```diff
 - Never edit an existing migration: `src/smartdoc/application/sql/001_*.sql` (Supabase) is immutable — add `002_*.sql`. In `DatabaseManager._migrate_add_missing_columns` only *append* new columns; never rename/drop/alter existing ones (users' `library.db` must upgrade in place).
+- Schema changes beyond appending a column go through the `user_version` migration framework (S1-02), which backs up the database first and never runs on a database it cannot back up. `_migrate_add_missing_columns` keeps the append-only rule.
```

(Nội dung A5 sẽ được chỉnh theo thiết kế thực tế của S1-02 khi làm.)

## Các thay đổi khác nên cân nhắc (không nằm trong A1–A6)

- Mục 1 (Project Overview) chưa nhắc `TRADEMARK.md`, `PARTNERS.md`, `docs/NAMING.md`; có thể thêm một dòng trỏ tới `docs/NAMING.md` (tên kỹ thuật `smartdoc`, `SmartDocLibrary` không được đổi).
- Mục 2 nói `build.ps1` chạy "tests + exe + installer"; khi thiếu Inno Setup nó chỉ cảnh báo. Đề xuất ở `docs/RELEASE_CHECKLIST.md` (cổng "có bộ cài") thay vì sửa `CLAUDE.md`.
