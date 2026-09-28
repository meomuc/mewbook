# SPDX-License-Identifier: AGPL-3.0-or-later
"""First-launch licence and privacy notice.

Shown once, before the main window ever appears, gating entry to the app on
an explicit "Tôi đã đọc, tiếp tục" click -- closing the dialog any other way
(the window's [x], Esc) does NOT count as agreeing (see app.py's main(),
which exits instead of building the main window when this dialog doesn't
return QDialog.Accepted). Acceptance is persisted to AppConfig.eula_accepted
so it is asked exactly once per install, not once per launch (the flag keeps
its old name so nobody who already accepted is asked again for no reason).

The wording is a short summary that must stay true to what the code does:
docs/legal/PRIVACY.md and docs/legal/TERMS.md hold the full drafts (shown in
Help -> About), tests/test_eula_dialog.py pins the facts this text states. It
takes no right away from the AGPL licence -- whether a notice may *block*
running the program at all is an open question for the lawyer.

EULA_TEXT is also reused verbatim by presentation/about_dialog.py's first legal
tab, so the wording only lives in one place.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout

EULA_TEXT = """Giấy phép và quyền riêng tư (bản tóm tắt)

Toàn văn nằm ở Trợ giúp → Giới thiệu → "Giấy phép, thông báo và quyền riêng tư": Chính sách riêng tư, Điều khoản, giấy phép AGPL và thông báo bên thứ ba.

1. Phần mềm tự do
MewBook (Mèo Mực) là phần mềm tự do theo giấy phép GNU AGPL-3.0-or-later: bạn được dùng, sao chép, chia sẻ và sửa đổi theo giấy phép đó, và có quyền nhận mã nguồn tương ứng với phiên bản bạn đang dùng. Phần mềm được cung cấp KHÔNG kèm bất kỳ bảo hành nào. Tên và logo có quy định riêng.

2. Sách của bạn ở trên máy bạn
MewBook chỉ đọc và sắp xếp các tệp trên máy bạn. Ứng dụng không tải tệp sách lên bất kỳ máy chủ nào, không di chuyển hay xóa tệp gốc. Bạn tự chịu trách nhiệm về nguồn gốc và bản quyền của tài liệu bạn thêm vào; ứng dụng không phân phối sách và không hỗ trợ gỡ DRM.

3. Dữ liệu chỉ rời khỏi máy khi bạn dùng một tính năng cần mạng
• Tìm ảnh bìa và metadata: tên sách, tác giả (đã làm sạch) và ISBN được gửi tới các nguồn bạn bật (Cài đặt → Ảnh bìa).
• Tóm tắt AI (tắt mặc định): thông tin nhận diện sách bạn thấy và duyệt trong hộp thoại (tên, tác giả, nhà xuất bản, năm…; không có nội dung bên trong sách) được gửi tới nhà cung cấp AI bạn chọn, bằng khóa của chính bạn. Khóa được mã hóa và lưu trên máy bạn, không gửi cho dự án. Kết quả AI có thể sai và chỉ để tham khảo.
• Đánh giá cộng đồng (tắt mặc định): mã tài liệu (chuỗi băm từ đường dẫn tệp, không có tên sách), biệt danh, điểm, nhận xét bạn viết và mã ẩn danh của bản cài đặt. Nội dung này hiển thị công khai.
• Báo lỗi ẩn danh: mặc định ứng dụng HỎI MỖI LẦN, cho bạn xem trước nguyên văn nội dung sẽ gửi và không gửi gì nếu bạn không đồng ý. Báo cáo đã che, không chứa tên sách, đường dẫn hay nội dung tài liệu; được giữ tối đa 90 ngày và được một công cụ AI hỗ trợ phân tích (chỉ phần đã lọc: loại lỗi, vị trí trong mã, phiên bản). Đổi hoặc tắt hẳn ở Cài đặt → Quyền riêng tư và báo lỗi.
• Kiểm tra bản mới (tắt mặc định): chỉ số phiên bản của ứng dụng.
Máy chủ nào nhận kết nối cũng thấy địa chỉ IP của bạn. Không có quảng cáo, không có theo dõi.

4. Đóng góp tự nguyện (Donate)
Ứng dụng miễn phí. "Ủng hộ tác giả" là tự nguyện, không phải điều kiện để dùng hay mở khóa tính năng.

Bấm "Tôi đã đọc, tiếp tục" nghĩa là bạn xác nhận đã đọc thông báo này."""


class EulaDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Giấy phép và quyền riêng tư")
        # Resizable, not fixed (task A2, docs/UI_DIALOG_AUDIT.md): a fixed size could not shrink on a very small
        # screen, and this is the one dialog shown before the app's own DialogSizeGuard-covered main window even
        # exists, so it needs to hold up on its own. Long as the text is, it already scrolls inside text_area
        # below regardless of window size -- only heading + button (both compact, one line) need to fit.
        self.setMinimumSize(360, 360)
        self.resize(560, 560)

        heading = QLabel("Giấy phép và quyền riêng tư", self)
        heading.setStyleSheet("font-weight: 700; font-size: 15px;")
        heading.setWordWrap(True)

        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setPlainText(EULA_TEXT)

        agree_button = QPushButton("Tôi đã đọc, tiếp tục", self)
        agree_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.text_area, stretch=1)
        layout.addWidget(agree_button)

    def reject(self) -> None:
        # Deliberately does nothing extra beyond the default -- overridden
        # only so the intent is explicit: closing via [x]/Esc must NOT be
        # mistaken for agreeing. main() checks exec()'s return value and
        # only ever treats Accepted (the button click) as consent.
        super().reject()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from smartdoc.presentation.theme import apply_light_theme

    app = QApplication(sys.argv)
    apply_light_theme(app)
    dialog = EulaDialog()
    print("result:", "Accepted" if dialog.exec() == QDialog.Accepted else "Rejected/closed")
