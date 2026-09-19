# SPDX-License-Identifier: AGPL-3.0-or-later
"""The error-report scrubber (E-02, FR-ERR-02). Test data is Vietnamese with diacritics on purpose: an account, a title
and folders like the ones real users have. The check that matters is the negative one -- none of the private strings
may survive -- because the report dialog promises the user exactly that (docs 09, ERR-A3)."""
from __future__ import annotations

import os
import sysconfig
import time
import unicodedata

import pytest

from smartdoc.domain import error_scrubber as s

ACCOUNT = "Nguyễn Văn Ánh"
TITLE = "Đắc nhân tâm"
FOLDER = "Sách hay"
HOME = rf"C:\Users\{ACCOUNT}"
BOOK_PATH = rf"{HOME}\Documents\{FOLDER}\{TITLE}.epub"
KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"

# Every word of these must be gone from the output ("Ánh" and "Sách" appear in more than one of them on purpose).
PRIVATE_WORDS = ("Nguyễn", "Văn", "Ánh", "Đắc", "nhân", "tâm", "Sách", "hay", "Documents", "Users")


def _leaks(text: str, words=PRIVATE_WORDS) -> list[str]:
    return [word for word in words if word.casefold() in text.casefold()]


# --- paths and file names ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "message",
    [
        rf"Không mở được {BOOK_PATH} vì bị khóa",
        rf"Cannot open {BOOK_PATH} because it is locked",
        rf"PermissionError: [Errno 13] Permission denied: '{BOOK_PATH}'",
        # repr() doubles the backslashes, and the name may be inside double quotes
        "PermissionError: [Errno 13] Permission denied: " + repr(BOOK_PATH),
        f'FileNotFoundError: "{BOOK_PATH}"',
        rf"{BOOK_PATH}: invalid header",
        rf"Folder {HOME}\Documents\{FOLDER} is not writable",
        rf"UNC \\may-tinh\chia-se\{FOLDER}\{TITLE}.epub: access denied",
        f"/home/{ACCOUNT.lower()}/Documents/{FOLDER}/{TITLE}.pdf could not be parsed",
        f"~/Documents/{FOLDER}/{TITLE}.mobi",
        rf"%USERPROFILE%\Documents\{FOLDER}\{TITLE}.azw3 is empty",
    ],
)
def test_no_part_of_a_path_survives(message):
    scrubbed = s.scrub_text(message)
    assert _leaks(scrubbed) == [], scrubbed
    assert "<PATH>" in scrubbed or "<USER_DIR>" in scrubbed


def test_the_words_around_a_path_survive_when_the_path_can_be_bounded():
    assert s.scrub_text(rf"Cannot open {BOOK_PATH} because it is locked") == "Cannot open <PATH> because it is locked"
    assert s.scrub_text(rf"{BOOK_PATH}: invalid header") == "<PATH>: invalid header"
    assert s.scrub_text(f"[Errno 2] No such file or directory: '{BOOK_PATH}'") == "[Errno 2] No such file or directory: '<PATH>'"


def test_a_folder_that_ends_the_line_is_cut_to_the_end_because_its_end_is_unknowable():
    # "Sách hay is not writable": nothing says where the folder name stops, so all of it goes.
    assert s.scrub_text(rf"{HOME}\Documents\{FOLDER} is not writable") == "<PATH>"


@pytest.mark.parametrize(
    "message",
    [
        f"Không đọc được {TITLE}.epub: bị hỏng",
        f"Không đọc được {TITLE} (bản 2).pdf: bị hỏng",
        f"Harry Potter: {TITLE}.mobi is corrupt",
        f"'{TITLE}.fb2' is not valid",
        f"[{TITLE}].DJVU",
        f"bad {TITLE}.cbz",
        f"the file Nguyễn Du. {TITLE} - Tập 1.docx",
    ],
)
def test_a_book_file_name_without_a_folder_is_removed_with_the_words_in_front_of_it(message):
    scrubbed = s.scrub_text(message)
    assert _leaks(scrubbed, ("Đắc", "nhân", "tâm", "Nguyễn", "Potter", "Tập")) == [], scrubbed
    assert "<BOOK_FILE>" in scrubbed


def test_a_bare_extension_is_not_a_file_name():
    assert s.scrub_text("unsupported format .epub and *.pdf here") == "unsupported format .epub and *.pdf here"


def test_two_names_on_one_line_are_both_removed():
    scrubbed = s.scrub_text(f"copy {TITLE}.epub to {FOLDER}.pdf failed")
    assert "Đắc" not in scrubbed and "Sách" not in scrubbed


# --- e-mail, URL, IP, secrets ------------------------------------------------------------------------------------------

def test_email_url_and_ip_addresses_are_replaced():
    scrubbed = s.scrub_text(
        "mail nguyen.van.anh+sách@gmail.com; GET https://user:pass@example.org/a/b?token=xyz HTTP; from 192.168.0.12 and 2001:db8::1"
    )
    assert scrubbed == "mail <EMAIL>; GET <URL> HTTP; from <IP> and <IP>"


def test_a_time_of_day_is_not_mistaken_for_an_ip_address():
    assert s.scrub_text("at 10:20:30 and 9:05:01") == "at 10:20:30 and 9:05:01"


def test_a_web_address_is_replaced_and_a_file_address_is_treated_as_the_path_it_is():
    # A file URL may hold raw spaces; it is a path, and a path is cut as one (nothing of it is kept).
    assert s.scrub_text(f"see www.example.org/x and file:///C:/Users/{ACCOUNT}/a.pdf") == "see <URL> and <PATH>"
    assert s.scrub_text(f"file:///home/{ACCOUNT}/sách/a.epub failed") == "<PATH> failed"


@pytest.mark.parametrize(
    "secret",
    [
        KEY,
        "AIzaSyA1234567890abcdefghijklmnopqrstuv",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "3f2b1c0d9e8a7b6c5d4e3f2a1b0c9d8e",  # a 32-hex document id or hash
        "Zm9vYmFyQmF6MTIzNDU2Nzg5MEFCQ0RFRkdISUpLTA",  # url-safe base64, like secrets.token_urlsafe()
        "sb_publishable_AbCdEfGhIjKlMnOpQrStUv",
    ],
)
def test_keys_and_tokens_are_replaced(secret):
    scrubbed = s.scrub_text(f"request failed with {secret} attached")
    assert secret not in scrubbed and "<SECRET>" in scrubbed


@pytest.mark.parametrize(
    "message",
    ["api_key=hunter2hunter2", "password: 'p@ss w0rd'", "Authorization: Bearer abcdef123456", "token=abc", 'apikey: "AbC"'],
)
def test_a_value_assigned_to_a_secret_name_is_replaced(message):
    scrubbed = s.scrub_text(message)
    assert "hunter2" not in scrubbed and "p@ss" not in scrubbed and "abcdef123456" not in scrubbed and "abc" not in scrubbed.replace("<SECRET>", "").replace("apikey", "")
    assert "<SECRET>" in scrubbed


def test_names_of_code_are_not_taken_for_keys():
    text = "SmartClassifyProgressEvent a_very_long_snake_case_identifier_name_here smartdoc.application.import_queue 100%s%"
    assert s.scrub_text(text) == text


# --- what the caller knows ------------------------------------------------------------------------------------------------

def test_known_terms_are_removed_wherever_they_occur_in_any_letter_case():
    scrubbed = s.scrub_text(
        f"KeyError: '{TITLE}' and {TITLE.upper()} by {ACCOUNT.lower()}, host MAY-CUA-ANH",
        private_terms=[TITLE, ACCOUNT, "may-cua-anh"],
    )
    assert _leaks(scrubbed, ("Đắc", "nhân", "tâm", "Nguyễn", "Ánh", "MAY-CUA")) == [], scrubbed
    assert scrubbed.count("<PRIVATE>") == 4


def test_known_terms_match_whatever_unicode_form_the_text_uses():
    decomposed = unicodedata.normalize("NFD", f"lỗi với {TITLE}")
    assert decomposed != unicodedata.normalize("NFC", decomposed)
    assert s.scrub_text(decomposed, private_terms=[TITLE]) == "lỗi với <PRIVATE>"
    assert s.scrub_text(f"lỗi với {TITLE}", private_terms=[unicodedata.normalize("NFD", TITLE)]) == "lỗi với <PRIVATE>"


def test_the_longest_term_wins():
    assert s.scrub_text("Nguyễn Văn Ánh viết", private_terms=["Nguyễn", "Nguyễn Văn Ánh"]) == "<PRIVATE> viết"


def test_a_short_term_only_matches_a_whole_word():
    assert s.scrub_text("Anne, Annette and Anne", private_terms=["Anne"]) == "<PRIVATE>, Annette and <PRIVATE>"
    assert s.scrub_text("an ab An", private_terms=["ab", "An"]) == "an ab An"  # below the minimum length: never a term


def test_a_known_secret_goes_even_when_it_looks_like_nothing():
    assert s.scrub_text("using key correct-horse-battery for x", private_terms=["correct-horse-battery"]) == "using key <PRIVATE> for x"


def test_a_term_does_not_break_the_placeholders_around_it():
    # An account called "user": `<USER_DIR>` (made before the terms are applied) must stay as it is.
    scrubbed = s.scrub_text(rf"open {HOME}\x.py now", private_terms=["user", "path", "dir"], user_dirs=[HOME])
    assert scrubbed == "open <USER_DIR>/<PATH> now"


def test_a_book_title_named_in_a_path_and_bare_are_both_gone():
    scrubbed = s.scrub_text(rf"scan {BOOK_PATH} then '{TITLE}' failed", private_terms=[TITLE], user_dirs=[HOME])
    assert _leaks(scrubbed, ("Đắc", "nhân", "tâm", "Nguyễn", "Sách", "Documents")) == [], scrubbed


def test_the_users_own_folders_are_named_but_nothing_below_them():
    assert s.scrub_text(HOME, user_dirs=[HOME]) == "<USER_DIR>"
    assert s.scrub_text(rf"{HOME}\Documents\{FOLDER}\x.py failed", user_dirs=[HOME]) == "<USER_DIR>/<PATH> failed"
    assert s.scrub_text(f"'{HOME}/AppData/x'", user_dirs=[HOME.replace("\\", "/")]) == "'<USER_DIR>/<PATH>'"
    assert s.scrub_text(rf"D:\elsewhere\x.py", user_dirs=[HOME]) == "<PATH>"


# --- normalisation and limits -------------------------------------------------------------------------------------------------

def test_the_text_is_normalised_and_cleaned():
    text = "a\u200bb\u202ec\x00d\x1be\r\nf\u2028g"
    cleaned = s.scrub_text(text, single_line=False)
    assert "\u200b" not in cleaned and "\u202e" not in cleaned and "\x00" not in cleaned and "\x1b" not in cleaned
    assert cleaned.split("\n") == ["abc d e", "f", "g"]
    assert s.scrub_text(unicodedata.normalize("NFD", "tâm")) == unicodedata.normalize("NFC", "tâm")


def test_lines_are_folded_into_one_and_long_text_is_cut():
    assert s.scrub_text("one\n\n two \nthree") == "one ⏎ two ⏎ three"
    cut = s.scrub_text("x" * 2000, max_length=100)
    assert len(cut) == 100 and cut.endswith("…")


def test_scrubbing_twice_changes_nothing():
    text = rf"Cannot open {BOOK_PATH} for {ACCOUNT}: {KEY} at 192.168.0.1 mail a@b.co '{TITLE}.pdf'"
    once = s.scrub_text(text, private_terms=[ACCOUNT, TITLE], user_dirs=[HOME])
    assert s.scrub_text(once, private_terms=[ACCOUNT, TITLE], user_dirs=[HOME]) == once


def test_a_hostile_line_is_processed_in_bounded_time():
    lines = [
        "C:\\" + "a b " * 15_000,
        "x" * 60_000,
        "/" + "a/" * 20_000,
        ("Đắc nhân tâm " * 5_000) + ".epub",
        "\\\\" + "s" * 30_000,
        "sk-" + "A1" * 30_000,
        "a@" + "b." * 10_000,
    ]
    started = time.perf_counter()
    for line in lines:
        s.scrub_text(line)
    assert time.perf_counter() - started < 5.0


# --- log tails -------------------------------------------------------------------------------------------------------------------

def test_a_log_tail_keeps_its_prefix_and_loses_what_is_personal():
    log = (
        "2026-09-19 10:00:01,123 WARNING [import-worker-1] smartdoc.application.import_queue: "
        f"Could not read {TITLE}.epub (corrupt zip)\n"
        f"2026-09-19 10:00:02,000 INFO    [MainThread] smartdoc.app: opened {BOOK_PATH} for {ACCOUNT}\n"
        f"a line that is not a log record {KEY}\n"
    )
    scrubbed = s.scrub_log_tail(log, private_terms=[ACCOUNT, TITLE], user_dirs=[HOME])
    assert _leaks(scrubbed) == [] and KEY not in scrubbed
    first, second, third = scrubbed.split("\n")
    assert first.startswith("2026-09-19 10:00:01,123 WARNING [import-worker-1] smartdoc.application.import_queue: ")
    assert second.startswith("2026-09-19 10:00:02,000 INFO    [MainThread] smartdoc.app: ")
    assert third == "a line that is not a log record <SECRET>"


def test_a_log_tail_is_limited_to_its_last_lines_and_characters():
    log = "\n".join(f"2026-09-19 10:00:{i % 60:02d},000 INFO [t] smartdoc.x: line {i}" for i in range(200))
    tail = s.scrub_log_tail(log, max_lines=50)
    assert tail.count("\n") == 49 and tail.endswith("line 199")
    assert len(s.scrub_log_tail(log, max_lines=200, max_chars=300)) <= 300


# --- stack frame paths ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (rf"{HOME}\code\src\smartdoc\application\import_queue.py", "smartdoc/application/import_queue.py"),
        (rf"{HOME}\smartdoc\src\smartdoc\app.py", "smartdoc/app.py"),  # a checkout inside a folder called smartdoc
        (r"C:\_MEI1234\smartdoc\presentation\main_window.py", "smartdoc/presentation/main_window.py"),
        (rf"{HOME}\.venv\Lib\site-packages\requests\adapters.py", "site-packages/requests/adapters.py"),
        ("requests/adapters.py", "requests/adapters.py"),  # relative inside a frozen bundle
        ("<string>", "<string>"),
        ("<frozen importlib._bootstrap>", "<frozen importlib._bootstrap>"),
        (rf"{HOME}\Documents\{FOLDER}\script.py", "<PATH>"),
        ("/home/anh/x.py", "<PATH>"),
        ("../up/x.py", "<PATH>"),
        ("", "<PATH>"),
    ],
)
def test_a_frame_path_keeps_only_what_is_safe(path, expected):
    assert s.scrub_path(path) == expected


def test_the_standard_library_is_named_by_its_relative_path():
    stdlib = sysconfig.get_paths()["stdlib"]
    assert s.scrub_path(os.path.join(stdlib, "threading.py")) == "stdlib/threading.py"


# --- the promise, end to end -------------------------------------------------------------------------------------------------------

def test_a_message_full_of_private_data_leaves_nothing_behind():
    """ERR-A3: Windows account name, a Vietnamese title, an absolute path, an e-mail and a key in one message."""
    message = (
        f"{ACCOUNT} <nguyen.van.anh@gmail.com> could not import {BOOK_PATH}: "
        f"'{TITLE}' has key {KEY}, doc 3f2b1c0d9e8a7b6c5d4e3f2a1b0c9d8e, from 10.1.2.3 via https://x.example/y?u={ACCOUNT}"
    )
    scrubbed = s.scrub_text(message, private_terms=[ACCOUNT, TITLE], user_dirs=[HOME], max_length=1000)
    assert _leaks(scrubbed, PRIVATE_WORDS + ("gmail", "abcdefghij", "3f2b1c0d", "10.1.2.3", "example")) == [], scrubbed
