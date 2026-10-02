# Kiến trúc UI phân loại — Danh sách kết quả & "Chưa chắc"

## Tổng quan

MewBook đã có sẵn cơ chế quản lý sách "chưa chắc" (sách mô hình gợi ý nhưng người dùng chưa xác nhận):
1. **Hashtag giữ chỗ:** "Chưa chắc" (UNSURE_TAG) được tự động gán cho sách không được phân loại với danh mục
2. **Danh sách kết quả:** component `smart_classify_results.py` hiển thị 3 thẻ kết quả (Đã gắn / Chưa chắc / Lỗi)
3. **Nhóm theo lý do:** sách "Chưa chắc" được nhóm theo lý do (Không có chữ / Tạp chí / Nhiều chủ đề / Mô hình phân vân / ...)
4. **Chỉnh sửa hàng loạt:** chọn nhiều sách từ một nhóm → "Gắn hashtag…" → gắn danh mục hay text tự do
5. **Cột theo dõi:** cột "Hashtag" cập nhật ngay khi gắn

## Cấu trúc dữ liệu

### Hashtag "Chưa chắc"
```python
# smartdoc/application/smart_classifier.py
UNSURE_TAG = "Chưa chắc"
```
- Trạng thái (không phải thể loại), tự động gán khi `result.category_id is None`
- Được loại bỏ ngay khi gắn danh mục thật (xem `tag_books`, `replace_tag`)

### Nhóm lý do ("Chưa chắc")
```python
# smartdoc/application/smart_classifier.py
UNSURE_REASONS = {
    "no_text": "Không có chữ đọc được (bản quét, có DRM hoặc định dạng không đọc được)",
    "periodical": "Tạp chí, báo: không thuộc thể loại sách nào",
    "mixed_topics": "Nội dung trộn nhiều chủ đề",
    "low_confidence": "Mô hình phân vân giữa nhiều thể loại",
    "not_enough_evidence": "Ít chữ hoặc chưa đủ manh mối",
}
```
- Key: reason code (từ `worker result.reason`)
- Value: label Tiếng Việt hiển thị cho người dùng

### Event kết quả phân loại
```python
# smartdoc/application/smart_classifier.py, ClassifyFinishedEvent
tagged_items: list[tuple[doc_id, tag, group]]  # sách được gắn → nhóm theo folder, rồi hashtag
tagged_ids: list[doc_id]  # khi event từ trước cơ sở dữ liệu (không có item detail)
unknown_items: list[tuple[doc_id, reason]]     # sách "Chưa chắc" → nhóm theo reason
unknown_ids: list[doc_id]
failed_items: list[tuple[doc_id, error]]       # sách lỗi đọc file
failed_ids: list[doc_id]
```

## Component hiển thị: SmartClassifyResultsDialog

**File:** `src/smartdoc/presentation/smart_classify_results.py`

**Hàm chính:** `build_tree(kind: str, event, docs) -> list[Node]`
- `kind="unknown"` → nhóm theo reason code (dùng `UNSURE_REASONS` để dịch label)
- Tạo `Node` cây: mỗi reason → danh sách sách

**Tính năng:**
- Thanh tìm kiếm (accent-insensitive)
- Cột "Hashtag" hiển thị hashtag hiện tại
- Chọn 1 hay nhiều sách → nút "Gắn hashtag…" → dialog chọn danh mục hoặc gõ text tự do
- Cột theo dõi cập nhật ngay (gọi `reload()` callback)

## Cách mở rộng: Thêm nhóm lý do mới

Khi B2 hoặc Ollama muốn thêm nhóm lý do mới (ví dụ "Gợi ý từ AI, chưa chắc"):

1. **Thêm vào `UNSURE_REASONS`** (`smart_classifier.py`):
   ```python
   UNSURE_REASONS = {
       ...
       "low_confidence": "Mô hình phân vân giữa nhiều thể loại",
       "ollama_suggestion": "Gợi ý từ AI, cần xác nhận",  # ← mới
   }
   ```

2. **Đảm bảo worker tạo result với reason code mới:**
   ```python
   # Khi Ollama gợi ý:
   result["reason"] = "ollama_suggestion"
   result["category_id"] = None  # chưa chắc
   ```

3. **Component tự động nhóm:** không cần sửa `smart_classify_results.py`
   - `build_tree()` sẽ tự động tạo nhóm "Gợi ý từ AI, cần xác nhận" bên cạnh "Không có chữ", "Tạp chí", v.v.
   - Người dùng chọn sách từ nhóm → "Gắn hashtag…" → xác nhận

4. **Xác nhận an toàn:**
   - Hashtag "Chưa chắc" vẫn là trạng thái duy nhất cho tất cả "chưa chắc" (không tạo hashtag giữ chỗ mới)
   - Khi gắn danh mục, "Chưa chắc" được loại bỏ (xem `tag_books` → `replace_tag`)
   - Các sách cũ với "Chưa chắc" từ Lớp 1 không bị ảnh hưởng

## Nếu gặp vướng mắc

Nếu cấu trúc không cho phép mở rộng theo cách trên (ví dụ cần thêm metadata về nguồn gợi ý hoặc độ tự tin của từng reason), **dừng lại và báo cáo chi tiết** — không tự ý xây dựng khu vực hiển thị riêng hay hashtag giữ chỗ thứ hai.
