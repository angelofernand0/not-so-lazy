from dataclasses import replace
from pathlib import Path

import pytest

from notsolazy.clean import Block, clean_html
from notsolazy.config import section_rule
from notsolazy.extract import Candidate, extract_section, fallback_extract, quality_flags

RULE = section_rule("1A")
BODY = "Material business uncertainty can affect operations and financial condition. " * 250


def html_body(end: str = "Item 1B. Unresolved Staff Comments") -> bytes:
    return (
        f"<p>Item 1A. Risk Factors</p><p>{BODY}</p><p>{end}</p><p>Outside the risks.</p>".encode()
    )


@pytest.mark.parametrize(
    "end", ["Item 1B. Unresolved Staff Comments", "Item 1C. Cybersecurity", "Item 2. Properties"]
)
def test_split_heading_toc_and_each_end_boundary(end: str) -> None:
    payload = (
        f"<p>Item 1A.</p><p>Risk Factors</p><p>TOC listing</p><p>{end}</p>"
        f"<p>Business narrative.</p><p>Item</p><p>1A.</p><p>RISK FACTORS</p>"
        f"<p>{BODY}</p><p>{end}</p><p>Outside the risks.</p>"
    ).encode()
    blocks = clean_html(payload)
    result = fallback_extract(blocks, RULE)
    assert "TOC listing" not in result.text
    assert BODY.strip() in result.text
    assert "Outside the risks." not in result.text
    assert not result.flags


def test_end_heading_can_share_a_block_with_its_body() -> None:
    result = fallback_extract(
        clean_html(html_body("ITEM 1B. UNRESOLVED STAFF COMMENTS. None.")), RULE
    )
    assert "None." not in result.text
    assert not result.flags


def test_prose_references_do_not_end_a_section() -> None:
    payload = html_body().replace(
        b"</p><p>Item 1B", b" See Item 2. Properties for details.</p><p>Item 1B", 1
    )
    result = fallback_extract(clean_html(payload), RULE)
    assert "See Item 2. Properties for details." in result.text
    assert "contains_item_2" in quality_flags(result, RULE, None)


def test_missing_end_boundary_and_incorporation_are_flagged() -> None:
    result = fallback_extract(
        clean_html(b"<p>Item 1A. Risk Factors</p><p>Incorporated by reference.</p>"), RULE
    )
    assert {"missing_end_boundary", "too_few_words", "incorporated_by_reference"} <= set(
        quality_flags(result, RULE, None)
    )


def test_bare_title_requires_item_mapping_and_ignores_smaller_risk_group_headings() -> None:
    blocks = [
        Block(text="Risk Factors", tag="div", font_size=18),
        Block(text=BODY, tag="p"),
        Block(text="Cybersecurity", tag="div", font_size=10),
        Block(text="Additional actual risks.", tag="p"),
        Block(text="Other Key Information", tag="div", font_size=18),
        Block(text="Outside the risks.", tag="p"),
        Block(text="Item 1A.", tag="td"),
        Block(text="Risk Factors", tag="td"),
        Block(text="Item 1B. Unresolved Staff Comments", tag="td"),
    ]
    result = fallback_extract(blocks, RULE)
    assert result.boundary_method == "title_with_cross_reference"
    assert "Additional actual risks." in result.text and "Outside the risks." not in result.text
    assert "section_not_found" in fallback_extract(blocks[:6], RULE).flags


def test_primary_failure_recovers_and_retains_both_candidates(tmp_path: Path) -> None:
    def failed(*args):
        raise RuntimeError("parser failure")

    result = extract_section(
        html_body(), clean_html(html_body()), RULE, primary=failed, cache_dir=tmp_path
    )
    assert result.selected.extractor == "fallback"
    assert not result.flags
    assert result.warnings == ["edgartools_error:RuntimeError"]
    assert len(result.candidates) == 2
    assert result.candidates[0]["quality_flags"]
    assert result.candidates[1]["text"] == result.selected.text


def test_primary_preferred_on_agreement_and_fallback_recovers_truncated_primary(
    tmp_path: Path,
) -> None:
    fallback = fallback_extract(clean_html(html_body()), RULE)

    def primary(*args):
        return Candidate(fallback.text, "edgartools")

    result = extract_section(
        html_body(), clean_html(html_body()), RULE, primary=primary, cache_dir=tmp_path
    )
    assert result.selected.extractor == "edgartools" and not result.flags

    def broken(*args):
        return Candidate(fallback.text + " Refer to", "edgartools")

    result = extract_section(
        html_body(), clean_html(html_body()), RULE, primary=broken, cache_dir=tmp_path
    )
    assert result.selected.extractor == "fallback" and not result.flags


def test_disagreement_between_plausible_extractors_requires_review(tmp_path: Path) -> None:
    def primary(*args):
        return Candidate("Item 1A. Risk Factors\n\n" + BODY * 2, "edgartools")

    result = extract_section(
        html_body(), clean_html(html_body()), RULE, primary=primary, cache_dir=tmp_path
    )
    assert "extractor_disagreement_unresolved" in result.flags
    assert "extractor_word_count_disagreement" in result.warnings
    assert len(result.candidates) == 2


def test_word_count_outlier_and_configured_item_are_not_hardcoded() -> None:
    candidate = Candidate("Item 1A. Risk Factors " + BODY, "fallback")
    assert "word_count_outlier" in quality_flags(candidate, RULE, 10000)
    custom = replace(RULE, item="7", title="Management Discussion", min_words=1)
    payload = (
        b"<p>Item 7. Management Discussion</p><p>Business evidence.</p><p>Item 2. Properties</p>"
    )
    assert "Business evidence." in fallback_extract(clean_html(payload), custom).text


def test_primary_footer_is_removed_using_source_artifacts_on_all_platforms(tmp_path: Path) -> None:
    raw = "<p>Item 1A. Risk Factors</p>"
    for page in range(1, 4):
        raw += f'<p>{BODY}</p><div style="font-size:7pt">{page} Example Corporation</div>'
        raw += '<div style="page-break-after:always"></div>'
    raw += "<p>Item 1B. Unresolved Staff Comments</p>"
    payload = raw.encode()
    blocks = clean_html(payload)
    fallback = fallback_extract(blocks, RULE)

    # Reproduce the Linux renderer joining a numeric company footer to the body.
    def primary(*args):
        return Candidate(fallback.text + " 3 Example Corporation", "edgartools")

    result = extract_section(payload, blocks, RULE, primary=primary, cache_dir=tmp_path)
    assert result.selected.extractor == "edgartools"
    assert result.selected.text == fallback.text
    assert not result.flags
