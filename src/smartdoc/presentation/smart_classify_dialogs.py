"""The two small questions smart classification asks the user.

- :class:`SmartClassifyOfferDialog`: right after documents were added (a file,
  a folder, a drag-and-drop, a Calibre import...), "do you want the smart model
  to categorise them for you?". Compact on purpose -- it follows the import
  summary, so it *carries* that summary instead of showing a second popup.
  "Ghi nhớ lựa chọn" makes the answer stick (Settings can change it back).
- :class:`SmartClassifyScopeDialog`: the button above the document list. It says
  what the run will apply to -- "the list you are looking at", which depends on
  the folder/collection/hashtag currently selected in the sidebar tree -- and how
  many documents that is, before anything happens.

Neither dialog does any work itself; they only collect a decision.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from smartdoc.application.smart_classifier import ScopePreview
from smartdoc.presentation.theme import current_colors

LIST_SUBJECT = "danh sách đang xem"

_WHAT_IT_DOES = (
    "Chỉ thêm hashtag thể loại và xếp hashtag đó vào cây Hashtag ở thanh bên. "
    "File gốc không bị di chuyển hay sửa, và bạn có thể hoàn tác."
)


def _muted_label(text: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {current_colors().muted_text};")
    return label


class SmartClassifyOfferDialog(QDialog):
    def __init__(self, count: int, summary: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kết quả thêm file" if summary else "Phân loại thông minh")
        self.setModal(True)
        self.setFixedWidth(430)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        if summary:
            summary_label = QLabel(summary, self)
            summary_label.setWordWrap(True)
            layout.addWidget(summary_label)
            divider = QFrame(self)
            divider.setFrameShape(QFrame.HLine)
            divider.setFrameShadow(QFrame.Sunken)
            layout.addWidget(divider)

        question = QLabel(
            f"<b>✨ Phân loại thông minh?</b><br>Dùng mô hình thông minh để tự động gắn thể loại và sắp xếp "
            f"{count:,} tài liệu vừa thêm vào cây Hashtag?",
            self,
        )
        question.setWordWrap(True)
        question.setTextFormat(Qt.RichText)
        layout.addWidget(question)
        layout.addWidget(_muted_label("Chạy nền, không làm chậm ứng dụng. " + _WHAT_IT_DOES, self))

        self.remember_checkbox = QCheckBox("Ghi nhớ lựa chọn của tôi (đổi lại trong Cài đặt → Phân loại)", self)
        layout.addWidget(self.remember_checkbox)

        self.skip_button = QPushButton("Bỏ qua", self)
        self.skip_button.clicked.connect(self.reject)
        self.classify_button = QPushButton("✨ Phân loại", self)
        self.classify_button.setDefault(True)
        self.classify_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.skip_button)
        buttons.addWidget(self.classify_button)
        layout.addLayout(buttons)

    def wants_classification(self) -> bool:
        return self.result() == QDialog.Accepted

    def remember_choice(self) -> bool:
        return self.remember_checkbox.isChecked()


class SmartClassifyScopeDialog(QDialog):
    def __init__(
        self,
        description: str,
        preview_for: Callable[[bool], ScopePreview],
        notice: str = "",
        parent=None,
        subject: str = LIST_SUBJECT,
    ) -> None:
        super().__init__(parent)
        self._preview_for = preview_for
        self._subject = subject
        self.setWindowTitle("Sắp xếp & phân loại thông minh")
        self.setModal(True)
        self.setFixedWidth(470)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        heading = QLabel("<b>✨ Sắp xếp và phân loại thông minh</b>", self)
        heading.setTextFormat(Qt.RichText)
        layout.addWidget(heading)

        self.scope_label = QLabel(self)
        self.scope_label.setWordWrap(True)
        self.scope_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.scope_label)
        self._description = description

        self.counts_label = QLabel(self)
        self.counts_label.setTextFormat(Qt.RichText)
        self.counts_label.setWordWrap(True)
        layout.addWidget(self.counts_label)

        self.reclassify_checkbox = QCheckBox("Xét lại cả những tài liệu máy đã phân loại trước đó", self)
        self.reclassify_checkbox.setToolTip(
            "Bỏ chọn: chỉ xử lý tài liệu chưa có thể loại và chưa từng được xét.\n"
            "Chọn: xét lại cả tài liệu máy đã gắn thể loại (thể loại cũ do máy gắn được thay bằng kết quả mới) "
            "hoặc đã từng bị bỏ qua vì chưa đủ chắc chắn. Thể loại bạn tự gắn luôn được giữ nguyên."
        )
        self.reclassify_checkbox.toggled.connect(self._refresh)
        layout.addWidget(self.reclassify_checkbox)

        layout.addWidget(_muted_label(_WHAT_IT_DOES, self))
        if notice:
            layout.addWidget(_muted_label("⚠️ " + notice, self))

        self.cancel_button = QPushButton("Hủy", self)
        self.cancel_button.clicked.connect(self.reject)
        self.start_button = QPushButton("✨ Bắt đầu phân loại", self)
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

        self._refresh()

    def reclassify(self) -> bool:
        return self.reclassify_checkbox.isChecked()

    def _refresh(self) -> None:
        preview = self._preview_for(self.reclassify())
        text = f"Áp dụng cho <b>{self._subject}</b> ({self._description}): <b>{preview.total:,}</b> tài liệu"
        if self._subject == LIST_SUBJECT:
            text += " (theo mục bạn đang chọn trong cây phân loại, không chỉ trang hiện tại)."
        self.scope_label.setText(text)
        lines = [f"• Sẽ được phân loại: <b>{preview.pending:,}</b>"]
        if preview.already_categorised:
            lines.append(f"• Bỏ qua, đã có thể loại: {preview.already_categorised:,}")
        if preview.already_looked_at:
            lines.append(f"• Bỏ qua, đã xét trước đó: {preview.already_looked_at:,}")
        self.counts_label.setText("<br>".join(lines))
        self.start_button.setEnabled(preview.pending > 0)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        app = QApplication(sys.argv)
        apply_theme(app, context.config.config.theme)
        offer = SmartClassifyOfferDialog(12, "Thêm thành công: 12\nĐã có trong thư viện (bỏ qua): 0\nThất bại: 0")
        offer.show()
        scope = SmartClassifyScopeDialog("Tất cả tài liệu", lambda again: ScopePreview(total=100, pending=100 if again else 60, already_categorised=30))
        scope.show()
        assert scope.start_button.isEnabled()
        print("dialogs build OK")
