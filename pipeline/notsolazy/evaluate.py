"""Offline source-anchored evaluation, independent of stored predictions and database state."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from lxml import html
from pydantic import BaseModel, ConfigDict, Field, model_validator

from notsolazy.align import ALIGNER_VERSION, MODEL_REVISION, Encoder, align
from notsolazy.clean import CLEANER_VERSION, clean_html, decode_html, normalize_text
from notsolazy.config import section_rule
from notsolazy.extract import EXTRACTOR_VERSION, extract_section
from notsolazy.segment import SEGMENTER_VERSION, Factor, segment
from notsolazy.storage import LocalBlobStore

EVALUATOR_VERSION = "evaluate-v1"


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    heading: str = Field(min_length=15)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    report_date: date
    source_url: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture: str
    section_start: str = Field(min_length=30)
    section_end: str = Field(min_length=30)
    factors: list[Label] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source(self) -> Source:
        url = urlparse(self.source_url)
        if (
            url.scheme != "https"
            or url.netloc != "www.sec.gov"
            or not url.path.startswith("/Archives/edgar/data/")
        ):
            raise ValueError("Expected an original SEC Archives URL.")
        if len({f.id for f in self.factors}) != len(self.factors):
            raise ValueError("Duplicate reference factor ID.")
        headings = [normalize_text(f.heading) for f in self.factors]
        if len(set(headings)) != len(headings):
            raise ValueError("Duplicate reference heading; add disambiguating anchors first.")
        return self


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prior: list[str]
    current: list[str]
    kind: Literal["match", "split", "merge", "added", "removed", "unresolved"]
    note: str = ""

    @model_validator(mode="after")
    def validate_shape(self) -> Relation:
        a, b = len(self.prior), len(self.current)
        valid = {
            "match": a == b == 1,
            "split": a == 1 and b > 1,
            "merge": a > 1 and b == 1,
            "added": a == 0 and b == 1,
            "removed": a == 1 and b == 0,
            "unresolved": a > 0 and b > 0 and bool(self.note.strip()),
        }
        if not valid[self.kind]:
            raise ValueError(f"Invalid {self.kind} relation shape.")
        return self


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    notes: str
    prior: Source
    current: Source
    relations: list[Relation]

    @model_validator(mode="after")
    def validate_coverage(self) -> Pair:
        if self.prior.report_date >= self.current.report_date:
            raise ValueError("Prior report date must precede current report date.")
        for side in ("prior", "current"):
            expected = {f.id for f in getattr(self, side).factors}
            actual = [f for r in self.relations for f in getattr(r, side)]
            if set(actual) != expected or len(actual) != len(expected):
                raise ValueError(f"Every {side} factor must occur in exactly one relation.")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    label_version: str
    review: dict[str, Any]
    pairs: list[Pair] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pairs(self) -> Manifest:
        if len({p.id for p in self.pairs}) != len(self.pairs):
            raise ValueError("Duplicate pair ID.")
        accessions = [s.accession for p in self.pairs for s in (p.prior, p.current)]
        if len(set(accessions)) != len(accessions):
            raise ValueError("Repeated filing would inflate document-level metrics.")
        return self


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(path.read_text())


def checked_source(source: Source, fixture_root: Path) -> bytes:
    """Reject stale/corrupt references before measuring any predictions."""
    raw = gzip.decompress(LocalBlobStore(fixture_root).read(source.fixture))
    if hashlib.sha256(raw).hexdigest() != source.sha256:
        raise ValueError(f"Source checksum mismatch: {source.accession}")
    # This reader deliberately does not use clean/extract/segment or their outputs.
    tree = html.fromstring(decode_html(raw), parser=html.HTMLParser(no_network=True))
    text = normalize_text(tree.text_content())
    start, end = normalize_text(source.section_start), normalize_text(source.section_end)
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Section reference anchors must each occur once: {source.accession}")
    begin, finish = text.find(start), text.find(end, text.find(start) + len(start))
    if begin < 0 or finish < begin:
        raise ValueError(f"Section reference anchors absent/out of order: {source.accession}")
    section = text[begin : finish + len(end)]
    cursor = 0
    for factor in source.factors:
        position = section.find(normalize_text(factor.heading), cursor)
        if position < 0:
            raise ValueError(
                f"Reference heading absent/out of order: {source.accession}:{factor.id}"
            )
        cursor = position + len(normalize_text(factor.heading))
    return raw


def measure(expected: set[Any], predicted: set[Any]) -> dict[str, Any]:
    return counts(len(expected & predicted), len(predicted - expected), len(expected - predicted))


def counts(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def heading_mapping(
    reference: list[Label], predicted: list[Factor]
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    """A reference heading must start a distinct predicted risk unit, not hide in its body."""
    candidates = {
        label.id: [
            f.id
            for f in predicted
            if normalize_text(f.text).startswith(normalize_text(label.heading))
        ]
        for label in reference
    }
    frequencies = Counter(f for ids in candidates.values() for f in ids)
    mapping = {
        ids[0]: label
        for label, ids in candidates.items()
        if len(ids) == 1 and frequencies[ids[0]] == 1
    }
    errors = [
        {"category": "missed_risk_start", "reference": f.id, "heading": f.heading}
        for f in reference
        if f.id not in mapping.values()
    ]
    errors.extend(
        {
            "category": "unexpected_risk_unit",
            "prediction": f.id,
            "heading": f.heading or f.text[:160],
        }
        for f in predicted
        if f.id not in mapping
    )
    return (
        mapping,
        counts(len(mapping), len(predicted) - len(mapping), len(reference) - len(mapping)),
        errors,
    )


def evaluate_pair(
    pair: Pair,
    payloads: tuple[bytes, bytes],
    cache_dir: Path,
    encoder: Encoder | None,
    *,
    semantic_threshold: float = 0.80,
) -> dict[str, Any]:
    rule = section_rule("1A")
    result: dict[str, Any] = {
        "id": pair.id,
        "notes": pair.notes,
        "reference": pair.model_dump(mode="json"),
        "documents": [],
        "errors": [],
    }
    predicted: list[list[Factor]] = []
    mappings: list[dict[str, str]] = []
    prior_words: int | None = None
    for side, source, raw in zip(
        ("prior", "current"), (pair.prior, pair.current), payloads, strict=True
    ):
        blocks = clean_html(raw)
        extraction = extract_section(
            raw, blocks, rule, prior_words=prior_words, cache_dir=cache_dir
        )
        if side == "prior":
            prior_words = extraction.selected.word_count
        text = extraction.selected.text
        normalized = normalize_text(text)
        start_ok = normalize_text(source.section_start) in normalized[:1000]
        end_ok = normalized.endswith(normalize_text(source.section_end))
        factors = [f for f in segment(text, source.accession, rule, blocks) if f.role == "risk"]
        mapping, score, errors = heading_mapping(source.factors, factors)
        predicted.append(factors)
        mappings.append(mapping)
        for error in errors:
            result["errors"].append({"side": side, **error})
        if not (start_ok and end_ok):
            result["errors"].append(
                {
                    "category": "section_boundary",
                    "side": side,
                    "start_ok": start_ok,
                    "end_ok": end_ok,
                    "expected_end": source.section_end,
                    "actual_end": normalized[-200:],
                }
            )
        result["documents"].append(
            {
                "side": side,
                "accession": source.accession,
                "source_url": source.source_url,
                "source_sha256": source.sha256,
                "extractor": extraction.selected.extractor,
                "primary_version": extraction.primary_version,
                "flags": extraction.flags,
                "start_ok": start_ok,
                "end_ok": end_ok,
                "boundaries_pass": start_ok and end_ok,
                "heading_starts": score,
            }
        )
    if encoder is None:
        result["alignment"] = None
        return result

    unresolved = {
        side: {f for r in pair.relations if r.kind == "unresolved" for f in getattr(r, side)}
        for side in ("prior", "current")
    }
    expected_links = {
        (a, b)
        for r in pair.relations
        if r.kind in {"match", "split", "merge"}
        for a in r.prior
        for b in r.current
    }
    expected_added = {f for r in pair.relations if r.kind == "added" for f in r.current}
    expected_removed = {f for r in pair.relations if r.kind == "removed" for f in r.prior}
    actual_links: set[tuple[str, str]] = set()
    actual_added: set[str] = set()
    actual_removed: set[str] = set()
    for match in align(
        predicted[0],
        predicted[1],
        encoder,
        prior_date=pair.prior.report_date,
        current_date=pair.current.report_date,
        semantic_threshold=semantic_threshold,
    ):
        a = (
            mappings[0].get(match.prior_id, "unmapped:" + match.prior_id)
            if match.prior_id
            else None
        )
        b = (
            mappings[1].get(match.current_id, "unmapped:" + match.current_id)
            if match.current_id
            else None
        )
        # Unresolved labels never silently become added/removed or missing links.
        # A resolved endpoint linked to an unresolved one still loses its expected edge.
        if a in unresolved["prior"] or b in unresolved["current"]:
            continue
        if a is not None and b is not None:
            actual_links.add((a, b))
        elif b is not None:
            actual_added.add(b)
        elif a is not None:
            actual_removed.add(a)
    detected_prior, detected_current = set(mappings[0].values()), set(mappings[1].values())
    observed_expected = {
        (a, b) for a, b in expected_links if a in detected_prior and b in detected_current
    }
    observed_actual = {
        (a, b) for a, b in actual_links if a in detected_prior and b in detected_current
    }
    result["alignment"] = {
        "links_end_to_end": measure(expected_links, actual_links),
        "links_on_detected_headings": measure(observed_expected, observed_actual),
        "added": measure(expected_added, actual_added),
        "removed": measure(expected_removed, actual_removed),
        "reference_links": len(expected_links),
        "reference_links_with_both_headings_detected": len(observed_expected),
        "unresolved_reference_factors": sum(map(len, unresolved.values())),
        "split_groups": sum(r.kind == "split" for r in pair.relations),
        "merge_groups": sum(r.kind == "merge" for r in pair.relations),
    }
    descriptions = {
        side: {
            **{f.id: f.heading for f in source.factors},
            **{"unmapped:" + f.id: f.heading or f.text[:160] for f in factors},
        }
        for side, source, factors in zip(
            ("prior", "current"), (pair.prior, pair.current), predicted, strict=True
        )
    }
    for category, rows in (
        ("false_link", actual_links - expected_links),
        ("missing_link", expected_links - actual_links),
    ):
        for a, b in sorted(rows):
            result["errors"].append(
                {
                    "category": category,
                    "prior": a,
                    "current": b,
                    "prior_heading": descriptions["prior"][a],
                    "current_heading": descriptions["current"][b],
                }
            )
    for category, factor_rows in (
        ("false_added", actual_added - expected_added),
        ("missed_added", expected_added - actual_added),
        ("false_removed", actual_removed - expected_removed),
        ("missed_removed", expected_removed - actual_removed),
    ):
        side = "current" if category.endswith("added") else "prior"
        result["errors"].extend(
            {"category": category, "factor": f, "heading": descriptions[side][f]}
            for f in sorted(factor_rows)
        )
    return result


def evaluate(
    manifest: Manifest,
    fixture_root: Path,
    cache_dir: Path,
    encoder: Encoder | None,
    *,
    semantic_threshold: float = 0.80,
) -> dict[str, Any]:
    # Validate *all* fixtures before doing work or printing partial measurements.
    payloads = [
        (checked_source(p.prior, fixture_root), checked_source(p.current, fixture_root))
        for p in manifest.pairs
    ]
    pairs = [
        evaluate_pair(p, raw, cache_dir, encoder, semantic_threshold=semantic_threshold)
        for p, raw in zip(manifest.pairs, payloads, strict=True)
    ]
    documents = [d for p in pairs for d in p["documents"]]

    def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return counts(*(sum(row[key] for row in rows) for key in ("tp", "fp", "fn")))

    summary: dict[str, Any] = {
        "pairs": len(pairs),
        "documents": len(documents),
        "section_boundaries_pass": sum(d["boundaries_pass"] for d in documents),
        "section_boundary_pass_rate": sum(d["boundaries_pass"] for d in documents) / len(documents),
        "documents_flagged": sum(bool(d["flags"]) for d in documents),
        "heading_starts": aggregate([d["heading_starts"] for d in documents]),
        "alignment": None,
        "error_categories": dict(
            sorted(Counter(e["category"] for p in pairs for e in p["errors"]).items())
        ),
    }
    if encoder is not None:
        summary["alignment"] = {
            name: aggregate([p["alignment"][name] for p in pairs])
            for name in ("links_end_to_end", "links_on_detected_headings", "added", "removed")
        }
        summary["alignment"]["unresolved_reference_factors"] = sum(
            p["alignment"]["unresolved_reference_factors"] for p in pairs
        )
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "label_version": manifest.label_version,
        "labels_sha256": hashlib.sha256(manifest.model_dump_json().encode()).hexdigest(),
        "review": manifest.review,
        "versions": {
            "cleaner": CLEANER_VERSION,
            "extractor": EXTRACTOR_VERSION,
            "segmenter": SEGMENTER_VERSION,
            "aligner": ALIGNER_VERSION if encoder is not None else None,
            "model_revision": MODEL_REVISION if encoder is not None else None,
            "semantic_threshold": semantic_threshold if encoder is not None else None,
            "fuzzy_threshold": 85 if encoder is not None else None,
        },
        "metric_definitions": {
            "section_boundaries": (
                "Start anchor in first 1000 normalized characters AND exact normalized end-anchor "
                "suffix; all filings included, even flagged ones. Not full text accuracy."
            ),
            "heading_starts": (
                "One distinct predicted risk unit must start with each reference heading. "
                "Does not measure exact body-end segmentation."
            ),
            "links_end_to_end": (
                "Micro precision/recall of labeled continuity edges including segmentation misses "
                "and split/merge edges. Unmapped units count as false predictions."
            ),
            "links_on_detected_headings": (
                "Conditional micro precision/recall restricted to links whose two reference "
                "heading starts were detected. Read alongside heading recall and end-to-end links."
            ),
            "added_removed": (
                "Standalone factor additions/removals, not new/deleted topics. Split/merge "
                "continuations are not additions/removals. Unresolved reference endpoints excluded."
            ),
            "undefined": "A zero denominator produces null, never a fabricated perfect score.",
        },
        "summary": summary,
        "pairs": pairs,
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]

    def metric(value: dict[str, Any]) -> str:
        def percent(number: float | None) -> str:
            return "undefined" if number is None else f"{number:.1%}"

        return (
            f"precision {percent(value['precision'])}; recall {percent(value['recall'])}; "
            f"TP/FP/FN {value['tp']}/{value['fp']}/{value['fn']}"
        )

    lines = [
        "# Filing comparison development evaluation",
        "",
        "Agent-reviewed pilot labels; independent human adjudication is pending. "
        "This is a development baseline, not a held-out benchmark or S&P 500 accuracy claim.",
        "",
        f"Sources: {summary['pairs']} filing pairs / {summary['documents']} cached SEC documents. "
        "All raw SHA-256 checks and reference anchors were verified before evaluation.",
        "",
        f"- Section boundary anchors pass: "
        f"{summary['section_boundaries_pass']}/{summary['documents']}.",
        f"- Documents with extraction flags: {summary['documents_flagged']} "
        "(included in denominators).",
        f"- Risk heading starts: {metric(summary['heading_starts'])}.",
    ]
    if summary["alignment"] is not None:
        for name, label in (
            ("links_end_to_end", "Continuity links, end to end"),
            ("links_on_detected_headings", "Continuity links, conditional on detected headings"),
            ("added", "Added standalone factors"),
            ("removed", "Removed standalone factors"),
        ):
            lines.append(f"- {label}: {metric(summary['alignment'][name])}.")
        lines.append(
            "- Unresolved reference endpoints excluded: "
            f"{summary['alignment']['unresolved_reference_factors']}."
        )
    else:
        lines.append("- Alignment was not run; no alignment metrics are inferred.")
    lines += ["", "## Definitions and limits", ""]
    for name, definition in report["metric_definitions"].items():
        lines.append(f"- {name}: {definition}")
    for limitation in report["review"].get("limitations", []):
        lines.append(f"- {limitation}")
    lines += ["", "## Versions", "", "```json", json.dumps(report["versions"], indent=2), "```"]
    for pair in report["pairs"]:
        lines += ["", f"## {pair['id']}", "", pair["notes"], ""]
        for doc in pair["documents"]:
            lines.append(
                f"- [{doc['side']} source]({doc['source_url']}): "
                f"boundary {'pass' if doc['boundaries_pass'] else 'FAIL'}; "
                f"heading starts {metric(doc['heading_starts'])}; "
                f"flags: {', '.join(doc['flags']) or 'none'}."
            )
        lines += ["", "### Errors", ""]
        if not pair["errors"]:
            lines.append("No errors under the measured checks.")
        for error in pair["errors"]:
            lines.append("- " + json.dumps(error, ensure_ascii=False))
    return "\n".join(lines) + "\n"
