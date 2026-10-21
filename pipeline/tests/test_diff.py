from datetime import date

import pytest

from notsolazy.diff import diff_text, masked_text


def assert_coverage(old, new, result):
    for side, text in [("prior", old), ("current", new)]:
        ranges = [op[side] for op in result["ops"] if op[side] is not None]
        assert ranges == sorted(ranges)
        cursor = 0
        for start, end in ranges:
            assert start == cursor and end > start
            cursor = end
        assert cursor == len(text)
        assert "".join(text[start:end] for start, end in ranges) == text
    for op in result["ops"]:
        if op["op"] == "equal" and not op["trivial"]:
            a, b = op["prior"], op["current"]
            assert old[a[0] : a[1]] == new[b[0] : b[1]]


@pytest.mark.parametrize(
    "old,new",
    [
        ("", "Entirely new."),
        ("Entirely removed.", ""),
        ("", ""),
        ("A. B. A.", "A. C. A."),
        ("  Alpha\n\nBeta.  ", "  Alpha\n\nNew Beta.  "),
        ("Unicode café 🧠 risk.", "Unicode café 🧠 changed risk."),
        ("One sentence. Another old sentence.", "One sentence. Another new sentence."),
    ],
)
def test_original_character_offsets_partition_both_sides(old, new):
    assert_coverage(old, new, diff_text(old, new))


def test_masked_equal_ops_are_limited_to_trivial_date_spans():
    old = "In fiscal 2024 revenue was 100. As of December 31, 2024 we had 4 sites."
    new = "In fiscal 2025 revenue was 200. As of December 31, 2025 we had 4 sites."
    result = diff_text(old, new, date(2024, 12, 31), date(2025, 12, 31))
    assert_coverage(old, new, result)
    trivial = [op for op in result["ops"] if op["trivial"]]
    assert len(trivial) == 2
    assert [old[o["prior"][0] : o["prior"][1]] for o in trivial] == [
        "fiscal 2024",
        "As of December 31, 2024",
    ]
    assert any(
        op["op"] == "insert" and "200" in new[op["current"][0] : op["current"][1]]
        for op in result["ops"]
    )


def test_historical_years_bare_years_and_unrelated_dates_are_not_masked():
    text = "In fiscal 2023, 2024 incidents rose. As of June 30, 2025 we had 2025 employees."
    assert masked_text(text, date(2025, 12, 31)) == text
    assert masked_text(text, None) == text
