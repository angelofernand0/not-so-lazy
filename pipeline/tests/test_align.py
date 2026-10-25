import hashlib
from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from notsolazy.align import LocalEncoder, align
from notsolazy.segment import Factor


def factor(key, heading, body="Evidence.", position=0, role="risk"):
    text = heading + "\n\n" + body if heading else body
    return Factor(
        key,
        key[:1],
        "test",
        position,
        "",
        heading,
        body,
        text,
        hashlib.sha256(text.encode()).hexdigest(),
        "heading",
        role,
        0,
        len(text),
    )


def forbidden(texts):
    pytest.fail("Unnecessary embedding call")


def test_exact_fuzzy_added_removed_and_context_exclusion():
    old = [
        factor("a", "Supplier disruption could harm us."),
        factor("b", "Cyberattacks could damage our systems.", position=1),
        factor("c", "Flooding.", role="summary"),
    ]
    new = [
        factor("d", "Supplier disruption could harm us.", "Changed evidence."),
        factor("e", "Severe cyberattacks could damage our systems.", position=1),
        factor("f", "Unrelated new risk.", position=2),
    ]
    matches = align(old, new, forbidden)
    assert [(m.method, m.change_type) for m in matches] == [
        ("exact_heading", "modified"),
        ("fuzzy_heading", "modified"),
        ("unmatched", "added"),
    ]
    assert "c" not in [m.prior_id for m in matches]


def test_movement_uses_relative_order_not_insertion_shifts():
    old = [factor("a", "A risk harms us."), factor("b", "B risk harms us.", position=1)]
    new = [
        factor("c", "C new risk.", position=0),
        factor("d", old[0].heading, position=1),
        factor("e", old[1].heading, position=2),
    ]
    matches = align(old, new, forbidden)
    assert [m.moved for m in matches] == [False, False, False]
    new = [replace(new[2], position=0), replace(new[1], position=1)]
    assert all(m.change_type == "moved" for m in align(old, new, forbidden))


def test_fiscal_only_change_is_unchanged_but_other_numbers_are_modified():
    old = [factor("a", "Liquidity risk may harm us.", "In fiscal 2024 we spent $25.")]
    new = [factor("b", old[0].heading, "In fiscal 2025 we spent $25.")]
    dates = dict(prior_date=date(2024, 12, 31), current_date=date(2025, 12, 31))
    assert align(old, new, forbidden, **dates)[0].change_type == "unchanged"
    new[0] = factor("b", old[0].heading, "In fiscal 2025 we spent $26.")
    assert align(old, new, forbidden, **dates)[0].change_type == "modified"


def test_embedding_uses_global_assignment_and_allows_unmatched():
    old = [factor("a", "", "Alpha."), factor("b", "", "Beta.")]
    new = [factor("c", "", "Gamma."), factor("d", "", "Delta.")]
    # Cosines: .9/.81 and .89/0. All-above-threshold global match is a-d, b-c.
    vectors = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0.7, 0.69, 0.183, 0], [0.81, 0, 0, 0.586]])
    result = align(old, new, lambda _: vectors, semantic_threshold=0.69)
    assert {(m.prior_id, m.current_id) for m in result} == {("a", "d"), ("b", "c")}
    result = align(old, new, lambda _: np.eye(4))
    assert [m.change_type for m in result] == ["added", "added", "removed", "removed"]


def test_duplicate_headings_are_disambiguated_by_body_not_position():
    old = [
        factor("a", "Repeated heading.", "First."),
        factor("b", "Repeated heading.", "Second.", 1),
    ]
    new = [
        factor("c", "Repeated heading.", "Second."),
        factor("d", "Repeated heading.", "First.", 1),
    ]
    result = align(old, new, forbidden)
    assert {(m.prior_id, m.current_id) for m in result} == {("a", "d"), ("b", "c")}
    assert all(m.moved for m in result)


def test_missing_model_is_explicit_and_never_downloaded(tmp_path):
    with pytest.raises(ValueError, match="model prepare"):
        LocalEncoder(tmp_path)(["x"])


@pytest.mark.parametrize("vectors", [np.array([1, 2]), np.array([[float("nan")], [1]])])
def test_invalid_encoder_results_fail(vectors):
    with pytest.raises(ValueError, match="invalid_embedding"):
        align([factor("a", "", "Old")], [factor("b", "", "New")], lambda _: vectors)
