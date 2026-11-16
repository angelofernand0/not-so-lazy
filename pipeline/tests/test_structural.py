"""Synthetic source-shaped contract tests; no discovery, model or metric claims."""

import copy
import hashlib
from dataclasses import FrozenInstanceError, replace

import pytest

from notsolazy.align import Match
from notsolazy.segment import Factor
from notsolazy.structural import CandidateGroup, Evidence, validate_candidates


def factor(key, heading, position=0, role="risk"):
    text = heading + "\n\nOriginal evidence 😀, not a section-relative range."
    return Factor(
        key,
        key[0],
        "1A",
        position,
        "",
        heading,
        text,
        text,
        hashlib.sha256(text.encode()).hexdigest(),
        "heading",
        role,
        1000,
        1000 + len(text),
    )


def case(kind="split", anchor=False):
    if kind == "split":
        prior = [
            factor(
                "p02",
                "Our focus on cloud-based and AI services presents "
                "execution and competitive risks.",
            )
        ]
        current = [
            factor("c02", "Our cloud and AI strategy requires substantial investments."),
            factor(
                "c03",
                "Our success depends on our ability to develop "
                "competitive cloud-based and AI products.",
                1,
            ),
        ]
    else:
        prior = [
            factor(
                "p02",
                "We are making significant, long-term and inherently risky investments in R&D.",
            ),
            factor(
                "p03",
                "The development and implementation of new semiconductor products involves risks.",
                1,
            ),
        ]
        current = [factor("c02", prior[0].heading)]
    matches = [Match(f.id, None, "unmatched", None, "removed") for f in prior]
    matches += [Match(None, f.id, "unmatched", None, "added") for f in current]
    edges = ()
    if anchor:
        edges = ((prior[0].id, current[0].id),)
        matches = [
            m for m in matches if m.prior_id != prior[0].id and m.current_id != current[0].id
        ]
        matches.append(Match(*edges[0], "exact_heading", 1.0, "modified"))
    evidence = tuple(
        Evidence(side, f.id, 0, len(f.text), f.text)
        for side, factors in (("prior", prior), ("current", current))
        for f in factors
    )
    group = CandidateGroup(
        kind, tuple(f.id for f in prior), tuple(f.id for f in current), evidence, "opaque", edges
    )
    return group, prior, current, matches


@pytest.mark.parametrize("shape", ["cloud", "infrastructure", "quality", "intel"])
def test_four_pilot_shapes_preserve_anchors_and_inputs(shape):
    group, prior, current, matches = case(
        "merge" if shape == "intel" else "split", shape != "cloud"
    )
    if shape in {"infrastructure", "quality"}:
        headings = (
            (
                "We may have excessive outages, data losses, "
                "and disruptions of our online services.",
                "We may be unable to develop and expand adequate infrastructure.",
                "We may experience outages, disruptions, or capacity constraints.",
            ),
            (
                "We may experience supply or quality problems.",
                "We may experience supply problems.",
                "We may experience other quality problems.",
            ),
        )[shape == "quality"]
        prior_id, current_ids = (
            ("p11", ("c12", "c14")) if shape == "infrastructure" else ("p12", ("c13", "c15"))
        )
        prior = [factor(prior_id, headings[0])]
        current = [
            factor(key, heading, i)
            for i, (key, heading) in enumerate(zip(current_ids, headings[1:], strict=True))
        ]
        group = CandidateGroup(
            "split",
            (prior_id,),
            current_ids,
            tuple(
                Evidence(side, f.id, 0, len(f.text), f.text)
                for side, factors in (("prior", prior), ("current", current))
                for f in factors
            ),
            "opaque",
            ((prior_id, current_ids[0]),),
        )
        matches = [
            Match(prior_id, current_ids[0], "exact_heading", 1.0, "modified"),
            Match(None, current_ids[1], "unmatched", None, "added"),
        ]
    before = copy.deepcopy((group, prior, current, matches))
    assert validate_candidates([group], prior, current, matches) == [group]
    assert (group, prior, current, matches) == before
    assert group.status == "candidate"
    actual_edges = {(m.prior_id, m.current_id) for m in matches if m.prior_id and m.current_id}
    assert actual_edges == set(group.anchor_edges)


def test_id_uses_only_kind_and_ordered_ids_and_records_are_frozen():
    group, *_ = case()
    assert group.id == replace(group, reasons=("another reason",), input_signature="other").id
    assert group.id != replace(group, current_ids=tuple(reversed(group.current_ids))).id
    with pytest.raises(FrozenInstanceError):
        group.kind = "merge"
    with pytest.raises(FrozenInstanceError):
        group.evidence[0].text = "changed"
    with pytest.raises(ValueError, match="immutable"):
        replace(group, reasons=["mutable"])


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "merge"},
        {"kind": "unresolved"},
        {"prior_ids": ()},
        {"current_ids": ("c02",)},
        {"current_ids": ("c02", "c02")},
        {"current_ids": ("c02", "unknown")},
        {"current_ids": ("c03", "c02")},
        {"anchor_edges": (("p02", "c02"),)},
        {"input_signature": ""},
        {"status": "accepted"},
    ],
)
def test_rejects_bad_group_contract(change):
    group, prior, current, matches = case()
    with pytest.raises(ValueError):
        validate_candidates([replace(group, **change)], prior, current, matches)


@pytest.mark.parametrize(
    "change",
    [
        {"start": -1},
        {"end": 10000},
        {"start": 1, "end": 1},
        {"start": True},
        {"text": "normalized instead of original"},
        {"side": "other"},
        {"factor_id": "unknown"},
        {"start": 1000, "end": 1001},
    ],
)
def test_rejects_invalid_or_section_relative_evidence(change):
    group, prior, current, matches = case()
    evidence = (replace(group.evidence[0], **change), *group.evidence[1:])
    with pytest.raises(ValueError):
        validate_candidates([replace(group, evidence=evidence)], prior, current, matches)


def test_unicode_evidence_uses_code_points_and_needs_every_endpoint():
    group, prior, current, matches = case()
    f = prior[0]
    start = f.text.index("😀")
    evidence = (Evidence("prior", f.id, start, start + 1, "😀"), *group.evidence[1:])
    assert validate_candidates([replace(group, evidence=evidence)], prior, current, matches)
    with pytest.raises(ValueError, match="every endpoint"):
        validate_candidates([replace(group, evidence=evidence[:-1])], prior, current, matches)


@pytest.mark.parametrize("change", ["role", "duplicate_input", "order", "section", "overlap"])
def test_rejects_bad_source_inventory_or_overlapping_groups(change):
    group, prior, current, matches = case()
    groups = [group]
    if change == "role":
        current[1] = replace(current[1], role="summary")
    elif change == "duplicate_input":
        prior.append(prior[0])
    elif change == "order":
        current[1] = replace(current[1], position=0)
    elif change == "section":
        current[1] = replace(current[1], accession="other-filing")
    else:
        groups.append(group)
    with pytest.raises(ValueError):
        validate_candidates(groups, prior, current, matches)


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "wrong_unmatched", "outside", "undeclared", "multiple"]
)
def test_rejects_inconsistent_baseline_or_anchors(change):
    group, prior, current, matches = case(anchor=change == "undeclared")
    if change == "missing":
        matches.pop()
    elif change == "duplicate":
        matches.append(matches[0])
    elif change == "wrong_unmatched":
        matches[0] = replace(matches[0], change_type="modified")
    elif change == "outside":
        matches[0] = Match(prior[0].id, "outside", "exact_heading", 1.0, "modified")
    elif change == "undeclared":
        group = replace(group, anchor_edges=())
    else:
        group = replace(group, anchor_edges=(("p02", "c02"), ("p02", "c03")))
    with pytest.raises(ValueError):
        validate_candidates([group], prior, current, matches)


def test_does_not_discover_or_promote_unresolved_or_same_topic_factors():
    prior = [factor("p04", "Our implementation of new business strategies involves foundry risks.")]
    current = [
        factor("c03", "If we are unable to secure an external foundry customer for Intel 14A.")
    ]
    matches = [
        Match("p04", None, "unmatched", None, "removed"),
        Match(None, "c03", "unmatched", None, "added"),
    ]
    before = copy.deepcopy(matches)
    assert validate_candidates([], prior, current, matches) == []
    assert matches == before


def test_rejects_unmatched_row_misrepresented_as_anchor():
    group, prior, current, matches = case(anchor=True)
    matches[-1] = replace(matches[-1], change_type="added", method="unmatched")
    with pytest.raises(ValueError, match="accepted baseline"):
        validate_candidates([group], prior, current, matches)
