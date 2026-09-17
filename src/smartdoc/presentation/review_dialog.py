"""TDD-016 UI: star-rating + comment reviews for one document, backed by
Supabase (application/cloud_reviews.py).

Network calls (fetch on open, submit on click) run on a plain background
thread and report back through Qt signals -- not the EventBus/QtEventBridge
pattern used elsewhere, since that exists for cross-module pub/sub, and
this is just one dialog's own async work reporting to itself. Qt signals
already marshal safely across threads the same way.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
)

from smartdoc.application.cloud_reviews import CloudReviewError, SupabaseReviewSync

_FULL_STAR = "★"
_EMPTY_STAR = "☆"


class ReviewDialog(QDialog):
    reviews_loaded = Signal(list, str)  # (reviews, error_message)
    submit_finished = Signal(list, str)

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self._rating = 0
        config = context.config.config
        self._configured = bool(config.supabase_url and config.supabase_anon_key)
        self._sync = SupabaseReviewSync(config.supabase_url or "", config.supabase_anon_key or "")

        self.setWindowTitle(f"Đánh giá: {doc.get('title', '')}")
        self.resize(480, 560)

        self.status_label = QLabel("Đang tải đánh giá...")
        self.reviews_list = QListWidget(self)
        self.reviews_list.setVisible(False)

        self.nickname_edit = QLineEdit(context.config.config.reviewer_nickname, self)
        self.nickname_edit.setPlaceholderText("Biệt danh của bạn")

        self._star_buttons: list[QToolButton] = []
        star_row = QHBoxLayout()
        for i in range(1, 6):
            button = QToolButton(self)
            button.setText(_EMPTY_STAR)
            button.setStyleSheet("QToolButton { font-size: 20px; border: none; }")
            button.clicked.connect(lambda _checked=False, n=i: self._set_rating(n))
            self._star_buttons.append(button)
            star_row.addWidget(button)
        star_row.addStretch(1)

        self.comment_edit = QTextEdit(self)
        self.comment_edit.setPlaceholderText("Nhận xét của bạn...")
        self.comment_edit.setMaximumHeight(80)

        self.submit_button = QPushButton("Gửi đánh giá", self)
        self.submit_button.clicked.connect(self._on_submit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.reviews_list, stretch=1)
        layout.addWidget(QLabel("Viết đánh giá của bạn:"))
        layout.addWidget(self.nickname_edit)
        layout.addLayout(star_row)
        layout.addWidget(self.comment_edit)
        layout.addWidget(self.submit_button)

        self.reviews_loaded.connect(self._on_reviews_loaded)
        self.submit_finished.connect(self._on_submit_finished)

        self._load_reviews_async()

    def _set_rating(self, n: int) -> None:
        self._rating = n
        for i, button in enumerate(self._star_buttons, start=1):
            button.setText(_FULL_STAR if i <= n else _EMPTY_STAR)

    def _load_reviews_async(self) -> None:
        if not self._configured:
            self.status_label.setText("Chưa cấu hình đánh giá cộng đồng (thiếu Supabase URL/key).")
            return

        def worker() -> None:
            try:
                reviews = self._sync.fetch_reviews(self.doc["id"])
                self.reviews_loaded.emit(reviews, "")
            except CloudReviewError as exc:
                self.reviews_loaded.emit([], str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_reviews_loaded(self, reviews: list[dict], error: str) -> None:
        if error:
            self.status_label.setText(f"Không tải được đánh giá: {error}")
            return
        self.status_label.setVisible(False)
        self.reviews_list.setVisible(True)
        self.reviews_list.clear()
        if not reviews:
            self.reviews_list.addItem(QListWidgetItem("Chưa có đánh giá nào. Hãy là người đầu tiên!"))
            return
        # Supabase already returns rows ordered by created_at desc (see
        # SupabaseReviewSync.fetch_reviews's query params).
        for review in reviews:
            stars = _FULL_STAR * review["rating"] + _EMPTY_STAR * (5 - review["rating"])
            self.reviews_list.addItem(QListWidgetItem(f"{stars}  {review['nickname']}\n{review['comment']}"))

    def _on_submit(self) -> None:
        if not self._configured:
            return
        if self._rating == 0:
            QMessageBox.warning(self, "Thiếu số sao", "Vui lòng chọn số sao đánh giá.")
            return

        nickname = self.nickname_edit.text().strip()
        self.context.config.config.reviewer_nickname = nickname
        self.context.config.save()

        rating = self._rating
        comment = self.comment_edit.toPlainText().strip()
        self.submit_button.setEnabled(False)
        self.submit_button.setText("Đang gửi...")

        def worker() -> None:
            try:
                reviews = self._sync.submit_review(self.doc["id"], nickname, rating, comment)
                self.submit_finished.emit(reviews, "")
            except (CloudReviewError, ValueError) as exc:
                self.submit_finished.emit([], str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_submit_finished(self, reviews: list[dict], error: str) -> None:
        self.submit_button.setEnabled(True)
        self.submit_button.setText("Gửi đánh giá")
        if error:
            QMessageBox.warning(self, "Lỗi", f"Không gửi được đánh giá: {error}")
            return
        self.comment_edit.clear()
        self._set_rating(0)
        self._on_reviews_loaded(reviews, "")


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        doc = {"id": "demo-doc", "title": "Demo Book"}

        app = QApplication(sys.argv)
        apply_light_theme(app)
        ReviewDialog(context, doc).exec()
