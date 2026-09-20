from PySide6.QtWidgets import QDialog

from smartdoc.presentation.eula_dialog import EULA_TEXT, EulaDialog


def test_full_text_is_shown_in_scrollable_area(qapp):
    dialog = EulaDialog()
    assert dialog.text_area.toPlainText() == EULA_TEXT
    assert dialog.text_area.isReadOnly()


def test_clicking_agree_accepts_the_dialog(qapp):
    dialog = EulaDialog()
    dialog.accept()
    assert dialog.result() == QDialog.Accepted


def test_closing_without_agreeing_does_not_accept(qapp):
    dialog = EulaDialog()
    dialog.reject()
    assert dialog.result() == QDialog.Rejected


# --- the notice must say what the code really does (S0-05 "sửa thêm", E-06) -----------------------------------------------------------

def test_the_notice_names_the_licence_and_disclaims_warranty():
    from smartdoc import APP_LICENSE_ID

    assert "AGPL-3.0-or-later" == APP_LICENSE_ID and "GNU AGPL-3.0-or-later" in EULA_TEXT
    assert "KHÔNG kèm bất kỳ bảo hành nào" in EULA_TEXT


def test_the_notice_mentions_every_feature_that_sends_something_out():
    for feature in ("ảnh bìa", "Tóm tắt AI", "Đánh giá cộng đồng", "Báo lỗi ẩn danh", "Kiểm tra bản mới", "địa chỉ IP"):
        assert feature in EULA_TEXT, feature


def test_the_notice_states_the_error_report_promises_the_app_keeps():
    assert "HỎI MỖI LẦN" in EULA_TEXT and "xem trước" in EULA_TEXT  # ERR-A1, ERR-A4
    assert "90 ngày" in EULA_TEXT  # the retention the server enforces (application/sql/003_error_reports.sql)
    assert "không chứa tên sách, đường dẫn hay nội dung tài liệu" in EULA_TEXT  # the promise FR-ERR-02 tests
    assert "công cụ AI" in EULA_TEXT  # spec 09 section 9: processing by an AI tool must be disclosed


def test_the_notice_no_longer_claims_titles_and_authors_are_synced_and_adds_no_restriction():
    assert "Tên sách, Tên tác giả" not in EULA_TEXT  # the 1.0.0 wording: the review server never gets them
    for restriction in ("dịch ngược", "cấm", "không được phép sao chép", "bảo lưu mọi quyền"):
        assert restriction not in EULA_TEXT.lower(), restriction


def test_the_button_confirms_reading_it_does_not_ask_for_agreement_to_terms(qapp):
    from PySide6.QtWidgets import QPushButton

    dialog = EulaDialog()
    assert [b.text() for b in dialog.findChildren(QPushButton)] == ["Tôi đã đọc, tiếp tục"]


# --- the full drafts and the notice agree (docs/legal/PRIVACY.md, TERMS.md) ---------------------------------------------------------------

def _legal(name: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "docs" / "legal" / name).read_text(encoding="utf-8")


def test_the_privacy_draft_carries_the_consent_version_the_app_uses():
    import re

    from smartdoc.application.error_reporter import CONSENT_VERSION

    match = re.search(r"Phiên bản văn bản: \*\*(\d+)\*\*", _legal("PRIVACY.md"))
    assert match and int(match.group(1)) == CONSENT_VERSION  # change one, change the other: the app re-asks on a bump


def test_the_privacy_draft_states_what_spec_09_section_9_requires():
    text = _legal("PRIVACY.md")
    for required in ("90 ngày", "địa chỉ IP", "nhật ký kết nối", "công cụ AI", "mã báo cáo", "xem trước", "ngoài Việt Nam", "Hỏi mỗi lần"):
        assert required in text, required
    assert "CẦN LUẬT SƯ DUYỆT" in text  # until a lawyer has looked, it says so


def test_the_review_data_the_privacy_draft_lists_is_what_the_server_stores():
    text = _legal("PRIVACY.md")
    assert "MD5" in text and "SHA-256" in text  # doc_id (models.generate_document_id) and user_hash (user_identity.hash_token)
    assert "tên sách" in text  # ... and that no title or author is sent


def test_the_terms_draft_adds_no_restriction_on_the_software_and_marks_open_legal_points():
    text = _legal("TERMS.md")
    assert "không thêm bất kỳ hạn chế nào" in text and "AGPL" in text
    assert "CẦN LUẬT SƯ DUYỆT" in text and "[CHỜ LUẬT SƯ" in text


def test_the_drafts_hold_no_personal_data_or_secret():
    import re

    for name in ("PRIVACY.md", "TERMS.md"):
        text = _legal(name)
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), f"an e-mail address in {name}"
        assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}|sb_(publishable|secret)_\w+", text), f"a key in {name}"
