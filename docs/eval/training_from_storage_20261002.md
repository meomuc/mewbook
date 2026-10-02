# Thử huấn luyện lại bằng kho `E:\Ebook_storage` — kết luận: không thay mô hình

**Ngày:** 2026-10-02 · **Kết quả:** giữ mô hình Lớp 1 hiện tại; dùng B2 (gợi ý nhận nhanh) và B4 (Ollama, tùy chọn) để đưa độ bao phủ lên mục tiêu 90%.

## Phát hiện

- `E:\Ebook_storage\000.Thư viện` **chính là thư viện**: 7.814/8.605 sách trong `library.db` trỏ vào đó. Kho không thêm sách mới nào để huấn luyện.
- Thứ kho có là cách chủ dự án xếp sách theo thư mục thể loại (Truyện ngắn, truyện dài, Trinh Thám, Kiếm Hiệp, Cổ tích, Phật giáo...): nhãn cho 4.872 sách chưa có hashtag. Các thư mục "Bài viết", "03. LƯU TRỮ", "EPUB THÊM", "1001 Books", "Trung Hoa" **không** phải nhãn thể loại.
- Nhãn `dc:subject` trong file `.opf` không dùng được: chỉ 1.271 sách ánh xạ được vào thể loại, 60% rơi vào "Hồi ký - Tùy bút", chỉ 7/48 thể loại có từ 30 cuốn.
- Nhãn do Ollama đoán (600 cuốn mẫu) không được dùng làm đáp án; Ollama và Lớp 1 chỉ đồng ý ở 36% số cuốn, và Ollama thiên về "tiểu thuyết"/"cổ văn Việt Nam".

## Thử nghiệm (trên bản sao `library.db`, không đụng bản thật)

Gán nhãn từ thư mục cho 80% sách (3.897), giữ 20% (975) làm tập thử; huấn luyện mô hình mới (A), và biến thể B bỏ 5 thư mục dễ lẫn (Hồi Ký, Suy ngẫm, Nhân Vật Lịch sử, Tuổi Học Trò, Phiêu Lưu).

| | Hiện tại | A | B |
|---|---:|---:|---:|
| 975 sách thể loại: đúng trên cả tập | 93,0% | 97,4% | 97,3% |
| 975 sách thể loại: gắn được | 95,9% | 99,7% | 99,5% |
| 150 sách khó (thư mục không có nhãn): gắn được | 0 | 29 | 26 |
| Trùng ý với trọng tài `qwen2.5:14b` ở sách khó | n/a | 36% | 36% |

Cải thiện lớn nhất: trinh thám (61 → 83 cuốn đúng), kinh dị (34 → 44).

## Vì sao không thay

- 1.606 sách còn thiếu nằm chủ yếu ở thư mục không có nhãn: "1001 Books" 390, ngoài kho 271, "03. LƯU TRỮ" 229, "EPUB THÊM" 201.
- Mô hình mới gắn thêm được 416/1.606, nhưng ở sách ngoài miền truyện/tiếng Việt độ tin cậy thấp (36% trùng trọng tài; xem tay 30 cuốn: khoảng 65% hợp lý, sai nhiều ở "Trung Hoa" → "kiếm hiệp"). Bỏ thư mục dễ lẫn không cải thiện.
- Thay mô hình sẽ cho +~185 sách thể loại đúng nhưng thêm ~270 hashtag tin cậy thấp và làm các sách đó mất nhãn "Chưa chắc", nên người dùng không còn thấy để duyệt.
- Không hạ ngưỡng tự tin (`min_score`/`min_group_prob`/`min_class_prob`) vì đó là quyết định của chủ dự án.

## Đường đi đã chọn

1. Giữ mô hình hiện tại.
2. B2: nhóm "Gợi ý từ mô hình, cần bạn xác nhận" — 590 sách (độ tự tin ≥ 0,5); nhận hết thì bao phủ khoảng 86,4%.
3. B4: Ollama tùy chọn (Cài đặt › Phân loại) cho ~1.000 sách còn lại, vẫn chỉ là gợi ý, người dùng xác nhận.
4. Nếu vẫn thiếu để chạm 90%: gắn tay vài chục cuốn cho mỗi miền khó (sách tiếng Anh kinh điển, bản tóm tắt, sách ngoài kho, văn học Trung Hoa), huấn luyện lại và đo riêng trên các miền đó.

Công cụ dùng: `tools/eval/label_with_ollama.py`, `train.py --library-db <bản sao> --output <file tạm>`. Nhãn từ thư mục chỉ gán trên bản sao.
