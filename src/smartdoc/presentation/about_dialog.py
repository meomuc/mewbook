# SPDX-License-Identifier: AGPL-3.0-or-later
"""Help -> About dialog: app identity, the licence (AGPL-3.0-or-later) with a link to the source of
this exact version, and a legal page with five texts: the short notice (eula_dialog.py's EULA_TEXT, the
single source for that wording, reused verbatim), the full privacy policy and terms (docs/legal/PRIVACY.md and
TERMS.md, shown as Markdown), the LICENSE and the third-party notices (all read from the files bundled with the
app -- see resources.legal_file_path()).
"""
from __future__ import annotations

import html
import logging

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from smartdoc import (
    APP_COPYRIGHT,
    APP_DESCRIPTION,
    APP_DISPLAY_NAME,
    APP_LICENSE_ID,
    APP_LICENSE_URL,
    APP_NAME,
    APP_PUBLISHER,
    APP_SOURCE_URL_TEMPLATE,
    __version__,
)
from smartdoc.core.diagnostics import current_log_path, support_info
from smartdoc.presentation.community import community_url, website_url
from smartdoc.presentation.eula_dialog import EULA_TEXT
from smartdoc.presentation.resources import brand_logo_path, legal_file_path
from smartdoc.presentation.theme import current_colors

logger = logging.getLogger(__name__)

_LOGO_SIZE = 64


def source_url(template: str | None = None, version: str = __version__) -> str:
    """Link to the source of this exact version, or "" while no public repository is configured."""
    template = APP_SOURCE_URL_TEMPLATE if template is None else template
    return template.format(version=version) if template else ""


def read_legal_file(name: str) -> str:
    """Text of a bundled legal file; a pointer to the official licence when it can't be read."""
    try:
        return legal_file_path(name).read_text(encoding="utf-8-sig")
    except OSError:
        logger.warning("Legal file %s is not available next to the app", name)
        return f"Không tìm thấy tệp {name} kèm theo ứng dụng.\nGiấy phép {APP_LICENSE_ID}: {APP_LICENSE_URL}"


class AboutDialog(QDialog):
    def __init__(self, parent=None, *, identity=None) -> None:
        super().__init__(parent)
        self._identity = identity
        self.setWindowTitle("Giới thiệu")
        # Fixed size -- an About dialog has fixed content, no reason to
        # ever grow beyond it.
        self.setFixedSize(440, 600)

        self._info_page = self._build_info_page()
        self._legal_page = self._build_legal_page()

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._info_page)
        self.stack.addWidget(self._legal_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    def _build_info_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        logo_label = QLabel(page)
        logo_label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(brand_logo_path()))
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaled(_LOGO_SIZE, _LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(logo_label)

        title = QLabel(APP_DISPLAY_NAME, page)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: 700; font-size: 18px;")
        layout.addWidget(title)

        self.version_label = QLabel(f"Phiên bản {__version__}", page)
        self.version_label.setAlignment(Qt.AlignCenter)
        self.version_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.version_label)

        subtitle = QLabel(f"{APP_NAME} -- {APP_DESCRIPTION.lower()}", page)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        author = QLabel(f"Tác giả: {APP_PUBLISHER}", page)
        author.setAlignment(Qt.AlignCenter)
        layout.addWidget(author)

        copyright_label = QLabel(APP_COPYRIGHT, page)
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(copyright_label)

        self.license_label = QLabel(
            f"Giấy phép {APP_LICENSE_ID}. Đây là phần mềm tự do: bạn có thể chia sẻ và sửa đổi theo giấy phép này. "
            "Phần mềm được cung cấp KHÔNG kèm bất kỳ bảo hành nào.",
            page,
        )
        self.license_label.setAlignment(Qt.AlignCenter)
        self.license_label.setWordWrap(True)
        self.license_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.license_label)

        self.source_label = QLabel(page)
        self.source_label.setAlignment(Qt.AlignCenter)
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet("font-size: 11px;")
        url = source_url()
        if url:
            # The palette's link colour is a pale cyan that is unreadable on light themes, and the
            # theme's stylesheet overrides a per-label palette; colour the link span with the accent.
            safe = html.escape(url, quote=True)
            link = f'<a href="{safe}"><span style="color:{current_colors().accent};">{html.escape(url)}</span></a>'
            self.source_label.setTextFormat(Qt.RichText)
            self.source_label.setText(f"Mã nguồn phiên bản {__version__}: {link}")
            self.source_label.setOpenExternalLinks(True)
        else:
            self.source_label.setText(f"Mã nguồn tương ứng của phiên bản {__version__} được cung cấp cùng bản phát hành.")
        layout.addWidget(self.source_label)

        # The official website, above the fan page: the first place to look for downloads and news.
        self.website_label = QLabel(page)
        self.website_label.setAlignment(Qt.AlignCenter)
        self.website_label.setWordWrap(True)
        self.website_label.setStyleSheet("font-size: 11px;")
        site = website_url()
        if site:
            safe_site = html.escape(site, quote=True)
            site_link = f'<a href="{safe_site}"><span style="color:{current_colors().accent};">{html.escape(site.removeprefix("https://").rstrip("/"))}</span></a>'
            self.website_label.setTextFormat(Qt.RichText)
            self.website_label.setText(f"Trang web chính thức: {site_link}")
            self.website_label.setOpenExternalLinks(True)
        else:
            self.website_label.setVisible(False)
        layout.addWidget(self.website_label)

        # Where new versions are announced and feedback is read. Same accent-coloured link as the source line above.
        self.community_label = QLabel(page)
        self.community_label.setAlignment(Qt.AlignCenter)
        self.community_label.setWordWrap(True)
        self.community_label.setStyleSheet("font-size: 11px;")
        community = community_url()
        if community:
            safe = html.escape(community, quote=True)
            link = f'<a href="{safe}"><span style="color:{current_colors().accent};">Fanpage cộng đồng Mèo Mực</span></a>'
            self.community_label.setTextFormat(Qt.RichText)
            self.community_label.setText(f"Tin cập nhật và góp ý: {link}")
            self.community_label.setOpenExternalLinks(True)
        else:
            self.community_label.setVisible(False)
        layout.addWidget(self.community_label)

        if self._identity is not None:
            id_label = QLabel(f"Mã cài đặt ẩn danh: {self._identity.short_id}", page)
            id_label.setAlignment(Qt.AlignCenter)
            id_label.setStyleSheet("color: palette(mid); font-size: 11px;")
            id_label.setToolTip(
                "Mã ngẫu nhiên sinh ra khi cài đặt, dùng để nhận biết bài đánh giá của bạn mà không cần đăng ký. "
                "Không chứa thông tin cá nhân; cài lại ứng dụng sẽ sinh mã mới."
            )
            layout.addWidget(id_label)

        layout.addStretch(1)

        support_row = QHBoxLayout()
        self.copy_support_button = QPushButton("📋 Sao chép thông tin hỗ trợ", page)
        self.copy_support_button.setToolTip("Phiên bản, hệ điều hành và đường dẫn file nhật ký -- gửi kèm khi báo lỗi.")
        self.copy_support_button.clicked.connect(self._on_copy_support_info)
        support_row.addWidget(self.copy_support_button)
        self.open_logs_button = QPushButton("📂 Thư mục nhật ký", page)
        self.open_logs_button.clicked.connect(self._on_open_logs)
        self.open_logs_button.setEnabled(current_log_path() is not None)
        support_row.addWidget(self.open_logs_button)
        layout.addLayout(support_row)

        self.legal_button = QPushButton("📄 Giấy phép, thông báo và quyền riêng tư", page)
        self.legal_button.clicked.connect(lambda: self.stack.setCurrentWidget(self._legal_page))
        layout.addWidget(self.legal_button)

        return page

    def _build_legal_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        heading = QLabel("Giấy phép, thông báo và quyền riêng tư", page)
        heading.setStyleSheet("font-weight: 700;")
        layout.addWidget(heading)

        self.legal_text_area = QTextEdit(page)
        self.legal_text_area.setReadOnly(True)
        self.legal_text_area.setPlainText(EULA_TEXT)

        # The texts are read lazily: LICENSE is 35 KB, no reason to load it before it is asked for. The second element
        # says whether the text is Markdown (the two drafts have headings, lists and tables; the others are plain).
        self._legal_sources = {
            "privacy": (lambda: EULA_TEXT, False),
            "policy": (lambda: read_legal_file("docs/legal/PRIVACY.md"), True),
            "terms": (lambda: read_legal_file("docs/legal/TERMS.md"), True),
            "license": (lambda: read_legal_file("LICENSE"), False),
            "notices": (lambda: read_legal_file("THIRD_PARTY_NOTICES.md"), False),
        }
        # Two rows: five tabs do not fit side by side in this narrow dialog.
        tabs = QGridLayout()
        self._legal_group = QButtonGroup(page)
        self._legal_group.setExclusive(True)
        labels = (("privacy", "Tóm tắt"), ("policy", "Chính sách riêng tư"), ("terms", "Điều khoản"),
                  ("license", APP_LICENSE_ID), ("notices", "Bên thứ ba"))
        for index, (key, label) in enumerate(labels):
            button = QPushButton(label, page)
            button.setCheckable(True)
            button.setChecked(key == "privacy")
            button.clicked.connect(lambda _checked=False, k=key: self._show_legal_text(k))
            self._legal_group.addButton(button)
            setattr(self, f"{key}_tab", button)
            tabs.addWidget(button, index // 3, index % 3)
        layout.addLayout(tabs)
        layout.addWidget(self.legal_text_area, stretch=1)

        self.back_button = QPushButton("← Quay lại", page)
        self.back_button.clicked.connect(lambda: self.stack.setCurrentWidget(self._info_page))
        layout.addWidget(self.back_button)

        return page

    def _show_legal_text(self, key: str) -> None:
        load, is_markdown = self._legal_sources[key]
        if is_markdown:
            self.legal_text_area.setMarkdown(load())
        else:
            self.legal_text_area.setPlainText(load())

    def _on_copy_support_info(self) -> None:
        QApplication.clipboard().setText(support_info(self._identity))
        self.copy_support_button.setText("✅ Đã sao chép")

    def _on_open_logs(self) -> None:
        log_path = current_log_path()
        if log_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path.parent)))


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from smartdoc.presentation.theme import apply_light_theme

    app = QApplication(sys.argv)
    apply_light_theme(app)
    AboutDialog().exec()
