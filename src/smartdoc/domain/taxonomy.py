"""Smart-classification taxonomy: the controlled vocabulary of categories.

The original spec asks for "Smart Tags có kiểm soát" -- tags kept under
control so the library doesn't fill up with duplicates and junk (FR2.3). The
smart classifier therefore never invents a label: every prediction is one of
the categories defined here. A category has

- ``name``   the hashtag written onto a document ("Tiểu thuyết"),
- ``group``  the folder the hashtag is filed under in the sidebar's Hashtag
             tree ("Văn học") -- the "sắp xếp" half of "phân loại và sắp xếp",
- ``aliases`` other spellings/labels that unambiguously mean this category
             ("novel", "truyện dài") -- used to recognise a document that is
             already categorised (by its tags or by the subjects embedded in
             the file) and to turn those labels into training data,
- ``weak_aliases`` labels that only *hint* at it ("fiction" says a book is a
             story, not which genre): they count as training labels when
             nothing more specific is present, and never override a
             specific label on the same book,
- ``title_cues`` phrases that, in a book's *title*, name its subject and are
             unlikely to mean anything else ("marketing", "khởi nghiệp"). Used
             only by train.py, to guess labels for books nobody labelled,
- ``keywords`` topical vocabulary seeding the model before it has seen any
             real book (see application/classification_trainer.py).

There are two files, merged at load time:

- the built-in ``smartdoc/data/taxonomy.json``, shipped with the app, and
- an optional ``taxonomy.json`` in the user's app-data folder, which can
  *add* categories ("có thể bổ sung thêm mới"), override fields of a built-in
  one by ``id``, or drop a built-in one with ``"disabled": true``.

A category added this way starts to be predicted once ``train.py`` has been
re-run (the model only knows the categories it was trained on); see
:meth:`Taxonomy.fingerprint`, which the model file records so the app can
tell the two are out of step.

Pure Python, no third-party imports: this module is loaded by the GUI
process, which must stay light.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BUILTIN_TAXONOMY_PATH = DATA_DIR / "taxonomy.json"
USER_TAXONOMY_FILENAME = "taxonomy.json"

_ID_RE = re.compile(r"^[a-z0-9_]+$")
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
# One label field in the wild often packs several labels: "Hồi ký, Tuỳ bút",
# "Dystopias -- Fiction", "Fiction / Thrillers / General".
_LABEL_SPLIT_RE = re.compile(r"\s*(?:,|;|/|\||\s--\s|\s>\s|\s-\s)\s*")


def fold(text: str | None) -> str:
    """Lowercase, Vietnamese diacritics removed ("đ" -> "d"), everything that
    isn't a letter or digit collapsed to single spaces. The common ground on
    which labels, tags and aliases are compared -- so "Tuỳ bút" == "tuy but"
    == "Tùy-bút"."""
    text = (text or "").lower().replace("đ", "d")
    stripped = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    return _NON_ALNUM_RE.sub(" ", stripped).strip()


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    group: str
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    weak_aliases: tuple[str, ...] = ()
    title_cues: tuple[str, ...] = ()

    @property
    def folded_labels(self) -> frozenset[str]:
        """Every folded string that firmly means this category: name + aliases."""
        return frozenset(filter(None, (fold(self.name), *(fold(a) for a in self.aliases))))

    @property
    def folded_weak_labels(self) -> frozenset[str]:
        return frozenset(filter(None, (fold(a) for a in self.weak_aliases))) - self.folded_labels


class TaxonomyError(ValueError):
    pass


def _parse_category(raw: dict, *, base: Category | None = None) -> Category:
    """Builds one Category from a JSON object, falling back to `base` for the
    keys the object doesn't provide (how a user file overrides a built-in)."""
    if not isinstance(raw, dict):
        raise TaxonomyError(f"category entry must be an object, got {type(raw).__name__}")
    category_id = str(raw.get("id") or (base.id if base else "")).strip()
    if not _ID_RE.match(category_id):
        raise TaxonomyError(f"invalid category id {category_id!r} (use a-z, 0-9 and _)")

    def text_of(key: str, fallback: str) -> str:
        return str(raw.get(key, fallback) or "").strip()

    def list_of(key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
        value = raw.get(key, fallback)
        if not isinstance(value, (list, tuple)):
            raise TaxonomyError(f"category {category_id!r}: {key!r} must be a list")
        return tuple(str(v).strip() for v in value if str(v).strip())

    name = text_of("name", base.name if base else "")
    group = text_of("group", base.group if base else "")
    if not name:
        raise TaxonomyError(f"category {category_id!r} has no name")
    if not group:
        raise TaxonomyError(f"category {category_id!r} has no group")
    return Category(
        id=category_id,
        name=name,
        group=group,
        aliases=list_of("aliases", base.aliases if base else ()),
        keywords=list_of("keywords", base.keywords if base else ()),
        weak_aliases=list_of("weak_aliases", base.weak_aliases if base else ()),
        title_cues=list_of("title_cues", base.title_cues if base else ()),
    )


def _read_categories(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    categories = payload.get("categories") if isinstance(payload, dict) else None
    if not isinstance(categories, list):
        raise TaxonomyError(f"{path.name}: expected an object with a 'categories' list")
    return categories


class Taxonomy:
    """An ordered, validated set of categories with label lookups."""

    def __init__(self, categories: list[Category]) -> None:
        self._categories: dict[str, Category] = {}
        self._label_index: dict[str, list[str]] = {}
        self._weak_label_index: dict[str, list[str]] = {}
        for category in categories:
            if category.id in self._categories:
                raise TaxonomyError(f"duplicate category id {category.id!r}")
            self._categories[category.id] = category
        for category in self._categories.values():
            for label in category.folded_labels:
                owners = self._label_index.setdefault(label, [])
                if category.id not in owners:
                    owners.append(category.id)
            for label in category.folded_weak_labels:
                owners = self._weak_label_index.setdefault(label, [])
                if category.id not in owners:
                    owners.append(category.id)
        # Two categories may not share a *name* -- the name is the hashtag,
        # and one hashtag can only mean one thing. (Aliases may overlap; a
        # label that several categories claim is simply "ambiguous" and
        # resolves to none of them, see match_label.)
        seen: dict[str, str] = {}
        for category in self._categories.values():
            key = fold(category.name)
            if key in seen:
                raise TaxonomyError(f"categories {seen[key]!r} and {category.id!r} share the name {category.name!r}")
            seen[key] = category.id

    # -- Loading ---------------------------------------------------------

    @classmethod
    def load_builtin(cls) -> "Taxonomy":
        return cls([_parse_category(raw) for raw in _read_categories(BUILTIN_TAXONOMY_PATH)])

    @classmethod
    def load(cls, user_dir: Path | None = None) -> "Taxonomy":
        """Built-in categories, then the user's taxonomy.json (if any) on top.
        A broken user file is logged and ignored -- the smart classifier
        must never fail to start because of a typo in a hand-edited file."""

        def builtin() -> dict[str, Category]:
            return {c.id: c for c in (_parse_category(raw) for raw in _read_categories(BUILTIN_TAXONOMY_PATH))}

        merged = builtin()
        user_path = (user_dir / USER_TAXONOMY_FILENAME) if user_dir else None
        if user_path is not None and user_path.is_file():
            try:
                for raw in _read_categories(user_path):
                    category_id = str(raw.get("id", "")).strip() if isinstance(raw, dict) else ""
                    if isinstance(raw, dict) and raw.get("disabled"):
                        merged.pop(category_id, None)
                        continue
                    merged[category_id] = _parse_category(raw, base=merged.get(category_id))
                return cls(list(merged.values()))
            except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
                logger.warning("Ignoring unreadable user taxonomy %s: %s", user_path, exc)
                merged = builtin()
        return cls(list(merged.values()))

    # -- Access ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._categories)

    def __iter__(self):
        return iter(self._categories.values())

    def __contains__(self, category_id: str) -> bool:
        return category_id in self._categories

    def get(self, category_id: str) -> Category | None:
        return self._categories.get(category_id)

    def ids(self) -> list[str]:
        return list(self._categories)

    def groups(self) -> list[str]:
        """Group names in the order they first appear."""
        return list(dict.fromkeys(c.group for c in self._categories.values()))

    def in_group(self, group: str) -> list[Category]:
        return [c for c in self._categories.values() if c.group == group]

    # -- Label matching --------------------------------------------------

    def _lookup(self, index: dict[str, list[str]], label: str) -> Category | None:
        owners = index.get(fold(label))
        if owners and len(owners) == 1:
            return self._categories[owners[0]]
        return None

    def match_label(self, label: str | None, *, include_weak: bool = True) -> Category | None:
        """The one category a single label unambiguously means, else None.
        Compared on folded text, against category names and aliases; weak
        aliases only when no firm alias matches."""
        if not label:
            return None
        firm = self._lookup(self._label_index, label)
        if firm is not None or not include_weak:
            return firm
        return self._lookup(self._weak_label_index, label)

    def resolve_labels(self, labels, *, include_weak: bool = True) -> list[Category]:
        """Every distinct category a set of labels points at, firm matches
        taking precedence: a book labelled ["Fiction", "Mystery"] is a
        crime/mystery book, not a generic novel. Weak matches are only used
        when no firm one exists. A label is tried as one unit first (people
        tag "Trinh thám, hình sự" as a single label), then split into its
        comma/slash/dash separated pieces. Order of first appearance."""
        firm: list[Category] = []
        weak: list[Category] = []
        for label in labels or ():
            if not label or not str(label).strip():
                continue
            text = str(label)
            whole = self._lookup(self._label_index, text)
            if whole is not None:
                if whole not in firm:
                    firm.append(whole)
                continue
            pieces = _LABEL_SPLIT_RE.split(text)
            firm_pieces = [c for c in (self._lookup(self._label_index, p) for p in pieces) if c is not None]
            if firm_pieces:
                firm.extend(c for c in firm_pieces if c not in firm)
                continue
            if not include_weak:
                continue
            weak_whole = self._lookup(self._weak_label_index, text)
            weak_pieces = (
                [weak_whole]
                if weak_whole is not None
                else [c for c in (self._lookup(self._weak_label_index, p) for p in pieces) if c is not None]
            )
            weak.extend(c for c in weak_pieces if c not in weak)
        if firm or not include_weak:
            return firm
        return weak

    def match_labels(self, label: str | None) -> list[Category]:
        """Every distinct category one possibly composite label points at:
        "Hồi ký, Tuỳ bút" -> [memoir_essay]."""
        return self.resolve_labels([label]) if label else []

    def categories_in_tags(self, tags: str | list[str] | None, *, include_weak: bool = False) -> list[Category]:
        """Categories a document *already* carries, judging by its tags (a
        comma-joined string, as the database stores them, or a list). Only
        firm labels count by default: a tag "fiction" doesn't mean the book
        has been given a genre."""
        if not tags:
            return []
        parts = tags.split(",") if isinstance(tags, str) else list(tags)
        return self.resolve_labels([p.strip() for p in parts], include_weak=include_weak)

    def without_category_tags(self, tags: str | list[str] | None) -> list[str]:
        """The user's own tags minus the ones that *are* a category. Those are
        the answer, not a clue, so they must never feed the features."""
        if not tags:
            return []
        parts = [t.strip() for t in (tags.split(",") if isinstance(tags, str) else tags) if t and t.strip()]
        return [t for t in parts if not self.resolve_labels([t], include_weak=False)]

    def fingerprint(self) -> str:
        """Stable hash of what the model's outputs mean (ids, names, groups).
        Recorded in the model file; when it differs from the current
        taxonomy's, the categories were edited after the last training."""
        digest = hashlib.sha1()
        for category in self._categories.values():
            digest.update(f"{category.id}\x1f{category.name}\x1f{category.group}\x1e".encode("utf-8"))
        return digest.hexdigest()[:16]


if __name__ == "__main__":
    taxonomy = Taxonomy.load_builtin()
    print(f"{len(taxonomy)} categories in {len(taxonomy.groups())} groups; fingerprint {taxonomy.fingerprint()}")
    for group in taxonomy.groups():
        print(f"  {group}: {', '.join(c.name for c in taxonomy.in_group(group))}")

    def ids(categories):
        return [c.id for c in categories]

    assert fold("Tuỳ bút") == fold("tùy-bút") == "tuy but"
    assert ids(taxonomy.match_labels("hồi ký, tuỳ bút")) == ["memoir_essay"]
    assert ids(taxonomy.resolve_labels(["Fiction", "Mystery"])) == ["crime_mystery"]  # firm beats weak
    assert ids(taxonomy.resolve_labels(["Fiction"])) == ["novel"]
    assert taxonomy.categories_in_tags("Fiction") == []  # a weak label isn't "already categorised"
    assert ids(taxonomy.categories_in_tags("Cổ tích, AI")) == ["folktale", "ai_data"]
    assert taxonomy.resolve_labels(["unread", "lang:vi"]) == []
    print("taxonomy self-test OK")
