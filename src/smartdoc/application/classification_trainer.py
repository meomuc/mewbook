"""Training the smart classifier. Used by ``train.py`` -- never by the app.

The app only *reads* a finished model (domain/text_classifier.py); everything
that creates one is here, so the GUI process never loads training code and
starting the app costs nothing for it.

What training does, in order:

1. **Labels.** Books get a category from what the library already knows: a tag
   that names a category (or one of its aliases), the subject labels embedded in
   the file ("Fiction", "Hồi ký"), or the folder a book sits in when training
   from a folder-per-category dataset. Ambiguous books (two different
   categories) and unlabelled ones are not used as examples. A label a book got
   from the classifier itself is not trusted as truth (it would just teach the
   model its own mistakes).
2. **Seeds.** Each category's name, aliases and keywords (taxonomy.json) are
   turned into a starter vector, so a category with no example books yet -- e.g.
   one the user just added -- can still be recognised a little, and rarely-seen
   ones are not lost.
3. **Model.** TF-IDF *centroids*: each category becomes the average of its
   books' L2-normalised vectors (plus the seed), pruned to its strongest
   features. Every labelled book is used twice -- with and without the file's
   own subject labels and description -- so the model learns to read the body
   text instead of leaning on labels most books don't have.
4. **Honest evaluation and calibration.** A stratified slice of the labelled
   books is held out. The model is scored on it *without* the embedded labels
   (the hard, realistic case), its confidence scale is fitted so that "80%"
   means about 80%, and the abstain thresholds are chosen to reach a target
   precision -- the classifier would rather say nothing than tag a book wrongly.
5. **Optional self-training.** Books nobody labelled are classified by the model;
   the confident ones become extra (weaker) examples and the model is rebuilt.
   It is kept only if it does better on the held-out books.

Pure Python + the standard library: the trainer doesn't need numpy, and the
model it writes is read by the app without it.
"""
from __future__ import annotations

import logging
import math
import random
import re
import time
import unicodedata
from array import array
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from smartdoc.application.classification_features import FeatureExtractor, FeatureParts
from smartdoc.application.classification_stoplist import is_stopped
from smartdoc.domain.taxonomy import Taxonomy, fold
from smartdoc.domain.text_classifier import (
    DEFAULT_FEATURE_WEIGHTS,
    ClassInfo,
    TextClassifierModel,
    new_meta,
)
from smartdoc.infrastructure.vi_tokenizer import TextProcessor

logger = logging.getLogger(__name__)

# -- Compact per-document feature storage -----------------------------------------
#
# A library of 15,000 books at ~1,500 distinct tokens each is 20M+ (token, weight)
# pairs. As Python dicts that is over a gigabyte; as two parallel arrays of small
# ints/floats it is ~150 MB.


class Interner:
    """token <-> small int, shared by every document."""

    def __init__(self) -> None:
        self.index: dict[str, int] = {}
        self.tokens: list[str] = []

    def intern(self, token: str) -> int:
        found = self.index.get(token)
        if found is None:
            found = self.index[token] = len(self.tokens)
            self.tokens.append(token)
        return found


class Counts:
    """One sparse count vector: parallel arrays of interned ids and weights."""

    __slots__ = ("ids", "vals")

    def __init__(self, ids: array, vals: array) -> None:
        self.ids = ids
        self.vals = vals

    @classmethod
    def from_dict(cls, interner: Interner, counts: dict[str, float]) -> "Counts":
        ids = array("I")
        vals = array("f")
        for token, value in counts.items():
            ids.append(interner.intern(token))
            vals.append(value)
        return cls(ids, vals)

    def to_dict(self, interner: Interner) -> dict[str, float]:
        return {interner.tokens[i]: v for i, v in zip(self.ids, self.vals)}

    def __len__(self) -> int:
        return len(self.ids)


EMPTY = Counts(array("I"), array("f"))


@dataclass
class TrainingDoc:
    doc_id: str
    body: Counts = EMPTY
    plain: Counts = EMPTY
    """title + author + the user's own tags."""
    front: Counts = EMPTY
    """The start of the body counted again, scaled by the front weight being tried (see apply_front)."""
    front_shells: tuple[Counts, ...] = ()
    """Raw counts of the successive slices of the start of the body (weight 1), kept so other zone sizes / weights can be tried."""
    hints: Counts = EMPTY
    """embedded subject labels + description + table of contents."""
    label: str | None = None
    label_source: str = ""  # "tag" | "subject" | "dataset" | "pseudo"
    weight: float = 1.0
    subjects: tuple[str, ...] = ()
    body_words: int = 0
    trusted: bool = True
    """False for labels guessed from a title or by the model itself: they train
    the model but are never used to *judge* it."""
    group_key: str = ""
    """Copies of one book (same title, other format) share a key, so they end up
    on the same side of the train/held-out split instead of leaking across it."""

    def variant(self, *, hints: bool) -> Iterable[tuple[Counts, float]]:
        yield self.body, 1.0
        if len(self.front):
            yield self.front, 1.0
        if self.label_source != "title":
            # A label guessed from the title must not be learned back from the
            # title (the model would just memorise the cue words and read
            # nothing else); it learns from what the book actually says.
            yield self.plain, 1.0
        if hints:
            yield self.hints, 1.0

    def token_ids(self) -> set[int]:
        return set(self.body.ids) | set(self.front.ids) | set(self.plain.ids) | set(self.hints.ids)

    def merged(self, interner: Interner, *, hints: bool) -> dict[str, float]:
        counts: dict[str, float] = {}
        for part, _ in self.variant(hints=hints):
            for i, v in zip(part.ids, part.vals):
                token = interner.tokens[i]
                counts[token] = counts.get(token, 0.0) + v
        return counts


def doc_from_parts(interner: Interner, doc_id: str, parts: FeatureParts) -> TrainingDoc:
    return TrainingDoc(
        doc_id=doc_id,
        body=Counts.from_dict(interner, parts.body),
        plain=Counts.from_dict(interner, parts.plain),
        hints=Counts.from_dict(interner, parts.hints),
        front=Counts.from_dict(interner, parts.front),
        front_shells=tuple(Counts.from_dict(interner, shell) for shell in parts.front_shells),
        subjects=tuple(parts.subjects),
        body_words=parts.body_words,
    )


def apply_front(docs: Iterable[TrainingDoc], shells: int, weight: float) -> None:
    """Sets, on every doc, the front zone made of its first `shells` slices, counted `weight` times more (0 = no front zone).

    The zone is the start of the text (title page, contents, preface), where a book says what it is about; the rest of the body
    is a long, noisy tail that can drown it. The slices were counted once at extraction, so trying another size or weight is
    only a change of these arrays."""
    for doc in docs:
        if weight <= 0 or shells <= 0 or not doc.front_shells:
            doc.front = EMPTY
            continue
        ids, vals = array("I"), array("f")
        for shell in doc.front_shells[:shells]:
            ids.extend(shell.ids)
            vals.extend(v * weight for v in shell.vals)
        doc.front = Counts(ids, vals)


# -- Labelling --------------------------------------------------------------------


def label_from_metadata(taxonomy: Taxonomy, tags: str | Sequence[str] | None, subjects: Sequence[str]) -> tuple[str | None, str]:
    """(category id or None, source). A firm category tag wins over embedded
    subjects; two different categories mean the book is ambiguous and is not
    used as an example."""
    from_tags = taxonomy.categories_in_tags(tags)
    if len(from_tags) == 1:
        return from_tags[0].id, "tag"
    if len(from_tags) > 1:
        return None, "ambiguous"
    from_subjects = taxonomy.resolve_labels(subjects)
    if len(from_subjects) == 1:
        return from_subjects[0].id, "subject"
    return None, "ambiguous" if from_subjects else "none"


def non_category_tags(taxonomy: Taxonomy, tags: str | Sequence[str] | None) -> list[str]:
    return taxonomy.without_category_tags(list(tags) if tags and not isinstance(tags, str) else tags)


_WORDS_RE = re.compile(r"[\W_]+", re.UNICODE)


def _spaced(text: str) -> str:
    """" lowercase words " -- diacritics kept, everything else a single space."""
    return " " + _WORDS_RE.sub(" ", unicodedata.normalize("NFC", text).lower()).strip() + " "


def title_cues(taxonomy: Taxonomy) -> dict[str, list[tuple[str, str]]]:
    """Per category, its curated title cues as (lowercase with diacritics,
    folded) pairs. Categories without cues are simply never guessed."""
    return {c.id: [(_spaced(cue), " " + fold(cue) + " ") for cue in c.title_cues] for c in taxonomy if c.title_cues}


def label_from_title(cues: dict[str, list[tuple[str, str]]], title: str) -> str | None:
    """The category a title names, when it names exactly one. A guess, and used
    as one: it trains with a reduced weight, never grades the model.

    A title with Vietnamese diacritics is matched *with* them ("thuốc", medicine,
    must not match "thuộc", belonging to: "Pháp thuộc" isn't about medicine); a
    title typed without them (common for file-name-derived titles) can only be
    matched folded, and then only on cues long enough not to be ambiguous."""
    spaced, folded = _spaced(title), " " + fold(title) + " "
    has_diacritics = spaced.strip() != folded.strip()
    hits = set()
    for category_id, pairs in cues.items():
        for with_marks, without in pairs:
            if has_diacritics:
                matched = with_marks in spaced
            else:
                matched = len(without.strip()) >= 6 and without in folded
            if matched:
                hits.add(category_id)
                break
    return next(iter(hits)) if len(hits) == 1 else None


# -- Seeds ------------------------------------------------------------------------


def seed_counts(taxonomy: Taxonomy, processor: TextProcessor) -> dict[str, dict[str, float]]:
    """Per category, the tokens of its name/aliases (weight 2), keywords (1) and
    weak aliases (0.5). Each phrase is tokenised on its own, so no junk pairs
    are formed across neighbouring keywords."""
    seeds: dict[str, dict[str, float]] = {}
    for category in taxonomy:
        counts: dict[str, float] = {}
        for weight, phrases in ((2.0, (category.name, *category.aliases)), (1.0, category.keywords), (0.5, category.weak_aliases)):
            for phrase in phrases:
                for token in processor.tokens(phrase):
                    counts[token] = counts.get(token, 0.0) + weight
        seeds[category.id] = counts
    return seeds


# -- Model construction --------------------------------------------------------------


RELEASE_MIN_BOOKS = 5
RELEASE_MIN_BOOKS_PRIVATE = 10


# The front zone is read as slices so that other sizes can be tried without reading the books again: the first 1,000 characters
# (about one printed page: title page, imprint), then up to 2,000 (contents), then up to 4,000 (preface, first lines).
FRONT_SHELL_BOUNDS = (1000, 2000, 4000)
FRONT_ZONE_CANDIDATES = (1, 2, 3)  # how many slices make the zone: 1,000 / 2,000 / 4,000 characters
FRONT_WEIGHT_CANDIDATES = (2.0, 4.0)
FRONT_MIN_GAIN = 0.005  # a zone must beat "no zone" by half a point of macro F1: a smaller difference is luck on a small holdout


@dataclass
class TrainOptions:
    algorithm: str = "auto"
    """"svm" (linear SVM via scikit-learn -- far more accurate on overlapping
    categories), "centroid" (pure Python), or "auto": svm when scikit-learn is
    installed, else centroid."""
    seed_strength: float = 2.0
    """How many 'virtual books' the seed vector counts for."""
    seed_only_penalty: float = 0.7
    """(centroid) A category with no example books at all is scaled by this, so
    its lexicon can't out-shout categories the model actually knows."""
    top_features: int = 2500
    """(centroid) features kept per category."""
    max_features: int = 60000
    """(svm) vocabulary size: the commonest features. More adds nothing
    measurable and makes the model file bigger."""
    prune_k: int = 4000
    """(svm) largest-magnitude weights kept per category in the model file."""
    svm_c: float = 1.0
    class_weight_cap: float = 12.0
    """(svm) small categories are up-weighted, 'balanced' style, but never by
    more than this: a category with three examples shouldn't dominate."""
    synthetic_per_class: int = 60
    """(svm) A category with fewer than this many real books is topped up with
    made-up ones: a handful of its taxonomy keywords among everyday background
    words. Real books are the only thing that ever *judges* the model."""
    synthetic_weight: float = 0.5
    title_label_weight: float = 0.7
    min_df: int = 2
    min_books: int = 2
    """(svm) A token becomes a feature only if it occurs in at least this many *distinct books* (copies of one
    book in other formats count once). Taxonomy keywords are exempt. The model shipped with the app is trained
    with ``RELEASE_MIN_BOOKS`` so that names and phrases belonging to a handful of books -- which could identify
    the library it was trained on -- stay out of the vocabulary; a personal model on a small library keeps 2."""
    min_books_private: int = 0
    """(svm) A token that is not in the *text* of at least ``min_books`` books, and only reaches that count
    through titles, authors or the user's own tags, needs this many books instead: one prolific author or a
    personal hashtag must not be enough. 0 turns the rule off (the release settings use
    ``RELEASE_MIN_BOOKS_PRIVATE``)."""
    df_by_group: bool = True
    """(svm) Count document frequency per book (``group_key``) instead of per file."""
    use_stoplist: bool = True
    """(svm) Drop release-site / copyright / contact boilerplate (application/classification_stoplist.py)."""
    holdout_fraction: float = 0.2
    target_precision: float = 0.85
    max_per_class: int = 2000
    self_train_rounds: int = 0
    self_train_min_group_confidence: float = 0.85
    self_train_weight: float = 0.5
    refit_on_all: bool = True
    """After evaluating and calibrating on a held-out slice, refit on *all* the
    labelled books (the slice included) with the same settings. The reported
    numbers are the honest ones from the first fit."""
    self_train_tolerance: float = 0.02
    """Unlabelled books are usually a different kind of book from the labelled
    ones (that is why they are unlabelled), so a held-out set of *labelled* books
    cannot show self-training helping -- only that it does no harm. A round is
    kept if held-out accuracy drops by no more than this."""
    rng_seed: int = 13
    max_words: int = 3000
    front_weight: float = 0.0
    """Extra weight of the front zone (the start of the text) -- 0 = none. See apply_front."""
    front_shells: int = 1
    """How many of the FRONT_SHELL_BOUNDS slices make the front zone (1 = the first FRONT_SHELL_BOUNDS[0] characters)."""
    tune_front: bool = False
    """Try every FRONT_ZONE_CANDIDATES x FRONT_WEIGHT_CANDIDATES on the held-out books and keep the best macro F1 (costs one fit
    each; the plain no-front fit is the baseline it must beat)."""
    hinted_variant_weight: float = 0.4
    """Share of a book's weight given to its with-labels view (the rest goes to
    the view without them)."""


def _tfidf(counts: dict[int, float], idf: list[float]) -> dict[int, float]:
    raw: dict[int, float] = {}
    for i, tf in counts.items():
        weight = idf[i]
        if weight > 0 and tf > 0:
            raw[i] = ((1.0 + math.log(tf)) if tf >= 1 else tf) * weight
    norm = math.sqrt(sum(v * v for v in raw.values()))
    if norm == 0:
        return {}
    return {i: v / norm for i, v in raw.items()}


def _doc_counts(doc: TrainingDoc, *, hints: bool) -> dict[int, float]:
    counts: dict[int, float] = {}
    for part, _ in doc.variant(hints=hints):
        for i, v in zip(part.ids, part.vals):
            counts[i] = counts.get(i, 0.0) + v
    return counts


def sklearn_available() -> bool:
    try:
        import numpy  # noqa: F401
        import scipy.sparse  # noqa: F401
        import sklearn.svm  # noqa: F401
    except Exception:
        return False
    return True


def build_model(
    docs: Sequence[TrainingDoc],
    taxonomy: Taxonomy,
    interner: Interner,
    seeds: dict[str, dict[str, float]],
    options: TrainOptions,
    *,
    tokenizer_name: str = "pyvi",
    feature_weights: dict[str, float] | None = None,
    background: Sequence[TrainingDoc] = (),
) -> TextClassifierModel:
    """Fits a model on labelled `docs` (their .label must be a category id in
    `taxonomy`) with the algorithm `options` asks for.

    `background` are books without a usable label. They are never examples, but
    they are part of the library and say which words are everyday there: a phrase
    like "[Tóm tắt]" in the title of a thousand files must count as common, not
    as a rare and therefore telling word, when IDF is computed."""
    algorithm = options.algorithm
    if algorithm == "auto":
        algorithm = "svm" if sklearn_available() else "centroid"
    builder = build_model_svm if algorithm == "svm" else build_model_centroid
    return builder(
        docs, taxonomy, interner, seeds, options,
        tokenizer_name=tokenizer_name, feature_weights=feature_weights, background=background,
    )


def build_model_svm(
    docs: Sequence[TrainingDoc],
    taxonomy: Taxonomy,
    interner: Interner,
    seeds: dict[str, dict[str, float]],
    options: TrainOptions,
    *,
    tokenizer_name: str = "pyvi",
    feature_weights: dict[str, float] | None = None,
    background: Sequence[TrainingDoc] = (),
) -> TextClassifierModel:
    """Linear SVM (one-vs-rest) on L2-normalised sublinear TF-IDF, exported as
    a plain sparse linear model so the app can score it without numpy.

    The vocabulary is fixed *before* fitting and is exactly what the model
    file carries: the app L2-normalises a document over the tokens it knows,
    and that only matches how the weights were learned if training saw the same
    set. Each category's starter vector (its taxonomy keywords) is added as one
    extra training row, so a category with no books yet still gets a weight
    vector and every category is always present in the fit.

    Measured on this project's own library (books held out by title, embedded
    labels hidden): 70% top-1 and 88% right-folder, against 61%/88% and far lower
    macro-F1 for the centroid model -- large categories no longer swallow small ones.
    """
    import numpy as np
    from scipy.sparse import csr_matrix, vstack
    from sklearn.svm import LinearSVC

    categories = list(taxonomy)
    n_classes = len(categories)
    class_index = {c.id: i for i, c in enumerate(categories)}
    labelled = [d for d in docs if d.label in class_index]
    if not labelled:
        raise ValueError("no labelled documents to train on")

    # Document frequency, counted over distinct books unless told otherwise. A book that exists in two formats
    # is two TrainingDocs sharing a group_key; counting them twice would let a token that belongs to a single
    # book pass a "two books" threshold.
    by_book: dict[str, set[int]] = {}
    text_by_book: dict[str, set[int]] = {}
    for doc in list(labelled) + list(background):
        key = (doc.group_key or doc.doc_id) if options.df_by_group else f"{doc.doc_id}#{id(doc)}"
        by_book.setdefault(key, set()).update(doc.token_ids())
        text_by_book.setdefault(key, set()).update(doc.body.ids)
        text_by_book[key].update(doc.hints.ids)
    df: Counter[int] = Counter()
    for token_ids in by_book.values():
        df.update(token_ids)
    text_df: Counter[int] = Counter()
    for token_ids in text_by_book.values():
        text_df.update(token_ids)
    seed_ids = {cid: {interner.intern(t): w for t, w in counts.items()} for cid, counts in seeds.items()}
    seed_token_ids = {i for counts in seed_ids.values() for i in counts}

    n_docs = len(by_book)
    vocab_size = len(interner.tokens)
    df_array = np.zeros(vocab_size, dtype=np.int64)
    for token_id, count in df.items():
        df_array[token_id] = count
    text_df_array = np.zeros(vocab_size, dtype=np.int64)
    for token_id, count in text_df.items():
        text_df_array[token_id] = count
    seed_mask = np.zeros(vocab_size, dtype=bool)
    seed_mask[list(seed_token_ids)] = True
    allowed = df_array >= options.min_books
    if options.min_books_private:
        allowed &= (text_df_array >= options.min_books) | (df_array >= options.min_books_private)
    # The stoplist wins even over taxonomy keywords: "ebook" or "facebook" as a seed word is drowned out by the
    # same word as release-site boilerplate in thousands of files, which is what it exists to keep out.
    stop_mask = np.zeros(vocab_size, dtype=bool)
    if options.use_stoplist:
        stop_mask = np.fromiter((is_stopped(t) for t in interner.tokens), dtype=bool, count=vocab_size)
    candidates = np.where((allowed | seed_mask) & ~stop_mask)[0]
    if len(candidates) > options.max_features:
        # Seed words always stay; the rest are ranked by document frequency.
        rest = candidates[~seed_mask[candidates]]
        rest = rest[np.argsort(-df_array[rest], kind="stable")[: max(0, options.max_features - int(seed_mask[candidates].sum()))]]
        candidates = np.sort(np.concatenate([candidates[seed_mask[candidates]], rest]))
    n_features = len(candidates)
    column_of = np.full(vocab_size, -1, dtype=np.int64)
    column_of[candidates] = np.arange(n_features)
    unseen_idf = math.log(n_docs + 1) + 1.0
    idf = np.where(df_array[candidates] > 0, np.log((n_docs + 1) / (df_array[candidates] + 1.0)) + 1.0, unseen_idf)

    def row_vector(ids: np.ndarray, values: np.ndarray):
        """One document as (columns, L2-normalised sublinear tf-idf values)."""
        if len(ids) == 0:
            return np.empty(0, dtype=np.int64), np.empty(0)
        unique, inverse = np.unique(ids, return_inverse=True)
        summed = np.bincount(inverse, weights=values)
        columns = column_of[unique]
        keep = columns >= 0
        columns, summed = columns[keep], summed[keep]
        weights = np.where(summed >= 1.0, 1.0 + np.log(np.maximum(summed, 1e-9)), summed) * idf[columns]
        norm = math.sqrt(float((weights * weights).sum())) or 1.0
        return columns, weights / norm

    def doc_arrays(doc: TrainingDoc, with_hints: bool):
        parts = [p for p, _ in doc.variant(hints=with_hints) if len(p)]
        if not parts:
            return np.empty(0, dtype=np.int64), np.empty(0)
        return (
            np.concatenate([np.frombuffer(p.ids, dtype=np.uint32) for p in parts]).astype(np.int64),
            np.concatenate([np.frombuffer(p.vals, dtype=np.float32) for p in parts]).astype(np.float64),
        )

    indptr, indices, data = [0], [], []
    labels: list[int] = []
    sample_weight: list[float] = []

    def add_row(columns: np.ndarray, values: np.ndarray, label: int, weight: float) -> None:
        indices.append(columns)
        data.append(values)
        indptr.append(indptr[-1] + len(columns))
        labels.append(label)
        sample_weight.append(weight)

    per_class_docs = Counter()
    for doc in labelled:
        ci = class_index[doc.label]
        per_class_docs[ci] += 1
        if len(doc.hints):
            share = options.hinted_variant_weight
            add_row(*row_vector(*doc_arrays(doc, False)), ci, (1.0 - share) * doc.weight)
            add_row(*row_vector(*doc_arrays(doc, True)), ci, share * doc.weight)
        else:
            add_row(*row_vector(*doc_arrays(doc, False)), ci, doc.weight)
    # Background words: what a book "sounds like" whatever it is about, drawn in
    # proportion to how many books use each word. Made-up books mix a category's
    # keywords into this, so the fit learns the keywords, not the background.
    background_ids = np.where((df_array >= max(5, options.min_df)) & ~seed_mask)[0]
    background_p = df_array[background_ids].astype(np.float64)
    background_p /= background_p.sum() or 1.0
    rng = np.random.default_rng(options.rng_seed)

    for category in categories:
        ci = class_index[category.id]
        counts = seed_ids.get(category.id, {})
        if not counts:  # no keywords and no books: can never be predicted; keep the fit well-formed anyway
            add_row(np.empty(0, dtype=np.int64), np.empty(0), ci, 0.0)
            continue
        keyword_ids = np.fromiter(counts.keys(), dtype=np.int64, count=len(counts))
        keyword_w = np.fromiter(counts.values(), dtype=np.float64, count=len(counts))
        add_row(*row_vector(keyword_ids, keyword_w), ci, options.seed_strength)
        missing = options.synthetic_per_class - per_class_docs.get(ci, 0)
        for _ in range(max(0, missing)):
            k = int(rng.integers(3, 31))  # from a whisper of the topic to a book that is all about it
            picked = rng.choice(keyword_ids, size=k, p=keyword_w / keyword_w.sum())
            noise = (
                rng.choice(background_ids, size=int(rng.integers(150, 600)), p=background_p)
                if len(background_ids)
                else np.empty(0, dtype=np.int64)
            )
            ids = np.concatenate([picked, noise])
            add_row(*row_vector(ids, np.ones(len(ids))), ci, options.synthetic_weight)

    matrix = csr_matrix(
        (np.concatenate(data), np.concatenate(indices).astype(np.int32), np.asarray(indptr, dtype=np.int64)),
        shape=(len(labels), n_features),
    )
    labels_array = np.asarray(labels)
    n_with_data = sum(1 for n in per_class_docs.values() if n)
    class_weight = {
        ci: float(min(options.class_weight_cap, max(0.3, n_docs / (n_with_data * max(per_class_docs.get(ci, 0), 1)))))
        for ci in range(n_classes)
    }
    classifier = LinearSVC(C=options.svm_c, class_weight=class_weight, max_iter=2000)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "did not converge" is routine at this scale and the fit is still good
        classifier.fit(matrix, labels_array, sample_weight=np.asarray(sample_weight))

    # Back to class order (classes_ only lists categories seen in training).
    weights_matrix = np.zeros((n_classes, n_features))
    bias = [-1.0] * n_classes
    for row, class_id in enumerate(classifier.classes_):
        weights_matrix[class_id] = classifier.coef_[row]
        bias[class_id] = float(classifier.intercept_[row])
    for ci in range(n_classes):
        row = weights_matrix[ci]
        if int((row != 0).sum()) > options.prune_k:
            cutoff = np.sort(np.abs(row))[-options.prune_k]
            row[np.abs(row) < cutoff] = 0.0
    weights_matrix[np.abs(weights_matrix) < 1e-4] = 0.0

    postings: list[list[tuple[int, float]]] = [[] for _ in range(n_features)]
    class_rows, feature_cols = np.nonzero(weights_matrix)
    for ci, col in zip(class_rows.tolist(), feature_cols.tolist()):
        postings[col].append((ci, float(weights_matrix[ci, col])))

    sources = Counter(d.label_source for d in labelled)
    return TextClassifierModel(
        classes=[ClassInfo(c.id, c.name, c.group) for c in categories],
        features=[interner.tokens[i] for i in candidates.tolist()],
        idf=idf.tolist(),
        postings=postings,
        bias=bias,
        params={"weights": {**DEFAULT_FEATURE_WEIGHTS, **(feature_weights or {})}, "max_words": options.max_words,
                "front_chars": FRONT_SHELL_BOUNDS[max(1, min(options.front_shells, len(FRONT_SHELL_BOUNDS))) - 1]},
        meta={
            **new_meta(
                taxonomy_fingerprint=taxonomy.fingerprint(),
                tokenizer=tokenizer_name,
                trained_docs=len(labelled),
                sources={**dict(sources), "per_class": {categories[ci].id: -(-n // 10) * 10 for ci, n in per_class_docs.items()}},
            ),
            "algorithm": "linear-svm",
        },
    )


def build_model_centroid(
    docs: Sequence[TrainingDoc],
    taxonomy: Taxonomy,
    interner: Interner,
    seeds: dict[str, dict[str, float]],
    options: TrainOptions,
    *,
    tokenizer_name: str = "pyvi",
    feature_weights: dict[str, float] | None = None,
    background: Sequence[TrainingDoc] = (),
) -> TextClassifierModel:
    """The dependency-free fallback: TF-IDF centroids (Rocchio). Usable, but
    weaker where categories overlap -- prefer the SVM."""
    categories = list(taxonomy)
    class_index = {c.id: i for i, c in enumerate(categories)}
    labelled = [d for d in docs if d.label in class_index]

    # Document frequency over the labelled books (full view = with hints).
    df: Counter[int] = Counter()
    for doc in labelled:
        df.update(doc.token_ids())
    seed_ids = {cid: {interner.intern(t): w for t, w in counts.items()} for cid, counts in seeds.items()}
    seed_token_ids = {i for counts in seed_ids.values() for i in counts}

    n_docs = len(labelled)
    vocab_size = len(interner.tokens)
    unseen_idf = math.log(n_docs + 1) + 1.0
    idf = [0.0] * vocab_size
    for i in range(vocab_size):
        frequency = df.get(i, 0)
        if frequency >= options.min_df or i in seed_token_ids:
            idf[i] = math.log((n_docs + 1) / (frequency + 1)) + 1.0 if frequency else unseen_idf

    sums: list[defaultdict[int, float]] = [defaultdict(float) for _ in categories]
    per_class_docs = Counter()
    for doc in labelled:
        ci = class_index[doc.label]
        per_class_docs[ci] += 1
        has_hints = len(doc.hints) > 0
        if has_hints:
            shares = ((False, 1.0 - options.hinted_variant_weight), (True, options.hinted_variant_weight))
        else:
            shares = ((False, 1.0),)
        for with_hints, share in shares:
            vector = _tfidf(_doc_counts(doc, hints=with_hints), idf)
            factor = share * doc.weight
            target = sums[ci]
            for i, v in vector.items():
                target[i] += factor * v

    for category in categories:
        ci = class_index[category.id]
        seed_vector = _tfidf(seed_ids.get(category.id, {}), idf)
        for i, v in seed_vector.items():
            sums[ci][i] += options.seed_strength * v

    # Centroids: normalise, prune to the strongest features, renormalise.
    centroids: list[dict[int, float]] = []
    for ci, category in enumerate(categories):
        total = sums[ci]
        norm = math.sqrt(sum(v * v for v in total.values())) or 1.0
        top = sorted(((i, v / norm) for i, v in total.items()), key=lambda kv: kv[1], reverse=True)[: options.top_features]
        norm2 = math.sqrt(sum(v * v for _, v in top)) or 1.0
        scale = options.seed_only_penalty if per_class_docs[ci] == 0 else 1.0
        centroids.append({i: scale * v / norm2 for i, v in top})

    postings_by_id: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for ci, centroid in enumerate(centroids):
        for i, w in centroid.items():
            postings_by_id[i].append((ci, w))
    kept_ids = sorted(postings_by_id)

    weights = {**DEFAULT_FEATURE_WEIGHTS, **(feature_weights or {})}
    sources = Counter(d.label_source for d in labelled)
    model = TextClassifierModel(
        classes=[ClassInfo(c.id, c.name, c.group) for c in categories],
        features=[interner.tokens[i] for i in kept_ids],
        idf=[idf[i] if idf[i] > 0 else unseen_idf for i in kept_ids],
        postings=[postings_by_id[i] for i in kept_ids],
        params={"weights": weights, "max_words": options.max_words,
                "front_chars": FRONT_SHELL_BOUNDS[max(1, min(options.front_shells, len(FRONT_SHELL_BOUNDS))) - 1]},
        meta=new_meta(
            taxonomy_fingerprint=taxonomy.fingerprint(),
            tokenizer=tokenizer_name,
            trained_docs=n_docs,
            sources={**dict(sources), "per_class": {categories[ci].id: n for ci, n in per_class_docs.items()}},
        ),
    )
    return model


# -- Evaluation and calibration -----------------------------------------------------


@dataclass
class ClassReport:
    category_id: str
    support: int = 0
    predicted: int = 0
    correct: int = 0

    @property
    def precision(self) -> float:
        return self.correct / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.correct / self.support if self.support else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class EvalReport:
    n: int = 0
    accuracy: float = 0.0
    """Top-1 accuracy if the model always answered."""
    group_accuracy: float = 0.0
    """...and if only the sidebar folder had to be right."""
    macro_f1: float = 0.0
    coverage: float = 0.0
    """Share of books the model answers under its stored thresholds."""
    precision: float = 0.0
    """Accuracy on just those books."""
    per_class: list[ClassReport] = field(default_factory=list)
    confusions: list[tuple[str, str, int]] = field(default_factory=list)


def evaluate(model: TextClassifierModel, docs: Sequence[TrainingDoc], interner: Interner, *, hints: bool) -> EvalReport:
    report = EvalReport(n=len(docs))
    if not docs:
        return report
    groups = {c.id: c.group for c in model.classes}
    per_class: dict[str, ClassReport] = {c.id: ClassReport(c.id) for c in model.classes}
    confusions: Counter[tuple[str, str]] = Counter()
    correct = group_correct = answered = answered_correct = 0
    for doc in docs:
        prediction = model.predict(doc.merged(interner, hints=hints))
        truth = doc.label
        per_class.setdefault(truth, ClassReport(truth)).support += 1
        best = prediction.best_id
        if best is not None:
            per_class[best].predicted += 1
            if best == truth:
                correct += 1
                per_class[best].correct += 1
            else:
                confusions[(truth, best)] += 1
            if groups.get(best) == groups.get(truth):
                group_correct += 1
        if prediction.category_id is not None:
            answered += 1
            if prediction.category_id == truth:
                answered_correct += 1
    report.accuracy = correct / len(docs)
    report.group_accuracy = group_correct / len(docs)
    report.coverage = answered / len(docs)
    report.precision = answered_correct / answered if answered else 0.0
    report.per_class = sorted((c for c in per_class.values() if c.support), key=lambda c: -c.support)
    report.macro_f1 = sum(c.f1 for c in report.per_class) / len(report.per_class) if report.per_class else 0.0
    report.confusions = [(a, b, n) for (a, b), n in confusions.most_common(12)]
    return report


def calibrate(model: TextClassifierModel, docs: Sequence[TrainingDoc], interner: Interner, target_precision: float) -> dict:
    """Fits `scale` (so confidences are honest) and the abstain thresholds
    (so answers reach `target_precision`) on held-out books, *without* their
    embedded labels -- the case that matters. Among the settings that reach the
    target it takes the one that answers the most books; if none does, the most
    precise one that still answers a meaningful share. Returns the params set."""
    rows = []  # (scores, index of the truth or -1, distinct known tokens)
    class_ids = [c.id for c in model.classes]
    for doc in docs:
        vector = model.vectorize(doc.merged(interner, hints=False))
        if not vector:
            continue
        scores = model.scores(vector)
        truth = class_ids.index(doc.label) if doc.label in class_ids else -1
        rows.append((scores, truth, len(vector)))
    if len(rows) < 10:
        return {}

    def nll(scale: float) -> float:
        total = 0.0
        for scores, truth, _ in rows:
            if truth < 0:
                continue
            peak = max(scores)
            denom = sum(math.exp(scale * (s - peak)) for s in scores)
            total -= math.log(max(math.exp(scale * (scores[truth] - peak)) / denom, 1e-12))
        return total

    scale = min((1, 1.5, 2, 3, 4, 6, 8, 10, 12, 15, 20, 27, 35, 50, 65, 80, 100, 130), key=nll)
    groups = [c.group for c in model.classes]
    members: dict[str, list[int]] = defaultdict(list)
    for i, g in enumerate(groups):
        members[g].append(i)

    decided = []  # (best score, group prob, class prob, distinct tokens, correct)
    for scores, truth, matched in rows:
        peak = max(scores)
        exps = [math.exp(scale * (s - peak)) for s in scores]
        total = sum(exps)
        best = max(range(len(scores)), key=scores.__getitem__)
        group_prob = sum(exps[i] for i in members[groups[best]]) / total
        decided.append((scores[best], group_prob, exps[best] / total, matched, best == truth))

    ordered_scores = sorted(d[0] for d in decided)
    score_grid = sorted({round(ordered_scores[min(len(ordered_scores) - 1, k * len(ordered_scores) // 14)], 4) for k in range(14)})
    best_setting = None
    fallback = None
    for min_matched in (3, 5, 8):
        for min_score in score_grid:
            for min_group in (0.3, 0.45, 0.6, 0.75, 0.9):
                for min_class in (0.0, 0.3, 0.5, 0.7):
                    taken = [
                        d for d in decided
                        if d[0] >= min_score and d[1] >= min_group and d[2] >= min_class and d[3] >= min_matched
                    ]
                    if len(taken) < max(5, 0.02 * len(decided)):
                        continue
                    coverage = len(taken) / len(decided)
                    precision = sum(1 for d in taken if d[4]) / len(taken)
                    candidate = (coverage, precision, min_matched, min_score, min_group, min_class)
                    if precision >= target_precision and (best_setting is None or coverage > best_setting[0]):
                        best_setting = candidate
                    # No setting reaches the target: take the most precise one that still answers >= 15% of books.
                    if coverage >= 0.15 and (fallback is None or (precision, coverage) > (fallback[1], fallback[0])):
                        fallback = candidate
    chosen = best_setting or fallback
    result = {"scale": float(scale)}
    if chosen:
        result.update(min_matched=chosen[2], min_score=chosen[3], min_group_prob=chosen[4], min_class_prob=chosen[5])
        result["holdout_coverage"] = round(chosen[0], 3)
        result["holdout_precision"] = round(chosen[1], 3)
        result["target_reached"] = best_setting is not None
    model.params.update(result)
    return result


# -- Orchestration ---------------------------------------------------------------------


@dataclass
class TrainResult:
    model: TextClassifierModel
    report_plain: EvalReport
    report_hinted: EvalReport
    n_train: int
    n_holdout: int
    pseudo_added: int = 0
    notes: list[str] = field(default_factory=list)

    def to_text(self, taxonomy: Taxonomy | None = None) -> str:
        names = {c.id: c.name for c in taxonomy} if taxonomy else {}
        label = lambda cid: names.get(cid, cid)  # noqa: E731
        m, p = self.model, self.report_plain
        lines = [
            f"Trained on {self.n_train} books ({m.meta.get('algorithm', 'centroid')}), evaluated on {self.n_holdout} "
            f"held-out books (+{self.pseudo_added} self-training examples). Copies of a title stay on one side of the split.",
            f"Held-out, WITHOUT embedded labels (the realistic case):",
            f"  top-1 accuracy if it always answered : {p.accuracy:6.1%}",
            f"  right sidebar folder                  : {p.group_accuracy:6.1%}",
            f"  macro F1                              : {p.macro_f1:6.1%}",
            f"  with abstain thresholds -> answers {p.coverage:5.1%} of books, {p.precision:6.1%} of those correct",
            f"Held-out, WITH embedded labels: accuracy {self.report_hinted.accuracy:6.1%}, "
            f"answers {self.report_hinted.coverage:5.1%} at {self.report_hinted.precision:6.1%} precision",
            f"Calibration: scale={m.params['scale']}, min_score={m.params['min_score']}, "
            f"min_group_prob={m.params['min_group_prob']}, min_class_prob={m.params.get('min_class_prob', 0.0)}, "
            f"min_matched={m.params['min_matched']}, target precision reached: {m.params.get('target_reached', 'n/a')}",
            f"Model: {m.feature_count} features, {len(m.classes)} categories",
            "",
            "Per category (held-out):    support  precision  recall     F1",
        ]
        for c in p.per_class:
            lines.append(f"  {label(c.category_id)[:34]:34} {c.support:7d}  {c.precision:8.1%} {c.recall:7.1%} {c.f1:6.1%}")
        if p.confusions:
            lines.append("")
            lines.append("Most common mix-ups (truth -> predicted):")
            for truth, predicted, n in p.confusions:
                lines.append(f"  {label(truth)} -> {label(predicted)}: {n}")
        lines.extend(self.notes)
        return "\n".join(lines)


def split_holdout(docs: Sequence[TrainingDoc], options: TrainOptions) -> tuple[list[TrainingDoc], list[TrainingDoc]]:
    """Stratified and deterministic, and *by book*: every copy of a title (the
    same book in two formats, say) goes to the same side, or the held-out
    score would just measure how well the model remembers what it has already
    seen. Only books with a trusted label are ever held out; guessed labels
    (from a title) only train. Categories with fewer than 5 trusted books keep
    all of them for training (there'd be nothing meaningful to measure)."""
    rng = random.Random(options.rng_seed)
    by_key: dict[str, list[TrainingDoc]] = defaultdict(list)
    for doc in docs:
        by_key[doc.group_key or doc.doc_id].append(doc)
    trusted_per_class: Counter[str] = Counter(d.label for d in docs if d.trusted)
    keys_by_class: dict[str, list[str]] = defaultdict(list)
    for key, members in by_key.items():
        trusted = [d for d in members if d.trusted]
        if trusted:
            keys_by_class[Counter(d.label for d in trusted).most_common(1)[0][0]].append(key)

    held_keys: set[str] = set()
    for label in sorted(keys_by_class):
        if trusted_per_class[label] < 5:
            continue
        keys = sorted(keys_by_class[label])
        rng.shuffle(keys)
        target = int(round(trusted_per_class[label] * options.holdout_fraction))
        taken = 0
        for key in keys:
            if taken >= target:
                break
            held_keys.add(key)
            taken += sum(1 for d in by_key[key] if d.trusted)

    holdout = [d for d in docs if d.trusted and (d.group_key or d.doc_id) in held_keys]
    train_by_class: dict[str, list[TrainingDoc]] = defaultdict(list)
    for doc in docs:
        if (doc.group_key or doc.doc_id) not in held_keys:  # a guessed-label copy of a held-out title is dropped too
            train_by_class[doc.label].append(doc)
    train_docs: list[TrainingDoc] = []
    for label in sorted(train_by_class):
        members = sorted(train_by_class[label], key=lambda d: (not d.trusted, d.doc_id))
        rng.shuffle(members)
        train_docs.extend(members[: options.max_per_class])
    return train_docs, holdout


def _tune_front(options, train_docs, holdout, everyone, taxonomy, interner, seeds, tokenizer_name, unlabelled, log, notes) -> None:
    """Grid search over the front zone (its size and its extra weight), scored by macro F1 on the held-out books without their
    embedded labels -- the same yardstick as the final report. The no-front fit is the baseline: a zone is adopted only if it
    beats it, so on a library where it does not help, the model is the one that would have been trained without this option.
    Sets `options.front_weight` / `options.front_shells` (and applies them to `everyone`)."""
    def score(shells: int, weight: float) -> tuple[float, float]:
        apply_front(everyone, shells, weight)
        trial = replace(options, front_shells=shells, front_weight=weight)
        model = build_model(train_docs, taxonomy, interner, seeds, trial, tokenizer_name=tokenizer_name,
                            background=unlabelled, feature_weights={"front": weight})
        calibrate(model, holdout, interner, options.target_precision)
        report = evaluate(model, holdout, interner, hints=False)
        return report.macro_f1, report.accuracy

    base = score(1, 0.0)
    best, best_score = (1, 0.0), base
    lines = [f"Front zone search (held-out macro F1 / accuracy): none {base[0]:.1%} / {base[1]:.1%}"]
    for shells in FRONT_ZONE_CANDIDATES:
        for weight in FRONT_WEIGHT_CANDIDATES:
            result = score(shells, weight)
            lines.append(f"  first {FRONT_SHELL_BOUNDS[shells - 1]} characters x{weight:g}: {result[0]:.1%} / {result[1]:.1%}")
            if result[0] >= best_score[0] + FRONT_MIN_GAIN if best[1] == 0 else result > best_score:
                best, best_score = (shells, weight), result
    options.front_shells, options.front_weight = best
    apply_front(everyone, *best)
    lines.append("  -> " + (f"kept first {FRONT_SHELL_BOUNDS[best[0] - 1]} characters x{best[1]:g}" if best[1] > 0
                            else "no front zone helps on this library; none used"))
    for line in lines:
        log(line)
    notes.extend(lines)


def train(
    labelled: Sequence[TrainingDoc],
    taxonomy: Taxonomy,
    interner: Interner,
    processor: TextProcessor,
    options: TrainOptions | None = None,
    unlabelled: Sequence[TrainingDoc] = (),
    log: Callable[[str], None] | None = None,
) -> TrainResult:
    options = options or TrainOptions()
    log = log or (lambda _msg: None)
    labelled = [d for d in labelled if d.label in taxonomy]
    seeds = seed_counts(taxonomy, processor)
    tokenizer_name = processor.segmenter_name if processor.segmenter_name != "unresolved" else "pyvi"

    train_docs, holdout = split_holdout(labelled, options)
    log(f"split: {len(train_docs)} train / {len(holdout)} held out")
    notes: list[str] = []
    if options.tune_front:
        options = replace(options)  # the caller's options are not changed by what the search picks
        _tune_front(options, train_docs, holdout, list(labelled) + list(unlabelled), taxonomy, interner, seeds, tokenizer_name,
                    unlabelled, log, notes)
    else:
        apply_front(list(labelled) + list(unlabelled), options.front_shells, options.front_weight)
    front = {"front": options.front_weight}
    model = build_model(train_docs, taxonomy, interner, seeds, options, tokenizer_name=tokenizer_name, background=unlabelled,
                        feature_weights=front)
    calibrate(model, holdout, interner, options.target_precision)
    report_plain = evaluate(model, holdout, interner, hints=False)
    pseudo_added = 0

    for round_number in range(1, options.self_train_rounds + 1):
        pseudo = []
        for doc in unlabelled:
            prediction = model.predict(doc.merged(interner, hints=True))
            if prediction.category_id and prediction.group_confidence >= options.self_train_min_group_confidence:
                clone = TrainingDoc(
                    doc_id=doc.doc_id, body=doc.body, plain=doc.plain, hints=doc.hints, front=doc.front,
                    front_shells=doc.front_shells, label=prediction.category_id,
                    label_source="pseudo", weight=options.self_train_weight, subjects=doc.subjects, body_words=doc.body_words,
                    trusted=False, group_key=doc.group_key,
                )
                pseudo.append(clone)
        log(f"self-training round {round_number}: {len(pseudo)} of {len(unlabelled)} unlabelled books are confident enough")
        if not pseudo:
            break
        candidate = build_model(
            train_docs + pseudo, taxonomy, interner, seeds, options, tokenizer_name=tokenizer_name, background=unlabelled,
            feature_weights=front,
        )
        calibrate(candidate, holdout, interner, options.target_precision)
        candidate_report = evaluate(candidate, holdout, interner, hints=False)
        better = candidate_report.accuracy >= report_plain.accuracy - options.self_train_tolerance
        notes.append(
            f"Self-training round {round_number}: {len(pseudo)} pseudo-labelled books, held-out accuracy "
            f"{report_plain.accuracy:.1%} -> {candidate_report.accuracy:.1%} ({'kept' if better else 'discarded: it hurt'})."
        )
        if not better:
            break
        model, report_plain, pseudo_added = candidate, candidate_report, len(pseudo)
        train_docs = train_docs + pseudo

    report_hinted = evaluate(model, holdout, interner, hints=True)

    evaluation = {
        "holdout_books": len(holdout),
        "accuracy": round(report_plain.accuracy, 4),
        "folder_accuracy": round(report_plain.group_accuracy, 4),
        "coverage": round(report_plain.coverage, 4),
        "precision": round(report_plain.precision, 4),
        "note": "held out by title, embedded labels hidden",
    }
    if options.refit_on_all and holdout:
        # Same settings and calibration, but every labelled book gets to teach it.
        calibrated = {k: v for k, v in model.params.items() if k not in ("weights", "max_words", "front_chars")}
        final = build_model(
            train_docs + holdout, taxonomy, interner, seeds, options, tokenizer_name=tokenizer_name, background=unlabelled,
            feature_weights=front,
        )
        final.params.update(calibrated)
        model = final
        notes.append(f"Final model refit on all {len(train_docs) + len(holdout)} labelled books (the numbers above are from the fit that did not see the held-out ones).")
    model.meta["evaluation"] = evaluation
    return TrainResult(
        model=model, report_plain=report_plain, report_hinted=report_hinted,
        n_train=len(train_docs) - pseudo_added, n_holdout=len(holdout), pseudo_added=pseudo_added, notes=notes,
    )


# -- Reading books from disk (the slow, I/O-bound part) ----------------------------------

_SUPPORTED_SUFFIXES = {".pdf", ".epub", ".mobi", ".azw3", ".azw", ".prc"}


def collect_dataset_folder(root: Path, taxonomy: Taxonomy) -> tuple[list[dict], list[str]]:
    """A folder-per-category dataset: root/<category>/**/<book files>. The
    folder is matched against category ids, names and aliases. Returns the
    extraction jobs (with `label`) and warnings for folders that matched no
    category."""
    jobs: list[dict] = []
    warnings: list[str] = []
    by_id = {c.id: c for c in taxonomy}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        category = by_id.get(folder.name.lower()) or taxonomy.match_label(folder.name, include_weak=False) or taxonomy.match_label(folder.name)
        if category is None:
            warnings.append(f"folder {folder.name!r} matches no category -- skipped")
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
                jobs.append({
                    "id": f"dataset:{path}", "title": path.stem, "author": "", "tags": [], "path": str(path),
                    "extension": path.suffix.lower().lstrip("."), "label": category.id, "label_source": "dataset",
                })
    return jobs, warnings


_WORKER: dict = {}


def _init_extract_worker(settings: dict) -> None:
    from smartdoc.application.classify_worker import lower_process_priority

    if settings.get("low_priority", True):
        lower_process_priority()
    _WORKER["extractor"] = FeatureExtractor(weights=settings.get("weights"), max_words=settings.get("max_words", 3000),
                                            shell_bounds=FRONT_SHELL_BOUNDS)


def _extract_job(job: dict) -> tuple[dict, dict | None]:
    extractor: FeatureExtractor = _WORKER["extractor"]
    try:
        parts = extractor.extract(
            title=job.get("title", ""), author=job.get("author", ""), tags=job.get("tags", ()),
            path=job.get("path"), extension=job.get("extension"),
        )
    except Exception as exc:  # keep the run alive; the job is reported as failed
        return job, {"error": f"{type(exc).__name__}: {exc}"}
    return job, {"body": parts.body, "plain": parts.plain, "hints": parts.hints, "subjects": parts.subjects,
                 "words": parts.body_words, "error": parts.error, "front_shells": parts.front_shells}


def extract_jobs(
    jobs: Sequence[dict], *, workers: int, max_words: int, weights: dict[str, float] | None = None,
    progress: Callable[[int, int], None] | None = None, low_priority: bool = True,
) -> Iterable[tuple[dict, dict | None]]:
    """Reads and tokenises many books. With workers > 1 it uses a pool of
    processes (each loads its own segmenter); with 1, it runs in this process,
    which is what the tests use."""
    settings = {"max_words": max_words, "weights": weights, "low_priority": low_priority and workers > 1}
    total = len(jobs)
    if workers <= 1:
        _init_extract_worker(settings)
        for done, job in enumerate(jobs, 1):
            yield _extract_job(job)
            if progress and done % 50 == 0:
                progress(done, total)
        return
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    with context.Pool(workers, initializer=_init_extract_worker, initargs=(settings,)) as pool:
        for done, item in enumerate(pool.imap_unordered(_extract_job, jobs, chunksize=16), 1):
            yield item
            if progress and done % 100 == 0:
                progress(done, total)


def docs_from_extraction(
    extracted: Iterable[tuple[dict, dict | None]], taxonomy: Taxonomy, interner: Interner,
    *, title_weight: float = 0.7, use_title_rules: bool = True,
) -> tuple[list[TrainingDoc], list[TrainingDoc], Counter]:
    """(labelled, unlabelled, stats). A job may carry a fixed `label` (dataset
    folders) or be labelled from its tags / embedded subjects; failing that, a
    book whose *title* clearly names one category gets that as a low-weight,
    untrusted label (see label_from_title)."""
    labelled: list[TrainingDoc] = []
    unlabelled: list[TrainingDoc] = []
    stats: Counter = Counter()
    cues = title_cues(taxonomy) if use_title_rules else {}
    for job, result in extracted:
        if result is None or result.get("body") is None:
            stats["failed"] += 1
            continue
        parts = FeatureParts(
            body=result["body"], plain=result["plain"], hints=result["hints"], subjects=result["subjects"],
            body_words=result["words"], error=result["error"], front_shells=result.get("front_shells") or [],
        )
        doc = doc_from_parts(interner, job["id"], parts)
        doc.group_key = fold(job.get("title", ""))[:60] or job["id"]
        if not parts.body_words:
            stats["no_text"] += 1
        if job.get("label"):
            doc.label, doc.label_source = job["label"], job.get("label_source", "dataset")
        else:
            label, source = label_from_metadata(taxonomy, job.get("raw_tags", ""), parts.subjects)
            if label:
                doc.label, doc.label_source = label, source
            else:
                guessed = label_from_title(cues, job.get("title", "")) if cues and source == "none" else None
                if guessed:
                    doc.label, doc.label_source, doc.trusted = guessed, "title", False
                else:
                    stats[f"unlabelled_{source}"] += 1
        if doc.label:
            doc.weight = {"tag": 1.5, "title": title_weight}.get(doc.label_source, 1.0)
            labelled.append(doc)
            stats[f"label_{doc.label_source}"] += 1
        else:
            unlabelled.append(doc)
    return labelled, unlabelled, stats


if __name__ == "__main__":
    # Self-test on synthetic books (no files, no segmenter): three tiny
    # categories with distinct vocabularies.
    taxonomy = Taxonomy.load_builtin()
    processor = TextProcessor(segmenter=None)
    interner = Interner()
    rng = random.Random(1)
    vocab = {
        "programming": "python code function variable compiler software developer algorithm database server".split(),
        "cooking": "recipe ingredients chicken sauce oven bake kitchen dish spice dessert".split(),
        "crime_mystery": "detective murder suspect victim police clue alibi killer investigation forensic".split(),
    }
    noise = "the book chapter introduction people world story life time way".split()
    docs = []
    for label, words in vocab.items():
        for n in range(40):
            tokens = [rng.choice(words) for _ in range(60)] + [rng.choice(noise) for _ in range(30)]
            counts: dict[str, float] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0.0) + 1
            docs.append(TrainingDoc(doc_id=f"{label}-{n}", body=Counts.from_dict(interner, counts),
                                    plain=Counts.from_dict(interner, {"title_" + label[:3]: 3.0}), label=label, label_source="tag"))

    result = train(docs, taxonomy, interner, processor, TrainOptions(min_df=2, top_features=200))
    print(result.to_text(taxonomy).splitlines()[0:9])
    assert result.report_plain.accuracy > 0.95, result.report_plain.accuracy

    # A category with no books at all is still recognised a little, from its seed vocabulary.
    fresh = result.model.predict({"pizza": 2.0, "recipe": 3.0, "ingredients": 2.0, "chicken": 2.0, "oven": 1.0, "spice": 2.0})
    assert fresh.best_id == "cooking", fresh
    print("trainer self-test OK")
