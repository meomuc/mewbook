# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C1: DRM is only ever detected here, never bypassed (docs/legal/DRM_POLICY.md) -- these tests check the
detector says yes/no correctly and never raises for a damaged or unrelated file."""
from __future__ import annotations

import zipfile

from smartdoc.infrastructure.drm_detect import is_drm_protected


def test_a_plain_epub_is_not_flagged(tmp_path):
    epub = tmp_path / "a.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", "<container/>")
    assert not is_drm_protected(str(epub))


def test_an_epub_with_an_encryption_xml_marker_is_flagged(tmp_path):
    epub = tmp_path / "protected.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/encryption.xml", "<encryption/>")
    assert is_drm_protected(str(epub))


def test_a_missing_file_is_not_flagged_it_is_simply_not_readable(tmp_path):
    assert not is_drm_protected(str(tmp_path / "nope.epub"))


def test_a_corrupt_epub_is_not_flagged_never_raises(tmp_path):
    fake = tmp_path / "broken.epub"
    fake.write_bytes(b"not actually a zip")
    assert not is_drm_protected(str(fake))


def test_a_non_pdf_non_epub_file_is_never_flagged(tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hello", encoding="utf-8")
    assert not is_drm_protected(str(txt))


def test_a_plain_pdf_is_not_flagged(tmp_path):
    import pymupdf

    pdf = tmp_path / "a.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()
    assert not is_drm_protected(str(pdf))


def test_an_encrypted_pdf_is_flagged(tmp_path):
    import pymupdf

    pdf = tmp_path / "locked.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    doc.close()
    assert is_drm_protected(str(pdf))
