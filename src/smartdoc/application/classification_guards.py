# SPDX-License-Identifier: AGPL-3.0-or-later
"""When the classifier should say "I don't know" instead of forcing a book category.

The model knows 48 categories of *books*. A magazine or a newspaper issue is not one of them and covers ten topics in a few
dozen pages, so the model picked whichever topic its first pages leaned to -- and with full confidence (the probabilities are
sharp): a lifestyle magazine became "Ẩm thực". A wrong hashtag is worse than none (it files the book in the wrong folder and
looks certain), so two guards withhold the answer, and the book is listed under "Sách chưa chắc" for the person to tag:

- `periodical_cue`: the title, file name or the folder it sits in says it is a magazine / newspaper / an issue of one
  ("Tạp chí Kiến thức số 12", "Thanh Niên 03/2019", a folder "Tap chi");
- `mixed_topics`: the text does not stay on one subject. The sample is cut in slices, each is classified alone, and when the
  confident slices do not agree on one *group* (Văn học, Kinh tế - Kinh doanh...) the book is a mix, not a subject.

No Qt, no database: runs in the classification worker process.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from smartdoc.domain.taxonomy import fold


REASON_PERIODICAL = "periodical"
REASON_MIXED_TOPICS = "mixed_topics"

# Words that name a periodical outright (no accents, lower case, punctuation kept -- "3/2019" must stay one piece).
_PERIODICAL_WORDS = re.compile(
    r"\b(tap chi|tap san|tuan bao|nhat bao|nguyet san|ban tin|magazines?|newspapers?|gazette|journal of|"
    r"bao xuan|bao tet|dac san)\b")
# "số 12 ... 2019", "issue 5 2018": an issue number together with a year.
_ISSUE_WITH_YEAR = re.compile(r"\b(so|no|issue|vol|n0)\.?\s*\d{1,3}\b.{0,30}\b(19|20)\d{2}\b")
# "tháng 3/2019", "03-2019", "T5.2020": a month and a year.
_MONTH_YEAR = re.compile(r"\b(thang|th|t)\s*\d{1,2}\s*[/.\-]\s*(19|20)\d{2}\b|\b(0?[1-9]|1[0-2])\s*[/.\-]\s*(19|20)\d{2}\b")

MIN_WORDS_TO_JUDGE_TOPICS = 1250  # five slices of at least 250 words: fewer words say too little about a slice
SLICES = 5
MIN_OPINIONS = 3
MAX_AGREEMENT = 0.6  # at most this share of the slices in one group = a mix (3 of 5 is a mix, 4 of 5 is a subject)


def _plain(text: str) -> str:
    stripped = "".join(ch for ch in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.replace("đ", "d").replace("_", " "))


def periodical_cue(title: str, path: str | None) -> str:
    """The cue that says this file is a magazine / newspaper issue, or "" (title, file name and the two folders above it)."""
    places = [title or ""]
    if path:
        location = Path(path)
        places += [location.stem, *(part.name for part in list(location.parents)[:2])]
    for place in places:
        text = _plain(place)
        if not text:
            continue
        for pattern in (_PERIODICAL_WORDS, _ISSUE_WITH_YEAR, _MONTH_YEAR):
            found = pattern.search(text)
            if found:
                return found.group(0)
    return ""


# -- Evidence from the file's own labels and from its title, for a book the model would not decide ----------------------

TITLE_CUE_CONFIDENCE = 0.6
LABEL_CONFIDENCE = 0.8


def label_verdict(taxonomy, subjects) -> str | None:
    """The one category the file's own subject labels (dc:subject, PDF keywords, MOBI subjects) name outright, else None.
    "Trinh thám" or "Hồi ký, Tuỳ bút" is how the training labels were made: a firm match is worth more than a short text's
    statistics, and it is the only evidence a very short document has. Two different categories = no verdict."""
    found = taxonomy.resolve_labels(list(subjects or ()), include_weak=False)
    return found[0].id if len(found) == 1 else None


def title_cue_verdict(taxonomy, title: str) -> str | None:
    """The one category whose title cues ("marketing", "khởi nghiệp") appear in `title`, else None (none, or several)."""
    padded = " " + fold(title) + " "
    hits = {category.id for category in taxonomy
            if any(" " + fold(cue) + " " in padded for cue in category.title_cues if fold(cue))}
    return hits.pop() if len(hits) == 1 else None


def mixed_topics(model, count_words: Callable[[str], dict[str, float]], body: str) -> bool:
    """True when slices of `body` confidently point at *different* groups.

    2026-09-29 (Task N2, docs/eval/classification_coverage_20260929.md and
    docs/eval/mixed_topics_fix_20260929.md): the previous version counted a slice the model
    would not decide on ("low_confidence" -- the slice is a fifth of the book, ~600-1000 words,
    far shorter than the whole-document length the model's confidence thresholds were tuned
    for, so most slices land there even for a perfectly ordinary single-topic book) as an
    *opinion of "" (nothing)*, then treated a low agreement ratio *among those* as evidence of
    disagreement. That conflated "most slices had too little text to be sure" with "the slices
    that WERE sure disagreed with each other" -- on the real library this false-flagged 73% of
    every hashtag-less book, the dominant cause of the whole coverage gap, typically while the
    model was >90% confident about the book as a whole.

    Now: only a slice the model actually committed to (`category_id` set) is an opinion.
    "Mixed" requires BOTH (a) at least `MIN_OPINIONS` slices committed to *some* group -- not
    silence padded out to look like a quorum -- AND (b) those opinions don't agree with each
    other (the same low-agreement-ratio test as before, just computed over real opinions only).
    Too few real opinions is "we don't know", not "it's mixed" -- so it returns False, leaving
    the whole-document verdict (usually confident) stand."""
    words = body.split()
    if len(words) < MIN_WORDS_TO_JUDGE_TOPICS:
        return False
    size = len(words) // SLICES
    opinions: list[str] = []  # one entry per slice the model actually committed to a group for
    for index in range(SLICES):
        prediction = model.predict(count_words(" ".join(words[index * size:(index + 1) * size])))
        if prediction.category_id:
            info = model.class_by_id(prediction.category_id)
            if info is not None:
                opinions.append(info.group)
    if len(opinions) < MIN_OPINIONS:
        return False  # not enough of the slices were sure of anything -- "don't know", not "mixed"
    return Counter(opinions).most_common(1)[0][1] / len(opinions) <= MAX_AGREEMENT
