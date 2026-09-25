/* SPDX-License-Identifier: AGPL-3.0-or-later
   Base look of every standard control ("Kệ sách" design, docs: Sample theme/.../07_quy-tac).
   Placeholders (a dollar sign plus a token name) come from styles/theme_tokens.json; ThemeManager fills them in, because QSS has no variables.
   Sizes: controls 30 px high, radius 6, dialogs radius 10 (spacing in multiples of 4). Widgets that paint
   themselves (shelf, covers, badges) read the same tokens from ThemeManager instead of this file. */

QToolTip { background: $surface; color: $ink; border: 1px solid $line2; padding: 4px 8px; }

QPushButton {
    background: $surface; color: $ink; border: 1px solid $line2; border-radius: 6px;
    min-height: 30px; padding: 0 12px;
}
QPushButton:hover { border-color: $accent; }
QPushButton:focus { border: 1px solid $accent; }
QPushButton:disabled { color: $ink3; border-color: $line; background: $surface2; }
QPushButton[role="primary"] { background: $accent; color: $accentink; border-color: $accent; font-weight: 600; }
QPushButton[role="primary"]:disabled { background: $surface2; color: $ink3; border-color: $line; }
QPushButton[role="danger"] { color: $err; border-color: $err; }
QPushButton[role="danger"]:disabled { color: $ink3; border-color: $line; }
QPushButton[role="dangerSolid"] { background: $err; color: $accentink; border-color: $err; font-weight: 600; }
QPushButton[role="dangerSolid"]:disabled { background: $surface2; color: $ink3; border-color: $line; }

/* Left-rail pill: upper-case, spaced, display font; the selected pill is filled with the accent. */
QPushButton[role="pill"], QToolButton[role="pill"] {
    background: transparent; color: $ink2; border: 1px solid $line2; border-radius: 6px;
    min-height: 30px; padding: 0 12px; text-align: left;
    font-family: $disp; font-size: 10px; font-weight: 600;
}
QPushButton[role="pill"]:hover, QToolButton[role="pill"]:hover { border-color: $accent; color: $ink; }
QPushButton[role="pill"]:checked, QToolButton[role="pill"]:checked { background: $accent; color: $accentink; border-color: $accent; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: $surface; color: $ink; border: 1px solid $line2; border-radius: 6px;
    selection-background-color: $accent; selection-color: $accentink;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { min-height: 28px; padding: 0 8px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid $accent;
}
QLineEdit:disabled, QComboBox:disabled { color: $ink3; background: $surface2; }
QComboBox QAbstractItemView { background: $surface; color: $ink; border: 1px solid $line2; selection-background-color: $accentsoft; selection-color: $ink; }

QMenu { background: $surface; color: $ink; border: 1px solid $line2; padding: 4px; }
QMenu::item { padding: 6px 16px; border-radius: 4px; }
QMenu::item:selected { background: $accentsoft; color: $ink; }
QMenu::item:disabled { color: $ink3; }
QMenu::separator { height: 1px; background: $line; margin: 4px 8px; }

QCheckBox, QRadioButton { color: $ink; spacing: 8px; }
QCheckBox:disabled, QRadioButton:disabled { color: $ink3; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: $line2; border-radius: 4px; min-height: 24px; min-width: 24px; margin: 2px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: $ink3; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSplitter::handle { background: $line; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

QProgressBar { background: $surface2; border: none; border-radius: 3px; max-height: 6px; text-align: center; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }

QSlider::groove:horizontal { height: 4px; background: $line2; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { background: $accent; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }

QTableView { background: $bg; border: none; outline: 0; gridline-color: transparent; }
QTableView::item { border-bottom: 1px solid $line; padding: 0 8px; color: $ink; }
QHeaderView { background: $bg; }

QTabWidget::pane { border: 1px solid $line; }
QHeaderView::section { background: $bg; color: $ink3; border: none; border-bottom: 1px solid $line2; padding: 8px 8px;
    font-family: $disp; font-size: 10px; font-weight: 600; }

QStatusBar { background: $rail; color: $ink2; border-top: 1px solid $line; }
QStatusBar::item { border: none; }

/* Dialog frame; the footer strip uses surface2. */
QDialog { background: $bg; }
QFrame[role="dialogFooter"] { background: $surface2; border-top: 1px solid $line; }
QLabel[role="hint"] { color: $ink3; }
QLabel[role="groupLabel"] { color: $ink3; font-family: $disp; font-size: 10px; font-weight: 600; }
