"""Independent extractors, quality arbitration, and original cleaned-block boundaries."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

from notsolazy.clean import Block, decode_html, normalize_text
from notsolazy.config import SectionRule

EXTRACTOR_VERSION = "extract-v1"


@dataclass
class Candidate:
    text: str
    extractor: str
    flags: list[str] = field(default_factory=list)
    start_block: int | None = None
    end_block: int | None = None
    boundary_method: str = "numbered"

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Extraction:
    selected: Candidate
    candidates: list[dict[str, object]]
    flags: list[str]
    warnings: list[str]
    primary_version: str


def _heading_at(blocks: list[Block], index: int, item: str, title: str) -> int | None:
    for width in range(1, min(3, len(blocks) - index) + 1):
        fragment = " ".join(block.text for block in blocks[index : index + width])
        # A title and first body sentence may share a block. The title must end
        # at a delimiter or at the end of the block, not inside another sentence.
        if re.match(
            rf"^item\s*{re.escape(item)}\s*[.:-]?\s*{re.escape(title)}(?:[.:-](?:\s|$)|$)",
            fragment,
            re.I,
        ):
            return index + width
        if len(fragment) > 220:
            break
    return None


def _bare_title(block: Block, title: str) -> bool:
    return bool(re.fullmatch(re.escape(title) + r"[.]?", block.text, re.I))


def _same_heading_level(first: Block, second: Block) -> bool:
    start_size, end_size = first.font_size, second.font_size
    return start_size is not None and end_size is not None and end_size >= start_size * 0.8


def fallback_extract(blocks: list[Block], rule: SectionRule) -> Candidate:
    candidates: list[Candidate] = []
    numbered = {i: _heading_at(blocks, i, rule.item, rule.title) for i in range(len(blocks))}
    has_cross_reference = any(end is not None for end in numbered.values())
    for i, block in enumerate(blocks):
        heading_end = numbered[i]
        method = "numbered"
        if heading_end is None and has_cross_reference and _bare_title(block, rule.title):
            heading_end, method = i + 1, "title_with_cross_reference"
        if heading_end is None:
            continue
        end = next(
            (
                j
                for j in range(heading_end, len(blocks))
                if any(
                    _heading_at(blocks, j, item, title) is not None
                    for item, title in rule.next_headers
                )
                or (
                    method == "title_with_cross_reference"
                    and any(
                        _bare_title(blocks[j], title) and _same_heading_level(block, blocks[j])
                        for title in rule.bare_end_titles
                    )
                )
            ),
            len(blocks),
        )
        text = "\n\n".join(block.text for block in blocks[i:end])
        candidates.append(
            Candidate(
                text,
                "fallback",
                [] if end < len(blocks) else ["missing_end_boundary"],
                i,
                end,
                method,
            )
        )
    if not candidates:
        return Candidate("", "fallback", ["section_not_found"])
    bounded = [
        candidate for candidate in candidates if "missing_end_boundary" not in candidate.flags
    ]
    return max(bounded or candidates, key=lambda candidate: candidate.word_count)


def edgartools_extract(payload: bytes, rule: SectionRule, cache_dir: Path) -> Candidate:
    # The parser never constructs Company/Filing objects or calls EDGAR. The library
    # initializes its HTTP cache on import, so keep that cache inside task data.
    os.environ.setdefault("EDGAR_LOCAL_DATA_DIR", str(cache_dir.resolve()))
    from edgar.documents import ParserConfig, parse_html

    document = parse_html(
        decode_html(payload),
        ParserConfig(
            form="10-K",
            enable_parallel=False,
            extract_xbrl=False,
        ),
    )
    section = document.get_section(f"Item {rule.item}") or document.get_section(rule.primary_key)
    if section is None:
        return Candidate("", "edgartools", ["section_not_found"])
    lines = [normalize_text(line) for line in section.text().splitlines()]
    text = "\n\n".join(
        line
        for line in lines
        if line and not re.fullmatch(r"(?:back to )?table of contents|\d{1,4}", line, re.I)
    )
    return Candidate(
        text,
        "edgartools",
        [] if text else ["section_not_found"],
        boundary_method="edgartools_sections",
    )


def quality_flags(candidate: Candidate, rule: SectionRule, prior_words: int | None) -> list[str]:
    flags = list(candidate.flags)
    if candidate.word_count < rule.min_words:
        flags.append("too_few_words")
    if prior_words and not 0.5 <= candidate.word_count / prior_words <= 2:
        flags.append("word_count_outlier")
    heading = normalize_text(candidate.text[:250])
    if not re.match(
        rf"^(?:item\s*{re.escape(rule.item)}\s*[.:-]?\s*)?{re.escape(rule.title)}\b", heading, re.I
    ):
        flags.append("implausible_start")
    if re.search(r"\bitem\s*2\b", candidate.text, re.I):
        flags.append("contains_item_2")
    if (
        "incorporated by reference" in candidate.text.lower()
        and candidate.word_count < rule.min_words
    ):
        flags.append("incorporated_by_reference")
    if re.search(r"(?:in the section titled|refer to|see section|\bsee)\s*$", candidate.text, re.I):
        flags.append("truncated_sentence")
    return sorted(set(flags))


def extract_section(
    payload: bytes,
    blocks: list[Block],
    rule: SectionRule,
    *,
    prior_words: int | None = None,
    cache_dir: Path = Path("data/edgartools"),
    primary: Callable[[bytes, SectionRule, Path], Candidate] = edgartools_extract,
) -> Extraction:
    warnings: list[str] = []
    try:
        first = primary(payload, rule, cache_dir)
    except Exception as error:
        # A parser failure is recorded and can be recovered by the independent path.
        first = Candidate("", "edgartools", ["parser_error"])
        warnings.append(f"edgartools_error:{type(error).__name__}")
    fallback = fallback_extract(blocks, rule)
    candidates = [first, fallback]
    evaluated = [
        (candidate, quality_flags(candidate, rule, prior_words)) for candidate in candidates
    ]
    if first.word_count and fallback.word_count:
        disagreement = abs(first.word_count - fallback.word_count) / max(
            first.word_count, fallback.word_count
        )
        if disagreement > 0.1:
            warnings.append("extractor_word_count_disagreement")
    # Prefer the primary when it passes. Otherwise choose the candidate with fewer
    # quality failures, preserving the primary as the tie-breaker.
    selected, flags = min(evaluated, key=lambda pair: (len(pair[1]), candidates.index(pair[0])))
    if "extractor_word_count_disagreement" in warnings and bool(evaluated[0][1]) == bool(
        evaluated[1][1]
    ):
        flags = sorted(set([*flags, "extractor_disagreement_unresolved"]))
    diagnostics: list[dict[str, object]] = [
        {
            "extractor": candidate.extractor,
            "word_count": candidate.word_count,
            "quality_flags": checks,
            "start_block": candidate.start_block,
            "end_block": candidate.end_block,
            "boundary_method": candidate.boundary_method,
            "text": candidate.text,
        }
        for candidate, checks in evaluated
    ]
    return Extraction(selected, diagnostics, flags, warnings, version("edgartools"))
