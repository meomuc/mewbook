"""Document -> weighted feature counts, shared by the trainer and the worker.

A book is described to the classifier by six kinds of text, each counted with
its own weight (the weights live in the model, see
domain/text_classifier.DEFAULT_FEATURE_WEIGHTS, so training and prediction can
never disagree):

    title, author, the user's own (non-category) tags   what the library knows
    subject labels stored in the file itself            "Fiction", "Hồi ký"
    description + table-of-contents chapter titles      short and informative
    the first ~3,000 words of the body                  the actual content

The parts are kept apart in :class:`FeatureParts` because the trainer needs
each book *twice*: once with everything, and once without the file's subject
labels and description. Those labels are also how many training books got
their category in the first place, so a model that only ever saw them would
learn to lean on them and read the body badly -- while most books to be
classified have no such labels.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from smartdoc.domain.taxonomy import fold
from smartdoc.domain.text_classifier import DEFAULT_FEATURE_WEIGHTS, DEFAULT_FRONT_CHARS
from smartdoc.infrastructure.text_sampler import DEFAULT_MAX_WORDS, TextSampler
from smartdoc.infrastructure.vi_tokenizer import TextProcessor

_UNKNOWN_AUTHORS = frozenset({"", "unknown", "khong ro", "chua xac dinh", "nhieu tac gia", "khuyet danh", "anonymous"})


@dataclass
class FeatureParts:
    body: dict[str, float] = field(default_factory=dict)
    front: dict[str, float] = field(default_factory=dict)
    """The first zone of the body counted a second time, with the "front" weight (empty when that weight is 0)."""
    front_shells: list[dict[str, float]] = field(default_factory=list)
    """Training only: raw (weight 1) counts of the successive slices of the start of the body, so the trainer can try other zone
    sizes and weights without reading the books again (see FeatureExtractor.shell_bounds)."""
    plain: dict[str, float] = field(default_factory=dict)
    """title + author + the user's own tags."""
    hints: dict[str, float] = field(default_factory=dict)
    """subject labels + description + table of contents."""
    subjects: list[str] = field(default_factory=list)
    body_words: int = 0
    body_text: str = ""
    """The sampled running text itself (the guards in classification_guards.py judge it again, in slices)."""
    source: str = "none"
    error: str = ""

    def merged(self, *, hints: bool = True) -> dict[str, float]:
        """One counts dict. `hints=False` is the "this book has no embedded
        labels" view."""
        counts = dict(self.body)
        parts = (self.front, self.plain, self.hints) if hints else (self.front, self.plain)
        for part in parts:
            for token, value in part.items():
                counts[token] = counts.get(token, 0.0) + value
        return counts


def front_zone(text: str, start: int, end: int) -> str:
    """text[start:end] moved to word boundaries, so that neighbouring slices share no half word and lose none."""
    def edge(position: int) -> int:
        if position <= 0:
            return 0
        if position >= len(text):
            return len(text)
        following = text.find(" ", position)
        return len(text) if following < 0 else following
    return text[edge(start):edge(end)]


class FeatureExtractor:
    def __init__(
        self,
        weights: dict[str, float] | None = None,
        max_words: int = DEFAULT_MAX_WORDS,
        processor: TextProcessor | None = None,
        sampler: TextSampler | None = None,
        front_chars: int = DEFAULT_FRONT_CHARS,
        shell_bounds: tuple[int, ...] = (),
    ) -> None:
        self.front_chars = front_chars
        self.shell_bounds = tuple(shell_bounds)
        """Training: character offsets closing each slice of the front zone, e.g. (1000, 2000, 4000)."""
        self.weights = {**DEFAULT_FEATURE_WEIGHTS, **(weights or {})}
        self.sampler = sampler or TextSampler(max_words)
        self.processor = processor or TextProcessor()

    def extract(
        self,
        *,
        title: str = "",
        author: str = "",
        tags: Iterable[str] = (),
        path: str | None = None,
        extension: str | None = None,
    ) -> FeatureParts:
        """`tags` must already exclude the taxonomy's own category tags --
        those are the answer, not a clue."""
        w = self.weights
        counts = self.processor.weighted_counts

        sample = self.sampler.sample(path, extension) if path else None
        parts = FeatureParts()
        if sample is not None:
            parts.source, parts.error, parts.subjects = sample.source, sample.error, list(sample.subjects)
            parts.body_words = sample.body_words
            parts.body_text = sample.body
            parts.body = counts([(sample.body, w["body"])])
            parts.hints = counts(
                [(subject, w["subject"]) for subject in sample.subjects] + [(sample.hint_text, w["hint"])]
            )
            if w["front"] > 0:
                parts.front = counts([(front_zone(sample.body, 0, self.front_chars), w["front"])])
            if self.shell_bounds:
                edges = (0, *self.shell_bounds)
                parts.front_shells = [counts([(front_zone(sample.body, a, b), 1.0)]) for a, b in zip(edges, edges[1:])]

        author_text = "" if fold(author) in _UNKNOWN_AUTHORS else author
        parts.plain = counts(
            [(title, w["title"]), (author_text, w["author"])] + [(tag, w["tag"]) for tag in tags if tag]
        )
        return parts


if __name__ == "__main__":
    import tempfile
    import zipfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        epub = Path(tmp) / "book.epub"
        with zipfile.ZipFile(epub, "w") as zf:
            zf.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                        '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
            zf.writestr(
                "OEBPS/content.opf",
                '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<metadata><dc:subject>Trinh thám</dc:subject></metadata>"
                '<manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                '<spine><itemref idref="c1"/></spine></package>',
            )
            zf.writestr("OEBPS/c1.xhtml", "<html><body><p>Thám tử điều tra vụ án mạng bí ẩn tại hiện trường.</p></body></html>")

        extractor = FeatureExtractor(processor=TextProcessor(segmenter=None))
        parts = extractor.extract(title="Vụ án bí ẩn", author="Unknown", path=str(epub), extension="epub")
        print("subjects:", parts.subjects, "| body tokens:", len(parts.body), "| plain:", sorted(parts.plain)[:6])
        assert parts.subjects == ["Trinh thám"]
        assert "tham" in parts.hints or "trinh" in parts.hints
        assert set(parts.merged(hints=False)) < set(parts.merged(hints=True)) | set(parts.merged(hints=False))
        assert not any(t in parts.plain for t in ("unknown",))  # "Unknown" author is not a clue
        print("feature extractor self-test OK")
