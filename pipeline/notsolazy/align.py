"""Three-pass, one-to-one alignment. Inference is local and model preparation explicit."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from rapidfuzz.fuzz import token_set_ratio
from scipy.optimize import linear_sum_assignment  # type: ignore[import-untyped]

from notsolazy.clean import normalize_text
from notsolazy.diff import masked_text
from notsolazy.segment import Factor

ALIGNER_VERSION = "align-v1"
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
Encoder = Callable[[list[str]], NDArray[np.float64]]


def model_path(data_dir: Path) -> Path:
    return data_dir / "models" / MODEL_REVISION


def prepare_model(data_dir: Path) -> Path:
    from huggingface_hub import snapshot_download

    path = model_path(data_dir)
    snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=str(path),
        allow_patterns=["*.json", "*.txt", "model.safetensors", "1_Pooling/*"],
    )
    return path


class LocalEncoder:
    def __init__(self, data_dir: Path) -> None:
        self.path = model_path(data_dir)
        self._model: object | None = None

    def __call__(self, texts: list[str]) -> NDArray[np.float64]:
        if not (self.path / "model.safetensors").exists():
            raise ValueError("Embedding model missing; run 'nsl model prepare' once.")
        from sentence_transformers import SentenceTransformer

        if self._model is None:
            self._model = SentenceTransformer(
                str(self.path.resolve()),
                device="cpu",
                local_files_only=True,
                trust_remote_code=False,
            )
        assert isinstance(self._model, SentenceTransformer)
        return np.asarray(
            self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float64,
        )


def normalized_heading(value: str) -> str:
    return " ".join(re.findall(r"\w+", normalize_text(value).lower()))


def heading_hash(value: str) -> str:
    return hashlib.sha256(normalized_heading(value).encode()).hexdigest()


@dataclass
class Match:
    prior_id: str | None
    current_id: str | None
    method: str
    similarity: float | None
    change_type: str = ""
    moved: bool = False


def align(
    prior: list[Factor],
    current: list[Factor],
    encoder: Encoder,
    *,
    prior_date: date | None = None,
    current_date: date | None = None,
    semantic_threshold: float = 0.80,
    fuzzy_threshold: float = 85,
) -> list[Match]:
    if not 0 <= semantic_threshold <= 1 or not 0 <= fuzzy_threshold <= 100:
        raise ValueError("Invalid alignment threshold.")
    old = {f.id: f for f in prior if f.role == "risk"}
    new = {f.id: f for f in current if f.role == "risk"}
    remaining_old, remaining_new = dict(old), dict(new)
    matches: list[Match] = []

    def accept(a: str, b: str, method: str, similarity: float) -> None:
        matches.append(Match(a, b, method, float(similarity)))
        del remaining_old[a], remaining_new[b]

    # Duplicate headings are not assumed to identify one factor. Use identical
    # text to disambiguate first, otherwise leave them for body embeddings.
    for key in dict.fromkeys(heading_hash(f.heading) for f in old.values() if f.heading):
        exact_old = [
            f for f in remaining_old.values() if f.heading and heading_hash(f.heading) == key
        ]
        exact_new = [
            f for f in remaining_new.values() if f.heading and heading_hash(f.heading) == key
        ]
        if len(exact_old) == len(exact_new) == 1:
            accept(exact_old[0].id, exact_new[0].id, "exact_heading", 1)
        else:
            for left in exact_old:
                same = [
                    right
                    for right in exact_new
                    if right.id in remaining_new and right.text_hash == left.text_hash
                ]
                if len(same) == 1:
                    accept(left.id, same[0].id, "exact_heading_and_text", 1)

    candidates = [
        (a.id, b.id, token_set_ratio(normalized_heading(a.heading), normalized_heading(b.heading)))
        for a in remaining_old.values()
        if a.heading
        for b in remaining_new.values()
        if b.heading
    ]
    # Only reciprocal, unambiguous best choices are accepted in the fuzzy pass.
    for a, b, score in sorted(candidates, key=lambda row: (-row[2], row[0], row[1])):
        if a not in remaining_old or b not in remaining_new or score < fuzzy_threshold:
            continue
        row = [s for x, y, s in candidates if x == a and y in remaining_new]
        col = [s for x, y, s in candidates if y == b and x in remaining_old]
        if score == max(row) == max(col) and row.count(score) == col.count(score) == 1:
            accept(a, b, "fuzzy_heading", score / 100)

    if remaining_old and remaining_new:
        semantic_old, semantic_new = list(remaining_old.values()), list(remaining_new.values())
        vectors = np.asarray(
            encoder([f.heading + "\n" + f.body[:500] for f in [*semantic_old, *semantic_new]]),
            dtype=np.float64,
        )
        if (
            vectors.ndim != 2
            or vectors.shape[0] != len(semantic_old) + len(semantic_new)
            or not np.isfinite(vectors).all()
        ):
            raise ValueError("invalid_embedding_vectors")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.maximum(norms, 1e-12)
        similarities = np.clip(vectors[: len(semantic_old)] @ vectors[len(semantic_old) :].T, -1, 1)
        # Dummy choices let either side remain unmatched. Below-threshold edges
        # must not steal a column and suppress a valid assignment elsewhere.
        weights = np.zeros(
            (len(semantic_old) + len(semantic_new), len(semantic_new) + len(semantic_old))
        )
        weights[: len(semantic_old), : len(semantic_new)] = np.where(
            similarities >= semantic_threshold, similarities, -1
        )
        rows, columns = linear_sum_assignment(weights, maximize=True)
        for i, j in zip(rows.tolist(), columns.tolist(), strict=True):
            if (
                i < len(semantic_old)
                and j < len(semantic_new)
                and similarities[i, j] >= semantic_threshold
            ):
                accept(
                    semantic_old[i].id, semantic_new[j].id, "embedding", float(similarities[i, j])
                )

    matched = [m for m in matches if m.prior_id and m.current_id]
    old_order = sorted(matched, key=lambda m: old[m.prior_id or ""].position)
    new_order = sorted(matched, key=lambda m: new[m.current_id or ""].position)
    old_rank = {m.prior_id: i for i, m in enumerate(old_order)}
    new_rank = {m.prior_id: i for i, m in enumerate(new_order)}
    for match in matched:
        a_factor, b_factor = old[match.prior_id or ""], new[match.current_id or ""]
        unchanged = normalize_text(masked_text(a_factor.text, prior_date)) == normalize_text(
            masked_text(b_factor.text, current_date)
        )
        match.moved = old_rank[match.prior_id] != new_rank[match.prior_id]
        match.change_type = ("moved" if match.moved else "unchanged") if unchanged else "modified"
    matches.extend(Match(None, f.id, "unmatched", None, "added") for f in remaining_new.values())
    matches.extend(Match(f.id, None, "unmatched", None, "removed") for f in remaining_old.values())
    return sorted(
        matches,
        key=lambda m: (
            m.current_id is None,
            new[m.current_id].position if m.current_id else old[m.prior_id or ""].position,
        ),
    )
