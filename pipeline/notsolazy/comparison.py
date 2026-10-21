"""Offline, stage-owned persistence with input checksums and downstream invalidation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from notsolazy.align import ALIGNER_VERSION, MODEL_ID, MODEL_REVISION, Encoder, Match, align
from notsolazy.clean import CLEANER_VERSION
from notsolazy.config import SectionRule
from notsolazy.diff import DIFFER_VERSION, MASK_VERSION, diff_text
from notsolazy.extract import EXTRACTOR_VERSION
from notsolazy.models import (
    Alignment,
    AlignmentRun,
    CleanedFiling,
    DiffRecord,
    Filing,
    FilingPair,
    RiskFactor,
    Section,
    SegmentationRun,
)
from notsolazy.processing import BLOCKS, StageInputError, _raw, extraction_signature
from notsolazy.segment import SEGMENTER_VERSION, Factor, segment
from notsolazy.storage import BlobStore


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _segment_inputs(
    session: Session, accession: str, store: BlobStore, rule: SectionRule
) -> tuple[Section, CleanedFiling, str]:
    filing = session.get(Filing, accession)
    section = session.get(Section, (accession, rule.item))
    cleaned = session.get(CleanedFiling, accession)
    if not filing or not section or not cleaned:
        raise StageInputError("extract_stage_missing")
    _raw(filing, store)
    if section.quality_flags or not section.input_signature:
        raise StageInputError("extraction_requires_review")
    if (
        section.extractor_version != EXTRACTOR_VERSION
        or section.cleaner_version != CLEANER_VERSION
        or cleaned.cleaner_version != CLEANER_VERSION
        or cleaned.source_sha256 != filing.sha256
    ):
        raise StageInputError("extraction_stale")
    if section.input_signature != extraction_signature(
        filing, cleaned, rule, section.prior_word_count
    ):
        raise StageInputError("extraction_stale")
    if hashlib.sha256(section.text.encode()).hexdigest() != section.text_sha256:
        raise StageInputError("section_checksum_mismatch")
    if (
        not store.exists(cleaned.blob_key)
        or hashlib.sha256(store.read(cleaned.blob_key)).hexdigest() != cleaned.blocks_sha256
    ):
        raise StageInputError("clean_checksum_mismatch")
    signature = digest(
        [
            section.input_signature,
            section.text_sha256,
            cleaned.blocks_sha256,
            SEGMENTER_VERSION,
            asdict(rule),
        ]
    )
    return section, cleaned, signature


def _factors(session: Session, accession: str, item: str) -> list[Factor]:
    rows = session.scalars(
        select(RiskFactor)
        .where(RiskFactor.accession == accession, RiskFactor.item == item)
        .order_by(RiskFactor.position)
    )
    return [
        Factor(**{field.name: getattr(row, field.name) for field in fields(Factor)}) for row in rows
    ]


def _factor_digest(factors: list[Factor]) -> str:
    return digest([asdict(f) for f in factors])


def valid_factors(
    session: Session, accession: str, store: BlobStore, rule: SectionRule
) -> tuple[list[Factor], SegmentationRun]:
    _, _, signature = _segment_inputs(session, accession, store, rule)
    run = session.get(SegmentationRun, (accession, rule.item))
    if not run or run.input_signature != signature:
        raise StageInputError("segment_stage_missing_or_stale")
    factors = _factors(session, accession, rule.item)
    if _factor_digest(factors) != run.output_sha256 or len(factors) != run.factor_count:
        raise StageInputError("factor_checksum_mismatch")
    return factors, run


def invalidate_pair(session: Session, pair_id: str, item: str, *, alignment: bool = True) -> None:
    if alignment:
        run = session.get(AlignmentRun, (pair_id, item))
        if run:
            run.input_signature = ""
        session.execute(
            delete(Alignment).where(Alignment.pair_id == pair_id, Alignment.item == item)
        )
    artifact = session.get(DiffRecord, (pair_id, item))
    if artifact:
        artifact.input_signature = ""
    session.flush()


def segment_filing(
    session: Session, accession: str, store: BlobStore, rule: SectionRule, *, force: bool = False
) -> SegmentationRun:
    section, cleaned, signature = _segment_inputs(session, accession, store, rule)
    existing = session.get(SegmentationRun, (accession, rule.item))
    if existing and not force and existing.input_signature == signature:
        valid_factors(session, accession, store, rule)
        return existing
    blocks = BLOCKS.validate_json(store.read(cleaned.blob_key))
    factors = segment(section.text, accession, rule, blocks)
    if not any(f.role == "risk" for f in factors):
        raise StageInputError("no_risk_units")
    for pair in session.scalars(
        select(FilingPair).where(
            or_(FilingPair.prior_accession == accession, FilingPair.current_accession == accession)
        )
    ):
        invalidate_pair(session, pair.id, rule.item)
    session.execute(
        delete(RiskFactor).where(RiskFactor.accession == accession, RiskFactor.item == rule.item)
    )
    session.flush()
    session.add_all(RiskFactor(**asdict(f), segmenter_version=SEGMENTER_VERSION) for f in factors)
    row = existing or SegmentationRun(accession=accession, item=rule.item)
    row.input_signature, row.output_sha256 = signature, _factor_digest(factors)
    row.factor_count, row.segmenter_version = len(factors), SEGMENTER_VERSION
    row.created_at = datetime.now(UTC)
    session.add(row)
    session.flush()
    return row


def _alignment_inputs(
    session: Session, pair: FilingPair, store: BlobStore, rule: SectionRule, threshold: float
) -> tuple[list[Factor], list[Factor], Filing, Filing, str]:
    if not pair.prior_accession:
        raise StageInputError("first_filing")
    old, old_run = valid_factors(session, pair.prior_accession, store, rule)
    new, new_run = valid_factors(session, pair.current_accession, store, rule)
    prior, current = (
        session.get(Filing, pair.prior_accession),
        session.get(Filing, pair.current_accession),
    )
    assert prior and current
    signature = digest(
        [
            old_run.input_signature,
            old_run.output_sha256,
            new_run.input_signature,
            new_run.output_sha256,
            ALIGNER_VERSION,
            MODEL_ID,
            MODEL_REVISION,
            threshold,
            MASK_VERSION,
            str(prior.report_date),
            str(current.report_date),
            {
                pkg: version(pkg)
                for pkg in ("rapidfuzz", "scipy", "sentence-transformers", "transformers", "torch")
            },
        ]
    )
    return old, new, prior, current, signature


def _matches(session: Session, pair_id: str, item: str) -> list[Match]:
    rows = session.scalars(
        select(Alignment)
        .where(Alignment.pair_id == pair_id, Alignment.item == item)
        .order_by(Alignment.id)
    )
    return [
        Match(
            row.prior_rf_id,
            row.current_rf_id,
            row.method,
            row.similarity,
            row.change_type,
            row.moved,
        )
        for row in rows
    ]


def _match_digest(matches: list[Match]) -> str:
    return digest(
        sorted(
            [asdict(m) for m in matches], key=lambda m: str(m["prior_id"]) + str(m["current_id"])
        )
    )


def align_pair(
    session: Session,
    pair: FilingPair,
    store: BlobStore,
    rule: SectionRule,
    encoder: Encoder,
    *,
    threshold: float = 0.80,
    force: bool = False,
) -> AlignmentRun:
    old, new, prior, current, signature = _alignment_inputs(session, pair, store, rule, threshold)
    existing = session.get(AlignmentRun, (pair.id, rule.item))
    if existing and not force and existing.input_signature == signature:
        if _match_digest(_matches(session, pair.id, rule.item)) != existing.output_sha256:
            raise StageInputError("alignment_checksum_mismatch")
        return existing
    matches = align(
        old,
        new,
        encoder,
        prior_date=prior.report_date,
        current_date=current.report_date,
        semantic_threshold=threshold,
    )
    invalidate_pair(session, pair.id, rule.item)
    for match in matches:
        key = digest([pair.id, rule.item, match.prior_id, match.current_id])
        session.add(
            Alignment(
                id=key,
                pair_id=pair.id,
                item=rule.item,
                current_rf_id=match.current_id,
                prior_rf_id=match.prior_id,
                method=match.method,
                similarity=match.similarity,
                change_type=match.change_type,
                moved=match.moved,
                aligner_version=ALIGNER_VERSION,
            )
        )
    row = existing or AlignmentRun(pair_id=pair.id, item=rule.item)
    row.input_signature, row.output_sha256 = signature, _match_digest(matches)
    row.aligner_version, row.model_id, row.model_revision = (
        ALIGNER_VERSION,
        MODEL_ID,
        MODEL_REVISION,
    )
    row.created_at = datetime.now(UTC)
    session.add(row)
    session.flush()
    return row


def diff_pair(
    session: Session,
    pair: FilingPair,
    store: BlobStore,
    rule: SectionRule,
    *,
    threshold: float = 0.80,
    force: bool = False,
) -> DiffRecord:
    old, new, prior, current, signature = _alignment_inputs(session, pair, store, rule, threshold)
    run = session.get(AlignmentRun, (pair.id, rule.item))
    if not run or run.input_signature != signature:
        raise StageInputError("align_stage_missing_or_stale")
    matches = _matches(session, pair.id, rule.item)
    if _match_digest(matches) != run.output_sha256:
        raise StageInputError("alignment_checksum_mismatch")
    signature = digest(
        [
            signature,
            run.output_sha256,
            DIFFER_VERSION,
            MASK_VERSION,
            version("pysbd"),
            version("diff-match-patch"),
        ]
    )
    existing = session.get(DiffRecord, (pair.id, rule.item))
    if (
        existing
        and not force
        and existing.input_signature == signature
        and store.exists(existing.blob_key)
    ):
        if hashlib.sha256(store.read(existing.blob_key)).hexdigest() == existing.sha256:
            return existing
    a, b = {f.id: f for f in old}, {f.id: f for f in new}
    factors: list[dict[str, Any]] = []
    for match in sorted(
        matches,
        key=lambda m: (
            m.current_id is None,
            b[m.current_id].position if m.current_id else a[m.prior_id or ""].position,
        ),
    ):
        left = a.get(match.prior_id or "")
        right = b.get(match.current_id or "")
        factors.append(
            {
                **asdict(match),
                "prior": asdict(left) if left else None,
                "current": asdict(right) if right else None,
                "diff": diff_text(
                    left.text if left else "",
                    right.text if right else "",
                    prior.report_date,
                    current.report_date,
                ),
            }
        )
    payload = {
        "schema_version": 1,
        "pair_id": pair.id,
        "item": rule.item,
        "input_signature": signature,
        "versions": {
            "segmenter": SEGMENTER_VERSION,
            "aligner": ALIGNER_VERSION,
            "differ": DIFFER_VERSION,
            "mask": MASK_VERSION,
            "embedding_model": MODEL_ID,
            "embedding_revision": MODEL_REVISION,
        },
        "prior": {
            "accession": prior.accession,
            "source_url": prior.primary_doc_url,
            "report_date": str(prior.report_date),
        },
        "current": {
            "accession": current.accession,
            "source_url": current.primary_doc_url,
            "report_date": str(current.report_date),
        },
        "factors": factors,
        "context": {
            "prior": [asdict(f) for f in old if f.role != "risk"],
            "current": [asdict(f) for f in new if f.role != "risk"],
        },
    }
    data = _json(payload)
    # Keep versioned evidence and the brief's convenient current accession pointer.
    key = f"diffs/{current.accession}/{rule.item}/{signature}.json"
    store.write(key, data)
    store.write(f"diffs/{current.accession}.json", data)
    row = existing or DiffRecord(pair_id=pair.id, item=rule.item)
    row.input_signature, row.blob_key, row.sha256 = signature, key, hashlib.sha256(data).hexdigest()
    row.differ_version, row.created_at = DIFFER_VERSION, datetime.now(UTC)
    session.add(row)
    session.flush()
    return row
