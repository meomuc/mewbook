# SPDX-License-Identifier: AGPL-3.0-or-later
"""Text that ordinary people read must not use the developer's words (docs/UI_TEXT_AUDIT.md).

Screens are built for real and every piece of text on them is collected -- labels, buttons, tick boxes, group
titles, tab names, tooltips, placeholders, form captions -- then checked against a list of internal terms. The list
is small on purpose: it names words that once appeared in the app and have a plain replacement, so a new screen
that brings one back fails here.
"""
import re

import pytest
from PySide6.QtWidgets import QAbstractButton, QGroupBox, QLabel, QLineEdit, QTabWidget, QWidget

from smartdoc.presentation.metadata_suggest_dialog import MetadataSuggestDialog
from smartdoc.presentation.settings_dialog import SettingsDialog

# term -> what to say instead (shown when the test fails)
INTERNAL_TERMS = {
    r"\bmetadata\b": "thông tin sách",
    r"\bworker\b": "(bỏ)",
    r"\bthreads?\b": "(bỏ)",
    r"\bluồng\b": "tác vụ chạy cùng lúc",
    r"\bCPU\b": "bộ xử lý / máy",
    r"\blõi\b": "(bỏ)",
    r"\bdebounce\b": "thời gian chờ",
    r"\bcache\b": "bộ nhớ tạm",
    r"\bSQLite\b": "thư viện",
    r"\bdatabase\b": "thư viện",
    r"\bhàng đợi\b": "danh sách chờ",
    r"\blog\b": "nhật ký",
    r"\bfile config\b": "(bỏ)",
    r"\bexception\b": "lỗi",
    r"\btrường\b": "thông tin",
    r"\bmodel\b": "mẫu AI",
    r"\bcx\b": "Search Engine ID",
}


def _texts(root: QWidget) -> list[str]:
    found: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        if isinstance(widget, (QLabel, QAbstractButton)):
            found.append(widget.text())
        if isinstance(widget, QGroupBox):
            found.append(widget.title())
        if isinstance(widget, QLineEdit):
            found.append(widget.placeholderText())
        if isinstance(widget, QTabWidget):
            found.extend(widget.tabText(i) for i in range(widget.count()))
        found.append(widget.toolTip())
        found.append(widget.windowTitle())
    return [text for text in found if text]


def _offences(texts: list[str]) -> list[str]:
    plain = [re.sub(r"<[^>]+>", " ", text) for text in texts]  # ignore markup
    return [
        f"{pattern!r} in {text[:80]!r} -> say {INTERNAL_TERMS[pattern]!r}"
        for text in plain
        for pattern in INTERNAL_TERMS
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def test_the_files_tab_of_settings_uses_plain_words(qapp, app_context):
    dialog = SettingsDialog(app_context)
    file_tab = dialog.extension_flow.window().findChild(QTabWidget).widget(0)
    assert _offences(_texts(file_tab)) == []


def test_the_performance_tab_uses_plain_words_and_explains_every_option(qapp, app_context):
    dialog = SettingsDialog(app_context)
    tabs = dialog.extension_flow.window().findChild(QTabWidget)
    performance = next(tabs.widget(i) for i in range(tabs.count()) if "Hiệu năng" in tabs.tabText(i))

    assert _offences(_texts(performance)) == []
    # every option carries one line of ordinary words: what happens if it goes up, and what if it goes down
    for hint in (dialog.worker_hint, dialog.debounce_hint):
        assert "Tăng lên thì" in hint.text() and "Giảm xuống thì" in hint.text()
        assert hint.wordWrap()


@pytest.mark.parametrize("tab_name", ["AI Tóm tắt", "Ảnh bìa"])
def test_the_key_tabs_use_plain_words(qapp, app_context, tab_name):
    """The AI and cover-search tabs (where the API-key guides live). The community-review tab is left out on
    purpose: it is for whoever runs the server, and the SQL and table names there are what they must copy."""
    dialog = SettingsDialog(app_context)
    tabs = dialog.extension_flow.window().findChild(QTabWidget)
    tab = next(tabs.widget(i) for i in range(tabs.count()) if tab_name in tabs.tabText(i))
    dialog.ai_provider_combo.setCurrentIndex(dialog.ai_provider_combo.findData("ollama"))  # show a real guide too

    assert _offences(_texts(tab)) == []


def test_the_metadata_dialog_uses_plain_words(qapp, app_context):
    doc = {"id": "d1", "title": "Sách", "author": "Ai đó", "file_path": "a.epub", "extension": "epub"}
    dialog = MetadataSuggestDialog(app_context, doc)
    try:
        assert _offences(_texts(dialog)) == []
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize(
    "source",
    [
        "src/smartdoc/presentation/library_view.py",
        "src/smartdoc/presentation/main_window.py",
        "src/smartdoc/presentation/toolbar.py",
        "src/smartdoc/presentation/metadata_suggest_dialog.py",
    ],
)
def test_message_boxes_avoid_internal_terms(source):
    """Every QMessageBox call's own text (title and message), read straight from the source."""
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parent.parent / source).read_text(encoding="utf-8"))
    strings: list[str] = []
    for node in ast.walk(tree):
        is_box_call = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "QMessageBox"
            and node.func.attr in ("warning", "information", "critical", "question")
        )
        if is_box_call:
            strings += [c.value for arg in node.args for c in ast.walk(arg) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
    assert strings, "found no QMessageBox calls: the test would prove nothing"
    assert _offences(strings) == []


def test_the_author_is_called_the_author_not_a_developer():
    """The project is credited as "tác giả" everywhere people read it ("Tác giả: ...", "gửi cho tác giả")."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "smartdoc"
    sources = [root / "app.py", *(root / "presentation").glob("*.py")]
    banned = re.compile(r"phát triển bởi|nhà phát triển|\bDev:", re.IGNORECASE)
    hits = [f"{path.name}: {m.group(0)}" for path in sources for m in banned.finditer(path.read_text(encoding="utf-8"))]
    assert hits == []
