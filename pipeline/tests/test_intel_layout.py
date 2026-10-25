"""Real source regressions for complete risk units, not just heading presence."""

import gzip
from pathlib import Path

import pytest

from notsolazy.clean import clean_html, normalize_text
from notsolazy.config import section_rule
from notsolazy.evaluate import load_manifest
from notsolazy.extract import extract_section
from notsolazy.segment import segment

TESTS = Path(__file__).parent
INTEL = next(p for p in load_manifest(TESTS / "golden/pilot.json").pairs if p.id == "INTC")


@pytest.mark.parametrize("side", ["prior", "current"])
def test_real_intel_sections_have_complete_heading_body_units(side: str, tmp_path: Path) -> None:
    source = getattr(INTEL, side)
    raw = gzip.decompress((TESTS / source.fixture).read_bytes())
    blocks = clean_html(raw)
    rule = section_rule("1A")
    extraction = extract_section(raw, blocks, rule, cache_dir=tmp_path)
    text = extraction.selected.text
    assert normalize_text(source.section_start) in normalize_text(text)[:1000]
    assert normalize_text(text).endswith(normalize_text(source.section_end))
    assert not extraction.flags
    assert "\n\nSales and Marketing\n\n" not in text
    assert "\n\nOther Key Information\n\n" not in text
    if side == "prior":
        assert "primary_crossed_source_boundary" in extraction.warnings
        assert "contains_following_section" in extraction.candidates[0]["quality_flags"]

    factors = segment(text, source.accession, rule, blocks)
    risks = [f for f in factors if f.role == "risk"]
    assert len(risks) == len(source.factors)  # 24 prior and 22 current, not 200/166 paragraphs.
    assert [normalize_text(f.heading) for f in risks] == [
        normalize_text(f.heading) for f in source.factors
    ]
    assert all(f.segmentation == "heading" and len(f.body.split()) > 15 for f in risks)
    assert all(text[f.start : f.end] == f.text for f in factors)
    assert all(f.body == f.text[len(f.heading) :].lstrip() for f in risks)
    assert factors[0].role == "preamble"
    assert "following summarizes" in factors[0].text
    assert risks[0].body.startswith("The industry in which we operate is highly competitive")
    assert "We face intense competition across our product portfolio." in risks[0].body
    if side == "prior":
        technology = next(f for f in risks if f.heading.startswith("The development and"))
        assert "Our disaggregated design strategy" in technology.body
        assert "disruptions in the production process" in technology.body
    else:
        technology = next(f for f in risks if f.heading.startswith("We are making significant"))
        assert "We have adopted a disaggregated design architecture" in technology.body
        assert "Intel 14A" not in technology.heading
