"""TDD-015 (upgrade): Settings Dialog.

Three tabs: File types + watch folders, Theme (+ font), Performance (worker
count + scan timing). The original spec's Tab 4 (Cloud: Google Drive
connect/disconnect) is not built here -- it depends on TDD-016/TDD-019
(Milestone F), which aren't implemented yet, and a tab full of buttons that
do nothing would be worse than no tab.

Watch folder / allowed-extension changes take effect immediately (the file
watcher and scan_folder read config live). Theme, font, worker thread count,
and the file-watcher debounce require a restart -- Qt widgets already built
don't retroactively re-theme, and the import queue's worker threads /
watcher are already running -- so those show a one-time notice instead of
silently doing nothing.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.config import KNOWN_EXTENSIONS, THEME_CHOICES

_THEME_DISPLAY_NAMES = {"light": "Sáng (Light)", "dark": "Tối (Dark)"}


class SettingsDialog(QDialog):
    def __init__(self, context, parent=None, watcher=None, import_manager=None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
        self.import_manager = import_manager
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(480)

        config = context.config.config
        self._restart_needed = False

        tabs = QTabWidget(self)
        tabs.addTab(self._build_file_tab(config), "Quản lý File")
        tabs.addTab(self._build_theme_tab(config), "Giao diện")
        tabs.addTab(self._build_performance_tab(config), "Hiệu năng")

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

        form.addRow(QLabel("(Cần khởi động lại ứng dụng để áp dụng)"))
        return tab

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
        self.debounce_spin.setRange(0.5, 30.0)
        self.debounce_spin.setSingleStep(0.5)
        self.debounce_spin.setSuffix(" giây")
        self.debounce_spin.setValue(config.watch_debounce_seconds)
        form.addRow("Thời gian chờ trước khi quét file mới:", self.debounce_spin)

        form.addRow(QLabel("(Cần khởi động lại ứng dụng để áp dụng)"))
        return tab

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
            self._restart_needed = True
            config.theme = new_theme

        new_font_family = self.font_combo.currentFont().family()
        if new_font_family != self._initial_font_family:
            self._restart_needed = True
            config.font_family = new_font_family

        new_font_size = self.font_size_spin.value()
        if new_font_size != config.font_size:
            self._restart_needed = True
            config.font_size = new_font_size

        new_worker_count = self.worker_spin.value()
        if new_worker_count != config.worker_thread_count:
            self._restart_needed = True
            config.worker_thread_count = new_worker_count

        new_debounce = self.debounce_spin.value()
        if new_debounce != config.watch_debounce_seconds:
            self._restart_needed = True
            config.watch_debounce_seconds = new_debounce

        self.context.config.save()

        if self.watcher:
            for folder in removed_folders:
                self.watcher.remove_folder(folder)
            for folder in added_folders:
                self.watcher.add_folder(folder)

        if self._restart_needed:
            QMessageBox.information(
                self, "Cần khởi động lại", "Một số thay đổi (giao diện, số luồng) sẽ áp dụng sau khi khởi động lại ứng dụng."
            )
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
