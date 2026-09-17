"""TDD-015 (upgrade): Settings Dialog.

Three tabs: File types + watch folders, Theme, Performance (worker count).
The original spec's Tab 4 (Cloud: Google Drive connect/disconnect) is not
built here -- it depends on TDD-016/TDD-019 (Milestone F), which aren't
implemented yet, and a tab full of buttons that do nothing would be worse
than no tab.

Watch folder / allowed-extension changes take effect immediately (the file
watcher and scan_folder read config live). Theme and worker thread count
require a restart -- Qt widgets already built don't retroactively re-theme,
and the import queue's worker threads are already running -- so those two
show a one-time notice instead of silently doing nothing.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
    def __init__(self, context, parent=None, watcher=None) -> None:
        super().__init__(parent)
        self.context = context
        self.watcher = watcher
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
        form.addRow(QLabel("(Cần khởi động lại ứng dụng để áp dụng)"))
        return tab

    def _build_performance_tab(self, config) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        self.worker_spin = QSpinBox(tab)
        self.worker_spin.setRange(1, 32)
        self.worker_spin.setValue(config.worker_thread_count)
        form.addRow("Số luồng nạp file (Worker Threads):", self.worker_spin)
        form.addRow(QLabel("(Cần khởi động lại ứng dụng để áp dụng)"))
        return tab

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục để theo dõi")
        if folder and not self.folder_list.findItems(folder, Qt.MatchExactly):
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

        new_worker_count = self.worker_spin.value()
        if new_worker_count != config.worker_thread_count:
            self._restart_needed = True
            config.worker_thread_count = new_worker_count

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
