"""TDD-016 UI: star-rating + comment reviews for one document, backed by
Supabase (application/cloud_reviews.py).

Identity without sign-up: every installation has an anonymous identity
(core/user_identity.py). Reviews are submitted with its secret token, so
the server can tie each review and nickname to this installation:

- a nickname already owned by another installation is refused ("nick name
  đã có người dùng") -- checked up front for a friendly message, enforced
  by the server either way;
- if this installation already reviewed the document, submitting asks
  whether to update that review or post a new one;
- this installation's own reviews are marked "Bạn" in the list.

After a successful submit the list, the average-rating summary, the
locally cached rating stats and every open view (via LibraryUpdatedEvent)
are refreshed immediately.

Network calls (fetch on open, submit on click) run on a plain background
thread and report back through Qt signals -- not the EventBus/QtEventBridge
pattern used elsewhere, since that exists for cross-module pub/sub, and
this is just one dialog's own async work reporting to itself. Qt signals
already marshal safely across threads the same way.
"""
from __future__ import annotations

import html
import threading
from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
)

from smartdoc.application.cloud_reviews import (
    ANONYMOUS_NICKNAME,
    NICKNAME_MAX_LENGTH,
    CloudReviewError,
    NicknameTakenError,
    SupabaseReviewSync,
    rating_summary,
    reviews_by_user,
)
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.theme import current_colors

_FULL_STAR = "★"
_EMPTY_STAR = "☆"
_STAR_GOLD = "#f5b301"
_STAR_EMPTY_COLOR = "#b0b0b0"
_HTML_ROLE = Qt.UserRole + 1

# Choices returned by ReviewDialog._ask_update_or_new().
UPDATE_EXISTING = "update"
CREATE_NEW = "new"


def stars_html(rating: float, size_px: int = 15) -> str:
    """Gold filled stars + grey empty ones (rounded to the nearest star)."""
    filled = max(0, min(5, round(rating)))
    return (
        f'<span style="color:{_STAR_GOLD}; font-size:{size_px}px;">{_FULL_STAR * filled}</span>'
        f'<span style="color:{_STAR_EMPTY_COLOR}; font-size:{size_px}px;">{_EMPTY_STAR * (5 - filled)}</span>'
    )


def _format_date(value) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y")
    except ValueError:
        return ""


class _ReviewItemDelegate(QStyledItemDelegate):
    """Paints each review's rich text (colored stars, bold nickname, muted
    date) from _HTML_ROLE, keeping the item's plain DisplayRole text for
    accessibility/copying."""

    def _document(self, option, index) -> QTextDocument:
        document = QTextDocument()
        document.setDefaultFont(option.font)
        document.setHtml(index.data(_HTML_ROLE) or html.escape(index.data(Qt.DisplayRole) or ""))
        document.setTextWidth(max(option.rect.width(), 200) - 16)
        return document

    def paint(self, painter, option, index) -> None:
        self.initStyleOption(option, index)
        if index.data(_HTML_ROLE) is None:
            super().paint(painter, option, index)
            return
        painter.save()
        text = option.text
        option.text = ""
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget)
        option.text = text
        document = self._document(option, index)
        painter.translate(option.rect.left() + 8, option.rect.top() + 6)
        context = QAbstractTextDocumentLayout.PaintContext()
        if option.state & QStyle.State_Selected:
            context.palette.setColor(QPalette.Text, option.palette.color(QPalette.HighlightedText))
        document.documentLayout().draw(painter, context)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 -- Qt override
        if index.data(_HTML_ROLE) is None:
            return super().sizeHint(option, index)
        self.initStyleOption(option, index)
        view = option.widget
        if view is not None:
            option.rect.setWidth(view.viewport().width())
        document = self._document(option, index)
        return QSize(int(document.idealWidth()) + 16, int(document.size().height()) + 12)


class ReviewDialog(QDialog):
    reviews_loaded = Signal(list, str)  # (reviews, error_message)
    submit_finished = Signal(list, str, bool)  # (reviews, error_message, was_update)
    nickname_taken = Signal(str)

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self._rating = 0
        self._reviews: list[dict] = []
        self._user_hash = context.identity.user_hash
        config = context.config.config
        self._configured = bool(config.supabase_url and config.supabase_anon_key)
        self._sync = SupabaseReviewSync(config.supabase_url or "", config.supabase_anon_key or "")
        colors = current_colors()
        self._muted = colors.muted_text
        self._accent = colors.accent

        self.setWindowTitle(f"Đánh giá: {doc.get('title', '')}")
        self.resize(520, 600)
        self.setMaximumSize(680, 820)

        self.summary_label = QLabel(self)
        self.summary_label.setTextFormat(Qt.RichText)
        self.status_label = QLabel("Đang tải đánh giá...")
        self.status_label.setWordWrap(True)
        self.reviews_list = QListWidget(self)
        self.reviews_list.setVisible(False)
        self.reviews_list.setWordWrap(True)
        self.reviews_list.setItemDelegate(_ReviewItemDelegate(self.reviews_list))
        self.reviews_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.reviews_list.setResizeMode(QListWidget.Adjust)  # re-wrap rows when the dialog resizes

        self.nickname_edit = QLineEdit(config.reviewer_nickname, self)
        self.nickname_edit.setPlaceholderText(f"Nick name của bạn (để trống = {ANONYMOUS_NICKNAME})")
        self.nickname_edit.setMaxLength(NICKNAME_MAX_LENGTH)

        self._star_buttons: list[QToolButton] = []
        star_row = QHBoxLayout()
        for i in range(1, 6):
            button = QToolButton(self)
            button.setText(_EMPTY_STAR)
            button.setStyleSheet(f"QToolButton {{ font-size: 22px; border: none; color: {_STAR_EMPTY_COLOR}; }}")
            button.clicked.connect(lambda _checked=False, n=i: self._set_rating(n))
            self._star_buttons.append(button)
            star_row.addWidget(button)
        star_row.addStretch(1)

        self.comment_edit = QTextEdit(self)
        self.comment_edit.setPlaceholderText("Nhận xét của bạn...")
        self.comment_edit.setMaximumHeight(80)

        self.my_review_label = QLabel(self)
        self.my_review_label.setWordWrap(True)
        self.my_review_label.setVisible(False)
        self.my_review_label.setStyleSheet(f"color: {self._accent}; font-size: 12px;")

        self.sync_notice_label = QLabel(
            "Đánh giá của bạn sẽ được đồng bộ lên thư viện cộng đồng. Hãy đảm bảo nội dung văn minh.", self
        )
        self.sync_notice_label.setWordWrap(True)
        self.sync_notice_label.setStyleSheet("color: palette(mid); font-size: 11px;")

        self.submit_button = QPushButton("Gửi đánh giá", self)
        self.submit_button.clicked.connect(self._on_submit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.reviews_list, stretch=1)
        layout.addWidget(QLabel("Viết đánh giá của bạn:"))
        layout.addWidget(self.my_review_label)
        layout.addWidget(self.nickname_edit)
        layout.addLayout(star_row)
        layout.addWidget(self.comment_edit)
        layout.addWidget(self.sync_notice_label)
        layout.addWidget(self.submit_button)

        self.reviews_loaded.connect(self._on_reviews_loaded)
        self.submit_finished.connect(self._on_submit_finished)
        self.nickname_taken.connect(self._on_nickname_taken)

        self._update_summary()
        self._load_reviews_async()

    # -- Rating input -------------------------------------------------------

    def _set_rating(self, n: int) -> None:
        self._rating = n
        for i, button in enumerate(self._star_buttons, start=1):
            filled = i <= n
            button.setText(_FULL_STAR if filled else _EMPTY_STAR)
            color = _STAR_GOLD if filled else _STAR_EMPTY_COLOR
            button.setStyleSheet(f"QToolButton {{ font-size: 22px; border: none; color: {color}; }}")

    # -- Loading / rendering ------------------------------------------------

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

    def _my_reviews(self) -> list[dict]:
        return reviews_by_user(self._reviews, self._user_hash)

    def _update_summary(self) -> None:
        average, count = rating_summary(self._reviews)
        if not count:
            self.summary_label.setText(f'<span style="color:{self._muted};">Chưa có đánh giá</span>')
            return
        self.summary_label.setText(
            f"{stars_html(average, 18)}&nbsp;&nbsp;<b style='font-size:16px;'>{average:.1f}</b>"
            f"<span style='color:{self._muted};'> / 5 · {count} đánh giá</span>"
        )

    def _review_html(self, review: dict, is_mine: bool) -> str:
        nickname = html.escape(review.get("nickname") or ANONYMOUS_NICKNAME)
        badge = (
            f' <span style="color:{self._accent}; font-size:11px; font-weight:600;">• Bạn</span>' if is_mine else ""
        )
        date = _format_date(review.get("updated_at") or review.get("created_at"))
        meta = date + (" (đã sửa)" if review.get("updated_at") else "")
        meta_html = f' <span style="color:{self._muted}; font-size:11px;">{html.escape(meta)}</span>' if meta else ""
        comment = html.escape(review.get("comment") or "").replace("\n", "<br>")
        comment_html = f"<div style='margin-top:3px;'>{comment}</div>" if comment else ""
        return f"<div>{stars_html(review['rating'])}&nbsp; <b>{nickname}</b>{badge}{meta_html}</div>{comment_html}"

    def _on_reviews_loaded(self, reviews: list[dict], error: str) -> None:
        if error:
            self.status_label.setText(f"Không tải được đánh giá: {error}")
            return
        self._reviews = list(reviews)
        self._update_summary()
        self._update_my_review_notice()
        self.status_label.setVisible(False)
        self.reviews_list.setVisible(True)
        self.reviews_list.clear()
        if not reviews:
            self.reviews_list.addItem(QListWidgetItem("Chưa có đánh giá nào. Hãy là người đầu tiên!"))
            return
        # Supabase already returns rows ordered by created_at desc (see
        # SupabaseReviewSync.fetch_reviews's query params).
        for review in reviews:
            is_mine = bool(self._user_hash) and review.get("user_hash") == self._user_hash
            stars = _FULL_STAR * review["rating"] + _EMPTY_STAR * (5 - review["rating"])
            item = QListWidgetItem(f"{stars}  {review.get('nickname', '')}\n{review.get('comment', '')}")
            item.setData(_HTML_ROLE, self._review_html(review, is_mine))
            self.reviews_list.addItem(item)

    def _update_my_review_notice(self) -> None:
        mine = self._my_reviews()
        if not mine:
            self.my_review_label.setVisible(False)
            return
        latest = mine[0]
        self.my_review_label.setText(
            f"Bạn đã đánh giá sách này ({latest['rating']}{_FULL_STAR}). Khi gửi, bạn có thể chọn "
            "cập nhật bài cũ hoặc tạo bài đánh giá mới."
        )
        self.my_review_label.setVisible(True)

    # -- Submitting ---------------------------------------------------------

    def _ask_update_or_new(self, existing: dict) -> str | None:
        """UPDATE_EXISTING / CREATE_NEW / None (cancel). Separate method so
        tests can answer it without a modal loop."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Bạn đã đánh giá sách này")
        box.setText(
            f"Bạn đã có bài đánh giá {existing['rating']}{_FULL_STAR} cho sách này.\n\n"
            "Bạn muốn cập nhật lại nội dung bài đánh giá trước đó, hay tạo bài đánh giá mới?"
        )
        update_button = box.addButton("Cập nhật bài cũ", QMessageBox.AcceptRole)
        new_button = box.addButton("Tạo bài mới", QMessageBox.ActionRole)
        box.addButton("Hủy", QMessageBox.RejectRole)
        box.setDefaultButton(update_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is update_button:
            return UPDATE_EXISTING
        if clicked is new_button:
            return CREATE_NEW
        return None

    def _on_submit(self) -> None:
        if not self._configured:
            return
        if self._rating == 0:
            QMessageBox.warning(self, "Thiếu số sao", "Vui lòng chọn số sao đánh giá.")
            return

        review_id = None
        mine = self._my_reviews()
        if mine:
            choice = self._ask_update_or_new(mine[0])
            if choice is None:
                return
            if choice == UPDATE_EXISTING:
                review_id = mine[0].get("id")

        nickname = self.nickname_edit.text().strip()
        rating = self._rating
        comment = self.comment_edit.toPlainText().strip()
        token, user_hash = self.context.identity.token, self._user_hash
        doc_id = self.doc["id"]
        self.submit_button.setEnabled(False)
        self.submit_button.setText("Đang gửi...")

        def worker() -> None:
            try:
                if self._sync.nickname_status(nickname, user_hash) == "taken":
                    raise NicknameTakenError(nickname)
                reviews = self._sync.submit_review(
                    doc_id, nickname, rating, comment, user_token=token, review_id=review_id
                )
                self.submit_finished.emit(reviews, "", review_id is not None)
            except NicknameTakenError as exc:
                self.nickname_taken.emit(exc.nickname)
            except (CloudReviewError, ValueError) as exc:
                self.submit_finished.emit([], str(exc), False)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_submit_button(self) -> None:
        self.submit_button.setEnabled(True)
        self.submit_button.setText("Gửi đánh giá")

    def _on_nickname_taken(self, nickname: str) -> None:
        self._reset_submit_button()
        QMessageBox.warning(
            self,
            "Nick name đã có người dùng",
            f"Nick name \"{nickname}\" đã có người dùng. Vui lòng chọn nick name khác.",
        )
        self.nickname_edit.setFocus()
        self.nickname_edit.selectAll()

    def _on_submit_finished(self, reviews: list[dict], error: str, was_update: bool) -> None:
        self._reset_submit_button()
        if error:
            QMessageBox.warning(self, "Lỗi", f"Không gửi được đánh giá: {error}")
            return

        # Only remember a nickname the server actually accepted.
        self.context.config.config.reviewer_nickname = self.nickname_edit.text().strip()
        self.context.config.save()

        # Refresh everything that shows this document's rating right away,
        # instead of waiting for the next "Được đánh giá cao nhất" sync
        # (rating_sync.py) to pick it up.
        average, count = rating_summary(reviews)
        self.context.db.update_rating_stats(self.doc["id"], average, count)
        self.doc["avg_rating"], self.doc["review_count"] = average, count
        self.context.event_bus.publish(LibraryUpdatedEvent())

        self.comment_edit.clear()
        self._set_rating(0)
        self._on_reviews_loaded(reviews, "")
        self.status_label.setText(
            "✅ Đã cập nhật bài đánh giá của bạn." if was_update else "✅ Đã gửi đánh giá. Cảm ơn bạn!"
        )
        self.status_label.setStyleSheet("color: green;")
        self.status_label.setVisible(True)


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
