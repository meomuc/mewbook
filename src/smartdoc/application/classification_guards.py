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


def mixed_topics(model, count_words: Callable[[str], dict[str, float]], body: str) -> bool:
    """True when slices of `body` confidently point at different groups. `count_words(text)` -> term counts, weighted as
    the model was trained; `model` is a TextClassifierModel."""
    words = body.split()
    if len(words) < MIN_WORDS_TO_JUDGE_TOPICS:
        return False
    size = len(words) // SLICES
    groups: list[str] = []  # one entry per slice that has an opinion; "" = it saw evidence but could not decide
    for index in range(SLICES):
        prediction = model.predict(count_words(" ".join(words[index * size:(index + 1) * size])))
        if prediction.category_id:
            info = model.class_by_id(prediction.category_id)
            if info is not None:
                groups.append(info.group)
        elif prediction.reason == "low_confidence":
            groups.append("")  # a slice torn between subjects is what a magazine looks like: it counts against agreement
    if len(groups) < MIN_OPINIONS:
        return False
    return Counter(g for g in groups if g).most_common(1)[0][1] / len(groups) <= MAX_AGREEMENT if any(groups) else True
