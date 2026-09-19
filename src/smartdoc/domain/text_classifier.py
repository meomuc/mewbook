"""The smart classifier's model: a sparse linear text classifier, inference only.

A document is a bag of weighted feature tokens (see
application/classification_features.py). The model turns it into an L2-
normalised TF-IDF vector and scores it against each category:

    score[c] = bias[c] + sum_t  q[t] * weight[c][t]

The format is a general linear model, so any trainer can export into it and the
app needs no change. The default trainer fits a one-vs-rest linear SVM (far
better than the alternative where categories overlap, which is most of the
time for books); the dependency-free fallback stores each category's TF-IDF
*centroid* instead, making a score the cosine similarity between the document
and the average book of that category (Rocchio).

Turning scores into a decision -- the part that makes it "smart" rather than
just "always answers":

- a softmax over ``scale * score`` gives probabilities (``scale`` is fitted by
  the trainer on held-out books so 0.8 really means ~80%),
- a *group* probability is the summed probability of the categories in the
  winner's sidebar folder: "Marketing" vs "Quản trị" is a coin flip, but
  "Kinh tế - Kinh doanh" vs "Văn học" is not, and either way the book lands in
  the right folder,
- the answer is withheld (``category_id`` is None) unless the best score, the
  group probability and the amount of evidence all clear the thresholds the
  trainer stored in the model. Better to leave a book unlabelled than to
  clutter the library with wrong tags -- the spec asks for tags "có kiểm soát".

Training lives elsewhere (application/classification_trainer.py, run through
train.py) and is never imported by the app. This module is pure Python with
no third-party imports, so loading it costs the GUI process nothing.
"""
from __future__ import annotations

import gzip
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

MODEL_FORMAT = 1
BUILTIN_MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "classifier_model.json.gz"
USER_MODEL_RELATIVE_PATH = Path("models") / "classifier_model.json.gz"

# What each part of a book counts for. Stored in the model (params["weights"])
# so the trainer and the classifier can never disagree.
DEFAULT_FEATURE_WEIGHTS = {"title": 3.0, "subject": 3.0, "tag": 2.0, "author": 1.5, "hint": 1.5, "body": 1.0}

DEFAULT_PARAMS = {
    "scale": 14.0,  # softmax sharpness over scores
    "min_score": 0.05,  # best score below this -> "doesn't look like anything I know"
    "min_group_prob": 0.55,
    "min_class_prob": 0.0,  # probability of the best category itself (0 = only the folder has to be clear)
    "min_matched": 6,  # distinct known tokens needed before an answer is trusted
    "weights": DEFAULT_FEATURE_WEIGHTS,
    "max_words": 3000,
}


class ModelError(ValueError):
    pass


@dataclass(frozen=True)
class ClassInfo:
    id: str
    name: str
    group: str


@dataclass
class Prediction:
    category_id: str | None
    """None = withheld (see `reason`)."""
    confidence: float = 0.0
    """Probability of the best category."""
    group_confidence: float = 0.0
    best_id: str | None = None
    """The best category even when withheld -- for previews/diagnostics."""
    top: list[tuple[str, float]] = field(default_factory=list)
    """(category id, probability), best first."""
    reason: str = "model"
    """"model" | "low_confidence" | "not_enough_evidence" | "no_text"."""
    score: float = 0.0
    matched: int = 0


def _softmax(values: list[float]) -> list[float]:
    peak = max(values)
    exps = [math.exp(v - peak) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


class TextClassifierModel:
    def __init__(
        self,
        classes: list[ClassInfo],
        features: list[str],
        idf: list[float],
        postings: list[list[tuple[int, float]]],
        bias: list[float] | None = None,
        params: dict | None = None,
        meta: dict | None = None,
    ) -> None:
        if not (len(features) == len(idf) == len(postings)):
            raise ModelError("features, idf and postings must be the same length")
        self.classes = classes
        self.bias = bias or [0.0] * len(classes)
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.params["weights"] = {**DEFAULT_FEATURE_WEIGHTS, **self.params.get("weights", {})}
        self.meta = meta or {}
        # token -> (idf, ((class_index, weight), ...)); the whole inference structure.
        self._index: dict[str, tuple[float, tuple[tuple[int, float], ...]]] = {
            token: (idf[i], tuple((int(c), float(w)) for c, w in postings[i])) for i, token in enumerate(features)
        }
        self._class_ids = [c.id for c in classes]
        self._group_members: dict[str, list[int]] = {}
        for index, info in enumerate(classes):
            self._group_members.setdefault(info.group, []).append(index)

    # -- Introspection ---------------------------------------------------

    @property
    def feature_count(self) -> int:
        return len(self._index)

    @property
    def feature_weights(self) -> dict[str, float]:
        return self.params["weights"]

    @property
    def max_words(self) -> int:
        return int(self.params.get("max_words", 3000))

    @property
    def taxonomy_fingerprint(self) -> str:
        return self.meta.get("taxonomy", "")

    def class_by_id(self, category_id: str) -> ClassInfo | None:
        for info in self.classes:
            if info.id == category_id:
                return info
        return None

    # -- Scoring ---------------------------------------------------------

    def vectorize(self, counts: dict[str, float]) -> dict[str, float]:
        """L2-normalised sublinear TF-IDF over the tokens the model knows."""
        raw: dict[str, float] = {}
        for token, tf in counts.items():
            entry = self._index.get(token)
            if entry is not None and tf > 0:
                raw[token] = (1.0 + math.log(tf)) * entry[0] if tf >= 1 else tf * entry[0]
        norm = math.sqrt(sum(v * v for v in raw.values()))
        if norm == 0:
            return {}
        return {token: v / norm for token, v in raw.items()}

    def scores(self, vector: dict[str, float]) -> list[float]:
        totals = list(self.bias)
        for token, q in vector.items():
            for class_index, weight in self._index[token][1]:
                totals[class_index] += q * weight
        return totals

    def predict(self, counts: dict[str, float]) -> Prediction:
        if not counts:
            return Prediction(category_id=None, reason="no_text")
        vector = self.vectorize(counts)
        matched = len(vector)
        if matched == 0:
            return Prediction(category_id=None, reason="not_enough_evidence", matched=0)

        scores = self.scores(vector)
        probs = _softmax([self.params["scale"] * s for s in scores])
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        best = order[0]
        group = self.classes[best].group
        group_prob = sum(probs[i] for i in self._group_members[group])
        top = [(self._class_ids[i], probs[i]) for i in order[:3]]

        prediction = Prediction(
            category_id=None,
            confidence=probs[best],
            group_confidence=group_prob,
            best_id=self._class_ids[best],
            top=top,
            score=scores[best],
            matched=matched,
        )
        if matched < self.params["min_matched"]:
            prediction.reason = "not_enough_evidence"
        elif (
            scores[best] < self.params["min_score"]
            or group_prob < self.params["min_group_prob"]
            or probs[best] < self.params["min_class_prob"]
        ):
            prediction.reason = "low_confidence"
        else:
            prediction.category_id = self._class_ids[best]
        return prediction

    def top_terms(self, counts: dict[str, float], category_id: str, limit: int = 8) -> list[tuple[str, float]]:
        """The tokens of this document that pushed hardest towards a
        category -- for diagnostics and the trainer's reports."""
        try:
            class_index = self._class_ids.index(category_id)
        except ValueError:
            return []
        vector = self.vectorize(counts)
        contributions = []
        for token, q in vector.items():
            for c, w in self._index[token][1]:
                if c == class_index:
                    contributions.append((token, q * w))
        contributions.sort(key=lambda kv: kv[1], reverse=True)
        return contributions[:limit]

    # -- Persistence -----------------------------------------------------

    def to_dict(self) -> dict:
        tokens = list(self._index)
        return {
            "format": MODEL_FORMAT,
            "kind": "linear",
            "meta": self.meta,
            "params": self.params,
            "classes": [{"id": c.id, "name": c.name, "group": c.group} for c in self.classes],
            "bias": [round(b, 5) for b in self.bias],
            "features": tokens,
            "idf": [round(self._index[t][0], 4) for t in tokens],
            "postings": [[[c, round(w, 5)] for c, w in self._index[t][1]] for t in tokens],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "TextClassifierModel":
        if payload.get("format") != MODEL_FORMAT:
            raise ModelError(f"unsupported model format {payload.get('format')!r}")
        try:
            return cls(
                classes=[ClassInfo(c["id"], c["name"], c["group"]) for c in payload["classes"]],
                features=payload["features"],
                idf=payload["idf"],
                postings=payload["postings"],
                bias=payload.get("bias"),
                params=payload.get("params"),
                meta=payload.get("meta"),
            )
        except (KeyError, TypeError) as exc:
            raise ModelError(f"malformed model file: {exc}") from exc

    def save(self, path: Path) -> None:
        """Writes the model, plus a small `<name>.meta.json` beside it: the GUI
        can then show which model is in use, or notice that the categories were
        edited since training, without parsing the whole model file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if path.suffix == ".gz":
            with gzip.open(path, "wb", compresslevel=6) as handle:
                handle.write(data)
        else:
            path.write_bytes(data)
        summary = {**self.meta, "categories": [c.id for c in self.classes], "features": self.feature_count}
        meta_sidecar_path(path).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "TextClassifierModel":
        try:
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rb") as handle:
                payload = json.loads(handle.read().decode("utf-8"))
        except (OSError, EOFError, ValueError) as exc:  # gzip errors are OSError/EOFError; bad JSON is ValueError
            raise ModelError(f"cannot read model {path}: {exc}") from exc
        return cls.from_dict(payload)


def meta_sidecar_path(model_path: Path) -> Path:
    return model_path.with_name(model_path.name + ".meta.json")


def read_model_meta(model_path: Path) -> dict | None:
    """The small summary saved next to a model (see TextClassifierModel.save),
    or None if there isn't one -- e.g. a model copied around without it."""
    try:
        return json.loads(meta_sidecar_path(model_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def resolve_model_path(app_data_dir: Path | None) -> Path | None:
    """The model to use: the user's own (trained with train.py, in the app
    data folder) if there is one, else the one shipped with the app."""
    if app_data_dir is not None:
        user_model = app_data_dir / USER_MODEL_RELATIVE_PATH
        if user_model.is_file():
            return user_model
    return BUILTIN_MODEL_PATH if BUILTIN_MODEL_PATH.is_file() else None


def new_meta(*, taxonomy_fingerprint: str, tokenizer: str, trained_docs: int, sources: dict | None = None) -> dict:
    return {
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "taxonomy": taxonomy_fingerprint,
        "tokenizer": tokenizer,
        "trained_docs": trained_docs,
        "sources": sources or {},
    }


if __name__ == "__main__":
    import tempfile

    classes = [ClassInfo("code", "Lập trình", "Công nghệ"), ClassInfo("cook", "Nấu ăn", "Đời sống"), ClassInfo("ai", "AI", "Công nghệ")]
    features = ["python", "code", "recipe", "chicken", "model", "training"]
    idf = [2.0, 1.5, 2.0, 2.2, 1.8, 1.9]
    postings = [
        [(0, 0.6), (2, 0.2)],
        [(0, 0.7)],
        [(1, 0.7)],
        [(1, 0.6)],
        [(2, 0.6), (0, 0.1)],
        [(2, 0.5)],
    ]
    model = TextClassifierModel(classes, features, idf, postings, params={"min_matched": 2})

    prediction = model.predict({"python": 3, "code": 2, "chicken": 0.0})
    print("code-ish  ->", prediction.category_id, round(prediction.confidence, 2), prediction.top)
    assert prediction.category_id == "code"
    cooking = model.predict({"recipe": 2, "chicken": 3})
    assert cooking.category_id == "cook"
    # a document the model knows nothing about is withheld, not guessed
    assert model.predict({"zebra": 5}).category_id is None
    assert model.predict({}).reason == "no_text"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.json.gz"
        model.save(path)
        reloaded = TextClassifierModel.load(path)
        assert reloaded.predict({"python": 3, "code": 2}).category_id == "code"
        print("round-trip OK,", path.stat().st_size, "bytes")
