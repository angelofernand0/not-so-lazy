"""Explicit local site snapshots. No EDGAR, model inference, scores or deployment."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC
from importlib.metadata import version
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from notsolazy.align import ALIGNER_VERSION
from notsolazy.clean import CLEANER_VERSION
from notsolazy.comparison import _alignment_inputs, _match_digest, _matches, digest
from notsolazy.config import SectionRule
from notsolazy.diff import DIFFER_VERSION, MASK_VERSION
from notsolazy.extract import EXTRACTOR_VERSION
from notsolazy.models import AlignmentRun, Company, CompanyAlias, DiffRecord, Filing, FilingPair
from notsolazy.processing import StageInputError
from notsolazy.segment import SEGMENTER_VERSION
from notsolazy.storage import BlobStore, LocalBlobStore
from notsolazy.universe import symbol_key

PREVIEW_VERSION = "preview-v1"


def read_diff(
    session: Session, pair: FilingPair, store: BlobStore, rule: SectionRule, threshold: float
) -> dict[str, Any]:
    _, _, _, _, signature = _alignment_inputs(session, pair, store, rule, threshold)
    run = session.get(AlignmentRun, (pair.id, rule.item))
    if not run or run.input_signature != signature:
        raise StageInputError("align_stage_missing_or_stale")
    if _match_digest(_matches(session, pair.id, rule.item)) != run.output_sha256:
        raise StageInputError("alignment_checksum_mismatch")
    expected = digest(
        [
            signature,
            run.output_sha256,
            DIFFER_VERSION,
            MASK_VERSION,
            version("pysbd"),
            version("diff-match-patch"),
        ]
    )
    record = session.get(DiffRecord, (pair.id, rule.item))
    if not record or record.input_signature != expected or not store.exists(record.blob_key):
        raise StageInputError("diff_stage_missing_or_stale")
    raw = store.read(record.blob_key)
    if hashlib.sha256(raw).hexdigest() != record.sha256:
        raise StageInputError("diff_checksum_mismatch")
    payload: dict[str, Any] = json.loads(raw)
    if payload.get("input_signature") != expected or payload.get("pair_id") != pair.id:
        raise StageInputError("diff_provenance_mismatch")
    validate_spans(payload)
    return payload


def validate_spans(payload: dict[str, Any]) -> None:
    for factor in payload["factors"]:
        for side in ("prior", "current"):
            text = factor[side]["text"] if factor[side] else ""
            cursor = 0
            for op in factor["diff"]["ops"]:
                span = op[side]
                if span is not None:
                    start, end = span
                    if start != cursor or not cursor < end <= len(text):
                        raise StageInputError("invalid_diff_offsets")
                    cursor = end
            if cursor != len(text):
                raise StageInputError("incomplete_diff_offsets")


def export_preview(
    session: Session,
    store: BlobStore,
    rule: SectionRule,
    tickers: list[str],
    output: Path,
    *,
    threshold: float = 0.80,
) -> dict[str, Any]:
    if not tickers:
        raise ValueError("Select preview tickers explicitly.")
    companies: list[tuple[str, Company]] = []
    for ticker in dict.fromkeys(t.upper() for t in tickers):
        if not re.fullmatch(r"[A-Z0-9.-]{1,20}", ticker):
            raise ValueError("Invalid ticker.")
        alias = session.get(CompanyAlias, symbol_key(ticker))
        company = session.get(Company, alias.cik) if alias else None
        if not company:
            raise ValueError(f"Ticker {ticker} is not in the universe.")
        companies.append((ticker, company))
    files: dict[str, bytes] = {}
    index: list[dict[str, Any]] = []
    timestamps = []
    filing_ids: set[str] = set()

    def encode(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    def filing_payload(accession: str | None) -> dict[str, Any] | None:
        filing = session.get(Filing, accession) if accession else None
        if not filing:
            return None
        filing_ids.add(filing.accession)
        if filing.fetched_at:
            timestamps.append(filing.fetched_at.replace(tzinfo=UTC))
        return {
            "accession": accession,
            "form": filing.form,
            "filed_at": str(filing.filed_at),
            "report_date": str(filing.report_date) if filing.report_date else None,
            "fiscal_year": filing.fiscal_year,
            "source_url": filing.primary_doc_url,
        }

    for ticker, company in companies:
        aliases = list(
            session.scalars(select(CompanyAlias.ticker).where(CompanyAlias.cik == company.cik))
        )
        pair = session.scalar(
            select(FilingPair).where(
                FilingPair.cik == company.cik, FilingPair.status != "superseded"
            )
        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "ticker": ticker,
            "cik": company.cik,
            "name": company.name,
            "sector": company.sector,
            "aliases": sorted(aliases),
            "item": rule.item,
            "status": "awaiting_filing",
            "flags": [],
            "current": None,
            "prior": None,
            "counts": None,
            "diff_url": None,
            "diff_sha256": None,
            "preview_version": PREVIEW_VERSION,
        }
        if pair:
            result.update(
                current=filing_payload(pair.current_accession),
                prior=filing_payload(pair.prior_accession),
                flags=pair.flags,
            )
            if not pair.prior_accession:
                result["status"] = "first_filing"
            else:
                try:
                    payload = read_diff(session, pair, store, rule, threshold)
                    blob = encode(payload)
                    key = f"diffs/{pair.current_accession}.json"
                    files[key] = blob
                    result.update(
                        status="ready",
                        diff_url=f"/site/{key}",
                        diff_sha256=hashlib.sha256(blob).hexdigest(),
                        counts=dict(Counter(f["change_type"] for f in payload["factors"])),
                    )
                    record = session.get(DiffRecord, (pair.id, rule.item))
                    assert record
                    timestamps.append(record.created_at.replace(tzinfo=UTC))
                except (StageInputError, OSError) as error:
                    result["status"] = "review_required"
                    result["flags"] = sorted(
                        set(
                            [
                                *pair.flags,
                                str(error)
                                if isinstance(error, StageInputError)
                                else "blob_io_error",
                            ]
                        )
                    )
        files[f"companies/{ticker}.json"] = encode(result)
        index.append(
            {key: result[key] for key in ("ticker", "cik", "name", "sector", "aliases", "status")}
        )
    index.sort(key=lambda company: company["ticker"])
    metadata = {
        "schema_version": 1,
        "status": "local_preview",
        "company_count": len(index),
        "comparison_count": sum(c["status"] == "ready" for c in index),
        "filing_count": len(filing_ids),
        "last_updated": max(timestamps).isoformat() if timestamps else None,
        "pipeline_versions": {
            "cleaner": CLEANER_VERSION,
            "extractor": EXTRACTOR_VERSION,
            "segmenter": SEGMENTER_VERSION,
            "aligner": ALIGNER_VERSION,
            "differ": DIFFER_VERSION,
            "preview": PREVIEW_VERSION,
        },
    }
    files["search-index.json"] = encode(index)
    files["meta.json"] = encode(metadata)
    # Build everything before replacing owned snapshot files. Never erase unrelated assets.
    target = LocalBlobStore(output)
    previous = (
        json.loads(target.read("preview-manifest.json"))
        if target.exists("preview-manifest.json")
        else []
    )
    for key, encoded in files.items():
        target.write(key, encoded)
    for key in previous:
        if key not in files and re.fullmatch(
            r"(?:companies/[A-Z0-9.-]+|diffs/[A-Za-z0-9-]+)\.json", key
        ):
            path = (output / key).resolve()
            if path.is_relative_to(output.resolve()) and path.is_file():
                path.unlink()
    target.write("preview-manifest.json", encode(sorted(files)))
    return metadata
