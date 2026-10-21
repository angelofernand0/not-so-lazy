"""Regression anchors on saved SEC sources; not a universe-wide accuracy claim."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from notsolazy.clean import clean_html, normalize_text
from notsolazy.config import section_rule
from notsolazy.discover import amendment_item_status
from notsolazy.extract import extract_section

FIXTURES = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "extraction-cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_real_source_integrity_and_section_anchors(case, tmp_path: Path) -> None:
    raw = gzip.decompress((FIXTURES / case["file"]).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == case["raw_sha256"]
    assert case["source_url"].startswith("https://www.sec.gov/Archives/edgar/data/")
    if case["form"] == "10-K/A":
        assert amendment_item_status(raw, "1A") == case["expected_amendment_status"]
        return
    blocks = clean_html(raw)
    result = extract_section(
        raw,
        blocks,
        section_rule("1A"),
        prior_words=case.get("prior_word_count"),
        cache_dir=tmp_path,
    )
    text = normalize_text(result.selected.text)
    assert case["start_anchor"] in text[:1000]
    assert text.endswith(case["end_anchor"])
    assert case["min_words"] <= result.selected.word_count <= case["max_words"]
    assert result.flags == case["expected_flags"]
    assert len(result.candidates) == 2


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c["id"] in {"AAPL-2024", "AAPL-2025", "MSFT-2026"}],
    ids=lambda c: c["id"],
)
def test_real_risk_headings_and_nested_evidence_are_preserved(case):
    from notsolazy.extract import fallback_extract
    from notsolazy.segment import segment

    raw = gzip.decompress((FIXTURES / case["file"]).read_bytes())
    blocks = clean_html(raw)
    rule = section_rule("1A")
    text = fallback_extract(blocks, rule).text
    factors = segment(text, case["accession"], rule, blocks)
    risks = [f for f in factors if f.role == "risk"]
    assert 20 <= len(risks) <= 40
    assert all(text[f.start : f.end] == f.text for f in factors)
    if case["ticker"] == "MSFT":
        competition = next(f for f in risks if f.heading.startswith("We face intense competition"))
        assert "Competition among platform-based ecosystems" in competition.body
        reputation = next(f for f in risks if f.heading.startswith("If our reputation"))
        assert reputation.heading.endswith("may be harmed.")
        assert "Social media may increase" in reputation.body
        assert any(f.heading.startswith("Our cloud and AI strategy") for f in risks)
        assert not any(f.text.strip() in {"•", "Item 1A"} for f in risks)
    else:
        assert any(f.heading.startswith("The Company's operations and performance") for f in risks)
        assert any(f.heading.startswith("Investment in new business strategies") for f in risks)
