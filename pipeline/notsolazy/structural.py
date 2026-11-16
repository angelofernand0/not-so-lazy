"""Candidate-only structural relations; never generate, promote or mutate matches.

Evidence ranges index Factor.text in half-open Unicode code points, NOT the
section-level Factor.start/end. Input signatures are opaque caller-supplied values.
Validation establishes structural consistency, not semantic correspondence.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from notsolazy.align import Match
from notsolazy.segment import Factor


@dataclass(frozen=True)
class Evidence:
    side: Literal["prior", "current"]
    factor_id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class CandidateGroup:
    kind: Literal["split", "merge"]
    prior_ids: tuple[str, ...]
    current_ids: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    input_signature: str
    anchor_edges: tuple[tuple[str, str], ...] = ()
    reasons: tuple[str, ...] = ()
    status: Literal["candidate"] = "candidate"

    def __post_init__(self) -> None:
        # Frozen records must not retain mutable list containers supplied at runtime.
        for value in (
            self.prior_ids,
            self.current_ids,
            self.evidence,
            self.anchor_edges,
            self.reasons,
        ):
            if not isinstance(value, tuple):
                raise ValueError("Candidate collections must be immutable tuples.")
        if any(not isinstance(edge, tuple) or len(edge) != 2 for edge in self.anchor_edges):
            raise ValueError("Anchor edges must be immutable endpoint pairs.")

    @property
    def id(self) -> str:
        payload = json.dumps(
            [self.kind, self.prior_ids, self.current_ids], ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def _index(factors: Sequence[Factor]) -> dict[str, Factor]:
    indexed = {factor.id: factor for factor in factors}
    if len(indexed) != len(factors):
        raise ValueError("Duplicate factor IDs in input.")
    return indexed


def validate_candidates(
    groups: Sequence[CandidateGroup],
    prior: Sequence[Factor],
    current: Sequence[Factor],
    matches: Sequence[Match],
) -> list[CandidateGroup]:
    """Return supplied candidates after all checks; raise ValueError on any failure.

    Every grouped endpoint must occur exactly once in the baseline Match list.
    It is either part of the declared internal anchor or explicitly unmatched.
    No input records, classifications, offsets, or signatures are changed.
    """
    indexes = {"prior": _index(prior), "current": _index(current)}
    incident: dict[tuple[str, str], list[Match]] = defaultdict(list)
    for match in matches:
        if match.prior_id is not None:
            incident["prior", match.prior_id].append(match)
        if match.current_id is not None:
            incident["current", match.current_id].append(match)
    used: set[tuple[str, str]] = set()
    result: list[CandidateGroup] = []
    for group in groups:
        shape = (len(group.prior_ids), len(group.current_ids))
        if (group.kind, shape) not in (("split", (1, 2)), ("merge", (2, 1))):
            raise ValueError("Only 1-to-2 splits and 2-to-1 merges are supported.")
        if (
            group.status != "candidate"
            or not isinstance(group.input_signature, str)
            or not group.input_signature
        ):
            raise ValueError("An unpromoted candidate and opaque input signature are required.")
        required: set[tuple[str, str]] = set()
        anchors: set[tuple[str, str]] = set()
        for side, ids in (("prior", group.prior_ids), ("current", group.current_ids)):
            if len(ids) != len(set(ids)) or any(key not in indexes[side] for key in ids):
                raise ValueError("Duplicate or unknown group endpoint.")
            factors = [indexes[side][key] for key in ids]
            if any(f.role != "risk" for f in factors):
                raise ValueError("Only risk-role factors can form structural candidates.")
            if len({(f.accession, f.item) for f in factors}) != 1:
                raise ValueError("Each side must belong to one filing section.")
            positions = [f.position for f in factors]
            if positions != sorted(set(positions)):
                raise ValueError("Endpoints must retain strict source order.")
            for key in ids:
                endpoint = (side, key)
                required.add(endpoint)
                rows = incident.get(endpoint, [])
                if len(rows) != 1:
                    raise ValueError("Each endpoint needs exactly one baseline Match row.")
                row = rows[0]
                if row.prior_id is not None and row.current_id is not None:
                    if row.change_type in {"added", "removed"} or row.method == "unmatched":
                        raise ValueError("An anchor must be an accepted baseline match.")
                    if (
                        row.prior_id not in group.prior_ids
                        or row.current_id not in group.current_ids
                    ):
                        raise ValueError(
                            "A non-anchor endpoint is already matched outside the group."
                        )
                    anchors.add((row.prior_id, row.current_id))
                elif (side == "prior" and row.change_type != "removed") or (
                    side == "current" and row.change_type != "added"
                ):
                    raise ValueError("Non-anchor endpoints must be explicitly unmatched.")
        if len(group.anchor_edges) > 1 or len(anchors) > 1 or set(group.anchor_edges) != anchors:
            raise ValueError("Declare exactly the existing internal anchor, at most one.")
        if required & used:
            raise ValueError("Overlapping candidate groups require review.")
        covered: set[tuple[str, str]] = set()
        for evidence in group.evidence:
            endpoint = (evidence.side, evidence.factor_id)
            if endpoint not in required:
                raise ValueError("Evidence must reference an endpoint of this group.")
            text = indexes[evidence.side][evidence.factor_id].text
            if (
                type(evidence.start) is not int
                or type(evidence.end) is not int
                or not 0 <= evidence.start < evidence.end <= len(text)
                or evidence.text != text[evidence.start : evidence.end]
            ):
                raise ValueError("Evidence must equal the exact original Factor.text substring.")
            covered.add(endpoint)
        if covered != required:
            raise ValueError("Source evidence is required for every endpoint.")
        used.update(required)
        result.append(group)
    return result
