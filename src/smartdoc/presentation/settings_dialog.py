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

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
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

from smartdoc.application.ai_summary import AISummaryError, PROVIDER_GUIDES, test_connection
from smartdoc.core.config import AI_PROVIDER_CHOICES, AI_PROVIDER_DISPLAY_NAMES, KNOWN_EXTENSIONS, THEME_CHOICES
from smartdoc.presentation.theme import current_colors

_THEME_DISPLAY_NAMES = {"light": "Sáng (Light)", "dark": "Tối (Dark)"}


class SettingsDialog(QDialog):
    connection_test_finished = Signal(bool, str)  # (success, message)

    def __init__(self, context, parent=None, watcher=None, import_manager=None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(480)

        config = context.config.config
        self.appearance_changed = False  # theme/font: see module docstring

        tabs = QTabWidget(self)
        tabs.addTab(self._build_file_tab(config), "📁 Quản lý File")
        tabs.addTab(self._build_theme_tab(config), "🎨 Giao diện")
        tabs.addTab(self._build_content_font_tab(config), "🔤 Font nội dung")
        tabs.addTab(self._build_performance_tab(config), "⚡ Hiệu năng")
        tabs.addTab(self._build_ai_tab(config), "🤖 AI Tóm tắt")

        self.connection_test_finished.connect(self._on_connection_test_finished)

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

        return tab

    def _build_theme_tab(self, config) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        self.theme_combo = QComboBox(tab)
        self.theme_combo.addItems([_THEME_DISPLAY_NAMES[name] for name in THEME_CHOICES])
        self.theme_combo.setCurrentIndex(list(THEME_CHOICES).index(config.theme) if config.theme in THEME_CHOICES else 0)
        form.addRow("Phong cách:", self.theme_combo)

        self.font_combo = QFontComboBox(tab)
        if config.font_family:
            self.font_combo.setCurrentFont(QFont(config.font_family))
        # The combo always shows *some* concrete family (the OS default when
        # config.font_family is None) -- compare against this on save rather
        # than against config.font_family directly, or "no change" would be
        # misread as "user picked a font" and needlessly flip the restart flag.
        self._initial_font_family = self.font_combo.currentFont().family()
        form.addRow("Font chữ:", self.font_combo)

        self.font_size_spin = QSpinBox(tab)
        self.font_size_spin.setRange(6, 32)
        self.font_size_spin.setValue(config.font_size)
        form.addRow("Cỡ chữ:", self.font_size_spin)

        return tab

    def _build_content_font_tab(self, config) -> QWidget:
        """Separate from "Giao diện" on purpose -- this governs how
        document text (library titles/authors, the detail panel) is
        displayed, not the app's own menus/buttons/dialogs."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        note = QLabel(
            "Áp dụng cho phần nội dung tài liệu (tiêu đề/tác giả trong danh sách, "
            "panel chi tiết) -- tách riêng khỏi font giao diện chung của ứng dụng.",
            tab,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()

        self.content_font_combo = QFontComboBox(tab)
        if config.content_font_family:
            self.content_font_combo.setCurrentFont(QFont(config.content_font_family))
        self._initial_content_font_family = self.content_font_combo.currentFont().family()
        form.addRow("Font chữ:", self.content_font_combo)

        self.content_font_size_spin = QSpinBox(tab)
        self.content_font_size_spin.setRange(6, 48)
        self.content_font_size_spin.setValue(config.content_font_size)
        form.addRow("Cỡ chữ:", self.content_font_size_spin)

        self._content_text_color = config.content_text_color
        color_row = QHBoxLayout()
        self.content_color_swatch = QLabel(tab)
        self.content_color_swatch.setFixedSize(24, 24)
        self._update_color_swatch()
        pick_color_button = QPushButton("Chọn màu...", tab)
        pick_color_button.clicked.connect(self._on_pick_content_color)
        reset_color_button = QPushButton("Mặc định", tab)
        reset_color_button.setToolTip("Dùng màu chữ theo giao diện (sáng/tối) hiện tại")
        reset_color_button.clicked.connect(self._on_reset_content_color)
        color_row.addWidget(self.content_color_swatch)
        color_row.addWidget(pick_color_button)
        color_row.addWidget(reset_color_button)
        color_row.addStretch(1)
        form.addRow("Màu chữ:", color_row)

        layout.addLayout(form)
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

    def _build_ai_tab(self, config) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        note = QLabel(
            "AI Tóm tắt đọc phần đầu tài liệu (nếu có) và tạo một đoạn giới thiệu "
            "chủ đề/thể loại -- không tiết lộ cốt truyện -- bằng API key của chính "
            "bạn. Ứng dụng không đi kèm hay chuyển tiếp key của ai khác; mọi yêu cầu "
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

        layout.addLayout(form)

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

    def _update_ai_provider_guide(self) -> None:
        provider_id = self.ai_provider_combo.currentData()
        guide = PROVIDER_GUIDES.get(provider_id, "")
        self.ai_provider_guide_label.setText(f"💡 {guide}" if guide else "")

    def _on_test_connection(self) -> None:
        provider = self.ai_provider_combo.currentData()
        api_key = self.ai_api_key_edit.text().strip()
        if not provider:
            self.connection_status_label.setText("Vui lòng chọn một nhà cung cấp AI trước.")
            return

        self.test_connection_button.setEnabled(False)
        self.test_connection_button.setText("Đang kiểm tra...")
        self.connection_status_label.setText("Đang kết nối, vui lòng đợi...")

        def worker() -> None:
            try:
                test_connection(provider, api_key)
                self.connection_test_finished.emit(True, "✅ Kết nối thành công!")
            except AISummaryError as exc:
                self.connection_test_finished.emit(False, f"❌ {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_connection_test_finished(self, success: bool, message: str) -> None:
        self.test_connection_button.setEnabled(True)
        self.test_connection_button.setText("🔌 Kiểm tra kết nối")
        self.connection_status_label.setText(message)
        self.connection_status_label.setStyleSheet(f"color: {'green' if success else 'crimson'};")

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

    def _on_save(self) -> None:
        config = self.context.config.config

        new_extensions = [ext for ext, box in self._extension_checkboxes.items() if box.isChecked()]
        config.allowed_extensions = new_extensions

        new_folders = [self.folder_list.item(i).text() for i in range(self.folder_list.count())]
        removed_folders = set(config.watch_folders) - set(new_folders)
        added_folders = set(new_folders) - set(config.watch_folders)
        config.watch_folders = new_folders

        new_theme = list(THEME_CHOICES)[self.theme_combo.currentIndex()]
        if new_theme != config.theme:
            self.appearance_changed = True
            config.theme = new_theme

        new_font_family = self.font_combo.currentFont().family()
        if new_font_family != self._initial_font_family:
            self.appearance_changed = True
            config.font_family = new_font_family

        new_font_size = self.font_size_spin.value()
        if new_font_size != config.font_size:
            self.appearance_changed = True
            config.font_size = new_font_size

        new_content_font_family = self.content_font_combo.currentFont().family()
        if new_content_font_family != self._initial_content_font_family:
            self.appearance_changed = True
            config.content_font_family = new_content_font_family

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

        config.ai_provider = self.ai_provider_combo.currentData()
        config.ai_api_key = self.ai_api_key_edit.text().strip() or None

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
