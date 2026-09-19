"""First-launch EULA / Privacy notice.

Shown once, before the main window ever appears, gating entry to the app on
an explicit "Tôi đã đọc và Đồng ý" click -- closing the dialog any other way
(the window's [x], Esc) does NOT count as agreeing (see app.py's main(),
which exits instead of building the main window when this dialog doesn't
return QDialog.Accepted). Acceptance is persisted to AppConfig.eula_accepted
so it is asked exactly once per install, not once per launch.

EULA_TEXT is also reused verbatim by presentation/about_dialog.py's "Điều
khoản pháp lý" tab, so the wording only lives in one place.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout

EULA_TEXT = """Thỏa thuận Người dùng (EULA & Privacy Policy)

1. Quyền sở hữu và Quản lý Dữ liệu
Phần mềm này là một công cụ quản lý file cục bộ. Người dùng hoàn toàn chịu trách nhiệm về nguồn gốc, bản quyền và tính hợp pháp của các tài liệu (PDF, EPUB, DOC...) được đưa vào ứng dụng. Ứng dụng không cung cấp, không phân phối và không chịu trách nhiệm đối với bất kỳ nội dung sách/tài liệu nào vi phạm bản quyền.

2. Thu thập và Xử lý Dữ liệu trên Cloud
Để phục vụ tính năng cộng đồng, ứng dụng chỉ đồng bộ các dữ liệu sau lên Cloud cơ sở dữ liệu: Tên sách, Tên tác giả, Điểm đánh giá (Rating) và Nội dung bài Đánh giá (Review) do chính bạn viết. Toàn bộ file tài liệu gốc của bạn được lưu trữ 100% trên ổ cứng máy tính cá nhân.

3. Tích hợp AI & Bảo mật API Key
Tính năng Tóm tắt AI yêu cầu người dùng tự cung cấp API Key (OpenAI, Gemini...). API Key của bạn được mã hóa và lưu trữ cục bộ (local storage) trên chính máy tính của bạn, tuyệt đối không được gửi về máy chủ của chúng tôi. Xin lưu ý: Kết quả tóm tắt do AI tạo ra có thể chứa thông tin không chính xác (hallucination) và chỉ mang tính chất tham khảo.

4. Đóng góp tự nguyện (Donation)
Ứng dụng này được cung cấp hoàn toàn miễn phí. Tính năng "Ủng hộ tác giả (Donate)" mang tính chất tự nguyện nhằm hỗ trợ chi phí duy trì dự án, không phải là điều kiện để mua bán hay mở khóa tính năng phần mềm.

Bằng việc tiếp tục sử dụng phần mềm, bạn đồng ý với các điều khoản nêu trên."""


class EulaDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thỏa thuận Người dùng (EULA & Privacy Policy)")
        # Fixed, modest size -- long as the text is, it belongs in the
        # scroll area below, not in an ever-taller window.
        self.setFixedSize(560, 520)

        heading = QLabel("Thỏa thuận Người dùng (EULA & Privacy Policy)", self)
        heading.setStyleSheet("font-weight: 700; font-size: 15px;")
        heading.setWordWrap(True)

        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setPlainText(EULA_TEXT)

        agree_button = QPushButton("Tôi đã đọc và Đồng ý", self)
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
