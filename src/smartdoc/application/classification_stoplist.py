# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tokens the classifier must never learn from (S0-04b).

Ebook files carry boilerplate that says nothing about what a book is about: the site or group that released
the scan, "share this ebook", copyright and licence blurbs (Project Gutenberg's included), contact e-mails,
social-media handles, converter credits. A model trained on them learns "released by X" as a genre signal
(a spurious correlation), and the vocabulary keeps traces of where the training library came from
(docs/legal/MODEL_VOCAB_AUDIT.md section 2.3), which is not something to publish.

The list is applied at training time only (application/classification_trainer.py); the app never imports this
module. Tokens are the normalised, accent-stripped, lower-case ones the tokenizer produces (word pieces joined
by "_", e.g. "chia_se", "project_gutenberg"). To extend it, add the word to STOP_WORDS (matches any compound
token containing it) or the whole token to STOP_TOKENS (exact match), then re-train.
"""
from __future__ import annotations

# A compound token is dropped when ANY of its "_"-separated parts is one of these.
STOP_WORDS: frozenset[str] = frozenset(
    {
        # file formats and tools
        "ebook", "ebooks", "epub", "mobi", "azw", "azw3", "prc", "pdf", "calibre", "kindle", "ocr", "scan", "scanned",
        # release groups and sites (Vietnamese ebook scene, Project Gutenberg)
        "tve", "vctvegroup", "vnthuquan", "thuquan", "thuvien", "waka", "gutenberg",
        # legal and licence boilerplate
        "copyright",
        # contact details, sites and social media
        "email", "mail", "gmail", "yahoo", "hotmail", "http", "https", "www", "website", "blog", "blogspot",
        "wordpress", "facebook", "twitter", "zalo", "telegram", "youtube", "instagram", "tiktok", "download",
    }
)

# Whole tokens (usually two-syllable Vietnamese words that are boilerplate as a phrase but ordinary alone).
STOP_TOKENS: frozenset[str] = frozenset(
    {
        "chia_se",  # "chia sẻ" (share): "chia sẻ ebook", "chia sẻ miễn phí"
        "thu_vien",  # "thư viện": "thư viện ebook", "tủ sách thư viện"
        "ban_quyen",  # "bản quyền": copyright blurbs
        "trang_web",  # "trang web"
    }
)


def is_stopped(token: str) -> bool:
    """True if the classifier must not use this token as a feature."""
    if token in STOP_TOKENS:
        return True
    return any(part in STOP_WORDS for part in token.split("_"))
