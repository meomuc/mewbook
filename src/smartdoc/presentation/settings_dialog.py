"""Settings window (stage G9): a column of ten pills on the left and one page per pill on the right.

Pages: Quản lý File, Giao diện (seven theme cards + both font axes), Hiệu năng (every option says what raising and
lowering it does), Phân loại, AI Tóm tắt, Ảnh bìa, Đánh giá cộng đồng, Sao lưu, Cập nhật & ủng hộ, Quyền riêng tư.
An option that does not exist yet is shown disabled with a "Sắp có" badge and has no behaviour behind it.

Changes are saved as they are made (a short pause after the last edit, see `_autosave_timer`); "Đóng" saves once
more and closes. The pages live in a QTabWidget whose tab bar is hidden -- the pills drive it.

Nothing here needs an app restart:
- Watch folder / allowed-extension changes take effect immediately (the
  file watcher and scan_folder read config live).
- Worker thread count and the file-watcher debounce are applied live via
  ImportQueueManager.restart() / LibraryWatcher.set_debounce_seconds().
- Theme and font can't be live-restyled onto already-built widgets that
  baked their colors into a stylesheet string at construction time --
  instead of a sprawling "every widget re-subscribes to a theme-changed
  event" refactor, this dialog just flags `appearance_changed`, and
  MainWindow rebuilds itself (same AppContext/watcher/import_manager, fresh
  widget tree) after the dialog closes. See app.py's on_appearance_changed.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.ai_summary import (
    DEFAULT_MODELS,
    SUMMARY_LANGUAGES,
    SUMMARY_LENGTHS,
    SUMMARY_STYLES,
    OLLAMA_DEFAULT_BASE_URL,
    provider_guide_html,
    AISummaryError,
    provider_requires_key,
    test_connection,
)
from smartdoc.application.cover_search import (
    MAX_MATCH_PERCENT,
    MIN_MATCH_PERCENT,
    SOURCE_APPLE_BOOKS,
    SOURCE_GOOGLE_BOOKS,
    SOURCE_OPEN_LIBRARY,
    SOURCE_TIKI,
    CoverSearchError,
)
from smartdoc.application.cover_search import test_connection as test_cover_connection
from smartdoc.application.review_endpoint import STATE_OFF as STATE_REVIEWS_OFF
from smartdoc.application.review_endpoint import STATE_ON as STATE_REVIEWS_ON
from smartdoc.application.review_endpoint import review_state
from smartdoc.core.event_bus import AiConnectionChangedEvent, LibraryUpdatedEvent
from smartdoc.core.config import AI_PROVIDER_CHOICES, AI_PROVIDER_DISPLAY_NAMES, KNOWN_EXTENSIONS
from smartdoc.domain.text_classifier import read_model_meta, resolve_model_path
from smartdoc.presentation.backup_panel import BackupPanel
from smartdoc.presentation.flow_widget import FlowWidget
from smartdoc.presentation.brand import mascot_pixmap
from smartdoc.presentation.library_view import PAGE_SIZE
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.privacy_panel import PrivacyPanel
from smartdoc.presentation.resources import donate_qr_path
from smartdoc.presentation.layouts import compose_tokens, layout_for, selectable_layouts, theme_label
from smartdoc.presentation.settings_widgets import LayoutCard, PillList, SettingsPage, ThemeCard, add_note_box, hint_pair
from smartdoc.presentation.theme import ROLE_HINT, ROLE_RESULT, colors_for, current_colors, resolve_font_family, role_css
from smartdoc.presentation.theme_manager import available_themes, load_tokens, theme_manager
from smartdoc.presentation.update_panel import UpdatePanel
from smartdoc.presentation.worker_relay import WorkerRelay, post

# Written out step by step rather than as a one-line "get a key here"
# pointer: this is the one setup in the app that spans two *different*
# Google consoles (Programmable Search Engine for the cx, Google Cloud for
# the API key), and getting either half subtly wrong fails in ways that
# don't obviously point back at the step that caused them.
_COVER_SEARCH_SETUP_GUIDE = """
<b>Cách lấy khóa tìm ảnh bìa của Google (miễn phí, khoảng 5 phút)</b>
<p>Bạn cần hai thứ: <b>Search Engine ID</b> (Phần 1) và <b>API key</b> (Phần 2). Tên các nút bên dưới là tiếng Anh
vì đó là chữ trên trang của Google.</p>

<p><b>Phần 1 — Lấy Search Engine ID:</b></p>
<ol>
<li>Mở trang <a href="https://programmablesearchengine.google.com/controlpanel/create">programmablesearchengine.google.com/controlpanel/create</a>.</li>
<li>Đăng nhập bằng tài khoản Google của bạn.</li>
<li>Ở ô <b>"Name"</b>, gõ tên bất kỳ, ví dụ <i>Bìa sách</i>.</li>
<li>Chọn <b>"Search the entire web"</b> (tìm trên toàn bộ web).</li>
<li>Bật công tắc <b>"Image search"</b> (tìm ảnh). Bước này bắt buộc, nếu bỏ qua sẽ không tìm được ảnh.</li>
<li>Bấm nút <b>"Create"</b>.</li>
<li>Bấm nút <b>"Customize"</b>.</li>
<li>Tìm dòng <b>"Search engine ID"</b> và sao chép dãy chữ số đó.</li>
<li>Quay lại cửa sổ này và dán vào ô <b>Search Engine ID</b> ở trên.</li>
</ol>

<p><b>Phần 2 — Lấy API key:</b></p>
<ol>
<li>Mở trang <a href="https://console.cloud.google.com/apis/library/customsearch.googleapis.com">console.cloud.google.com/apis/library/customsearch.googleapis.com</a> (cùng tài khoản Google).</li>
<li>Nếu trang bắt tạo dự án: bấm <b>"Create project"</b>.</li>
<li>Gõ tên bất kỳ cho dự án, rồi bấm <b>"Create"</b>.</li>
<li>Bấm nút <b>"Enable"</b>. Bước này bắt buộc, nếu bỏ qua sẽ không dùng được.</li>
<li>Mở trang <a href="https://console.cloud.google.com/apis/credentials">console.cloud.google.com/apis/credentials</a>.</li>
<li>Bấm <b>"+ Create credentials"</b>.</li>
<li>Chọn <b>"API key"</b>.</li>
<li>Sao chép khóa vừa hiện ra.</li>
<li>Quay lại cửa sổ này và dán vào ô <b>API key</b> ở trên.</li>
</ol>

<p><b>Phần 3 — Kiểm tra:</b></p>
<ol>
<li>Bấm nút <b>"Kiểm tra kết nối"</b> ở trên.</li>
<li>Nếu báo thành công là xong. Nếu báo lỗi, câu báo lỗi cho biết phải làm lại bước nào ở trên.</li>
</ol>

<p><i>Miễn phí 100 lượt tìm mỗi ngày. Hết lượt, ứng dụng vẫn tìm ảnh bìa bằng các nguồn khác.</i></p>
"""


class SettingsDialog(QDialog):
    connection_test_finished = Signal(bool, str)  # (success, message)
    cover_test_finished = Signal(bool, str)  # (success, message)
    calibre_import_requested = Signal()  # "Nhập từ Calibre…": the main window owns that flow

    FOLDER_LIST_MAX_ROWS = 5  # the watched-folders box grows up to this many rows, then scrolls

    # -- frame ------------------------------------------------------------------------------------------------------
    _PAGE_KEYS = ("file", "theme", "perf", "classify", "ai", "cover", "reviews", "backup", "update", "privacy")

    def __init__(self, context, parent=None, watcher=None, import_manager=None, initial_tab: str | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager
        self.setWindowTitle("Cài đặt")
        self.setObjectName("SettingsDialog")
        self.setMinimumSize(860, 560)
        self.resize(1000, 700)

        config = context.config.config
        self.appearance_changed = False  # theme/font: see module docstring
        self._relay = WorkerRelay(self)  # what the connection-test threads talk to
        tm = theme_manager()

        # One page per pill. A QTabWidget without its own tab bar: the pill column drives it.
        self.tabs = QTabWidget(self)
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.pills = PillList(self)
        self.tabs.currentChanged.connect(self.pills.setCurrentRow)
        self.pills.page_selected.connect(self.tabs.setCurrentIndex)
        self.backup_panel = BackupPanel(context, self)
        self.update_panel = UpdatePanel(context, self)
        self.privacy_panel = PrivacyPanel(context, self)
        pages = (
            ("folder", "Quản lý File", self._build_file_tab(config)),
            ("palette", "Giao diện", self._build_theme_tab(config)),
            ("bolt", "Hiệu năng", self._build_performance_tab(config)),
            ("tag", "Phân loại", self._build_smart_classify_tab(config)),
            ("bot", "AI Tóm tắt", self._build_ai_tab(config)),
            ("image", "Ảnh bìa", self._build_cover_search_tab(config)),
            ("star", "Đánh giá cộng đồng", self._build_reviews_tab(config)),
            ("archive", "Sao lưu", self.backup_panel),
            ("download", "Cập nhật & ủng hộ", self._add_donation(self.update_panel)),
            ("shield", "Quyền riêng tư", self.privacy_panel),
        )
        for icon, name, page in pages:
            self.tabs.addTab(page, name)
            self.pills.add_page(icon, name)
        if initial_tab in self._PAGE_KEYS:
            self.tabs.setCurrentIndex(self._PAGE_KEYS.index(initial_tab))
        self.pills.setCurrentRow(self.tabs.currentIndex())

        self.connection_test_finished.connect(self._on_connection_test_finished)
        self.cover_test_finished.connect(self._on_cover_test_finished)

        heading = QLabel("CÀI ĐẶT", self)
        heading.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px; letter-spacing: 1px; padding: 14px 0 0 18px;"
                              f" background: {tm.token('rail')};")
        rail = QVBoxLayout()
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(0)
        rail.addWidget(heading)
        rail.addWidget(self.pills, 1)
        rail_holder = QWidget(self)
        rail_holder.setObjectName("SettingsRail")
        rail_holder.setStyleSheet(f"#SettingsRail {{ background: {tm.token('rail')}; border-right: 1px solid {tm.token('line')}; }}")
        rail_holder.setLayout(rail)

        self.saved_label = QLabel("Thay đổi được lưu ngay.", self)
        self.saved_label.setStyleSheet(f"color: {tm.token('ink3')};")
        self.done_button = QPushButton("Đóng", self)
        self.done_button.clicked.connect(self._on_save)
        footer = QFrame(self)
        footer.setObjectName("SettingsFooter")
        footer.setStyleSheet(f"#SettingsFooter {{ background: {tm.token('surface2')}; border-top: 1px solid {tm.token('line')}; }}")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(18, 10, 18, 10)
        footer_row.addWidget(self.saved_label)
        footer_row.addStretch(1)
        footer_row.addWidget(self.done_button)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(rail_holder)
        body.addWidget(self.tabs, 1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(body, 1)
        outer.addWidget(footer)
        self.setStyleSheet(f"#SettingsDialog {{ background: {tm.token('bg')}; }}"
                           f" #SettingsPage, #SettingsPageBody {{ background: {tm.token('bg')}; }}")

        # Changes are saved as they are made (a moment after the last one), so "Đóng" never loses anything.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self._apply_settings)
        self._wire_autosave()

    def _wire_autosave(self) -> None:
        for box in self.findChildren(QCheckBox):
            box.toggled.connect(self._schedule_autosave)
        for combo in self.findChildren(QComboBox):
            combo.currentIndexChanged.connect(self._schedule_autosave)
        for spin in [*self.findChildren(QSpinBox), *self.findChildren(QDoubleSpinBox)]:
            spin.valueChanged.connect(self._schedule_autosave)
        for edit in self.findChildren(QLineEdit):
            edit.editingFinished.connect(self._schedule_autosave)
        for radio in self.privacy_panel.mode_buttons.values():
            radio.toggled.connect(self._schedule_autosave)

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        self._fit_folder_list()
        QTimer.singleShot(0, self._fit_folder_list)  # row heights are only exact once the window's style is applied

    def _schedule_autosave(self, *_args) -> None:
        self._autosave_timer.start()

    # -- pages -------------------------------------------------------------------------------------------------------
    def _build_file_tab(self, config) -> QWidget:
        page = SettingsPage("Quản lý File", "Nơi MewBook tìm sách và cách nó đối xử với file của bạn.", self)

        # The formats sit side by side and wrap onto a new line when the window is narrow.
        self.extension_flow = FlowWidget(page, h_spacing=16, v_spacing=6)
        self._extension_checkboxes: dict[str, QCheckBox] = {}
        for extension in KNOWN_EXTENSIONS:
            checkbox = QCheckBox(extension.upper(), self.extension_flow)
            checkbox.setChecked(extension in config.allowed_extensions)
            self._extension_checkboxes[extension] = checkbox
        self.extension_flow.set_widgets(list(self._extension_checkboxes.values()))
        page.add_row("Định dạng quét tự động", "Chỉ những định dạng được tích mới được thêm vào thư viện.", self.extension_flow)

        folders = QWidget(page)
        folders_layout = QVBoxLayout(folders)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_list = QListWidget(folders)
        self.folder_list.addItems(config.watch_folders)
        self._fit_folder_list()
        folders_layout.addWidget(self.folder_list)
        folder_buttons = QHBoxLayout()
        add_button = QPushButton("Thêm thư mục…", folders)
        add_button.setIcon(line_icon("plus", theme_manager().token("ink"), 14))
        add_button.clicked.connect(self._on_add_folder)
        remove_button = QPushButton("Bỏ theo dõi thư mục đã chọn", folders)
        remove_button.clicked.connect(self._on_remove_folder)
        folder_buttons.addWidget(add_button)
        folder_buttons.addWidget(remove_button)
        folder_buttons.addStretch(1)
        folders_layout.addLayout(folder_buttons)
        page.add_row("Thư mục theo dõi", "Sách mới chép vào các thư mục này tự hiện trong thư viện.", folders)

        self.calibre_button = QPushButton("Nhập từ thư viện Calibre…", page)
        self.calibre_button.clicked.connect(self.calibre_import_requested)
        page.add_row("Nhập từ Calibre", "Đọc thư viện Calibre của bạn; Calibre không bị thay đổi.", self.calibre_button)

        page.add_block(add_note_box(page, "<b>MewBook không bao giờ di chuyển, đổi tên hay xóa file sách gốc của bạn.</b> "
                                    "Chỉ khi chính bạn chọn (chuyển file trùng vào Thùng rác của MewBook, hoặc “Gom sách” bằng cách di chuyển), và luôn có bước xác nhận.", "ok"))
        page.add_row("Gom sách về một thư mục", "Sao chép hoặc di chuyển sách về một nơi cho gọn.", QPushButton("Gom sách…", page),
                     soon=True)

        ereader = QWidget(page)
        ereader_row = QHBoxLayout(ereader)
        ereader_row.setContentsMargins(0, 0, 0, 0)
        self._ereader_folder_path = config.ereader_folder_path
        self.ereader_folder_edit = QLineEdit(ereader)
        self.ereader_folder_edit.setText(self._ereader_folder_path or "")
        self.ereader_folder_edit.setReadOnly(True)
        self.ereader_folder_edit.setPlaceholderText("Chưa thiết lập")
        choose_ereader_button = QPushButton("Chọn…", ereader)
        choose_ereader_button.clicked.connect(self._on_choose_ereader_folder)
        ereader_row.addWidget(self.ereader_folder_edit, 1)
        ereader_row.addWidget(choose_ereader_button)
        page.add_row("Thư mục sách trên máy đọc sách", "Nơi “Gửi sang máy đọc sách” chép sách tới (cắm qua USB).", ereader)

        metadata = QWidget(page)
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata_write_check = QCheckBox("Mặc định ghi đè lên file sách gốc khi cập nhật thông tin sách (EPUB/PDF)", metadata)
        self.metadata_write_check.setToolTip(
            "Tắt (nên để vậy): chỉ thư viện thay đổi, file sách giữ nguyên trừ khi bạn chọn ghi đè từng lần. "
            "Muốn giữ file cũ để hoàn tác: bật \"Sao lưu trước khi thay đổi\" ở Cài đặt › Sao lưu."
        )
        self.metadata_write_check.setChecked(config.metadata_write_to_file_default)
        metadata_layout.addWidget(self.metadata_write_check)
        page.add_row("Tìm thông tin sách", "Mặc định là chỉ sửa trong thư viện, không sửa file.", metadata)
        return page

    def _build_theme_tab(self, config) -> QWidget:
        """Everything about how the app looks, in one place: the theme itself plus both font axes -- the app's own
        chrome font, and the separate "content" font used for document text (see AppConfig's docstring on
        content_font_family for why those two stay distinct settings even though they now live on one page)."""
        page = SettingsPage("Giao diện", "Chọn kiểu giao diện, rồi bảng màu và kiểu chữ. Đổi xong là áp dụng khi đóng cửa sổ này.", self)

        # Two layers: the layout (the window's shape, code) and, inside it, the theme (colour and type, data). The
        # hidden combos stay the single source of truth (what the tests and _apply_settings read); the cards drive them.
        layouts = selectable_layouts()
        self._layout_id = config.layout if config.layout in layouts else next(iter(layouts))
        self._theme_memory: dict[str, str] = dict(config.theme_by_layout)  # layout id -> the theme last used with it
        self._theme_memory[self._layout_id] = config.theme
        self.layout_combo = QComboBox(page)
        for spec in layouts.values():
            self.layout_combo.addItem(spec.name, spec.id)
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(self._layout_id)))
        self.layout_combo.hide()
        layout_cards = FlowWidget(page, h_spacing=12, v_spacing=12)
        self.layout_cards: dict[str, LayoutCard] = {}
        for spec in layouts.values():
            card = LayoutCard(spec.id, spec.name, spec.description, layout_cards)
            card.chosen.connect(self._on_layout_card_chosen)
            self.layout_cards[spec.id] = card
        layout_cards.set_widgets(list(self.layout_cards.values()))
        self._sync_layout_cards()
        page.add_row("Kiểu giao diện", "Hình khối và cách bố trí của cửa sổ.", self.layout_combo)
        page.add_block(layout_cards)

        self.theme_combo = QComboBox(page)
        self.theme_combo.hide()
        self._theme_cards_holder = FlowWidget(page, h_spacing=12, v_spacing=12)
        self.theme_cards: dict[str, ThemeCard] = {}
        self._other_layout_note = QLabel(page)
        self._other_layout_note.setWordWrap(True)
        self._other_layout_note.setTextFormat(Qt.RichText)
        self._other_layout_note.linkActivated.connect(self._on_layout_link)
        self._theme_row_hint = QLabel(page)
        self._fill_theme_cards()
        self.theme_combo.currentIndexChanged.connect(self._sync_theme_cards)
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        page.add_row("Bảng màu", "Chỉ hiện những bảng màu dùng được với kiểu đang chọn.", self.theme_combo)
        page.add_block(self._theme_cards_holder)  # full width, so the cards wrap to as many rows as the window needs
        page.add_block(self._other_layout_note)

        self.backdrop_check = QCheckBox("Hiện hình phong cảnh của theme", page)
        self.backdrop_check.setChecked(bool(config.show_backdrop))
        page.add_row("Hình phong cảnh", "Một hình mờ phía sau lưới sách ở các theme có (lá thu, núi, đồi…). Tắt đi thì nền phẳng.",
                     self.backdrop_check)

        # With no font chosen by the user, a font picker shows the theme's own typeface -- and follows the theme
        # cards as they change.
        theme_family = resolve_font_family(colors_for(config.theme))
        self.font_combo = QFontComboBox(page)
        self.font_combo.setCurrentFont(QFont(config.font_family or theme_family))
        # The combo always shows *some* concrete family -- compare against this on save rather than against
        # config.font_family directly, or "no change" would be misread as "user picked a font".
        self._initial_font_family = self.font_combo.currentFont().family()
        self.font_size_spin = QSpinBox(page)
        self.font_size_spin.setRange(6, 32)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setFixedWidth(84)
        self.font_size_spin.setValue(config.font_size)
        page.add_row("Phông chữ ứng dụng", "Menu, nút, bảng.", self._pair(self.font_combo, self.font_size_spin))

        self.content_font_combo = QFontComboBox(page)
        self.content_font_combo.setCurrentFont(QFont(config.content_font_family or theme_family))
        self._initial_content_font_family = self.content_font_combo.currentFont().family()
        self.content_font_size_spin = QSpinBox(page)
        self.content_font_size_spin.setRange(6, 48)
        self.content_font_size_spin.setSuffix(" px")
        self.content_font_size_spin.setFixedWidth(84)
        self.content_font_size_spin.setValue(config.content_font_size)
        self._content_text_color = config.content_text_color
        self.content_color_swatch = QLabel(page)
        self.content_color_swatch.setFixedSize(24, 24)
        self._update_color_swatch()
        pick_color_button = QPushButton("Chọn màu…", page)
        pick_color_button.clicked.connect(self._on_pick_content_color)
        reset_color_button = QPushButton("Mặc định", page)
        reset_color_button.setToolTip("Dùng màu chữ theo giao diện (sáng/tối) hiện tại")
        reset_color_button.clicked.connect(self._on_reset_content_color)
        color_box = QWidget(page)
        color_row = QHBoxLayout(color_box)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(QLabel("Màu chữ", color_box))
        color_row.addWidget(self.content_color_swatch)
        color_row.addWidget(pick_color_button)
        color_row.addWidget(reset_color_button)
        color_row.addStretch(1)
        preview = QLabel("Tiếng mưa trên mái ngói", page)
        preview.setStyleSheet(f"font-family: {theme_manager().token('content')}; font-size: 15px; color: {theme_manager().token('ink2')};")
        content_box = QWidget(page)
        content_layout = QVBoxLayout(content_box)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._pair(self.content_font_combo, self.content_font_size_spin))
        content_layout.addWidget(preview)
        content_layout.addWidget(color_box)
        page.add_row("Phông chữ nội dung", "Tên sách, tóm tắt, cửa sổ đọc.", content_box)

        # A font counts as "chosen by the user" only once they touch its picker; until then it follows the theme
        # (see _on_theme_preview_changed and _apply_settings), so picking a new theme also switches the typeface.
        self._font_touched = {"app": False, "content": False}
        self.font_combo.currentFontChanged.connect(lambda _font: self._font_touched.update(app=True))
        self.content_font_combo.currentFontChanged.connect(lambda _font: self._font_touched.update(content=True))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_preview_changed)
        return page

    @staticmethod
    def _pair(*widgets: QWidget) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            row.addWidget(widget)
        if len(widgets) < 3:
            row.addStretch(1)
        return box

    def _on_theme_card_chosen(self, name: str) -> None:
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(name)))

    def _on_layout_card_chosen(self, layout_id: str) -> None:
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(layout_id)))

    def _on_layout_link(self, target: str) -> None:
        self._on_layout_card_chosen(target)

    def _on_layout_changed(self, _index: int = 0) -> None:
        """Another layout: remember the theme chosen in the old one, list the themes the new one accepts, and if the
        current theme is not among them switch to the layout's default (the old choice comes back on the way back)."""
        current = self.theme_combo.currentData()
        if current is not None:
            self._theme_memory[self._layout_id] = str(current)
        self._layout_id = str(self.layout_combo.currentData())
        self._sync_layout_cards()
        self._fill_theme_cards()

    def _sync_layout_cards(self) -> None:
        for layout_id, card in self.layout_cards.items():
            card.set_selected(layout_id == self.layout_combo.currentData())

    def _fill_theme_cards(self) -> None:
        """(Re)build the theme combo and cards for the selected layout."""
        spec = layout_for(self._layout_id)
        themes = load_tokens()
        infos = available_themes(spec.id)
        remembered = self._theme_memory.get(spec.id)
        keys = [info.key for info in infos]
        wanted = remembered if remembered in keys else next(
            (i.key for i in infos if i.theme_id == spec.default_theme), keys[0] if keys else "")
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for info in infos:
            self.theme_combo.addItem(info.name, info.key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(wanted)))
        self.theme_combo.blockSignals(False)
        for card in self.theme_cards.values():
            card.setParent(None)
            card.deleteLater()  # a discarded widget is destroyed by Qt, not left to the cycle collector
        self.theme_cards = {}
        for info in infos:
            tokens = compose_tokens(themes[info.theme_id], spec, info.theme_id)
            caption = theme_label(spec, info.theme_id) or ("Nền tối" if info.dark else "Nền sáng")
            card = ThemeCard(info.key, info.name, caption, self._theme_cards_holder, tokens=tokens)
            card.setToolTip(info.description)
            card.chosen.connect(self._on_theme_card_chosen)
            self.theme_cards[info.key] = card
        self._theme_cards_holder.set_widgets(list(self.theme_cards.values()))
        self._sync_theme_cards()
        parts = []
        for other in (o for o in selectable_layouts().values() if o.id != spec.id):
            other_id, other_name = other.id, other.name
            only_there = [i.name for i in available_themes(other_id) if i.key not in keys]
            if only_there:
                parts.append(f"Bảng màu chỉ dùng ở kiểu {other_name}: {', '.join(only_there)}. "
                             f"<a href=\"{other_id}\">Chuyển sang kiểu {other_name}</a>.")
        self._other_layout_note.setText(" ".join(parts))
        self._other_layout_note.setVisible(bool(parts))
        if hasattr(self, "_font_touched"):
            self._on_theme_preview_changed(self.theme_combo.currentIndex())

    def _sync_theme_cards(self, _index: int = 0) -> None:
        current = self.theme_combo.currentData()
        for name, card in self.theme_cards.items():
            card.set_selected(name == current)

    def _update_color_swatch(self) -> None:
        color = self._content_text_color or current_colors().text
        self.content_color_swatch.setStyleSheet(f"background: {color}; border: 1px solid {theme_manager().token('line2')};")

    def _on_pick_content_color(self) -> None:
        initial = QColor(self._content_text_color or current_colors().text)
        chosen = QColorDialog.getColor(initial, self, "Chọn màu chữ nội dung")
        if chosen.isValid():
            self._content_text_color = chosen.name()
            self._update_color_swatch()
            self._schedule_autosave()

    def _on_reset_content_color(self) -> None:
        self._content_text_color = None
        self._update_color_swatch()
        self._schedule_autosave()

    _PAGE_SIZE_CHOICES = (12, 24, 48, 96, 200)
    _CACHE_MB_CHOICES = (100, 300, 600, 1200)
    _READER_CHOICES = (1, 2, 3, 5, 8, 12)
    _CONTENT_PAGE_CHOICES = (10, 50, 200, 500)

    def _build_performance_tab(self, config) -> QWidget:
        page = SettingsPage("Hiệu năng", "Mỗi tùy chọn đều có lời giải thích ngắn: tăng lên thì được gì, giảm xuống thì được gì.", self)

        cpu_count = os.cpu_count() or 1
        active = self.import_manager.active_worker_count() if self.import_manager else 0
        self.performance_status_label = QLabel(
            f"Lúc này đang xử lý {active} sách cùng lúc. Máy của bạn làm tốt nhất khoảng {cpu_count} việc cùng lúc.", page
        )
        self.performance_status_label.setWordWrap(True)
        # A live measurement the app just produced -- the "kết quả" role (docs/UI_TEXT_ROLES.md).
        self.performance_status_label.setStyleSheet(role_css(ROLE_RESULT, theme_manager().token("ink")))
        page.add_block(self.performance_status_label)

        self.page_size_combo = self._choice_combo(page, self._PAGE_SIZE_CHOICES, config.page_size or PAGE_SIZE, "{}")
        page.add_row("Số sách mỗi trang", "", self.page_size_combo, extra=hint_pair(
            "Tăng lên thì cuộn ít hơn, nhưng mở trang chậm hơn.", "Giảm xuống thì mở trang nhanh hơn, phải chuyển trang nhiều hơn."))
        self.cover_cache_combo = self._choice_combo(page, self._CACHE_MB_CHOICES, config.cover_cache_mb or 300, "{} MB")
        page.add_row("Bộ nhớ đệm ảnh bìa", "", self.cover_cache_combo, extra=hint_pair(
            "Tăng lên thì lướt bìa mượt hơn, tốn thêm bộ nhớ.", "Giảm xuống thì tiết kiệm bộ nhớ, bìa có thể phải tải lại chậm hơn."))

        self.worker_spin = QSpinBox(page)
        self.worker_spin.setRange(1, 32)
        self.worker_spin.setValue(config.worker_thread_count)
        self.worker_hint = hint_pair(
            "Tăng lên thì nhập xong nhanh hơn, nhưng máy có thể nóng và chậm hơn trong lúc nhập.",
            "Giảm xuống thì nhập lâu hơn, nhưng máy êm hơn và bạn vẫn dùng mượt các việc khác.", page)
        page.add_row("Số việc chạy cùng lúc khi nhập", "Khi nhập nhiều sách một lúc, ứng dụng làm song song ngần này cuốn.",
                     self.worker_spin, extra=self.worker_hint)

        self.debounce_spin = QDoubleSpinBox(page)
        # No real upper limit -- just a very large ceiling so the widget has *some* bound (QDoubleSpinBox requires
        # one) without meaningfully constraining what the user can type.
        self.debounce_spin.setRange(0.5, 86400.0)
        self.debounce_spin.setSingleStep(0.5)
        self.debounce_spin.setSuffix(" giây")
        self.debounce_spin.setValue(config.watch_debounce_seconds)
        self.debounce_hint = hint_pair(
            "Tăng lên thì ít gặp file chép dở, nhưng sách mới hiện ra chậm hơn.",
            "Giảm xuống thì sách mới hiện ra nhanh hơn, nhưng có thể gặp file chưa chép xong.", page)
        page.add_row("Chờ bao lâu rồi mới thêm sách mới",
                     "Khi có file mới chép vào thư mục theo dõi, ứng dụng chờ ngần này giây để file chép xong.",
                     self.debounce_spin, extra=self.debounce_hint)

        self.reader_windows_combo = self._choice_combo(page, self._READER_CHOICES, config.max_reader_windows or 5, "{}")
        page.add_row("Số cửa sổ đọc mở cùng lúc", "", self.reader_windows_combo, extra=hint_pair(
            "Tăng lên thì đọc song song nhiều cuốn, tốn thêm bộ nhớ.",
            "Giảm xuống thì nhẹ máy hơn; mở cuốn mới sẽ đóng cuốn cũ nhất."))
        self.content_pages_combo = self._choice_combo(page, self._CONTENT_PAGE_CHOICES, config.content_search_pages or 10, "{} trang đầu")
        page.add_row("Đọc nội dung để tìm kiếm", "Số trang đầu của mỗi sách (PDF, EPUB, MOBI) được đọc khi thêm sách.", self.content_pages_combo,
                     extra=hint_pair("Tăng lên thì tìm theo nội dung chính xác hơn, thêm sách lâu hơn.",
                                     "Giảm xuống thì thêm sách nhanh hơn, có thể bỏ sót chữ ở cuối sách."))
        return page

    @staticmethod
    def _choice_combo(parent: QWidget, choices: tuple[int, ...], current: int, pattern: str) -> QComboBox:
        combo = QComboBox(parent)
        values = list(choices) if current in choices else sorted([*choices, current])
        for value in values:
            combo.addItem(pattern.format(value), value)
        combo.setCurrentIndex(combo.findData(current))
        combo.setMinimumWidth(140)
        return combo

    _ON_IMPORT_LABELS = (
        ("ask", "Hỏi tôi mỗi lần thêm file/thư mục"),
        ("always", "Luôn tự động phân loại tài liệu mới"),
        ("never", "Không phân loại (chỉ dùng nút trong Công cụ)"),
    )

    def _build_smart_classify_tab(self, config) -> QWidget:
        page = SettingsPage("Phân loại", "MewBook đoán thể loại của sách và gắn hashtag. File sách không bị đụng tới.", self)
        info = QLabel(self._smart_classify_model_text(), page)
        info.setWordWrap(True)
        info.setTextFormat(Qt.PlainText)
        page.add_row("Mô hình phân loại", "Bộ máy dùng để đoán thể loại.", info)

        self.smart_on_import_combo = QComboBox(page)
        for key, label in self._ON_IMPORT_LABELS:
            self.smart_on_import_combo.addItem(label, key)
        index = self.smart_on_import_combo.findData(config.smart_classify_on_import)
        self.smart_on_import_combo.setCurrentIndex(max(index, 0))
        page.add_row("Khi thêm sách mới", "Có tự phân loại sau khi nhập hay không.", self.smart_on_import_combo)

        self.smart_max_words_spin = QSpinBox(page)
        self.smart_max_words_spin.setRange(2000, 5000)
        self.smart_max_words_spin.setSingleStep(500)
        self.smart_max_words_spin.setSuffix(" từ")
        self.smart_max_words_spin.setValue(min(max(config.smart_classify_max_words, 2000), 5000))
        page.add_row("Số từ đọc ở đầu mỗi sách", "Tối đa. Sách ngắn hơn thì đọc hết. Nhiều từ hơn chính xác hơn một chút nhưng chậm hơn.", self.smart_max_words_spin)

        self.smart_workers_spin = QSpinBox(page)
        self.smart_workers_spin.setRange(1, 4)
        self.smart_workers_spin.setValue(min(max(config.smart_classify_max_workers, 1), 4))
        page.add_row("Số tiến trình nền tối đa",
                     "Chạy ở mức ưu tiên thấp; thư viện nhỏ luôn chỉ dùng một tiến trình.", self.smart_workers_spin)

        for label, description in (
            ("Nguồn dùng để phân loại", "Tên file, thông tin trong file, mục lục, vài trang đầu, AI."),
            ("Mức chắc chắn tối thiểu", "Dưới mức này, sách được để lại cho bạn tự chọn."),
            ("Hashtag ưu tiên", "Danh sách hashtag MewBook nên chọn trước."),
        ):
            page.add_row(label, description, QPushButton("Thiết lập…", page), soon=True)
        return page

    def _smart_classify_model_text(self) -> str:
        path = resolve_model_path(self.context.config.app_data_dir)
        if path is None:
            return "Chưa có mô hình phân loại. Hãy tạo mô hình từ thư viện của bạn bằng công cụ huấn luyện (xem hướng dẫn của dự án)."
        meta = read_model_meta(path) or {}
        trained_at = str(meta.get("trained_at", ""))[:10]
        docs = meta.get("trained_docs")
        parts = [f"Mô hình: {path.name}"]
        if trained_at:
            parts.append(f"huấn luyện {trained_at}")
        if docs:
            parts.append(f"{int(docs):,} sách")
        return " · ".join(parts)

    def _build_ai_tab(self, config) -> QWidget:
        page = SettingsPage(
            "AI Tóm tắt",
            "AI viết phần giới thiệu, ý chính hoặc nhận xét về một cuốn sách. Mọi yêu cầu đi thẳng từ máy bạn tới nhà cung cấp bạn chọn.",
            self)
        self.ai_provider_combo = QComboBox(page)
        self.ai_provider_combo.addItem("(Chưa cấu hình)", None)
        for provider_id in AI_PROVIDER_CHOICES:
            self.ai_provider_combo.addItem(AI_PROVIDER_DISPLAY_NAMES[provider_id], provider_id)
        if config.ai_provider:
            index = self.ai_provider_combo.findData(config.ai_provider)
            if index >= 0:
                self.ai_provider_combo.setCurrentIndex(index)
        self.ai_provider_combo.currentIndexChanged.connect(self._update_ai_provider_guide)
        page.add_row("Nhà cung cấp AI", "Có nơi cho dùng miễn phí; Ollama chạy ngay trên máy bạn, không cần khóa.", self.ai_provider_combo)

        self.ai_api_key_edit = QLineEdit(config.ai_api_key or "", page)
        self.ai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ai_api_key_edit.setPlaceholderText("Dán API key vào đây...")
        show_key_button = QToolButton(page)
        show_key_button.setIcon(line_icon("eye", theme_manager().token("ink2"), 14))
        show_key_button.setCheckable(True)
        show_key_button.setToolTip("Hiện/ẩn API key")
        show_key_button.toggled.connect(
            lambda checked: self.ai_api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        key_box = QWidget(page)
        key_row = QHBoxLayout(key_box)
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.addWidget(self.ai_api_key_edit)
        key_row.addWidget(show_key_button)
        page.add_row("Khóa API", "Chuỗi ký tự giống mật khẩu do nhà cung cấp cấp cho bạn.", key_box,
                     extra=self._build_key_security_note(page))

        # Optional model override -- providers retire/rename models every few months, so this lets the user move on
        # without an app update.
        self.ai_model_edit = QLineEdit(config.ai_model or "", page)
        self.ai_model_edit.setToolTip("Để trống để dùng mẫu AI mặc định của nhà cung cấp.")
        page.add_row("Mẫu AI", "Để trống nếu không rõ.", self.ai_model_edit)

        self.ai_base_url_edit = QLineEdit(config.ai_base_url or "", page)
        self.ai_base_url_edit.setPlaceholderText(OLLAMA_DEFAULT_BASE_URL)
        self._ai_base_url_row = page.add_row("Địa chỉ Ollama", "Chỉ cần khi dùng Ollama trên máy khác.", self.ai_base_url_edit)

        self.ai_summary_style_combo = self._summary_combo(page, {k: v[0] for k, v in SUMMARY_STYLES.items()}, config.ai_summary_style)
        self.ai_summary_length_combo = self._summary_combo(page, {k: v[0] for k, v in SUMMARY_LENGTHS.items()}, config.ai_summary_length)
        self.ai_summary_language_combo = self._summary_combo(page, {k: v[0] for k, v in SUMMARY_LANGUAGES.items()}, config.ai_summary_language)
        page.add_row("Mặc định khi tóm tắt", "Kiểu, độ dài và ngôn ngữ; đổi lại được ở từng lần tóm tắt.",
                     self._pair(self.ai_summary_style_combo, self.ai_summary_length_combo, self.ai_summary_language_combo))

        test_box = QWidget(page)
        test_layout = QVBoxLayout(test_box)
        test_layout.setContentsMargins(0, 0, 0, 0)
        self.test_connection_button = QPushButton("Kiểm tra kết nối", test_box)
        self.test_connection_button.clicked.connect(self._on_test_connection)
        test_layout.addWidget(self.test_connection_button, 0, Qt.AlignLeft)
        self.connection_status_label = QLabel(test_box)
        self.connection_status_label.setWordWrap(True)
        test_layout.addWidget(self.connection_status_label)
        page.add_row("Thử kết nối", "Kiểm tra nhanh khóa và nhà cung cấp đã đúng chưa.", test_box)

        # Where to get a key for whichever provider is currently selected, updated live as the dropdown changes.
        self.ai_provider_guide_label = QLabel(page)
        self.ai_provider_guide_label.setWordWrap(True)
        self.ai_provider_guide_label.setOpenExternalLinks(True)
        # Static how-to-use text -- the "hướng dẫn" role (docs/UI_TEXT_ROLES.md). Not a HintLabel: it carries
        # clickable links that widget doesn't support yet.
        self.ai_provider_guide_label.setStyleSheet(f"{role_css(ROLE_HINT, theme_manager().token('ink2'))} background: transparent;")
        page.add_row("Cách lấy khóa", "Từng bước, theo nhà cung cấp bạn chọn ở trên.", self.ai_provider_guide_label)
        self._update_ai_provider_guide()
        return page

    @staticmethod
    def _summary_combo(parent: QWidget, choices: dict[str, str], current: str) -> QComboBox:
        combo = QComboBox(parent)
        for key, label in choices.items():
            combo.addItem(label, key)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        return combo

    def _build_key_security_note(self, parent: QWidget) -> QLabel:
        """Reused under every API key field in this window (AI Tóm tắt, Google Images) -- see core.secret_store,
        which is what actually makes this true rather than just a claim in the UI."""
        note = QLabel(
            "Khóa của bạn được mã hóa và chỉ lưu trên máy tính này. Chúng tôi không thu thập thông tin này.", parent)
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme_manager().token('ink3')}; font-size: 13px;")
        return note

    def _build_cover_search_tab(self, config) -> QWidget:
        """Which sources "Đổi ảnh bìa" may ask, and the optional Google Custom Search (Image) setup -- see
        application/cover_search.py. Without a key here, cover search still works via the free sources."""
        page = SettingsPage(
            "Ảnh bìa", "Chọn nơi MewBook được phép tìm ảnh bìa. Tên sách và tác giả sẽ được gửi tới nơi bạn bật.", self)

        # Which keyless sources may be contacted at all (search text goes to them); see docs/legal/DATA_SOURCES.md.
        sources = QWidget(page)
        sources_layout = QVBoxLayout(sources)
        sources_layout.setContentsMargins(0, 0, 0, 0)
        self._cover_source_checkboxes: dict[str, QCheckBox] = {}
        disabled_sources = set(config.disabled_cover_sources)
        for name, hint in (
            (SOURCE_OPEN_LIBRARY, ""),
            (SOURCE_GOOGLE_BOOKS, ""),
            (SOURCE_APPLE_BOOKS, " (tắt sẵn: điều khoản của Apple chỉ cho dùng ảnh để quảng bá cửa hàng)"),
            (SOURCE_TIKI, " (tắt sẵn: API nội bộ của cửa hàng, chưa có điều khoản cho phép dùng)"),
        ):
            checkbox = QCheckBox(f"{name}{hint}", sources)
            checkbox.setChecked(name not in disabled_sources)
            self._cover_source_checkboxes[name] = checkbox
            sources_layout.addWidget(checkbox)
        page.add_row("Nguồn được phép tra cứu", "Gửi tên sách/tác giả ra ngoài để tìm ảnh.", sources)

        self.cover_match_spin = QSpinBox(page)
        self.cover_match_spin.setRange(MIN_MATCH_PERCENT, MAX_MATCH_PERCENT)
        self.cover_match_spin.setSuffix(" %")
        self.cover_match_spin.setValue(max(MIN_MATCH_PERCENT, min(MAX_MATCH_PERCENT, int(config.cover_match_percent))))
        page.add_row("Độ khớp tối thiểu", "Thấp hơn: ra nhiều kết quả hơn, có thể kém liên quan. Cao hơn: ít kết quả, sát hơn. "
                     "Mỗi kết quả vẫn hiện % khớp của nó.", self.cover_match_spin)

        self.google_image_api_key_edit = QLineEdit(config.google_image_api_key or "", page)
        self.google_image_api_key_edit.setEchoMode(QLineEdit.Password)
        self.google_image_api_key_edit.setPlaceholderText("Dán API key vào đây...")
        show_button = QToolButton(page)
        show_button.setIcon(line_icon("eye", theme_manager().token("ink2"), 14))
        show_button.setCheckable(True)
        show_button.setToolTip("Hiện/ẩn API key")
        show_button.toggled.connect(
            lambda checked: self.google_image_api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        key_box = QWidget(page)
        key_row = QHBoxLayout(key_box)
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.addWidget(self.google_image_api_key_edit)
        key_row.addWidget(show_button)
        self.google_image_cx_edit = QLineEdit(config.google_image_search_cx or "", page)
        self.google_image_cx_edit.setPlaceholderText("Dán Search Engine ID vào đây...")
        google_box = QWidget(page)
        google_layout = QVBoxLayout(google_box)
        google_layout.setContentsMargins(0, 0, 0, 0)
        google_layout.addWidget(key_box)
        google_layout.addWidget(self.google_image_cx_edit)
        google_layout.addWidget(self._build_key_security_note(google_box))
        self.cover_test_button = QPushButton("Kiểm tra kết nối", google_box)
        self.cover_test_button.clicked.connect(self._on_test_cover_connection)
        google_layout.addWidget(self.cover_test_button, 0, Qt.AlignLeft)
        self.cover_test_status_label = QLabel(google_box)
        self.cover_test_status_label.setWordWrap(True)
        google_layout.addWidget(self.cover_test_status_label)
        page.add_row("Google Images (tùy chọn)",
                     "Tìm trên toàn web. Google đã ngừng nhận khách hàng mới cho dịch vụ này, nên chỉ dùng được với tài khoản có sẵn. ○ Chưa thiết lập.",
                     google_box)

        page.add_row("Tự tìm bìa cho sách mới", "Chỉ thay khi khớp từ 90% trở lên.", QCheckBox("Bật", page), soon=True)

        guide = QLabel(_COVER_SEARCH_SETUP_GUIDE, page)
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.RichText)
        guide.setOpenExternalLinks(True)
        guide.setStyleSheet(f"color: {theme_manager().token('ink2')};")
        page.add_row("Cách lấy khóa Google", "Từng bước; mất khoảng 5 phút.", guide)
        return page

    def _build_reviews_tab(self, config) -> QWidget:
        page = SettingsPage("Đánh giá cộng đồng", "Xem và viết nhận xét về sách cùng những người dùng MewBook khác.", self)
        self.community_reviews_check = QCheckBox("Bật đánh giá cộng đồng", page)
        self.community_reviews_check.setChecked(config.community_reviews_enabled)
        page.add_row("Đánh giá cộng đồng", "Tắt thì MewBook không lấy và không gửi gì cho tính năng này. Mặc định là bật.", self.community_reviews_check)
        # The connection is the app's own and always defined; only the person's switch decides whether it is used.
        self.reviews_server_label = QLabel(page)
        self.reviews_server_label.setWordWrap(True)
        self._show_reviews_server(config)
        self.community_reviews_check.toggled.connect(lambda _on: self._show_reviews_server(self._config_with_switch()))
        page.add_row("Máy chủ", "Kết nối có sẵn trong MewBook; bạn không cần nhập gì.", self.reviews_server_label)
        self.reviewer_nickname_edit = QLineEdit(config.reviewer_nickname or "", page)
        self.reviewer_nickname_edit.setPlaceholderText("Ví dụ: Mèo Mực")
        page.add_row("Nick name", "Tên hiện cạnh nhận xét của bạn. Không cần thật.", self.reviewer_nickname_edit)
        page.add_block(add_note_box(
            page,
            "<b>Chỉ gửi</b> khi bạn đăng bài: nick name, số sao, nhận xét và mã của cuốn sách.<br>"
            "<b>Không gửi:</b> file sách, đường dẫn, tên máy, hay danh sách sách của bạn.", "ok"))
        page.add_row("Hiện điểm cộng đồng trên bìa", "Một huy hiệu nhỏ ở góc bìa sách.", QCheckBox("Bật", page), soon=True)
        return page

    def _config_with_switch(self):
        """The saved config with the checkbox as it is now (before "Đóng" saves it), for the status line."""
        import dataclasses

        return dataclasses.replace(self.context.config.config, community_reviews_enabled=self.community_reviews_check.isChecked())

    def _show_reviews_server(self, config) -> None:
        state = review_state(config)
        by_hand = bool(config.supabase_url and config.supabase_anon_key)
        self.reviews_server_label.setText({
            STATE_REVIEWS_ON: "Đang dùng máy chủ của MewBook" + (" (máy chủ riêng do bạn đặt trong settings.json)" if by_hand else "") + ".",
            STATE_REVIEWS_OFF: "Đã tắt: MewBook không kết nối tới máy chủ đánh giá.",
        }.get(state, "Bản này chưa có máy chủ đánh giá cộng đồng, nên tính năng chưa chạy được dù đã bật."))

    def _add_donation(self, page: SettingsPage) -> SettingsPage:
        """The update page also carries the donation block: the QR code and the mascot with a coffee."""
        qr = QLabel(page)
        qr.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(donate_qr_path()))
        if pixmap.isNull():
            qr.setText("(Chưa có mã QR)")
        else:
            qr.setPixmap(pixmap.scaled(190, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        mascot = QLabel(page)
        mascot_image = mascot_pixmap("logo", 150, self.devicePixelRatioF())
        if mascot_image is not None:
            mascot.setPixmap(mascot_image)
        box = QWidget(page)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(qr)
        row.addWidget(mascot)
        row.addStretch(1)
        page.add_row("Ủng hộ tác giả", "Hoàn toàn tự nguyện, không phải điều kiện để dùng ứng dụng.", box)
        return page

    def _update_ai_provider_guide(self) -> None:
        provider_id = self.ai_provider_combo.currentData()
        self.ai_provider_guide_label.setTextFormat(Qt.RichText)
        self.ai_provider_guide_label.setText(provider_guide_html(provider_id))
        # Built in field order, so the key/model widgets may not exist yet
        # on the very first call from _build_ai_tab.
        if hasattr(self, "_ai_base_url_row"):
            default_model = DEFAULT_MODELS.get(provider_id, "")
            self.ai_model_edit.setPlaceholderText(f"Mặc định: {default_model}" if default_model else "")
            is_local = provider_id == "ollama"
            self._ai_base_url_row.setVisible(is_local)
            self.ai_api_key_edit.setPlaceholderText(
                "Không cần API key" if not provider_requires_key(provider_id) else "Dán API key vào đây..."
            )

    def _on_test_connection(self) -> None:
        provider = self.ai_provider_combo.currentData()
        api_key = self.ai_api_key_edit.text().strip()
        if not provider:
            self.connection_status_label.setText("Vui lòng chọn một nhà cung cấp AI trước.")
            return

        self.test_connection_button.setEnabled(False)
        self.test_connection_button.setText("Đang kiểm tra...")
        self.connection_status_label.setText("Đang kết nối, vui lòng đợi...")
        self._tested_provider = provider

        model = self.ai_model_edit.text().strip() or None
        base_url = self.ai_base_url_edit.text().strip() or None

        relay = self._relay

        def worker() -> None:
            try:
                test_connection(provider, api_key, model=model, base_url=base_url)
                post(relay, "connection_test_finished", True, "Kết nối thành công!")
            except AISummaryError as exc:
                post(relay, "connection_test_finished", False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connection_test_finished(self, success: bool, message: str) -> None:
        if getattr(self, "_tested_provider", None) == "ollama":
            # The status bar shows the local AI as connected only after a real check, so tell it the result now.
            self.context.event_bus.publish(AiConnectionChangedEvent(connected=success))
        self.test_connection_button.setEnabled(True)
        self.test_connection_button.setText("Kiểm tra kết nối")
        self.connection_status_label.setText(message)
        # The pass/fail check the app just ran -- the "kết quả" role. Uses the theme's own ok/err tokens (never a
        # hardcoded CSS color name) so it stays readable on every theme, dark ones included.
        tm = theme_manager()
        self.connection_status_label.setStyleSheet(role_css(ROLE_RESULT, tm.token("ok" if success else "err")))

    def _on_test_cover_connection(self) -> None:
        api_key = self.google_image_api_key_edit.text().strip()
        cx = self.google_image_cx_edit.text().strip()

        self.cover_test_button.setEnabled(False)
        self.cover_test_button.setText("Đang kiểm tra...")
        self.cover_test_status_label.setText("Đang kết nối tới Google, vui lòng đợi...")

        relay = self._relay

        def worker() -> None:
            try:
                found = test_cover_connection(api_key, cx)
                if found:
                    post(relay, "cover_test_finished", True, "Kết nối thành công! Google đã trả về kết quả ảnh.")
                else:
                    # The call itself worked (key + cx are valid), there just
                    # weren't any images for the probe query -- almost always
                    # means the search engine is restricted to specific sites
                    # instead of the whole web.
                    post(
                        relay, "cover_test_finished", False,
                        "Kết nối được nhưng không có ảnh nào trả về. Kiểm tra lại công cụ tìm kiếm "
                        "đã bật \"Search the entire web\" và \"Image search\" chưa (bước 3-4, Phần 1).",
                    )
            except CoverSearchError as exc:
                post(relay, "cover_test_finished", False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_cover_test_finished(self, success: bool, message: str) -> None:
        self.cover_test_button.setEnabled(True)
        self.cover_test_button.setText("Kiểm tra kết nối")
        self.cover_test_status_label.setText(message)
        # Same "kết quả" role + theme token as the AI connection test above.
        tm = theme_manager()
        self.cover_test_status_label.setStyleSheet(role_css(ROLE_RESULT, tm.token("ok" if success else "err")))

    def _on_add_folder(self) -> None:
        start_dir = self.context.config.config.last_used_directory or ""
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục để theo dõi", start_dir)
        if folder:
            self.context.config.config.last_used_directory = folder
            if not self.folder_list.findItems(folder, Qt.MatchExactly):
                self.folder_list.addItem(folder)
                self._fit_folder_list()

    def _on_remove_folder(self) -> None:
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))
        self._fit_folder_list()

    def _fit_folder_list(self) -> None:
        """The watched-folders box is as tall as its folders (at least one row, at most FOLDER_LIST_MAX_ROWS);
        beyond that it scrolls, so a long list can never push the other settings off the screen."""
        rows = min(max(self.folder_list.count(), 1), self.FOLDER_LIST_MAX_ROWS)
        row_height = self.folder_list.fontMetrics().height() + 4
        if self.folder_list.count():
            row_height = self.folder_list.sizeHintForRow(0)
            first = self.folder_list.visualItemRect(self.folder_list.item(0))  # exact once the list has been laid out
            if first.height() > row_height:
                row_height = first.height()
        self.folder_list.setFixedHeight(rows * row_height + 2 * self.folder_list.frameWidth())
        self.folder_list.doItemsLayout()  # the scroll bar follows the new height at once, not one event later

    def _on_choose_ereader_folder(self) -> None:
        start_dir = self._ereader_folder_path or self.context.config.config.last_used_directory or ""
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục sách trên máy đọc sách", start_dir)
        if folder:
            self._ereader_folder_path = folder
            self.ereader_folder_edit.setText(folder)

    def _on_theme_preview_changed(self, index: int) -> None:
        """Shows the picked theme's own font in every font picker the user
        hasn't set by hand -- programmatically, so it doesn't count as a
        choice of theirs."""
        family = resolve_font_family(colors_for(str(self.theme_combo.itemData(index))))
        for key, combo in (("app", self.font_combo), ("content", self.content_font_combo)):
            if self._font_touched[key]:
                continue
            combo.blockSignals(True)
            combo.setCurrentFont(QFont(family))
            combo.blockSignals(False)

    def _on_save(self) -> None:
        """"Đóng": one last save (nothing is lost if the timer has not fired yet), then close."""
        self._autosave_timer.stop()
        self._apply_settings()
        self.accept()

    def _apply_settings(self) -> None:
        config = self.context.config.config

        new_extensions = [ext for ext, box in self._extension_checkboxes.items() if box.isChecked()]
        config.allowed_extensions = new_extensions

        new_folders = [self.folder_list.item(i).text() for i in range(self.folder_list.count())]
        removed_folders = set(config.watch_folders) - set(new_folders)
        added_folders = set(new_folders) - set(config.watch_folders)
        config.watch_folders = new_folders

        config.backup_keep = self.backup_panel.keep()
        config.backup_before_change = self.backup_panel.before_change()
        config.update_check_enabled = self.update_panel.is_enabled()
        self.privacy_panel.apply()  # the error-report mode is kept by the reporter (it also records the consent wording)
        config.ereader_folder_path = self._ereader_folder_path or None
        config.metadata_write_to_file_default = self.metadata_write_check.isChecked()

        if self.backdrop_check.isChecked() != config.show_backdrop:
            self.appearance_changed = True
            config.show_backdrop = self.backdrop_check.isChecked()

        new_theme = self.theme_combo.currentData()
        new_layout = str(self.layout_combo.currentData())
        theme_changed = new_theme != config.theme
        if theme_changed or new_layout != config.layout:
            self.appearance_changed = True
            config.theme = new_theme
            config.layout = new_layout
        self._theme_memory[new_layout] = str(new_theme)
        config.theme_by_layout = dict(self._theme_memory)  # so switching layout and back finds each choice again

        # A font the user picked by hand wins; otherwise a theme change must
        # drop any font saved earlier, or the old typeface would stick to the
        # new theme and only the colors would change.
        new_font_family = self.font_combo.currentFont().family()
        if self._font_touched["app"] and new_font_family != self._initial_font_family:
            self.appearance_changed = True
            config.font_family = new_font_family
        elif theme_changed and config.font_family:
            config.font_family = None

        new_font_size = self.font_size_spin.value()
        if new_font_size != config.font_size:
            self.appearance_changed = True
            config.font_size = new_font_size

        new_content_font_family = self.content_font_combo.currentFont().family()
        if self._font_touched["content"] and new_content_font_family != self._initial_content_font_family:
            self.appearance_changed = True
            config.content_font_family = new_content_font_family
        elif theme_changed and config.content_font_family:
            config.content_font_family = None

        new_content_font_size = self.content_font_size_spin.value()
        if new_content_font_size != config.content_font_size:
            self.appearance_changed = True
            config.content_font_size = new_content_font_size

        if self._content_text_color != config.content_text_color:
            self.appearance_changed = True
            config.content_text_color = self._content_text_color

        new_worker_count = self.worker_spin.value()
        if new_worker_count != config.worker_thread_count:
            config.worker_thread_count = new_worker_count
            if self.import_manager:
                self.import_manager.restart(new_worker_count)

        new_debounce = self.debounce_spin.value()
        if new_debounce != config.watch_debounce_seconds:
            config.watch_debounce_seconds = new_debounce
            if self.watcher:
                self.watcher.set_debounce_seconds(new_debounce)

        config.smart_classify_on_import = self.smart_on_import_combo.currentData()
        config.smart_classify_max_words = self.smart_max_words_spin.value()
        config.smart_classify_max_workers = self.smart_workers_spin.value()

        config.ai_provider = self.ai_provider_combo.currentData()
        config.ai_api_key = self.ai_api_key_edit.text().strip() or None
        config.ai_model = self.ai_model_edit.text().strip() or None
        config.ai_base_url = self.ai_base_url_edit.text().strip().rstrip("/") or None

        config.cover_match_percent = self.cover_match_spin.value()
        config.google_image_api_key = self.google_image_api_key_edit.text().strip() or None
        config.google_image_search_cx = self.google_image_cx_edit.text().strip() or None
        # Keep entries this tab has no checkbox for (e.g. a hand-added "Google Images").
        shown = set(self._cover_source_checkboxes)
        config.disabled_cover_sources = [name for name in config.disabled_cover_sources if name not in shown] + [
            name for name, box in self._cover_source_checkboxes.items() if not box.isChecked()
        ]

        # The community-review connection has no settings tab any more: whatever is already saved is left as it is.

        config.ai_summary_style = self.ai_summary_style_combo.currentData()
        config.ai_summary_length = self.ai_summary_length_combo.currentData()
        config.ai_summary_language = self.ai_summary_language_combo.currentData()
        config.community_reviews_enabled = self.community_reviews_check.isChecked()
        config.reviewer_nickname = self.reviewer_nickname_edit.text().strip()
        old_page_size = config.page_size
        config.page_size = self.page_size_combo.currentData()
        config.cover_cache_mb = self.cover_cache_combo.currentData()
        config.max_reader_windows = self.reader_windows_combo.currentData()
        config.content_search_pages = self.content_pages_combo.currentData()

        self.context.config.save()
        if config.page_size != old_page_size:
            self.context.event_bus.publish(LibraryUpdatedEvent())  # the list re-cuts its pages

        if self.watcher:
            for folder in removed_folders:
                self.watcher.remove_folder(folder)
            for folder in added_folders:
                self.watcher.add_folder(folder)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.config.add_watch_folder(r"D:\Ebooks")

        app = QApplication(sys.argv)
        apply_theme(app, "light")
        dialog = SettingsDialog(context)
        dialog.exec()
        print("allowed_extensions:", context.config.config.allowed_extensions)
        print("watch_folders:", context.config.config.watch_folders)
