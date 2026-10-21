"""Offline clean/extract persistence. These stages never construct an SEC client."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from lxml import etree
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from notsolazy.clean import CLEANER_VERSION, Block, clean_html
from notsolazy.config import SectionRule
from notsolazy.extract import EXTRACTOR_VERSION, extract_section
from notsolazy.models import CleanedFiling, Filing, FilingPair, ReviewEntry, Section
from notsolazy.storage import BlobStore

BLOCKS = TypeAdapter(list[Block])


class StageInputError(ValueError):
    """A safe, machine-readable reason rather than a dump of input text."""


def _review(session: Session, accession: str, stage: str, reason: str, code_version: str) -> None:
    key = hashlib.sha256(f"{accession}:{stage}:{code_version}:{reason}".encode()).hexdigest()
    existing = session.get(ReviewEntry, key)
    if existing is not None and existing.resolved_at is not None:
        existing.note = (existing.note or "") + (
            f" Reopened by {code_version}; the flag was reproduced after resolution at "
            f"{existing.resolved_at.isoformat()}."
        )
        existing.resolved_at = None
    if existing is None:
        session.add(
            ReviewEntry(
                id=key,
                accession=accession,
                stage=stage,
                reason=reason,
                code_version=code_version,
                created_at=datetime.now(UTC),
            )
        )


def _reconcile_review(session: Session, accession: str, item: str, flags: list[str]) -> None:
    active_reasons = {f"{item}:{flag}" for flag in flags}
    for entry in session.scalars(
        select(ReviewEntry).where(
            ReviewEntry.accession == accession,
            ReviewEntry.stage == "extract",
            ReviewEntry.resolved_at.is_(None),
        )
    ):
        if entry.reason.startswith(item + ":") and (
            entry.reason not in active_reasons or entry.code_version != EXTRACTOR_VERSION
        ):
            entry.resolved_at = datetime.now(UTC)
            entry.note = f"Re-evaluated by {EXTRACTOR_VERSION}; this flag is no longer current."


def _raw(filing: Filing, store: BlobStore) -> bytes:
    if not filing.raw_blob_key or not store.exists(filing.raw_blob_key):
        raise StageInputError("raw_blob_missing")
    raw = store.read(filing.raw_blob_key)
    if not filing.sha256 or hashlib.sha256(raw).hexdigest() != filing.sha256:
        raise StageInputError("raw_checksum_mismatch")
    return raw


def clean_filing(
    session: Session, filing: Filing, store: BlobStore, *, force: bool = False
) -> CleanedFiling:
    raw = _raw(filing, store)
    existing = session.get(CleanedFiling, filing.accession)
    if (
        existing
        and not force
        and existing.source_sha256 == filing.sha256
        and existing.cleaner_version == CLEANER_VERSION
        and store.exists(existing.blob_key)
    ):
        return existing
    try:
        blocks = clean_html(raw)
    except (etree.ParserError, etree.XMLSyntaxError):
        raise StageInputError("html_parse_failed") from None
    payload = BLOCKS.dump_json(blocks)
    source_hash = hashlib.sha256(raw).hexdigest()
    key = f"clean/{filing.accession}/{CLEANER_VERSION}-{source_hash[:12]}.json"
    store.write(key, payload)
    row = existing or CleanedFiling(accession=filing.accession)
    row.blob_key, row.source_sha256 = key, hashlib.sha256(raw).hexdigest()
    row.blocks_sha256 = hashlib.sha256(payload).hexdigest()
    row.block_count, row.word_count = len(blocks), sum(len(block.text.split()) for block in blocks)
    row.cleaner_version, row.created_at = CLEANER_VERSION, datetime.now(UTC)
    row.quality_flags = [] if blocks else ["no_visible_text"]
    session.add(row)
    for flag in row.quality_flags:
        _review(session, filing.accession, "clean", flag, CLEANER_VERSION)
    session.flush()
    return row


def extract_filing(
    session: Session,
    filing: Filing,
    store: BlobStore,
    rule: SectionRule,
    *,
    prior_words: int | None = None,
    force: bool = False,
    cache_dir: Path = Path("data/edgartools"),
) -> Section:
    raw = _raw(filing, store)
    cleaned = session.get(CleanedFiling, filing.accession)
    if not cleaned or cleaned.cleaner_version != CLEANER_VERSION:
        raise StageInputError("clean_stage_missing_or_stale")
    if cleaned.source_sha256 != filing.sha256:
        raise StageInputError("clean_source_checksum_mismatch")
    if not store.exists(cleaned.blob_key):
        raise StageInputError("clean_blob_missing")
    payload = store.read(cleaned.blob_key)
    if hashlib.sha256(payload).hexdigest() != cleaned.blocks_sha256:
        raise StageInputError("clean_checksum_mismatch")
    try:
        blocks = BLOCKS.validate_json(payload)
    except ValidationError:
        raise StageInputError("invalid_clean_blob") from None
    signature = hashlib.sha256(
        json.dumps(
            {
                "raw": filing.sha256,
                "clean": cleaned.blocks_sha256,
                "cleaner": CLEANER_VERSION,
                "extractor": EXTRACTOR_VERSION,
                "primary": version("edgartools"),
                "rule": asdict(rule),
                "prior_words": prior_words,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = session.get(Section, (filing.accession, rule.item))
    if (
        existing
        and not force
        and existing.input_signature == signature
        and store.exists(existing.candidates_blob_key)
    ):
        return existing
    result = extract_section(raw, blocks, rule, prior_words=prior_words, cache_dir=cache_dir)
    key = f"extraction-candidates/{filing.accession}/{rule.item}/{signature}.json"
    store.write(
        key,
        json.dumps(
            {
                "accession": filing.accession,
                "source_url": filing.primary_doc_url,
                "item": rule.item,
                "selected": result.selected.extractor,
                "input_signature": signature,
                "warnings": result.warnings,
                "extractor_version": EXTRACTOR_VERSION,
                "primary_version": result.primary_version,
                "candidates": result.candidates,
            }
        ).encode(),
    )
    row = existing or Section(accession=filing.accession, item=rule.item)
    row.text, row.word_count = result.selected.text, result.selected.word_count
    row.text_sha256 = hashlib.sha256(row.text.encode()).hexdigest()
    row.extractor, row.extractor_version = result.selected.extractor, EXTRACTOR_VERSION
    row.primary_version, row.cleaner_version = result.primary_version, CLEANER_VERSION
    row.input_signature, row.prior_word_count = signature, prior_words
    row.start_block, row.end_block = result.selected.start_block, result.selected.end_block
    row.quality_flags, row.warnings = result.flags, result.warnings
    row.diagnostics = [
        {k: v for k, v in candidate.items() if k != "text"} for candidate in result.candidates
    ]
    row.candidates_blob_key, row.created_at = key, datetime.now(UTC)
    session.add(row)
    _reconcile_review(session, filing.accession, rule.item, row.quality_flags)
    for flag in row.quality_flags:
        _review(session, filing.accession, "extract", f"{rule.item}:{flag}", EXTRACTOR_VERSION)
    session.flush()
    return row


def process_pair(
    session: Session,
    pair: FilingPair,
    store: BlobStore,
    rule: SectionRule,
    *,
    stage: str,
    force: bool,
    cache_dir: Path,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    prior_words: int | None = None
    for accession in dict.fromkeys(filter(None, [pair.prior_accession, pair.current_accession])):
        filing = session.get(Filing, accession)
        assert filing is not None
        try:
            if stage == "clean":
                cleaned = clean_filing(session, filing, store, force=force)
                results.append(
                    {
                        "accession": accession,
                        "blocks": cleaned.block_count,
                        "blob_key": cleaned.blob_key,
                        "source_url": filing.primary_doc_url,
                        "word_count": cleaned.word_count,
                        "quality_flags": cleaned.quality_flags,
                        "cleaner_version": cleaned.cleaner_version,
                    }
                )
            else:
                section = extract_filing(
                    session,
                    filing,
                    store,
                    rule,
                    prior_words=prior_words,
                    force=force,
                    cache_dir=cache_dir,
                )
                prior_words = section.word_count or None
                results.append(
                    {
                        "accession": accession,
                        "item": rule.item,
                        "status": "review_required" if section.quality_flags else "extracted",
                        "word_count": section.word_count,
                        "extractor": section.extractor,
                        "quality_flags": section.quality_flags,
                        "warnings": section.warnings,
                        "extractor_version": section.extractor_version,
                        "primary_version": section.primary_version,
                        "candidates_blob_key": section.candidates_blob_key,
                        "source_url": filing.primary_doc_url,
                        "text_sha256": section.text_sha256,
                    }
                )
        except (StageInputError, OSError) as error:
            reason = str(error) if isinstance(error, StageInputError) else "blob_io_error"
            if stage == "extract":
                stale = session.get(Section, (filing.accession, rule.item))
                if stale:
                    stale.quality_flags = [reason]
                    stale.input_signature = ""
            _review(
                session,
                filing.accession,
                stage,
                f"{rule.item}:{reason}",
                CLEANER_VERSION if stage == "clean" else EXTRACTOR_VERSION,
            )
            results.append(
                {
                    "accession": accession,
                    "item": rule.item,
                    "status": "review_required",
                    "quality_flags": [reason],
                }
            )
            if accession == pair.prior_accession:
                prior_words = None
    return results
