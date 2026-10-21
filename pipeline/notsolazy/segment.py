"""Formatting-aware units with offsets into the selected extraction, never a substitute text."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from notsolazy.clean import Block, normalize_text
from notsolazy.config import SectionRule

SEGMENTER_VERSION = "segment-v1"


@dataclass(frozen=True)
class Factor:
    id: str
    accession: str
    item: str
    position: int
    group: str
    heading: str
    body: str
    text: str
    text_hash: str
    segmentation: str
    role: str
    start: int
    end: int


def segment(text: str, accession: str, rule: SectionRule, blocks: list[Block]) -> list[Factor]:
    styles = {normalize_text(block.text): block for block in blocks}
    paragraphs: list[re.Match[str]] = []
    for paragraph in re.finditer(r"\S(?:[^\n]|\n(?!\s*\n))*", text):
        block = styles.get(normalize_text(paragraph.group()))
        prefix = block.leading_heading if block else ""
        if prefix and 4 <= len(prefix.split()) <= 100 and paragraph.group().startswith(prefix):
            cut = paragraph.start() + len(prefix)
            heading_match = re.compile(r"[\s\S]+").match(text, paragraph.start(), cut)
            assert heading_match is not None
            paragraphs.append(heading_match)
            remainder = re.compile(r"\S[\s\S]*").search(text, cut, paragraph.end())
            if remainder:
                paragraphs.append(remainder)
            assert block is not None
            styles[normalize_text(prefix)] = block.model_copy(update={"is_bold": True})
        else:
            paragraphs.append(paragraph)
    heading_ids: set[int] = set()
    groups: set[int] = set()
    summaries: set[int] = set()
    titles: set[int] = set()
    for i, paragraph in enumerate(paragraphs):
        value = paragraph.group().strip()
        if re.fullmatch(
            rf"(?:item\s*{re.escape(rule.item)}\s*[.:-]?\s*)?{re.escape(rule.title)}[.]?",
            value,
            re.I,
        ):
            titles.add(i)
            continue
        block = styles.get(normalize_text(value))
        styled = block and (
            block.is_bold
            or block.is_italic
            or block.is_underlined
            or block.is_all_caps
            or block.tag in {"h1", "h2", "h3", "h4"}
        )
        if re.fullmatch(r"summary of (?:our )?risk factors[.:]?", value, re.I):
            summaries.add(i)
            groups.add(i)
        elif styled and len(value.split()) <= 18 and not re.search(r"[.!?;:]$", value):
            # Small mixed bold/italic labels are commonly subheads within a risk.
            if block and not (block.is_bold and block.is_italic and heading_ids):
                groups.add(i)
        elif styled and 4 <= len(value.split()) <= 100 and re.search(r"[.!?]$", value):
            heading_ids.add(i)
    structured = bool(heading_ids)
    results: list[Factor] = []
    group = ""
    summary = False
    pending: list[int] = []
    heading = ""

    def flush() -> None:
        nonlocal pending, heading
        if not pending:
            return
        start, end = paragraphs[pending[0]].start(), paragraphs[pending[-1]].end()
        value = text[start:end]
        role = (
            "summary" if summary else ("risk" if heading or not structured or group else "preamble")
        )
        body = value[len(heading) :].lstrip() if heading else value
        digest = hashlib.sha256(value.encode()).hexdigest()
        key = hashlib.sha256(f"{accession}:{rule.item}:{start}:{digest}".encode()).hexdigest()
        results.append(
            Factor(
                key,
                accession,
                rule.item,
                len(results),
                group,
                heading,
                body,
                value,
                digest,
                "heading" if heading else "paragraph",
                role,
                start,
                end,
            )
        )
        pending, heading = [], ""

    for i, paragraph in enumerate(paragraphs):
        if i in titles:
            flush()
        elif i in groups:
            flush()
            group = paragraph.group().strip()
            summary = i in summaries
        elif i in heading_ids:
            flush()
            summary = False
            heading = paragraph.group().strip()
            pending = [i]
        elif summary:
            pending.append(i)
        elif structured and heading:
            pending.append(i)
        elif structured and not group:
            pending.append(i)
        else:
            pending = [i]
            flush()
    flush()
    return results
