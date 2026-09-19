"""AI Summary dialog: generate a summary of a document using the user's own
configured AI provider/key (Settings -> AI Tóm tắt). The default kind is a
non-spoiler, theme/genre-only overview that helps decide whether to read
it; the user can instead pick key points, a full summary, a review or
discussion questions, plus length and language (see
application/ai_summary.SUMMARY_STYLES). Generating and saving are
separate, deliberate steps -- a fresh generation is only a preview until
the user clicks "Lưu tóm tắt".

The request content (title/author/tags + extracted text, uncapped -- see
application/ai_summary.py) is shown in its own editable box so the user can
see exactly what's being sent and adjust it before generating, rather than
it being a hidden implementation detail.

Network call runs on a background thread and reports back through a Qt
signal, same pattern as ReviewDialog/CoverSearchDialog.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from smartdoc.application.ai_summary import (
    SUMMARY_LANGUAGES,
    SUMMARY_LENGTHS,
    SUMMARY_STYLES,
    AISummaryError,
    build_request_content,
    generate_summary_from_content,
    provider_requires_key,
)
from smartdoc.core.event_bus import LibraryUpdatedEvent


class AISummaryDialog(QDialog):
    generation_finished = Signal(str, str)  # (summary_text, error_message)

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        config = context.config.config
        self._provider = config.ai_provider
        self._api_key = config.ai_api_key
        self._model = config.ai_model
        self._base_url = config.ai_base_url
        self._configured = bool(self._provider and (self._api_key or not provider_requires_key(self._provider)))

        self.setWindowTitle(f"Tóm tắt AI: {doc.get('title', '')}")
        self.resize(560, 620)
        self.setMinimumWidth(460)
        self.setMaximumSize(820, 900)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        self.request_content_edit = QTextEdit(self)
        self.request_content_edit.setPlainText(build_request_content(doc))
        self.request_content_edit.setToolTip(
            "Đây là toàn bộ nội dung sẽ gửi cho AI -- không giới hạn độ dài. "
            "Bạn có thể chỉnh sửa trước khi tạo tóm tắt."
        )

        # What kind of summary to ask for -- remembered across dialogs.
        self.style_combo = self._combo({k: v[0] for k, v in SUMMARY_STYLES.items()}, config.ai_summary_style)
        self.length_combo = self._combo({k: v[0] for k, v in SUMMARY_LENGTHS.items()}, config.ai_summary_length)
        self.language_combo = self._combo({k: v[0] for k, v in SUMMARY_LANGUAGES.items()}, config.ai_summary_language)
        # Two rows: the style labels are long and must not be elided.
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Kiểu tóm tắt:", self))
        style_row.addWidget(self.style_combo, stretch=1)
        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Độ dài:", self))
        options_row.addWidget(self.length_combo)
        options_row.addSpacing(12)
        options_row.addWidget(QLabel("Ngôn ngữ:", self))
        options_row.addWidget(self.language_combo)
        options_row.addStretch(1)

        self.summary_edit = QTextEdit(self)
        self.summary_edit.setReadOnly(True)
        self.summary_edit.setPlaceholderText("Nhấn \"Tạo tóm tắt\" để bắt đầu.")

        existing = doc.get("ai_summary")
        if existing:
            self.summary_edit.setPlainText(existing)
            self.status_label.setText("Tóm tắt đã lưu trước đó. Có thể tạo lại nếu muốn.")

        self.generate_button = QPushButton("✨ Tạo tóm tắt", self)
        self.generate_button.clicked.connect(self._on_generate)
        self.save_button = QPushButton("💾 Lưu tóm tắt", self)
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setEnabled(bool(existing))

        button_row = QHBoxLayout()
        button_row.addWidget(self.generate_button)
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nội dung yêu cầu AI tóm tắt (có thể chỉnh sửa):", self))
        layout.addWidget(self.request_content_edit, stretch=2)
        layout.addLayout(style_row)
        layout.addLayout(options_row)
        layout.addWidget(QLabel("Kết quả:", self))
        layout.addWidget(self.summary_edit, stretch=1)
        layout.addWidget(self.status_label)
        layout.addLayout(button_row)

        self.generation_finished.connect(self._on_generation_finished)

        if not self._configured:
            self.generate_button.setEnabled(False)
            self.status_label.setText(
                "Chưa cấu hình AI Tóm tắt. Vào Cài đặt > AI Tóm tắt để thêm nhà cung cấp và API key của bạn."
            )

    def _combo(self, choices: dict[str, str], current: str) -> QComboBox:
        combo = QComboBox(self)
        for key, label in choices.items():
            combo.addItem(label, key)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        return combo

    def _selected_options(self) -> dict:
        return {
            "style": self.style_combo.currentData(),
            "length": self.length_combo.currentData(),
            "language": self.language_combo.currentData(),
        }

    def _remember_options(self, options: dict) -> None:
        config = self.context.config.config
        config.ai_summary_style = options["style"]
        config.ai_summary_length = options["length"]
        config.ai_summary_language = options["language"]
        self.context.config.save()

    def _on_generate(self) -> None:
        if not self._configured:
            return
        self.generate_button.setEnabled(False)
        self.generate_button.setText("Đang tạo...")
        self.status_label.setText("Đang gọi AI, vui lòng đợi...")

        provider, api_key = self._provider, self._api_key
        request_content = self.request_content_edit.toPlainText()
        options = self._selected_options()
        self._remember_options(options)
        options.update(model=self._model, base_url=self._base_url)

        def worker() -> None:
            try:
                summary = generate_summary_from_content(provider, api_key, request_content, **options)
                self.generation_finished.emit(summary, "")
            except AISummaryError as exc:
                self.generation_finished.emit("", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_generation_finished(self, summary: str, error: str) -> None:
        self.generate_button.setEnabled(True)
        self.generate_button.setText("✨ Tạo tóm tắt")
        if error:
            self.status_label.setText(f"Lỗi: {error}")
            return
        self.summary_edit.setPlainText(summary)
        self.save_button.setEnabled(True)
        self.status_label.setText("Đã tạo xong -- nhấn \"Lưu tóm tắt\" nếu muốn giữ lại.")

    def _on_save(self) -> None:
        summary = self.summary_edit.toPlainText().strip()
        doc_id = self.doc.get("id")
        if not summary or not doc_id:
            return
        self.context.db.update_ai_summary(doc_id, summary)
        self.doc["ai_summary"] = summary
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self.status_label.setText("Đã lưu.")


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "The Hobbit", "author": "J.R.R. Tolkien", "file_path": "hobbit.pdf", "created_at": 0.0}
        )
        doc = context.db.get_document("d1")

        app = QApplication(sys.argv)
        apply_light_theme(app)
        AISummaryDialog(context, doc).exec()
