"""Text -> feature tokens for the smart classifier (Vietnamese-aware).

The trainer (``train.py``) and the classifier both build their features here,
so a book is turned into exactly the same tokens when the model learns from it
and when the model later reads it.

Vietnamese is written with a space between *syllables*, not words, so a plain
split reads "văn học thế giới" as four unrelated tokens. `pyvi` segments it
into words -- "văn_học thế_giới" -- which is what lets a classifier tell
"học" (study) apart from "văn_học" (literature). Text without Vietnamese
diacritics -- English, or Vietnamese typed without accents, which is common
in file-name-derived titles like "Nghe Thuat Ban Hang" -- is not segmented;
its adjacent word pairs are added as features instead ("nghe_thuat",
"machine_learning"), which lines up with the compounds pyvi produces for the
accented spelling. Every token is finally reduced to lowercase ASCII, so
"văn_học" and "van_hoc" are the same feature.

Weight of the dependency: importing pyvi pulls in scikit-learn, scipy and
numpy (~100 MB of RAM, seconds on a cold disk). It is therefore imported
lazily -- on the first Vietnamese text -- and this module is meant to run
inside the short-lived classification worker process, never in the GUI
process (see application/classify_worker.py). An English-only library never
loads it at all.
"""
from __future__ import annotations

import functools
import logging
import re
import unicodedata
import warnings
from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

Segmenter = Callable[[str], str]

# Letters that exist only in Vietnamese (not French/Spanish/Portuguese, which
# share plain acute/grave accents): the tell-tale for "this text is
# Vietnamese and has its diacritics".
_VIETNAMESE_ONLY_LETTERS = frozenset(
    "ăằắẳẵặầấẩẫậềếểễệồốổỗộơờớởỡợưừứửữựỳỷỹỵạảãẹẻẽịỉĩọỏụủũđ"
    "ĂẰẮẲẴẶẦẤẨẪẬỀẾỂỄỆỒỐỔỖỘƠỜỚỞỠỢƯỪỨỬỮỰỲỶỸỴẠẢÃẸẺẼỊỈĨỌỎỤỦŨĐ"
)
_VIETNAMESE_RATIO_THRESHOLD = 0.012  # of all letters; real Vietnamese runs ~15-25%

_URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.IGNORECASE)
_LETTER_RUN_RE = re.compile(r"[^\W\d_]+(?:_[^\W\d_]+)*", re.UNICODE)  # words, keeping pyvi's "_" joins
_TOKEN_OK_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REPEATED_CHAR_RE = re.compile(r"(.)\1{3,}")

MIN_TOKEN_LENGTH = 2
MAX_TOKEN_LENGTH = 28

_VIETNAMESE_STOPWORDS = """
và của là có các những một được trong cho không với đến từ này đó khi như cũng đã sẽ đang rất hay hoặc nếu thì mà
để về trên dưới sau trước ra vào lên xuống bị bởi do vì nên cả mỗi mọi nhiều ít còn vẫn lại đều chỉ cùng theo tại qua
bằng thế vậy gì nào ai đâu sao ấy kia đây ở nhưng cứ mới rồi luôn thật đã_là như_vậy bên giữa cái con việc
""".split()
_ENGLISH_STOPWORDS = """
the of and to in a is that for it as was with be by on not he i this are or his from at which but have an had they you
were their one all we can her has there been if more when will would who so no she my than into its them up about do
out what some could other me then now only your over also just like these him our any how most such very may must
should shall did does done being am us us yet still each both few many much own same too again here where why
""".split()


@functools.lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    return frozenset(fold_token(w) for w in (*_VIETNAMESE_STOPWORDS, *_ENGLISH_STOPWORDS))


@functools.lru_cache(maxsize=200_000)
def fold_token(token: str) -> str:
    """Lowercase ASCII form of one token: "Cuộc_Sống" -> "cuoc_song"."""
    lowered = token.lower().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFD", lowered) if unicodedata.category(ch) != "Mn")


def looks_vietnamese(text: str) -> bool:
    """True when the text is Vietnamese *with* its diacritics."""
    letters = vietnamese = 0
    for ch in text:
        if ch.isalpha():
            letters += 1
            if ch in _VIETNAMESE_ONLY_LETTERS:
                vietnamese += 1
    return letters >= 20 and vietnamese / letters >= _VIETNAMESE_RATIO_THRESHOLD


class SegmenterUnavailable(RuntimeError):
    pass


def load_pyvi_segmenter() -> Segmenter:
    """pyvi's tokenizer, imported on demand. The import is where the
    scikit-learn/scipy/numpy cost is paid, hence "on demand"."""
    try:
        with warnings.catch_warnings():
            # pyvi ships un-raw regex strings that Python 3.12 flags at compile time.
            warnings.simplefilter("ignore")
            from pyvi import ViTokenizer
    except Exception as exc:  # ImportError, or a broken scikit-learn/pickle pairing
        raise SegmenterUnavailable(f"pyvi is not usable: {exc}") from exc
    return ViTokenizer.tokenize


def _decap_shouting(text: str) -> str:
    """"LÁ RỤNG VỀ ĐÂU?" -> "lá rụng về đâu?" line by line. pyvi's model
    was trained on ordinary mixed-case prose and segments all-caps text
    badly; headings and titles are very often all caps."""
    if not any(ch.isupper() for ch in text):
        return text
    return "\n".join(line.lower() if line.isupper() else line for line in text.split("\n"))


class TextProcessor:
    """Turns text into feature tokens. Stateless apart from the (lazily
    loaded) segmenter, so one instance can be reused for a whole batch."""

    def __init__(self, segmenter: Segmenter | None | str = "auto") -> None:
        self._segmenter_spec = segmenter
        self._segmenter: Segmenter | None = None
        self._segmenter_resolved = False
        self.segmenter_name = "unresolved"

    # -- Segmenter -------------------------------------------------------

    def _resolve_segmenter(self) -> Segmenter | None:
        if self._segmenter_resolved:
            return self._segmenter
        self._segmenter_resolved = True
        if callable(self._segmenter_spec):
            self._segmenter, self.segmenter_name = self._segmenter_spec, "custom"
        elif self._segmenter_spec == "auto":
            try:
                self._segmenter, self.segmenter_name = load_pyvi_segmenter(), "pyvi"
            except SegmenterUnavailable as exc:
                # Degrade rather than fail: word pairs stand in for the
                # segmenter's compounds. Accuracy drops a little; the
                # feature keeps working.
                logger.warning("%s -- falling back to syllable pairs for Vietnamese text", exc)
                self._segmenter, self.segmenter_name = None, "fallback"
        else:
            self._segmenter, self.segmenter_name = None, "none"
        return self._segmenter

    # -- Tokenizing ------------------------------------------------------

    def tokens(self, text: str | None) -> list[str]:
        """Feature tokens of one piece of text, in reading order, with
        repeats (the caller counts them)."""
        if not text or not text.strip():
            return []
        text = unicodedata.normalize("NFC", _URL_RE.sub(" ", text))
        segmenter = self._resolve_segmenter() if looks_vietnamese(text) else None
        if segmenter is not None:
            try:
                text = segmenter(_decap_shouting(text))
            except Exception:  # a pathological input must not sink the whole document
                logger.debug("segmenter failed on a text of %d chars", len(text), exc_info=True)
            return self._filter(_LETTER_RUN_RE.findall(text))
        # Not segmented (English, or Vietnamese without accents): plain words
        # plus adjacent pairs.
        words = self._filter(_LETTER_RUN_RE.findall(text))
        return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]

    @staticmethod
    def _filter(raw_tokens: Iterable[str]) -> list[str]:
        stop = stopwords()
        kept: list[str] = []
        for raw in raw_tokens:
            token = fold_token(raw)
            if (
                MIN_TOKEN_LENGTH <= len(token) <= MAX_TOKEN_LENGTH
                and token not in stop
                and _TOKEN_OK_RE.match(token)
                and not _REPEATED_CHAR_RE.search(token)
            ):
                kept.append(token)
        return kept

    def weighted_counts(self, parts: Iterable[tuple[str | None, float]]) -> dict[str, float]:
        """Term counts over several pieces of text, each with its own
        weight -- a book's title counts for more than a line of body text."""
        counts: dict[str, float] = {}
        for text, weight in parts:
            if weight <= 0:
                continue
            for token in self.tokens(text):
                counts[token] = counts.get(token, 0.0) + weight
        return counts


if __name__ == "__main__":
    assert fold_token("Cuộc_Sống") == "cuoc_song"
    assert looks_vietnamese("Cuốn sách này kể về cuộc sống của những con người bình thường ở miền quê")
    assert not looks_vietnamese("Learning Python: programming for beginners and data science")
    assert not looks_vietnamese("Nghe thuat ban hang bac cao cua Zig Ziglar")

    processor = TextProcessor()
    vietnamese = processor.tokens("Văn học thế giới và lịch sử Việt Nam trong cuốn sách này, dành cho bạn đọc trẻ.")
    print("vi :", vietnamese, f"[{processor.segmenter_name}]")
    print("en :", processor.tokens("Machine learning for beginners, with Python and data science"))
    print("asc:", processor.tokens("Nghe thuat ban hang bac cao"))
    assert "van_hoc" in vietnamese or "van" in vietnamese

    fake = TextProcessor(segmenter=lambda s: s.replace("văn học", "văn_học"))
    assert "van_hoc" in fake.tokens("Nền văn học thế giới của chúng ta ngày nay thật phong phú và đa dạng, thưa bạn đọc")
    print("weighted:", TextProcessor(segmenter=None).weighted_counts([("python python code", 1.0), ("python", 3.0)]))
