"""AI Summary dialog: generate a non-spoiler, theme/genre-only overview of a
document to help decide whether to read it, using the user's own configured
AI provider/key (Settings -> AI Tóm tắt). Generating and saving are
separate, deliberate steps -- a fresh generation is only a preview until
the user clicks "Lưu tóm tắt".

Network call runs on a background thread and reports back through a Qt
signal, same pattern as ReviewDialog/CoverSearchDialog.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from smartdoc.application.ai_summary import AISummaryError, generate_summary
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
        self._configured = bool(self._provider and self._api_key)

        self.setWindowTitle(f"Tóm tắt AI: {doc.get('title', '')}")
        self.resize(480, 420)
        self.setMinimumWidth(420)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

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
        layout.addWidget(
            QLabel("Tóm tắt chủ đề/thể loại (không tiết lộ nội dung/cốt truyện):", self)
        )
        layout.addWidget(self.summary_edit, stretch=1)
        layout.addWidget(self.status_label)
        layout.addLayout(button_row)

        self.generation_finished.connect(self._on_generation_finished)

        if not self._configured:
            self.generate_button.setEnabled(False)
            self.status_label.setText(
                "Chưa cấu hình AI Tóm tắt. Vào Cài đặt > AI Tóm tắt để thêm nhà cung cấp và API key của bạn."
            )

    def _on_generate(self) -> None:
        if not self._configured:
            return
        self.generate_button.setEnabled(False)
        self.generate_button.setText("Đang tạo...")
        self.status_label.setText("Đang gọi AI, vui lòng đợi...")

        provider, api_key, doc = self._provider, self._api_key, self.doc

        def worker() -> None:
            try:
                summary = generate_summary(provider, api_key, doc)
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
