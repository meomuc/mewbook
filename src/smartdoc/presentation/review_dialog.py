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

Moderation (S2-03, 002_review_moderation.sql): "Báo cáo bài đã chọn..." reports somebody else's review for a reason (enough
different reporters hide it, and the list is refreshed afterwards). The server's public switches are read once when the
dialog opens (cached ten minutes by application/service_flags.py, on a background thread): a banner message from the owner is
shown, and while reviews are switched off writing and reporting are disabled with a sentence saying so -- reading still
works. If the switches cannot be read they are simply unknown and nothing is disabled; a server that is down shows
"tạm thời không khả dụng" and never breaks the dialog.

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

import shiboken6
from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.cloud_reviews import (
    ANONYMOUS_NICKNAME,
    NICKNAME_MAX_LENGTH,
    REPORT_REASONS,
    CloudReviewError,
    NicknameTakenError,
    SupabaseReviewSync,
    rating_summary,
    reviews_by_user,
)
from smartdoc.application.review_endpoint import resolve_review_endpoint
from smartdoc.application.service_flags import REVIEWS_ENABLED, BANNER_MESSAGE
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

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


def open_review_dialog(context, doc: dict, parent=None) -> None:
    """Opens the reviews of `doc`, unless the person switched community reviews off in Settings."""
    if not context.config.config.community_reviews_enabled:
        QMessageBox.information(parent, "Đánh giá cộng đồng", "Đánh giá cộng đồng đang tắt. Bật lại trong Cài đặt > Đánh giá cộng đồng.")
        return
    dialog = ReviewDialog(context, doc, parent)
    dialog.exec()
    dialog.deleteLater()


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


class _Relay(QObject):
    """What the background threads talk to. A worker never holds the dialog itself: if the last reference to a dialog
    were dropped on a worker thread, Python would destroy the widget there (an access violation). The relay is a child
    of the dialog, so it dies with it, and `send` checks that before emitting."""

    reviews_loaded = Signal(list, str)  # (reviews, error_message)
    submit_finished = Signal(list, str, bool)  # (reviews, error_message, was_update)
    nickname_taken = Signal(str)
    flags_loaded = Signal(object)  # FlagSnapshot | None
    report_finished = Signal(str, bool)  # (error_message, ok)
    nickname_checked = Signal(str, str)  # (nickname that was asked about, "free" | "taken" | "")


def _send(relay: _Relay, name: str, *args) -> None:
    if not shiboken6.isValid(relay):
        return  # the dialog was closed while the server was thinking
    try:
        getattr(relay, name).emit(*args)
    except RuntimeError:
        pass


class ReviewDialog(DesignDialog):

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent, title="Đánh giá cộng đồng", subtitle=doc.get("title", "") or "", icon="star", width=980)
        self.context = context
        self.doc = doc
        self._rating = 0
        self._relay = _Relay(self)
        self._reviews: list[dict] = []
        self._user_hash = context.identity.user_hash
        config = context.config.config
        endpoint = resolve_review_endpoint(config)  # the app's own connection unless one was set by hand
        self._configured = endpoint is not None
        self._sync = SupabaseReviewSync(endpoint.url if endpoint else "", endpoint.anon_key if endpoint else "")
        tm = theme_manager()
        self._muted = tm.token("ink2")
        self._accent = tm.token("accent")
        self.resize(1020, 620)

        # -- left: the book, its average and how the stars are spread ------------------------------------------------
        self.cover_label = QLabel(self)
        self.cover_label.setFixedSize(118, 168)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setStyleSheet(f"background: {tm.token('surface2')}; border: 1px solid {tm.token('line')};")
        cover = QPixmap(doc.get("cover_path") or "") if doc.get("cover_path") else QPixmap()
        if cover.isNull():
            self.cover_label.setText("Chưa có bìa")
        else:
            self.cover_label.setPixmap(cover.scaled(114, 164, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.book_label = QLabel(f"<b>{html.escape(doc.get('title', '') or '')}</b><br>{html.escape(doc.get('author', '') or '')}", self)
        self.book_label.setTextFormat(Qt.RichText)
        self.book_label.setWordWrap(True)
        self.summary_label = QLabel(self)
        self.summary_label.setTextFormat(Qt.RichText)
        self.summary_label.setWordWrap(True)
        self.distribution_bars: dict[int, QProgressBar] = {}
        self.distribution_counts: dict[int, QLabel] = {}
        distribution = QVBoxLayout()
        distribution.setSpacing(4)
        for stars in range(5, 0, -1):
            bar = QProgressBar(self)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            count = QLabel("0", self)
            count.setFixedWidth(26)
            count.setAlignment(Qt.AlignRight)
            count.setStyleSheet(f"color: {self._muted}; font-size: 12px;")
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(QLabel(f"{stars}", self))
            row.addWidget(bar, 1)
            row.addWidget(count)
            distribution.addLayout(row)
            self.distribution_bars[stars] = bar
            self.distribution_counts[stars] = count
        left = QVBoxLayout()
        left.addWidget(self.cover_label)
        left.addWidget(self.book_label)
        left.addWidget(self.summary_label)
        left.addLayout(distribution)
        left.addStretch(1)
        left_holder = QWidget(self)
        left_holder.setFixedWidth(230)
        left_holder.setLayout(left)

        # -- middle: the reviews ---------------------------------------------------------------------------------------
        self.status_label = self.add_footer_note("Đang tải đánh giá...")
        self.status_label.setWordWrap(True)
        # A message from the project owner (service_flags.banner_message) and the notice shown while reviews are switched off.
        self.banner_label = QLabel(self)
        self.banner_label.setTextFormat(Qt.PlainText)
        self.banner_label.setWordWrap(True)
        self.banner_label.setStyleSheet(f"color: {self._accent}; font-size: 12px;")
        self.banner_label.setVisible(False)
        self.notice_label = QLabel(self)
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(f"color: {tm.token('warn')}; font-size: 12px;")
        self.notice_label.setVisible(False)
        self._reviews_enabled = True
        self.reviews_list = QListWidget(self)
        self.reviews_list.setVisible(False)
        self.reviews_list.setWordWrap(True)
        self.reviews_list.setItemDelegate(_ReviewItemDelegate(self.reviews_list))
        self.reviews_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.reviews_list.setResizeMode(QListWidget.Adjust)  # re-wrap rows when the dialog resizes
        self.sort_combo = QComboBox(self)
        self.sort_combo.addItem("Mới nhất", "newest")
        self.sort_combo.addItem("Được đánh giá cao nhất", "highest")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.report_button = QPushButton("Báo cáo bài đã chọn…", self)
        self.report_button.setIcon(line_icon("warn", tm.token("ink"), 14))
        self.report_button.setToolTip("Báo cáo bài đánh giá spam, xúc phạm hay vi phạm. Nhiều người báo cáo thì bài bị ẩn để chủ dự án xem lại.")
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self._on_report)
        head = QHBoxLayout()
        heading = QLabel("<b>Nhận xét</b>", self)
        heading.setTextFormat(Qt.RichText)
        head.addWidget(heading)
        head.addStretch(1)
        head.addWidget(QLabel("Sắp xếp", self))
        head.addWidget(self.sort_combo)
        middle = QVBoxLayout()
        middle.addLayout(head)
        middle.addWidget(self.banner_label)
        middle.addWidget(self.notice_label)
        middle.addWidget(self.reviews_list, 1)
        middle.addWidget(self.report_button, 0, Qt.AlignRight)

        # -- right: your review ------------------------------------------------------------------------------------------
        self.nickname_edit = QLineEdit(config.reviewer_nickname, self)
        self.nickname_edit.setPlaceholderText(f"Nick name (để trống = {ANONYMOUS_NICKNAME})")
        self.nickname_edit.setMaxLength(NICKNAME_MAX_LENGTH)
        self.nickname_hint_label = QLabel("", self)
        self.nickname_hint_label.setStyleSheet(f"font-size: 12px; color: {self._muted};")
        self._nickname_timer = QTimer(self)
        self._nickname_timer.setSingleShot(True)
        self._nickname_timer.setInterval(600)
        self._nickname_timer.timeout.connect(self._check_nickname_async)
        self.nickname_edit.textEdited.connect(self._on_nickname_edited)

        self._star_buttons: list[QToolButton] = []
        star_row = QHBoxLayout()
        star_row.setSpacing(0)
        for i in range(1, 6):
            button = QToolButton(self)
            button.setText(_EMPTY_STAR)
            button.setStyleSheet(f"QToolButton {{ font-size: 22px; border: none; color: {_STAR_EMPTY_COLOR}; }}")
            button.clicked.connect(self._on_star_clicked)
            self._star_buttons.append(button)
            star_row.addWidget(button)
        star_row.addStretch(1)

        self.comment_edit = QTextEdit(self)
        self.comment_edit.setPlaceholderText("Nhận xét của bạn… (đừng tiết lộ nội dung sách)")
        self.comment_edit.setMinimumHeight(90)

        self.my_review_label = QLabel(self)
        self.my_review_label.setWordWrap(True)
        self.my_review_label.setVisible(False)
        self.my_review_label.setStyleSheet(f"color: {self._accent}; font-size: 12px;")

        self.sync_notice_label = QLabel(
            "Chỉ gửi nick name, số sao và nhận xét. Không gửi tên file, thư viện hay thông tin máy.", self
        )
        self.sync_notice_label.setWordWrap(True)
        self.sync_notice_label.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px;")

        self.submit_button = QPushButton("Gửi đánh giá", self)
        self.submit_button.setProperty("role", "primary")
        self.submit_button.clicked.connect(self._on_submit)

        mine = QVBoxLayout()
        mine.addWidget(QLabel("<b>Bài của bạn</b>", self))
        mine.addWidget(QLabel("Nick name", self))
        mine.addWidget(self.nickname_edit)
        mine.addWidget(self.nickname_hint_label)
        mine.addWidget(QLabel("Số sao", self))
        mine.addLayout(star_row)
        mine.addWidget(QLabel("Nhận xét", self))
        mine.addWidget(self.comment_edit)
        mine.addWidget(self.my_review_label)
        mine.addWidget(self.submit_button, 0, Qt.AlignLeft)
        mine.addStretch(1)
        mine.addWidget(self.sync_notice_label)
        right_holder = QWidget(self)
        right_holder.setFixedWidth(290)
        right_holder.setLayout(mine)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.addWidget(left_holder)
        columns.addLayout(middle, 1)
        columns.addWidget(right_holder)
        self.body.addLayout(columns, 1)
        self.add_footer_button("Đóng", on_click=self.accept)

        relay = self._relay
        relay.reviews_loaded.connect(self._on_reviews_loaded)
        relay.submit_finished.connect(self._on_submit_finished)
        relay.nickname_taken.connect(self._on_nickname_taken)
        relay.flags_loaded.connect(self._on_flags_loaded)
        relay.report_finished.connect(self._on_report_finished)
        self.reviews_list.itemSelectionChanged.connect(self._update_report_button)

        relay.nickname_checked.connect(self._on_nickname_checked)
        self._update_summary()
        self._load_reviews_async()
        self._load_flags_async()

    # -- Rating input -------------------------------------------------------

    def _on_star_clicked(self) -> None:
        button = self.sender()
        if button in self._star_buttons:
            self._set_rating(self._star_buttons.index(button) + 1)

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
            self.status_label.setText("Bản này chưa có máy chủ đánh giá cộng đồng, nên chưa xem được đánh giá của người khác.")
            return

        sync, doc_id, relay = self._sync, self.doc["id"], self._relay

        def worker() -> None:
            try:
                reviews = sync.fetch_reviews(doc_id)
                _send(relay, "reviews_loaded", reviews, "")
            except CloudReviewError as exc:
                _send(relay, "reviews_loaded", [], str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _my_reviews(self) -> list[dict]:
        return reviews_by_user(self._reviews, self._user_hash)

    def _update_summary(self) -> None:
        average, count = rating_summary(self._reviews)
        spread = {stars: sum(1 for r in self._reviews if r.get("rating") == stars) for stars in range(1, 6)}
        for stars, bar in self.distribution_bars.items():
            bar.setRange(0, max(count, 1))
            bar.setValue(spread[stars])
            self.distribution_counts[stars].setText(str(spread[stars]))
        if not count:
            self.summary_label.setText(f'<span style="color:{self._muted};">Chưa có đánh giá</span>')
            return
        self.summary_label.setText(
            f"{stars_html(average, 18)}&nbsp;&nbsp;<b style='font-size:20px;'>{average:.1f}</b>"
            f"<span style='color:{self._muted};'> / 5 · {count} đánh giá</span>"
        )

    def _on_sort_changed(self, _index: int = 0) -> None:
        if self._reviews:
            self._on_reviews_loaded(self._reviews, "")

    def _sorted(self, reviews: list[dict]) -> list[dict]:
        """"Mới nhất" keeps the server's order (newest first); "Được đánh giá cao nhất" puts more stars first."""
        if self.sort_combo.currentData() == "highest":
            return sorted(reviews, key=lambda r: r.get("rating", 0), reverse=True)
        return list(reviews)

    # -- The nickname check (live) ------------------------------------------------------

    def _on_nickname_edited(self, *_args) -> None:
        self.nickname_hint_label.setText("")
        if self._configured and self.nickname_edit.text().strip():
            self._nickname_timer.start()

    def _check_nickname_async(self) -> None:
        nickname = self.nickname_edit.text().strip()
        if not nickname or not self._configured:
            return
        user_hash, sync, relay = self._user_hash, self._sync, self._relay

        def worker() -> None:
            try:
                status = sync.nickname_status(nickname, user_hash)
            except CloudReviewError:
                status = ""
            _send(relay, "nickname_checked", nickname, status)

        threading.Thread(target=worker, daemon=True).start()

    def _on_nickname_checked(self, nickname: str, status: str) -> None:
        if nickname != self.nickname_edit.text().strip():
            return  # the person kept typing: this answer is about an older name
        tm = theme_manager()
        if status == "taken":
            self.nickname_hint_label.setText("Nick name này đã có người dùng")
            self.nickname_hint_label.setStyleSheet(f"font-size: 12px; color: {tm.token('err')};")
        elif status:
            self.nickname_hint_label.setText("Tên này chưa ai dùng")
            self.nickname_hint_label.setStyleSheet(f"font-size: 12px; color: {tm.token('ok')};")

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
        self.status_label.setText("Đã kết nối máy chủ đánh giá cộng đồng")
        self.reviews_list.setVisible(True)
        self.reviews_list.clear()
        if not reviews:
            self.reviews_list.addItem(QListWidgetItem("Chưa có đánh giá nào. Hãy là người đầu tiên!"))
            return
        # Supabase already returns rows ordered by created_at desc (see
        # SupabaseReviewSync.fetch_reviews's query params).
        for review in self._sorted(reviews):
            is_mine = bool(self._user_hash) and review.get("user_hash") == self._user_hash
            stars = _FULL_STAR * review["rating"] + _EMPTY_STAR * (5 - review["rating"])
            item = QListWidgetItem(f"{stars}  {review.get('nickname', '')}\n{review.get('comment', '')}")
            item.setData(_HTML_ROLE, self._review_html(review, is_mine))
            item.setData(Qt.UserRole, review)
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

    # -- The server's switches ------------------------------------------------

    def _load_flags_async(self) -> None:
        if not self._configured:
            return

        sync, relay = self._sync, self._relay

        def worker() -> None:
            # flags() never raises: an unreachable server is "unknown" (None) and changes nothing on screen.
            _send(relay, "flags_loaded", sync.flags())

        threading.Thread(target=worker, daemon=True).start()

    def _on_flags_loaded(self, snapshot) -> None:
        if snapshot is None:
            return
        banner = snapshot.text(BANNER_MESSAGE).strip()
        self.banner_label.setText(banner)  # plain text: whatever the owner (or anybody who got hold of the table) wrote is never HTML
        self.banner_label.setVisible(bool(banner))
        self._reviews_enabled = snapshot.enabled(REVIEWS_ENABLED)
        self.notice_label.setVisible(not self._reviews_enabled)
        if not self._reviews_enabled:
            self.notice_label.setText("Tính năng đánh giá cộng đồng đang tạm ngừng. Bạn vẫn xem được các đánh giá đã có.")
        self.submit_button.setEnabled(self._reviews_enabled)
        self._update_report_button()

    # -- Reporting -------------------------------------------------------------

    def _selected_review(self) -> dict | None:
        item = self.reviews_list.currentItem()
        review = item.data(Qt.UserRole) if item is not None else None
        return review if isinstance(review, dict) and review.get("id") is not None else None

    def _update_report_button(self) -> None:
        review = self._selected_review()
        is_mine = review is not None and bool(self._user_hash) and review.get("user_hash") == self._user_hash
        self.report_button.setEnabled(self._configured and self._reviews_enabled and review is not None and not is_mine)

    def _ask_report_reason(self) -> str | None:
        """The reason code to report a review for, or None (cancel). Separate method so tests can answer it."""
        labels = [label for _code, label in REPORT_REASONS]
        chosen, ok = QInputDialog.getItem(self, "Báo cáo bài đánh giá", "Lý do báo cáo:", labels, 0, False)
        if not ok:
            return None
        return next(code for code, label in REPORT_REASONS if label == chosen)

    def _on_report(self) -> None:
        review = self._selected_review()
        if review is None:
            return
        reason = self._ask_report_reason()
        if reason is None:
            return
        token, review_id = self.context.identity.token, review["id"]
        self.report_button.setEnabled(False)

        sync, relay = self._sync, self._relay

        def worker() -> None:
            try:
                sync.report_review(review_id, reason, user_token=token)
                _send(relay, "report_finished", "", True)
            except CloudReviewError as exc:
                _send(relay, "report_finished", str(exc), False)

        threading.Thread(target=worker, daemon=True).start()

    def _on_report_finished(self, error: str, ok: bool) -> None:
        self._update_report_button()
        if not ok:
            QMessageBox.warning(self, "Không báo cáo được", error)
            return
        QMessageBox.information(self, "Đã gửi báo cáo", "Cảm ơn bạn. Chủ dự án sẽ xem lại bài đánh giá này.")
        self._load_reviews_async()  # if it was the report that tipped it over, the review is gone from the list now

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

        sync, relay = self._sync, self._relay

        def worker() -> None:
            try:
                if sync.nickname_status(nickname, user_hash) == "taken":
                    raise NicknameTakenError(nickname)
                reviews = sync.submit_review(doc_id, nickname, rating, comment, user_token=token, review_id=review_id)
                _send(relay, "submit_finished", reviews, "", review_id is not None)
            except NicknameTakenError as exc:
                _send(relay, "nickname_taken", exc.nickname)
            except (CloudReviewError, ValueError) as exc:
                _send(relay, "submit_finished", [], str(exc), False)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_submit_button(self) -> None:
        self.submit_button.setEnabled(self._reviews_enabled)
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
            "Đã cập nhật bài đánh giá của bạn." if was_update else "Đã gửi đánh giá. Cảm ơn bạn!"
        )
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
