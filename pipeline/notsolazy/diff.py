"""Sentence/word diffs with half-open Unicode offsets into both original strings."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any

import pysbd  # type: ignore[import-untyped]
from diff_match_patch import diff_match_patch  # type: ignore[import-untyped]

DIFFER_VERSION = "diff-v1"
MASK_VERSION = "fiscal-mask-v1"


@dataclass(frozen=True)
class Mask:
    start: int
    end: int
    token: str


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


def masks(text: str, report_date: date | None) -> list[Mask]:
    if report_date is None:
        return []
    year = report_date.year
    month = report_date.strftime("%B")
    patterns = [
        (rf"\bfiscal(?:\s+year)?\s+{year}\b", "<FISCAL_YEAR>"),
        (rf"\bas of\s+{month}\s+{report_date.day},?\s+{year}\b", "<REPORT_DATE>"),
        (rf"\bas of\s+{report_date.isoformat()}\b", "<REPORT_DATE>"),
    ]
    spans = [
        Mask(m.start(), m.end(), token)
        for pattern, token in patterns
        for m in re.finditer(pattern, text, re.I)
    ]
    return sorted(spans, key=lambda span: span.start)


def masked_text(text: str, report_date: date | None) -> str:
    result, cursor = "", 0
    for span in masks(text, report_date):
        result += text[cursor : span.start] + span.token
        cursor = span.end
    return result + text[cursor:]


def _tokens(text: str, spans: list[Mask]) -> list[Token]:
    result: list[Token] = []
    cursor = 0
    for span in [*spans, Mask(len(text), len(text), "")]:
        for match in re.finditer(r"\s+|\w+|[^\w\s]", text[cursor : span.start]):
            result.append(Token(match.group(), cursor + match.start(), cursor + match.end()))
        if span.token:
            result.append(Token(span.token, span.start, span.end))
        cursor = span.end
    return result


def diff_text(
    prior: str, current: str, prior_date: date | None = None, current_date: date | None = None
) -> dict[str, Any]:
    prior_masks, current_masks = masks(prior, prior_date), masks(current, current_date)
    left, right = _tokens(prior, prior_masks), _tokens(current, current_masks)
    vocabulary = {
        value: chr(i + 1)
        for i, value in enumerate(dict.fromkeys(token.value for token in [*left, *right]))
    }
    if len(vocabulary) > 60000:
        raise ValueError("factor_too_large_for_word_diff")
    ops: list[dict[str, Any]] = []

    def append(op: str, old: list[int] | None, new: list[int] | None, trivial: bool) -> None:
        if ops and ops[-1]["op"] == op and ops[-1]["trivial"] == trivial:
            previous = ops[-1]
            contiguous = all(
                previous[side] is None
                if value is None
                else previous[side] is not None and previous[side][1] == value[0]
                for side, value in (("prior", old), ("current", new))
            )
            if contiguous:
                for side, value in (("prior", old), ("current", new)):
                    if value is not None:
                        previous[side][1] = value[1]
                return
        ops.append({"op": op, "prior": old, "current": new, "trivial": trivial})

    def words(a0: int, a1: int, b0: int, b1: int) -> None:
        a = [token for token in left if a0 <= token.start < a1]
        b = [token for token in right if b0 <= token.start < b1]
        engine = diff_match_patch()
        engine.Diff_Timeout = 0
        changes = engine.diff_main(
            "".join(vocabulary[t.value] for t in a), "".join(vocabulary[t.value] for t in b), False
        )
        engine.diff_cleanupSemantic(changes)
        ai, bi = 0, 0
        for kind, value in changes:
            count = len(value)
            old = [a[ai].start, a[ai + count - 1].end] if kind != 1 else None
            new = [b[bi].start, b[bi + count - 1].end] if kind != -1 else None
            if kind == 0:
                for offset in range(count):
                    x, y = a[ai + offset], b[bi + offset]
                    append(
                        "equal",
                        [x.start, x.end],
                        [y.start, y.end],
                        prior[x.start : x.end] != current[y.start : y.end],
                    )
            else:
                append("insert" if kind == 1 else "delete", old, new, False)
            ai += count if kind != 1 else 0
            bi += count if kind != -1 else 0

    def sentences(text: str, tokens: list[Token]) -> list[tuple[int, int, str]]:
        if not text:
            return []
        spans = pysbd.Segmenter(language="en", clean=False, char_span=True).segment(text)
        boundaries = [0, *[span.start for span in spans[1:]], len(text)]
        # Do not split a fiscal mask token at a sentence boundary.
        boundaries = [p for p in boundaries if not any(t.start < p < t.end for t in tokens)]
        return [
            (a, b, "".join(vocabulary[t.value] for t in tokens if a <= t.start < b))
            for a, b in zip(boundaries, boundaries[1:], strict=False)
        ]

    a_sent, b_sent = sentences(prior, left), sentences(current, right)
    matcher = SequenceMatcher(None, [s[2] for s in a_sent], [s[2] for s in b_sent], autojunk=False)
    for _, a0, a1, b0, b1 in matcher.get_opcodes():
        words(
            a_sent[a0][0] if a0 < len(a_sent) else len(prior),
            a_sent[a1 - 1][1] if a1 > a0 else (a_sent[a0][0] if a0 < len(a_sent) else len(prior)),
            b_sent[b0][0] if b0 < len(b_sent) else len(current),
            b_sent[b1 - 1][1] if b1 > b0 else (b_sent[b0][0] if b0 < len(b_sent) else len(current)),
        )
    return {
        "ops": ops,
        "prior_masks": [asdict(m) for m in prior_masks],
        "current_masks": [asdict(m) for m in current_masks],
        "differ_version": DIFFER_VERSION,
        "mask_version": MASK_VERSION,
    }
