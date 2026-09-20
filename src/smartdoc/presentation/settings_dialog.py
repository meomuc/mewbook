"""TDD-015 (upgrade): Settings Dialog.

Tabs: File types + watch folders, Giao diện (Theme + the app's own chrome
font), Font nội dung (the separate content font/size/color -- see
AppConfig's docstring on why these two are kept apart), Performance
(worker count + scan timing), AI Tóm tắt. The original spec's Tab 4
(Cloud: Google Drive connect/disconnect) is not built here -- it depends
on TDD-016/TDD-019 (Milestone F), which aren't implemented yet, and a tab
full of buttons that do nothing would be worse than no tab.

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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.ai_summary import (
    DEFAULT_MODELS,
    OLLAMA_DEFAULT_BASE_URL,
    PROVIDER_GUIDES,
    AISummaryError,
    provider_requires_key,
    test_connection,
)
from smartdoc.application.cloud_reviews import CloudReviewError, SupabaseReviewSync, upgrade_sql
from smartdoc.application.cover_search import (
    SOURCE_APPLE_BOOKS,
    SOURCE_GOOGLE_BOOKS,
    SOURCE_OPEN_LIBRARY,
    SOURCE_TIKI,
    CoverSearchError,
)
from smartdoc.application.cover_search import test_connection as test_cover_connection
from smartdoc.core.config import AI_PROVIDER_CHOICES, AI_PROVIDER_DISPLAY_NAMES, KNOWN_EXTENSIONS, THEME_CHOICES
from smartdoc.domain.text_classifier import read_model_meta, resolve_model_path
from smartdoc.presentation.backup_panel import BackupPanel
from smartdoc.presentation.theme import THEMES, current_colors, resolve_font_family
from smartdoc.presentation.privacy_panel import PrivacyPanel
from smartdoc.presentation.update_panel import UpdatePanel
from smartdoc.presentation.theme_effects import theme_preview_pixmap

# Written out step by step rather than as a one-line "get a key here"
# pointer: this is the one setup in the app that spans two *different*
# Google consoles (Programmable Search Engine for the cx, Google Cloud for
# the API key), and getting either half subtly wrong fails in ways that
# don't obviously point back at the step that caused them.
_COVER_SEARCH_SETUP_GUIDE = """
<b>Hướng dẫn lấy API key &amp; Search Engine ID (miễn phí, ~5 phút)</b>

<p><b>Phần 1 — Tạo công cụ tìm kiếm để lấy Search Engine ID (cx):</b></p>
<ol>
<li>Mở <a href="https://programmablesearchengine.google.com/controlpanel/create">programmablesearchengine.google.com/controlpanel/create</a> và đăng nhập bằng tài khoản Google.</li>
<li>Ở ô <i>"Name"</i>: đặt tên bất kỳ, ví dụ <i>MewBook Cover Search</i>.</li>
<li>Chọn <b>"Search the entire web"</b> (tìm toàn bộ web) — không chọn "Search specific sites", nếu không sẽ gần như không tìm được bìa nào.</li>
<li>Bật công tắc <b>"Image search"</b> (tìm kiếm hình ảnh). <b>Bắt buộc</b> — nếu tắt, ứng dụng sẽ báo lỗi 400.</li>
<li>Bấm <b>"Create"</b>.</li>
<li>Ở màn hình tiếp theo bấm <b>"Customize"</b>, tìm dòng <b>"Search engine ID"</b> và sao chép chuỗi đó → dán vào ô <b>Search Engine ID</b> ở trên.</li>
</ol>

<p><b>Phần 2 — Lấy API key:</b></p>
<ol>
<li>Mở <a href="https://console.cloud.google.com/apis/library/customsearch.googleapis.com">console.cloud.google.com/apis/library/customsearch.googleapis.com</a> (cùng tài khoản Google).</li>
<li>Nếu chưa có project: bấm <b>"Create project"</b> ở góc trên, đặt tên bất kỳ, rồi chọn project vừa tạo.</li>
<li>Bấm nút <b>"Enable"</b> để bật <b>Custom Search API</b> cho project đó. <b>Bắt buộc</b> — nếu bỏ qua, ứng dụng sẽ báo lỗi 403.</li>
<li>Vào <a href="https://console.cloud.google.com/apis/credentials">console.cloud.google.com/apis/credentials</a> → bấm <b>"+ Create credentials"</b> → chọn <b>"API key"</b>.</li>
<li>Sao chép key vừa hiện ra → dán vào ô <b>API key</b> ở trên.</li>
</ol>

<p><b>Phần 3 — Kiểm tra:</b> bấm nút <b>"🔌 Kiểm tra kết nối"</b> ở trên. Nếu báo thành công là xong; nếu báo lỗi, thông báo sẽ chỉ rõ bước nào ở trên cần xem lại.</p>

<p><i>Hạn mức miễn phí: 100 lượt tìm kiếm/ngày. Hết hạn mức, tính năng tìm ảnh bìa vẫn chạy bình thường bằng Open Library + Google Books.</i></p>
"""


_CLOUD_REVIEW_SETUP_GUIDE = """
<b>Hướng dẫn thiết lập Supabase cho đánh giá cộng đồng (miễn phí, ~5 phút)</b>

<p><b>Phần 1 — Tạo project và bảng đánh giá:</b></p>
<ol>
<li>Mở <a href="https://supabase.com/dashboard">supabase.com/dashboard</a>, đăng nhập và bấm <b>"New project"</b> (chọn gói Free).</li>
<li>Vào mục <b>SQL Editor</b> ở menu bên trái → bấm <b>"New query"</b>, dán đoạn sau rồi bấm <b>Run</b>:</li>
</ol>
<pre>create table reviews (
  id bigint generated always as identity primary key,
  doc_id text not null,
  nickname text not null default 'Ẩn danh',
  rating int2 not null check (rating between 1 and 5),
  comment text not null default '',
  created_at timestamptz not null default now()
);

alter table reviews enable row level security;
create policy "Allow public read" on reviews for select using (true);
create policy "Allow public insert" on reviews for insert with check (true);</pre>

<p><b>Phần 2 — Tạo view cho sắp xếp "Được đánh giá cao nhất":</b><br/>
Bước này <b>bắt buộc</b> nếu bạn muốn dùng sắp xếp theo điểm đánh giá. Thiếu nó, ứng dụng sẽ báo lỗi
<i>"Could not find the table 'public.review_stats'"</i>. Vẫn trong SQL Editor, chạy tiếp:</p>
<pre>create view review_stats as
  select doc_id, avg(rating)::float8 as avg_rating, count(*) as review_count
  from reviews
  group by doc_id;

grant select on review_stats to anon, authenticated;</pre>

<p><b>Phần 2b — Định danh người dùng &amp; nick name duy nhất (bắt buộc từ phiên bản 1.0.0):</b><br/>
Bấm nút <b>"📋 Sao chép SQL nâng cấp"</b> ở trên, dán vào SQL Editor và bấm <b>Run</b>. Đoạn SQL này
thêm bảng <i>reviewers</i> (mỗi nick name thuộc về một người dùng), cột <i>user_hash</i> và hàm
<i>submit_review</i> -- từ đây mọi bài đánh giá được gửi qua hàm này để chống giả mạo; quyền ghi
trực tiếp của Phần 1 sẽ được thu hồi. Chạy lại nhiều lần cũng an toàn.</p>

<p><b>Phần 3 — Lấy URL và key:</b></p>
<ol>
<li>Vào <b>Project Settings</b> (biểu tượng bánh răng) → <b>API Keys</b>.</li>
<li>Sao chép <b>Project URL</b> (dạng <i>https://xxxxx.supabase.co</i>) → dán vào ô <b>Supabase URL</b> ở trên.</li>
<li>Sao chép key <b>"anon" / "public"</b> → dán vào ô <b>Anon key</b> ở trên.
<br/><b>Lưu ý:</b> tuyệt đối không dùng key <i>"service_role"</i> — key đó bỏ qua mọi lớp bảo vệ của database.
Key "anon" được thiết kế để nhúng công khai trong ứng dụng, quyền truy cập do các chính sách RLS ở Phần 1 kiểm soát.</li>
</ol>

<p><b>Phần 4 — Kiểm tra:</b> bấm <b>"🔌 Kiểm tra kết nối"</b> ở trên. Nút này kiểm tra riêng bảng
<i>reviews</i>, view <i>review_stats</i> và bảng <i>reviewers</i>, nên nếu thiếu bước nào thông báo sẽ chỉ rõ đúng bước đó.</p>
"""


class SettingsDialog(QDialog):
    connection_test_finished = Signal(bool, str)  # (success, message)
    cover_test_finished = Signal(bool, str)  # (success, message)
    supabase_test_finished = Signal(bool, str)  # (success, message)

    def __init__(self, context, parent=None, watcher=None, import_manager=None, initial_tab: str | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(480)
        self.setMaximumSize(760, 720)  # tabbed content shouldn't be able to grow this into a huge window

        config = context.config.config
        self.appearance_changed = False  # theme/font: see module docstring

        tabs = QTabWidget(self)
        tabs.addTab(self._build_file_tab(config), "📁 Quản lý File")
        tabs.addTab(self._build_theme_tab(config), "🎨 Giao diện")
        tabs.addTab(self._build_performance_tab(config), "⚡ Hiệu năng")
        tabs.addTab(self._build_smart_classify_tab(config), "✨ Phân loại")
        tabs.addTab(self._build_ai_tab(config), "🤖 AI Tóm tắt")
        tabs.addTab(self._build_cover_search_tab(config), "🖼️ Ảnh bìa")
        tabs.addTab(self._build_cloud_review_tab(config), "☁️ Đánh giá cộng đồng")
        self.backup_panel = BackupPanel(context, self)
        tabs.addTab(self.backup_panel, "💾 Sao lưu")
        self.update_panel = UpdatePanel(context, self)
        tabs.addTab(self.update_panel, "⬆️ Cập nhật")
        self.privacy_panel = PrivacyPanel(context, self)
        tabs.addTab(self.privacy_panel, "🔒 Quyền riêng tư và báo lỗi")
        if initial_tab == "backup":
            tabs.setCurrentWidget(self.backup_panel)
        elif initial_tab == "privacy":
            tabs.setCurrentWidget(self.privacy_panel)

        self.connection_test_finished.connect(self._on_connection_test_finished)
        self.cover_test_finished.connect(self._on_cover_test_finished)
        self.supabase_test_finished.connect(self._on_supabase_test_finished)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _build_file_tab(self, config) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Định dạng quét tự động:"))
        self._extension_checkboxes: dict[str, QCheckBox] = {}
        for extension in KNOWN_EXTENSIONS:
            checkbox = QCheckBox(extension.upper())
            checkbox.setChecked(extension in config.allowed_extensions)
            self._extension_checkboxes[extension] = checkbox
            layout.addWidget(checkbox)

        layout.addWidget(QLabel("Thư mục đang theo dõi:"))
        self.folder_list = QListWidget(tab)
        self.folder_list.addItems(config.watch_folders)
        layout.addWidget(self.folder_list, stretch=1)

        folder_buttons = QHBoxLayout()
        add_button = QPushButton("Thêm thư mục...")
        add_button.clicked.connect(self._on_add_folder)
        remove_button = QPushButton("Xóa thư mục đã chọn")
        remove_button.clicked.connect(self._on_remove_folder)
        folder_buttons.addWidget(add_button)
        folder_buttons.addWidget(remove_button)
        layout.addLayout(folder_buttons)

        layout.addWidget(QLabel("📱 Thư mục sách trên máy đọc sách (USB):"))
        self._ereader_folder_path = config.ereader_folder_path
        ereader_row = QHBoxLayout()
        self.ereader_folder_edit = QLineEdit(tab)
        self.ereader_folder_edit.setText(self._ereader_folder_path or "")
        self.ereader_folder_edit.setReadOnly(True)
        self.ereader_folder_edit.setPlaceholderText("Chưa thiết lập")
        choose_ereader_button = QPushButton("Chọn...", tab)
        choose_ereader_button.clicked.connect(self._on_choose_ereader_folder)
        ereader_row.addWidget(self.ereader_folder_edit, stretch=1)
        ereader_row.addWidget(choose_ereader_button)
        layout.addLayout(ereader_row)

        layout.addWidget(QLabel("🔎 Tìm metadata:"))
        self.metadata_write_check = QCheckBox("Mặc định tick \"Ghi vào file gốc\" khi áp dụng metadata (EPUB/PDF)", tab)
        self.metadata_write_check.setToolTip(
            "Tắt (khuyến nghị): chỉ cập nhật thư viện, file sách giữ nguyên trừ khi bạn tick từng lần. "
            "Khi ghi vào file, ứng dụng luôn sao lưu file trước và bạn có thể hoàn tác."
        )
        self.metadata_write_check.setChecked(config.metadata_write_to_file_default)
        layout.addWidget(self.metadata_write_check)
        backup_row = QHBoxLayout()
        backup_row.addWidget(QLabel("Số bản sao lưu file giữ lại cho mỗi sách:"))
        self.metadata_backup_spin = QSpinBox(tab)
        self.metadata_backup_spin.setRange(1, 20)
        self.metadata_backup_spin.setValue(config.metadata_backup_keep)
        backup_row.addWidget(self.metadata_backup_spin)
        backup_row.addStretch(1)
        layout.addLayout(backup_row)

        return tab

    def _build_theme_tab(self, config) -> QWidget:
        """Everything about how the app looks, in one place: the theme
        itself plus both font axes -- the app's own chrome font, and the
        separate "content" font used for document text (see AppConfig's
        docstring on content_font_family for why those two stay distinct
        settings even though they now live under one tab)."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        app_group = QGroupBox("Giao diện ứng dụng", tab)
        app_form = QFormLayout(app_group)

        self.theme_combo = QComboBox(app_group)
        # Each theme with a small picture of it, so they're easy to tell apart.
        self.theme_combo.setIconSize(QSize(64, 40))
        for name in THEME_CHOICES:
            self.theme_combo.addItem(QIcon(theme_preview_pixmap(THEMES[name], QSize(64, 40))), THEMES[name].display_name)
        self.theme_combo.setCurrentIndex(list(THEME_CHOICES).index(config.theme) if config.theme in THEME_CHOICES else 0)
        app_form.addRow("Phong cách:", self.theme_combo)

        # With no font chosen by the user, a font picker shows the theme's own
        # typeface -- and follows the theme combo above as it changes.
        theme_family = resolve_font_family(THEMES.get(config.theme, current_colors()))
        self.font_combo = QFontComboBox(app_group)
        self.font_combo.setCurrentFont(QFont(config.font_family or theme_family))
        # The combo always shows *some* concrete family -- compare against
        # this on save rather than against config.font_family directly, or
        # "no change" would be misread as "user picked a font" and needlessly
        # flip the restart flag.
        self._initial_font_family = self.font_combo.currentFont().family()
        app_form.addRow("Font chữ:", self.font_combo)

        self.font_size_spin = QSpinBox(app_group)
        self.font_size_spin.setRange(6, 32)
        self.font_size_spin.setValue(config.font_size)
        app_form.addRow("Cỡ chữ:", self.font_size_spin)

        layout.addWidget(app_group)

        content_group = QGroupBox("Font nội dung tài liệu", tab)
        content_layout = QVBoxLayout(content_group)

        note = QLabel(
            "Áp dụng cho phần nội dung tài liệu (tiêu đề/tác giả trong danh sách, "
            "panel chi tiết) -- tách riêng khỏi font giao diện chung ở trên.",
            content_group,
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        content_layout.addWidget(note)

        content_form = QFormLayout()

        self.content_font_combo = QFontComboBox(content_group)
        self.content_font_combo.setCurrentFont(QFont(config.content_font_family or theme_family))
        self._initial_content_font_family = self.content_font_combo.currentFont().family()
        content_form.addRow("Font chữ:", self.content_font_combo)

        # A font counts as "chosen by the user" only once they touch its
        # picker; until then it follows the theme (see _on_theme_preview_changed
        # and _on_save), so picking a new theme also switches the typeface.
        self._font_touched = {"app": False, "content": False}
        self.font_combo.currentFontChanged.connect(lambda _font: self._font_touched.update(app=True))
        self.content_font_combo.currentFontChanged.connect(lambda _font: self._font_touched.update(content=True))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_preview_changed)

        self.content_font_size_spin = QSpinBox(content_group)
        self.content_font_size_spin.setRange(6, 48)
        self.content_font_size_spin.setValue(config.content_font_size)
        content_form.addRow("Cỡ chữ:", self.content_font_size_spin)

        self._content_text_color = config.content_text_color
        color_row = QHBoxLayout()
        self.content_color_swatch = QLabel(content_group)
        self.content_color_swatch.setFixedSize(24, 24)
        self._update_color_swatch()
        pick_color_button = QPushButton("Chọn màu...", content_group)
        pick_color_button.clicked.connect(self._on_pick_content_color)
        reset_color_button = QPushButton("Mặc định", content_group)
        reset_color_button.setToolTip("Dùng màu chữ theo giao diện (sáng/tối) hiện tại")
        reset_color_button.clicked.connect(self._on_reset_content_color)
        color_row.addWidget(self.content_color_swatch)
        color_row.addWidget(pick_color_button)
        color_row.addWidget(reset_color_button)
        color_row.addStretch(1)
        content_form.addRow("Màu chữ:", color_row)

        content_layout.addLayout(content_form)
        layout.addWidget(content_group)
        layout.addStretch(1)
        return tab

    def _update_color_swatch(self) -> None:
        color = self._content_text_color or current_colors().text
        self.content_color_swatch.setStyleSheet(f"background: {color}; border: 1px solid palette(mid);")

    def _on_pick_content_color(self) -> None:
        initial = QColor(self._content_text_color or current_colors().text)
        chosen = QColorDialog.getColor(initial, self, "Chọn màu chữ nội dung")
        if chosen.isValid():
            self._content_text_color = chosen.name()
            self._update_color_swatch()

    def _on_reset_content_color(self) -> None:
        self._content_text_color = None
        self._update_color_swatch()

    def _build_performance_tab(self, config) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)

        cpu_count = os.cpu_count() or 1
        active = self.import_manager.active_worker_count() if self.import_manager else 0
        self.performance_status_label = QLabel(f"Đang chạy: {active} luồng  •  Số lõi CPU khả dụng: {cpu_count}")
        form.addRow(self.performance_status_label)

        self.worker_spin = QSpinBox(tab)
        self.worker_spin.setRange(1, 32)
        self.worker_spin.setValue(config.worker_thread_count)
        form.addRow("Số luồng nạp file tối đa (Worker Threads):", self.worker_spin)

        self.debounce_spin = QDoubleSpinBox(tab)
        # No real upper limit -- just a very large ceiling so the widget has
        # *some* bound (QDoubleSpinBox requires one) without meaningfully
        # constraining what the user can type.
        self.debounce_spin.setRange(0.5, 86400.0)
        self.debounce_spin.setSingleStep(0.5)
        self.debounce_spin.setSuffix(" giây")
        self.debounce_spin.setValue(config.watch_debounce_seconds)
        form.addRow("Thời gian chờ trước khi quét file mới:", self.debounce_spin)

        return tab

    _ON_IMPORT_LABELS = (
        ("ask", "Hỏi tôi mỗi lần thêm file/thư mục"),
        ("always", "Luôn tự động phân loại tài liệu mới"),
        ("never", "Không phân loại (chỉ dùng nút trên danh sách)"),
    )

    def _build_smart_classify_tab(self, config) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)

        info = QLabel(self._smart_classify_model_text(), tab)
        info.setWordWrap(True)
        info.setTextFormat(Qt.PlainText)
        form.addRow(info)

        self.smart_on_import_combo = QComboBox(tab)
        for key, label in self._ON_IMPORT_LABELS:
            self.smart_on_import_combo.addItem(label, key)
        index = self.smart_on_import_combo.findData(config.smart_classify_on_import)
        self.smart_on_import_combo.setCurrentIndex(max(index, 0))
        form.addRow("Khi thêm tài liệu mới:", self.smart_on_import_combo)

        self.smart_max_words_spin = QSpinBox(tab)
        self.smart_max_words_spin.setRange(2000, 5000)
        self.smart_max_words_spin.setSingleStep(500)
        self.smart_max_words_spin.setSuffix(" từ")
        self.smart_max_words_spin.setValue(min(max(config.smart_classify_max_words, 2000), 5000))
        self.smart_max_words_spin.setToolTip("Số từ đầu sách được đọc để phân loại. Nhiều từ hơn: chính xác hơn một chút nhưng chậm hơn.")
        form.addRow("Số từ đọc ở đầu mỗi sách:", self.smart_max_words_spin)

        self.smart_workers_spin = QSpinBox(tab)
        self.smart_workers_spin.setRange(1, 4)
        self.smart_workers_spin.setValue(min(max(config.smart_classify_max_workers, 1), 4))
        self.smart_workers_spin.setToolTip(
            "Số tiến trình nền tối đa dùng khi phân loại nhiều sách. Tiến trình chạy ở mức ưu tiên thấp; "
            "thư viện nhỏ luôn chỉ dùng một tiến trình."
        )
        form.addRow("Số tiến trình nền tối đa:", self.smart_workers_spin)

        note = QLabel(
            "Việc phân loại chạy nền ở mức ưu tiên thấp và chỉ bắt đầu khi bạn yêu cầu, nên không làm chậm ứng dụng. "
            "Mô hình được huấn luyện riêng bằng train.py (xem README), không huấn luyện trong ứng dụng.",
            tab,
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {current_colors().muted_text};")
        form.addRow(note)
        return tab

    def _smart_classify_model_text(self) -> str:
        path = resolve_model_path(self.context.config.app_data_dir)
        if path is None:
            return "Chưa có mô hình phân loại. Chạy train.py để tạo mô hình từ thư viện của bạn."
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
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        note = QLabel(
            "AI Tóm tắt đọc nội dung tài liệu (nếu có) và tạo phần giới thiệu, ý chính, "
            "tóm tắt hoặc nhận xét (chọn kiểu khi tạo) bằng API key của chính bạn -- "
            "hoặc miễn phí hoàn toàn với Groq/OpenRouter/Gemini, hay Ollama chạy ngay trên máy. Ứng dụng không đi kèm hay chuyển tiếp key của ai khác; mọi yêu cầu "
            "gọi thẳng từ máy bạn đến nhà cung cấp bạn chọn.",
            tab,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.ai_provider_combo = QComboBox(tab)
        self.ai_provider_combo.addItem("(Chưa cấu hình)", None)
        for provider_id in AI_PROVIDER_CHOICES:
            self.ai_provider_combo.addItem(AI_PROVIDER_DISPLAY_NAMES[provider_id], provider_id)
        if config.ai_provider:
            index = self.ai_provider_combo.findData(config.ai_provider)
            if index >= 0:
                self.ai_provider_combo.setCurrentIndex(index)
        self.ai_provider_combo.currentIndexChanged.connect(self._update_ai_provider_guide)
        form.addRow("Nhà cung cấp AI:", self.ai_provider_combo)

        key_row = QHBoxLayout()
        self.ai_api_key_edit = QLineEdit(config.ai_api_key or "", tab)
        self.ai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ai_api_key_edit.setPlaceholderText("Dán API key vào đây...")
        show_key_button = QToolButton(tab)
        show_key_button.setText("👁")
        show_key_button.setCheckable(True)
        show_key_button.setToolTip("Hiện/ẩn API key")
        show_key_button.toggled.connect(
            lambda checked: self.ai_api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        key_row.addWidget(self.ai_api_key_edit)
        key_row.addWidget(show_key_button)
        form.addRow("API key:", key_row)

        # Optional model override -- providers retire/rename models every
        # few months, so this lets the user move on without an app update.
        self.ai_model_edit = QLineEdit(config.ai_model or "", tab)
        self.ai_model_edit.setToolTip("Để trống để dùng model mặc định của nhà cung cấp.")
        form.addRow("Model:", self.ai_model_edit)

        self.ai_base_url_edit = QLineEdit(config.ai_base_url or "", tab)
        self.ai_base_url_edit.setPlaceholderText(OLLAMA_DEFAULT_BASE_URL)
        self.ai_base_url_label = QLabel("Địa chỉ Ollama:", tab)
        form.addRow(self.ai_base_url_label, self.ai_base_url_edit)

        layout.addLayout(form)
        layout.addWidget(self._build_key_security_note(tab))

        # Mẫu hướng dẫn: where to get a key for whichever provider is
        # currently selected, updated live as the dropdown changes.
        self.ai_provider_guide_label = QLabel(tab)
        self.ai_provider_guide_label.setWordWrap(True)
        self.ai_provider_guide_label.setOpenExternalLinks(True)
        self.ai_provider_guide_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.ai_provider_guide_label)
        self._update_ai_provider_guide()

        test_row = QHBoxLayout()
        self.test_connection_button = QPushButton("🔌 Kiểm tra kết nối", tab)
        self.test_connection_button.clicked.connect(self._on_test_connection)
        test_row.addWidget(self.test_connection_button)
        test_row.addStretch(1)
        layout.addLayout(test_row)

        self.connection_status_label = QLabel(tab)
        self.connection_status_label.setWordWrap(True)
        layout.addWidget(self.connection_status_label)

        layout.addStretch(1)
        return tab

    def _build_key_security_note(self, tab: QWidget) -> QLabel:
        """Reused under every API key field in this dialog (AI Tóm tắt,
        Google Images) -- see core.secret_store.SecretStore, which is what
        actually makes this true rather than just a claim in the UI."""
        note = QLabel(
            "🔒 API Key của bạn được mã hóa và chỉ lưu trữ cục bộ trên máy tính này. "
            "Chúng tôi không thu thập thông tin này.",
            tab,
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-style: italic;")
        return note

    def _build_cover_search_tab(self, config) -> QWidget:
        """Optional Google Custom Search (Image) setup for "Tìm ảnh bìa" --
        see application/cover_search.py. Without a key/cx here, cover
        search still works via the free sources (Open Library, Google
        Books, Apple Books); this just adds real Google Images results on
        top, and the key also gives Google Books its own daily quota."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        note = QLabel(
            "Tìm ảnh bìa luôn dùng 3 nguồn MIỄN PHÍ, không cần cấu hình: Apple Books "
            "(nhiều sách tiếng Việt), Open Library và Google Books -- kết quả được xếp "
            "theo độ khớp tên sách/tác giả. Phần dưới đây là tùy chọn: thêm Google Images "
            "để tìm trên toàn web, và API key này cũng giúp Google Books không bị hết "
            "lượt tra cứu miễn phí dùng chung trong ngày (cần bật thêm \"Books API\"). Lưu ý: Google đã "
            "ngừng nhận khách hàng mới cho Custom Search JSON API, nên Google Images chỉ dùng được "
            "với tài khoản đã có sẵn.",
            tab,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        # Which keyless sources may be contacted at all (search text goes to them); see docs/legal/DATA_SOURCES.md.
        sources_box = QGroupBox("Nguồn được phép tra cứu (gửi tên sách/tác giả ra ngoài)", tab)
        sources_layout = QVBoxLayout(sources_box)
        self._cover_source_checkboxes: dict[str, QCheckBox] = {}
        disabled_sources = set(config.disabled_cover_sources)
        for name, hint in (
            (SOURCE_OPEN_LIBRARY, ""),
            (SOURCE_GOOGLE_BOOKS, ""),
            (SOURCE_APPLE_BOOKS, " -- tắt sẵn: điều khoản của Apple chỉ cho dùng ảnh để quảng bá cửa hàng"),
            (SOURCE_TIKI, " -- tắt sẵn: API nội bộ của cửa hàng, chưa có điều khoản cho phép dùng"),
        ):
            checkbox = QCheckBox(f"{name}{hint}", sources_box)
            checkbox.setChecked(name not in disabled_sources)
            self._cover_source_checkboxes[name] = checkbox
            sources_layout.addWidget(checkbox)
        layout.addWidget(sources_box)

        form = QFormLayout()
        self.google_image_api_key_edit = QLineEdit(config.google_image_api_key or "", tab)
        self.google_image_api_key_edit.setEchoMode(QLineEdit.Password)
        self.google_image_api_key_edit.setPlaceholderText("Dán API key vào đây...")
        show_button = QToolButton(tab)
        show_button.setText("👁")
        show_button.setCheckable(True)
        show_button.setToolTip("Hiện/ẩn API key")
        show_button.toggled.connect(
            lambda checked: self.google_image_api_key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        key_row = QHBoxLayout()
        key_row.addWidget(self.google_image_api_key_edit)
        key_row.addWidget(show_button)
        form.addRow("API key:", key_row)

        self.google_image_cx_edit = QLineEdit(config.google_image_search_cx or "", tab)
        self.google_image_cx_edit.setPlaceholderText("Search Engine ID (cx)")
        form.addRow("Search Engine ID:", self.google_image_cx_edit)

        layout.addLayout(form)
        layout.addWidget(self._build_key_security_note(tab))

        cover_test_row = QHBoxLayout()
        self.cover_test_button = QPushButton("🔌 Kiểm tra kết nối", tab)
        self.cover_test_button.clicked.connect(self._on_test_cover_connection)
        cover_test_row.addWidget(self.cover_test_button)
        cover_test_row.addStretch(1)
        layout.addLayout(cover_test_row)

        self.cover_test_status_label = QLabel(tab)
        self.cover_test_status_label.setWordWrap(True)
        layout.addWidget(self.cover_test_status_label)

        guide = QLabel(_COVER_SEARCH_SETUP_GUIDE, tab)
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.RichText)
        guide.setOpenExternalLinks(True)
        guide.setStyleSheet("color: palette(mid);")

        # The step-by-step guide is long on purpose (it walks through two
        # different Google consoles) -- park it in its own scroll area so a
        # tab that is mostly instructions can't stretch the dialog.
        guide_scroll = QScrollArea(tab)
        guide_scroll.setWidgetResizable(True)
        guide_scroll.setWidget(guide)
        guide_scroll.setMinimumHeight(180)
        layout.addWidget(guide_scroll, stretch=1)

        return tab

    def _build_cloud_review_tab(self, config) -> QWidget:
        """Supabase setup for the community review feature. Previously the
        only way to configure this was to hand-edit settings.json -- the
        status bar would just say "Chưa cấu hình" with nowhere in the app
        to actually fix it."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        note = QLabel(
            "Đánh giá cộng đồng (tùy chọn) -- cho phép bạn xem và gửi đánh giá sao/nhận xét "
            "dùng chung với người khác, qua Supabase. Chỉ tên sách, tác giả, điểm và nội dung "
            "đánh giá được đồng bộ; file tài liệu luôn nằm 100% trên máy bạn.",
            tab,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.supabase_url_edit = QLineEdit(config.supabase_url or "", tab)
        self.supabase_url_edit.setPlaceholderText("https://xxxxx.supabase.co")
        form.addRow("Supabase URL:", self.supabase_url_edit)

        self.supabase_key_edit = QLineEdit(config.supabase_anon_key or "", tab)
        self.supabase_key_edit.setEchoMode(QLineEdit.Password)
        self.supabase_key_edit.setPlaceholderText("Dán anon / public key vào đây...")
        show_button = QToolButton(tab)
        show_button.setText("👁")
        show_button.setCheckable(True)
        show_button.setToolTip("Hiện/ẩn key")
        show_button.toggled.connect(
            lambda checked: self.supabase_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        key_row = QHBoxLayout()
        key_row.addWidget(self.supabase_key_edit)
        key_row.addWidget(show_button)
        form.addRow("Anon key:", key_row)
        layout.addLayout(form)

        test_row = QHBoxLayout()
        self.supabase_test_button = QPushButton("🔌 Kiểm tra kết nối", tab)
        self.supabase_test_button.clicked.connect(self._on_test_supabase_connection)
        test_row.addWidget(self.supabase_test_button)
        self.copy_upgrade_sql_button = QPushButton("📋 Sao chép SQL nâng cấp", tab)
        self.copy_upgrade_sql_button.setToolTip(
            "Sao chép đoạn SQL bật định danh người dùng & nick name duy nhất (Phần 2b) vào clipboard."
        )
        self.copy_upgrade_sql_button.clicked.connect(self._on_copy_upgrade_sql)
        test_row.addWidget(self.copy_upgrade_sql_button)
        test_row.addStretch(1)
        layout.addLayout(test_row)

        self.supabase_test_status_label = QLabel(tab)
        self.supabase_test_status_label.setWordWrap(True)
        layout.addWidget(self.supabase_test_status_label)

        guide = QLabel(_CLOUD_REVIEW_SETUP_GUIDE, tab)
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.RichText)
        guide.setOpenExternalLinks(True)
        guide.setTextInteractionFlags(Qt.TextBrowserInteraction)  # so the SQL can be selected/copied
        guide.setStyleSheet("color: palette(mid);")
        guide_scroll = QScrollArea(tab)
        guide_scroll.setWidgetResizable(True)
        guide_scroll.setWidget(guide)
        guide_scroll.setMinimumHeight(180)
        layout.addWidget(guide_scroll, stretch=1)

        return tab

    def _on_test_supabase_connection(self) -> None:
        url = self.supabase_url_edit.text().strip()
        key = self.supabase_key_edit.text().strip()

        self.supabase_test_button.setEnabled(False)
        self.supabase_test_button.setText("Đang kiểm tra...")
        self.supabase_test_status_label.setText("Đang kết nối tới Supabase, vui lòng đợi...")

        def worker() -> None:
            try:
                summary = SupabaseReviewSync(url, key).test_connection()
                self.supabase_test_finished.emit(True, f"✅ Kết nối thành công! {summary}")
            except CloudReviewError as exc:
                self.supabase_test_finished.emit(False, f"❌ {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_copy_upgrade_sql(self) -> None:
        QApplication.clipboard().setText(upgrade_sql())
        self.supabase_test_status_label.setText(
            "📋 Đã sao chép SQL nâng cấp -- dán vào Supabase SQL Editor và bấm Run."
        )
        self.supabase_test_status_label.setStyleSheet("")

    def _on_supabase_test_finished(self, success: bool, message: str) -> None:
        self.supabase_test_button.setEnabled(True)
        self.supabase_test_button.setText("🔌 Kiểm tra kết nối")
        self.supabase_test_status_label.setText(message)
        self.supabase_test_status_label.setStyleSheet(f"color: {'green' if success else 'crimson'};")

    def _update_ai_provider_guide(self) -> None:
        provider_id = self.ai_provider_combo.currentData()
        guide = PROVIDER_GUIDES.get(provider_id, "")
        self.ai_provider_guide_label.setText(f"💡 {guide}" if guide else "")
        # Built in field order, so the key/model widgets may not exist yet
        # on the very first call from _build_ai_tab.
        if hasattr(self, "ai_model_edit"):
            default_model = DEFAULT_MODELS.get(provider_id, "")
            self.ai_model_edit.setPlaceholderText(f"Mặc định: {default_model}" if default_model else "")
            is_local = provider_id == "ollama"
            self.ai_base_url_edit.setVisible(is_local)
            self.ai_base_url_label.setVisible(is_local)
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

        model = self.ai_model_edit.text().strip() or None
        base_url = self.ai_base_url_edit.text().strip() or None

        def worker() -> None:
            try:
                test_connection(provider, api_key, model=model, base_url=base_url)
                self.connection_test_finished.emit(True, "✅ Kết nối thành công!")
            except AISummaryError as exc:
                self.connection_test_finished.emit(False, f"❌ {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_connection_test_finished(self, success: bool, message: str) -> None:
        self.test_connection_button.setEnabled(True)
        self.test_connection_button.setText("🔌 Kiểm tra kết nối")
        self.connection_status_label.setText(message)
        self.connection_status_label.setStyleSheet(f"color: {'green' if success else 'crimson'};")

    def _on_test_cover_connection(self) -> None:
        api_key = self.google_image_api_key_edit.text().strip()
        cx = self.google_image_cx_edit.text().strip()

        self.cover_test_button.setEnabled(False)
        self.cover_test_button.setText("Đang kiểm tra...")
        self.cover_test_status_label.setText("Đang kết nối tới Google, vui lòng đợi...")

        def worker() -> None:
            try:
                found = test_cover_connection(api_key, cx)
                if found:
                    self.cover_test_finished.emit(True, "✅ Kết nối thành công! Google đã trả về kết quả ảnh.")
                else:
                    # The call itself worked (key + cx are valid), there just
                    # weren't any images for the probe query -- almost always
                    # means the search engine is restricted to specific sites
                    # instead of the whole web.
                    self.cover_test_finished.emit(
                        False,
                        "⚠️ Kết nối được nhưng không có ảnh nào trả về. Kiểm tra lại công cụ tìm kiếm "
                        "đã bật \"Search the entire web\" và \"Image search\" chưa (bước 3-4, Phần 1).",
                    )
            except CoverSearchError as exc:
                self.cover_test_finished.emit(False, f"❌ {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_cover_test_finished(self, success: bool, message: str) -> None:
        self.cover_test_button.setEnabled(True)
        self.cover_test_button.setText("🔌 Kiểm tra kết nối")
        self.cover_test_status_label.setText(message)
        self.cover_test_status_label.setStyleSheet(f"color: {'green' if success else 'crimson'};")

    def _on_add_folder(self) -> None:
        start_dir = self.context.config.config.last_used_directory or ""
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục để theo dõi", start_dir)
        if folder:
            self.context.config.config.last_used_directory = folder
            if not self.folder_list.findItems(folder, Qt.MatchExactly):
                self.folder_list.addItem(folder)

    def _on_remove_folder(self) -> None:
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))

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
        family = resolve_font_family(THEMES[list(THEME_CHOICES)[index]])
        for key, combo in (("app", self.font_combo), ("content", self.content_font_combo)):
            if self._font_touched[key]:
                continue
            combo.blockSignals(True)
            combo.setCurrentFont(QFont(family))
            combo.blockSignals(False)

    def _on_save(self) -> None:
        config = self.context.config.config

        new_extensions = [ext for ext, box in self._extension_checkboxes.items() if box.isChecked()]
        config.allowed_extensions = new_extensions

        new_folders = [self.folder_list.item(i).text() for i in range(self.folder_list.count())]
        removed_folders = set(config.watch_folders) - set(new_folders)
        added_folders = set(new_folders) - set(config.watch_folders)
        config.watch_folders = new_folders

        config.backup_retention = self.backup_panel.retention()
        config.update_check_enabled = self.update_panel.is_enabled()
        self.privacy_panel.apply()  # the error-report mode is kept by the reporter (it also records the consent wording)
        config.ereader_folder_path = self._ereader_folder_path or None
        config.metadata_write_to_file_default = self.metadata_write_check.isChecked()
        config.metadata_backup_keep = self.metadata_backup_spin.value()

        new_theme = list(THEME_CHOICES)[self.theme_combo.currentIndex()]
        theme_changed = new_theme != config.theme
        if theme_changed:
            self.appearance_changed = True
            config.theme = new_theme

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

        config.google_image_api_key = self.google_image_api_key_edit.text().strip() or None
        config.google_image_search_cx = self.google_image_cx_edit.text().strip() or None
        # Keep entries this tab has no checkbox for (e.g. a hand-added "Google Images").
        shown = set(self._cover_source_checkboxes)
        config.disabled_cover_sources = [name for name in config.disabled_cover_sources if name not in shown] + [
            name for name, box in self._cover_source_checkboxes.items() if not box.isChecked()
        ]

        config.supabase_url = self.supabase_url_edit.text().strip().rstrip("/") or None
        config.supabase_anon_key = self.supabase_key_edit.text().strip() or None

        self.context.config.save()

        if self.watcher:
            for folder in removed_folders:
                self.watcher.remove_folder(folder)
            for folder in added_folders:
                self.watcher.add_folder(folder)

        self.accept()


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
