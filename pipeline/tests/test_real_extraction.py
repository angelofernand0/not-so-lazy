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
