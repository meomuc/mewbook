"""Bottom status bar: three fixed zones, icons first.

Built as a real QStatusBar (QMainWindow.setStatusBar) rather than a plain widget docked at the bottom, so it gets
the OS-native "thin bar, small text" treatment for free. The bar is split into three zones with a divider between
them, so every item always has one obvious home:

- Left, "Thư viện": how many documents, the selected collection, watched folders, and any import or
  classification that is running. Fed by LibraryUpdatedEvent / FilterChangedEvent (the two events the library
  view itself reacts to, so the counts never lag behind what is on screen), ImportProgressEvent,
  ImportBatchCompletedEvent and SmartClassify*Event (progress appears while a job runs and goes away after it).
- Middle, "Hệ thống & kết nối": the community-review service, the AI, and the network. One small icon each,
  nothing more; the words live in the tooltip.
- Right, "Tác giả & ủng hộ": the donate ticker, the link to the community page and the author's credit.

A status is an icon plus a badge whose *shape* says the state (✓ working, ○ not set up, ✕ a problem) and whose
colour only repeats it, so it can still be read by someone who cannot tell the colours apart.

Nothing here contacts the internet: the network state comes from the operating system's own reachability report,
the review service counts as connected once it is configured, and Ollama is asked on this computer only.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStatusBar, QToolTip, QWidget

from smartdoc import APP_DISPLAY_NAME, APP_NAME, APP_PUBLISHER
from smartdoc.application.ai_summary import probe_ollama, provider_requires_key
from smartdoc.application.cloud_reviews import CloudReviewError, SupabaseReviewSync
from smartdoc.core.event_bus import (
    AiConnectionChangedEvent,
    FilterChangedEvent,
    ImportBatchCompletedEvent,
    ImportProgressEvent,
    LibraryFilesMissingEvent,
    LibraryUpdatedEvent,
    SmartClassifyFinishedEvent,
    SmartClassifyProgressEvent,
    UpdateAvailableEvent,
)
from smartdoc.presentation.community import open_community_page
from smartdoc.presentation.donate_dialog import DonateDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.theme import current_colors

# Same green/crimson pair settings_dialog.py's connection test uses -- one
# consistent "connected vs. not" color language across the app instead of
# each status indicator inventing its own.
_STATUS_OK_COLOR = "green"
_STATUS_MISSING_COLOR = "crimson"

# Layout numbers for the bar: every item is one row high and the status icons share one slot width, so the rows of
# icons line up whatever glyphs they hold.
_ROW_HEIGHT = 22
_STATUS_ICON_WIDTH = 40
_ZONE_SPACING_WIDE = 16
_ZONE_SPACING_TIGHT = 4

# State -> (badge shape, is it coloured). The shapes differ on purpose: see the module docstring.
STATE_OK = "ok"
STATE_OFF = "off"
STATE_ERROR = "error"
_BADGES = {STATE_OK: "✓", STATE_OFF: "○", STATE_ERROR: "✕"}


class _ClickableStatusLabel(QLabel):
    """A status-bar notice that can be clicked: "N sách không tìm thấy file. Tìm lại?", "Có bản mới"..."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _StatusIcon(QLabel):
    """One connection status: the feature's icon and a state badge, with the explanation in the tooltip.
    A click asks the panel to say the status in words (a bubble beside the icon); it never opens a settings window."""

    clicked = Signal()

    def __init__(self, feature_icon: str, parent=None) -> None:
        super().__init__(parent)
        self._feature_icon = feature_icon
        self.setCursor(Qt.PointingHandCursor)
        self.state = STATE_OFF
        self.setTextFormat(Qt.RichText)
        self.set_state(STATE_OFF, "")

    def set_state(self, state: str, tooltip: str) -> None:
        self.state = state
        colors = current_colors()
        color = {STATE_OK: _STATUS_OK_COLOR, STATE_ERROR: _STATUS_MISSING_COLOR}.get(state, colors.muted_text)
        self.setText(f'{self._feature_icon}<span style="color:{color}; font-weight:700;">{_BADGES[state]}</span>')
        self.setToolTip(tooltip)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _DonateTicker(QLabel):
    """A small scrolling ticker calling out the donate popup -- a static
    label here would be easy to lose among the other status bar items, so
    the text instead scrolls through a fixed-width window on a timer, like
    a classic marquee, to actually catch the eye. Click opens DonateDialog.

    It is slow on purpose: a character stays in view for WINDOW_CHARS * TICK_MS (about 12 s), far longer than
    reading one short message takes, and moving the mouse over it pauses it. The messages are short, differ
    from each other, and each comes round only once per full loop (about 45 s).
    """

    clicked = Signal()

    MESSAGES = (
        "☕ Mèo Mực miễn phí. Mời tác giả một ly cà phê nhé!",
        "📚 Thấy app hữu ích? Một ly cà phê là động lực lớn.",
        "💌 Góp ý hay lời cảm ơn? Ghé fanpage của Mèo Mực nhé.",
    )
    GAP = "    •    "
    WINDOW_CHARS = 42
    TICK_MS = 280
    TEXT_SCALE = 0.7  # the line is a quiet aside, so it is set smaller than the rest of the bar

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loop_text = self.GAP.join(self.MESSAGES) + self.GAP
        self._offset = 0
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Ủng hộ tác giả một ly cà phê ☕ (bấm để xem mã QR)")
        colors = current_colors()
        self.setStyleSheet(f"color: {colors.accent}; font-weight: 600;")
        font = self.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * self.TEXT_SCALE)
        else:
            font.setPixelSize(max(1, round(font.pixelSize() * self.TEXT_SCALE)))
        self.setFont(font)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # A slot of one constant width: the text moves inside it, and its preferred width does not follow the
        # characters showing, so the icons beside it stay exactly where they are. It may still shrink to nothing
        # (minimumSizeHint), and _fit_ticker hides it when the window has no room for it.
        self._slot_width = QFontMetrics(font).averageCharWidth() * self.WINDOW_CHARS
        self.setMaximumWidth(self._slot_width)

        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        return QSize(self._slot_width, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        return QSize(0, super().minimumSizeHint().height())

    def _tick(self) -> None:
        doubled = self._loop_text * 2
        self.setText(doubled[self._offset : self._offset + self.WINDOW_CHARS])
        self._offset = (self._offset + 1) % len(self._loop_text)

    def enterEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._timer.stop()  # hold still while the pointer is over it, so a line can be read at leisure
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt convention
        self.clicked.emit()
        super().mousePressEvent(event)


class StatusBarPanel(QStatusBar):
    relink_requested = Signal()  # the "N sách không tìm thấy file. Tìm lại?" label was clicked
    _ollama_probed = Signal(bool)  # the background check finished (emitted from a worker thread)
    _cloud_probed = Signal(bool)  # the community-reviews check finished (emitted from a worker thread)

    STATUS_BUBBLE_MS = 6000  # how long the sentence stays beside the icon

    # Ollama has no key to look for, so "connected" has to be observed: asked again this often, so switching
    # Ollama off (or on) is noticed without touching Settings.
    OLLAMA_POLL_MS = 30_000

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._active_collection_ids: tuple[str, ...] = ()
        self._ollama_up: bool | None = None  # None = not checked yet
        self._ollama_probe_running = False
        self._cloud_reachable: bool | None = None  # None = not asked yet; set by a click on the cloud icon
        self._cloud_probe_running = False
        self.last_status_text = ""  # the sentence the latest click on a status icon showed
        self._import_progress: tuple[int, int] | None = None
        self._classify_progress: tuple[int, int] | None = None

        colors = current_colors()
        # A top border so the bar reads as its own strip, separated from
        # whatever's directly above it (library view or detail panel) --
        # QStatusBar spans the full window width, under both.
        self.setStyleSheet(f"QStatusBar {{ border-top: 1px solid {colors.border}; }}")

        # -- left zone: library --
        self.files_label = QLabel(self)
        self.complete_label = QLabel(self)
        self.incomplete_label = QLabel(self)
        self.collection_label = QLabel(self)
        self.folders_label = QLabel(self)
        self.activity_label = QLabel(self)
        self.activity_label.setVisible(False)
        self.missing_label = _ClickableStatusLabel(self)
        self.missing_label.setCursor(Qt.PointingHandCursor)
        self.missing_label.setVisible(False)
        self.missing_label.clicked.connect(self.relink_requested)
        self.update_label = _ClickableStatusLabel(self)
        self.update_label.setCursor(Qt.PointingHandCursor)
        self.update_label.setVisible(False)
        self._update_url = ""
        self.update_label.clicked.connect(self._on_update_clicked)

        # -- middle zone: system & connections --
        self.cloud_label = _StatusIcon("☁️", self)
        self.ai_label = _StatusIcon("🤖", self)
        self.network_label = _StatusIcon("🌐", self)

        # -- right zone: author & support --
        self.donate_ticker = _DonateTicker(self)
        self.donate_ticker.clicked.connect(self._on_donate_clicked)
        self.community_label = _ClickableStatusLabel("📣", self)
        self.community_label.setCursor(Qt.PointingHandCursor)
        self.community_label.setToolTip("Fanpage cộng đồng: tin về bản mới và nơi gửi góp ý (mở trong trình duyệt)")
        self.community_label.clicked.connect(open_community_page)
        self.author_label = QLabel("Tác giả: AnhTienSinh", self)
        self.author_label.setToolTip(f"{APP_DISPLAY_NAME} ({APP_NAME}) -- tác giả: {APP_PUBLISHER}")

        for label in (
            self.files_label,
            self.complete_label,
            self.incomplete_label,
            self.collection_label,
            self.folders_label,
            self.activity_label,
        ):
            label.setTextFormat(Qt.RichText)

        self.library_zone = self._zone(
            [
                self.files_label,
                self.complete_label,
                self.incomplete_label,
                self.folders_label,
                self.collection_label,
                self.activity_label,
                self.missing_label,
                self.update_label,
            ],
            spacing=_ZONE_SPACING_WIDE,
            trailing_stretch=True,
        )
        self.system_zone = self._zone([self.cloud_label, self.ai_label, self.network_label], spacing=_ZONE_SPACING_TIGHT)
        self.support_zone = self._zone([self.donate_ticker, self.community_label, self.author_label], spacing=_ZONE_SPACING_WIDE)
        for label in (self.cloud_label, self.ai_label, self.network_label):
            label.setFixedWidth(_STATUS_ICON_WIDTH)  # equal slots: the three icons sit evenly, whatever their glyphs
        for widget in (
            self.files_label,
            self.complete_label,
            self.incomplete_label,
            self.folders_label,
            self.collection_label,
            self.activity_label,
            self.community_label,
            self.author_label,
            self.cloud_label,
            self.ai_label,
            self.network_label,
        ):
            widget.setFixedHeight(_ROW_HEIGHT)
            widget.setAlignment(widget.alignment() | Qt.AlignVCenter)

        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(10)
        row.addWidget(self.library_zone, 1)
        row.addWidget(self._divider(container))
        row.addWidget(self.system_zone, 0)
        row.addWidget(self._divider(container))
        row.addWidget(self.support_zone, 0)
        self.addWidget(container, 1)

        self._refresh_timer = debounced(self, self.refresh)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        for event_type in (
            LibraryUpdatedEvent,
            FilterChangedEvent,
            LibraryFilesMissingEvent,
            UpdateAvailableEvent,
            AiConnectionChangedEvent,
            ImportProgressEvent,
            ImportBatchCompletedEvent,
            SmartClassifyProgressEvent,
            SmartClassifyFinishedEvent,
        ):
            self._bridge.subscribe(context.event_bus, event_type)

        self._ollama_probed.connect(self._on_ollama_probed)
        self._cloud_probed.connect(self._on_cloud_probed)
        self.cloud_label.clicked.connect(self._on_cloud_clicked)
        self.ai_label.clicked.connect(lambda: self._say(self.ai_label))
        self.network_label.clicked.connect(lambda: self._say(self.network_label))
        self._ollama_timer = QTimer(self)
        self._ollama_timer.setInterval(self.OLLAMA_POLL_MS)
        self._ollama_timer.timeout.connect(self._start_ollama_probe)
        self._ollama_timer.start()

        self._network_info = self._load_network_information()
        if self._network_info is not None:
            self._network_info.reachabilityChanged.connect(lambda _reachability: self._refresh_network())

        self.refresh()

    # -- construction helpers --

    @staticmethod
    def _zone(widgets: list[QWidget], *, spacing: int = 10, trailing_stretch: bool = False) -> QWidget:
        zone = QWidget()
        layout = QHBoxLayout(zone)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        layout.setAlignment(Qt.AlignVCenter)
        for widget in widgets:
            layout.addWidget(widget)
        if trailing_stretch:
            layout.addStretch(1)
        return zone

    @staticmethod
    def _divider(parent: QWidget) -> QFrame:
        line = QFrame(parent)
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet(f"color: {current_colors().border};")
        return line

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._fit_ticker()

    def _fit_ticker(self) -> None:
        """In a narrow window the moving text is the first thing to go: the zones then hold only their icons, so
        nothing is ever drawn on top of anything else."""
        others = (
            self.library_zone.minimumSizeHint().width()
            + self.system_zone.sizeHint().width()
            + self.community_label.sizeHint().width()
            + self.author_label.sizeHint().width()
        )
        room = self.width() - others - 60  # dividers, margins and the spacing between items
        self.donate_ticker.setVisible(room >= self.donate_ticker._slot_width)

    # -- events --

    def _on_donate_clicked(self) -> None:
        DonateDialog(self).exec()

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, FilterChangedEvent):
            self._active_collection_ids = event.filter.collections
            self.refresh()
        elif isinstance(event, LibraryFilesMissingEvent):
            self._show_missing(event.count)
        elif isinstance(event, UpdateAvailableEvent):
            self._show_update(event.version, event.url)
        elif isinstance(event, AiConnectionChangedEvent):
            self._set_ollama_up(event.connected)
        elif isinstance(event, ImportProgressEvent):
            self._import_progress = (event.done, event.total) if event.done < event.total else None
            self._show_activity()
        elif isinstance(event, ImportBatchCompletedEvent):
            self._import_progress = None
            self._show_activity()
        elif isinstance(event, SmartClassifyProgressEvent):
            self._classify_progress = (event.done, event.total) if event.done < event.total else None
            self._show_activity()
        elif isinstance(event, SmartClassifyFinishedEvent):
            self._classify_progress = None
            self._show_activity()
        else:
            self._refresh_timer.start()  # LibraryUpdatedEvent bursts during imports

    def _show_activity(self) -> None:
        """Import and classification progress: shown only while a job runs, as an icon and a count."""
        parts: list[str] = []
        tips: list[str] = []
        if self._import_progress:
            done, total = self._import_progress
            parts.append(f"⏳ {done}/{total}")
            tips.append(f"Đang thêm sách vào thư viện: {done}/{total}")
        if self._classify_progress:
            done, total = self._classify_progress
            parts.append(f"🧠 {done}/{total}")
            tips.append(f"Đang tự phân loại sách: {done}/{total}")
        self.activity_label.setText("  ".join(parts))
        self.activity_label.setToolTip("\n".join(tips))
        self.activity_label.setVisible(bool(parts))

    def _show_update(self, version: str, url: str) -> None:
        self._update_url = url
        self.update_label.setTextFormat(Qt.RichText)
        self.update_label.setText(f"<span style='color:{_STATUS_OK_COLOR}; font-weight:600;'>⬆️ Có bản mới {version}. Xem?</span>")
        self.update_label.setVisible(True)

    def _on_update_clicked(self) -> None:
        if self._update_url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(self._update_url))

    def _show_missing(self, count: int) -> None:
        self.missing_label.setVisible(count > 0)
        if count > 0:
            self.missing_label.setText(f"<span style='color:{_STATUS_MISSING_COLOR}; font-weight:600;'>⚠️ {count} sách không tìm thấy file. Tìm lại?</span>")
            self.missing_label.setTextFormat(Qt.RichText)

    # -- refresh --

    def refresh(self) -> None:
        self._show_missing(self.context.db.count_missing())
        total = self.context.db.count_documents()
        complete, incomplete = self.context.db.count_metadata_completeness()
        self.files_label.setText(f"📚 {total}")
        self.files_label.setToolTip(f"Thư viện có {total} tài liệu")
        self.complete_label.setText(f"✅ {complete}")
        self.complete_label.setToolTip(f"{complete} tài liệu đã đủ thông tin")
        self.incomplete_label.setText(f"⚠️ {incomplete}")
        self.incomplete_label.setToolTip(f"{incomplete} tài liệu còn thiếu thông tin (tác giả, bìa...)")

        ids = self._active_collection_ids
        if len(ids) == 1:
            row = self.context.db.get_collection(ids[0])
            name = row["name"] if row else "Bộ sưu tập"
            count = self.context.db.count_documents_in_collection(ids[0])
            self.collection_label.setText(f"📁 {name}: {count}")
            self.collection_label.setToolTip(f"Bộ sưu tập \"{name}\": {count} tài liệu")
        elif ids:
            # Several collections combined: the count is of their union
            # (a document in two of them counts once), matching what the
            # library view is actually showing.
            sql, params = self.context.db.collections_where_fragment(ids)
            count = self.context.db.count_documents_matching(where_sql=sql, params=params)
            self.collection_label.setText(f"📁 {len(ids)}: {count}")
            self.collection_label.setToolTip(f"{len(ids)} bộ sưu tập gộp lại: {count} tài liệu")
        else:
            self.collection_label.setText("")
            self.collection_label.setToolTip("")

        folder_count = len(self.context.config.config.watch_folders)
        self.folders_label.setText(f"👁 {folder_count}")
        self.folders_label.setToolTip(f"Đang theo dõi {folder_count} thư mục: sách mới bỏ vào đó sẽ tự được thêm")

        self._refresh_cloud()

        self._refresh_ai()
        self._refresh_network()
        self._fit_ticker()

    def _cloud_configured(self) -> bool:
        config = self.context.config.config
        return bool(config.supabase_url and config.supabase_anon_key)

    def _refresh_cloud(self) -> None:
        if not self._cloud_configured():
            self.cloud_label.set_state(STATE_OFF, "Đánh giá cộng đồng: chưa được bật trong bản này. Bấm để xem trạng thái")
        elif self._cloud_reachable is False:
            self.cloud_label.set_state(STATE_ERROR, "Đánh giá cộng đồng: chưa kết nối được. Bấm để kiểm tra lại")
        else:
            self.cloud_label.set_state(STATE_OK, "Đánh giá cộng đồng: đang bật, bạn có thể xem và viết đánh giá. Bấm để kiểm tra kết nối")

    # -- a click on a status icon: the state in words, never a settings window --

    def _say(self, icon: _StatusIcon, text: str | None = None) -> None:
        """Shows `text` (default: the icon's own tooltip sentence) in a bubble just above the icon."""
        text = text if text is not None else icon.toolTip()
        self.last_status_text = text
        anchor = icon.mapToGlobal(QPoint(icon.width() // 2, 0))
        QToolTip.showText(anchor, text, icon, QRect(), self.STATUS_BUBBLE_MS)

    def _on_cloud_clicked(self) -> None:
        if not self._cloud_configured():
            self._say(self.cloud_label, "Đánh giá cộng đồng: chưa được bật trong bản này, nên chưa xem được đánh giá của người khác.")
            return
        if self._cloud_probe_running:
            return
        self._cloud_probe_running = True
        self._say(self.cloud_label, "Đánh giá cộng đồng: đang kiểm tra kết nối...")
        config = self.context.config.config
        url, key = config.supabase_url or "", config.supabase_anon_key or ""

        def worker() -> None:
            try:
                SupabaseReviewSync(url, key).test_connection()
                ok = True
            except CloudReviewError:
                ok = False
            except Exception:  # noqa: BLE001 -- any failure just means "cannot reach it"; the user sees a plain sentence
                ok = False
            try:
                self._cloud_probed.emit(ok)
            except RuntimeError:
                pass  # the window was closed while the check was running

        threading.Thread(target=worker, name="cloud-probe", daemon=True).start()

    def _on_cloud_probed(self, ok: bool) -> None:
        self._cloud_probe_running = False
        self._cloud_reachable = ok
        self._refresh_cloud()
        self._say(
            self.cloud_label,
            "Đánh giá cộng đồng: kết nối tốt, bạn có thể xem và viết đánh giá."
            if ok
            else "Đánh giá cộng đồng: chưa kết nối được. Hãy kiểm tra mạng rồi bấm lại.",
        )

    def _refresh_ai(self) -> None:
        config = self.context.config.config
        if config.ai_provider and not provider_requires_key(config.ai_provider):
            # A local AI (Ollama): connected means "answers right now", not "has a key".
            if self._ollama_up is None:
                self._start_ollama_probe()
                self.ai_label.set_state(STATE_OFF, "AI tóm tắt: đang kiểm tra Ollama...")
            elif self._ollama_up:
                self.ai_label.set_state(STATE_OK, "AI tóm tắt: Ollama đang chạy, sẵn sàng dùng")
            else:
                self.ai_label.set_state(STATE_ERROR, "AI tóm tắt: không thấy Ollama. Hãy mở Ollama rồi thử lại")
        elif config.ai_provider and config.ai_api_key:
            self.ai_label.set_state(STATE_OK, "AI tóm tắt: đã thiết lập, sẵn sàng dùng")
        else:
            self.ai_label.set_state(STATE_OFF, "AI tóm tắt: chưa thiết lập (vào Cài đặt → AI Tóm tắt)")

    # -- network (the operating system's own report; nothing is sent) --

    @staticmethod
    def _load_network_information():
        try:
            from PySide6.QtNetwork import QNetworkInformation

            if QNetworkInformation.instance() is None and not QNetworkInformation.loadDefaultBackend():
                return None
            return QNetworkInformation.instance()
        except (ImportError, RuntimeError):
            return None

    def _network_state(self) -> str | None:
        """ok / error, or None when this system cannot say (then the icon is hidden rather than guessed)."""
        if self._network_info is None:
            return None
        from PySide6.QtNetwork import QNetworkInformation

        reachability = self._network_info.reachability()
        if reachability == QNetworkInformation.Reachability.Online:
            return STATE_OK
        if reachability == QNetworkInformation.Reachability.Unknown:
            return None
        return STATE_ERROR

    def _refresh_network(self) -> None:
        state = self._network_state()
        self.network_label.setVisible(state is not None)
        if state == STATE_OK:
            self.network_label.set_state(STATE_OK, "Mạng: đang có Internet")
        elif state == STATE_ERROR:
            self.network_label.set_state(STATE_ERROR, "Mạng: không có Internet. Tìm ảnh bìa và tóm tắt bằng AI trên mạng sẽ chưa dùng được")

    # -- Ollama --

    def _start_ollama_probe(self) -> None:
        config = self.context.config.config
        if not config.ai_provider or provider_requires_key(config.ai_provider) or self._ollama_probe_running:
            return
        self._ollama_probe_running = True
        base_url = config.ai_base_url

        def worker() -> None:
            up = probe_ollama(base_url)
            try:
                self._ollama_probed.emit(up)
            except RuntimeError:
                pass  # the window was closed while the check was running

        threading.Thread(target=worker, name="ollama-probe", daemon=True).start()

    def _on_ollama_probed(self, up: bool) -> None:
        self._ollama_probe_running = False
        self._set_ollama_up(up)

    def _set_ollama_up(self, up: bool) -> None:
        if up != self._ollama_up:
            self._ollama_up = up
            self.refresh()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QMainWindow

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Complete Book", "author": "Someone", "file_path": "a.pdf", "cover_path": "a.webp", "created_at": 0.0}
        )
        context.db.add_or_update_document("d2", {"title": "Missing info", "author": "Unknown", "file_path": "b.pdf", "created_at": 0.0})

        app = QApplication(sys.argv)
        apply_light_theme(app)
        window = QMainWindow()
        window.setStatusBar(StatusBarPanel(context))
        window.resize(900, 200)
        window.show()
        sys.exit(app.exec())
