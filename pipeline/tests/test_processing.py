import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import notsolazy.processing as processing
from notsolazy.config import section_rule
from notsolazy.extract import Candidate, extract_section
from notsolazy.models import (
    Base,
    CleanedFiling,
    Company,
    CompanyAlias,
    Filing,
    FilingPair,
    ReviewEntry,
    Section,
    make_engine,
)
from notsolazy.storage import LocalBlobStore

RULE = section_rule("1A")
RAW = (
    "<p>Item 1A. Risk Factors</p><p>"
    + "Risk evidence affects business operations. " * 500
    + "</p><p>Item 1B. Unresolved Staff Comments</p>"
).encode()


@pytest.fixture
def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'stage.db'}")
    Base.metadata.create_all(engine)
    store = LocalBlobStore(tmp_path / "blobs")

    def offline_extract(raw, blocks, rule, **kwargs):
        return extract_section(
            raw,
            blocks,
            rule,
            **kwargs,
            primary=lambda *args: Candidate("", "edgartools", ["section_not_found"]),
        )

    monkeypatch.setattr(processing, "extract_section", offline_extract)
    with Session(engine) as session:
        session.add(
            Company(
                cik=1,
                ticker="TEST",
                name="Test",
                sector="Test",
                in_sp500=True,
                universe_version="test",
            )
        )
        session.flush()
        session.add(CompanyAlias(ticker="TEST", cik=1))
        filing = Filing(
            accession="0000000001-26-000001",
            cik=1,
            form="10-K",
            filed_at=date(2026, 2, 1),
            report_date=date(2025, 12, 31),
            status="fetched",
            discover_version="test",
            raw_blob_key="raw/1/source.html",
            sha256=hashlib.sha256(RAW).hexdigest(),
        )
        store.write(filing.raw_blob_key, RAW)
        session.add(filing)
        session.flush()
        yield session, filing, store, tmp_path
    engine.dispose()


def test_versioned_clean_and_extract_reruns_preserve_records_and_audit(inputs, monkeypatch):
    session, filing, store, tmp_path = inputs
    cleaned = processing.clean_filing(session, filing, store)
    created = cleaned.created_at
    assert processing.clean_filing(session, filing, store).created_at == created
    section = processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    created = section.created_at
    monkeypatch.setattr(
        processing,
        "extract_section",
        lambda *args, **kwargs: pytest.fail("Cached extraction reran"),
    )
    assert (
        processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path).created_at
        == created
    )
    assert session.scalar(select(func.count()).select_from(CleanedFiling)) == 1
    assert session.scalar(select(func.count()).select_from(Section)) == 1
    audit = json.loads(store.read(section.candidates_blob_key))
    assert audit["candidates"][1]["text"] == section.text
    assert section.text_sha256 == hashlib.sha256(section.text.encode()).hexdigest()
    assert all("text" not in candidate for candidate in section.diagnostics)


def test_changed_prior_word_count_recomputes_quality_and_deduplicates_review(inputs):
    session, filing, store, tmp_path = inputs
    processing.clean_filing(session, filing, store)
    good = processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    assert not good.quality_flags
    bad = processing.extract_filing(
        session, filing, store, RULE, prior_words=10000, cache_dir=tmp_path
    )
    assert "word_count_outlier" in bad.quality_flags
    count = session.scalar(select(func.count()).select_from(ReviewEntry))
    processing.extract_filing(session, filing, store, RULE, prior_words=10000, cache_dir=tmp_path)
    assert session.scalar(select(func.count()).select_from(ReviewEntry)) == count


def test_input_corruption_invalidates_previously_good_section(inputs):
    session, filing, store, tmp_path = inputs
    processing.clean_filing(session, filing, store)
    section = processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    store.write(filing.raw_blob_key, b"corrupt")
    pair = FilingPair(cik=1, current_accession=filing.accession, prior_accession=None)
    results = processing.process_pair(
        session, pair, store, RULE, stage="extract", force=False, cache_dir=tmp_path
    )
    assert results[0]["quality_flags"] == ["raw_checksum_mismatch"]
    assert section.quality_flags == ["raw_checksum_mismatch"]
    assert section.input_signature == ""
    store.write(filing.raw_blob_key, RAW)
    repaired = processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    assert not repaired.quality_flags and repaired.input_signature


def test_missing_clean_stage_and_corrupt_blocks_are_rejected(inputs):
    session, filing, store, tmp_path = inputs
    with pytest.raises(processing.StageInputError, match="clean_stage_missing"):
        processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    cleaned = processing.clean_filing(session, filing, store)
    store.write(cleaned.blob_key, b"corrupt")
    with pytest.raises(processing.StageInputError, match="clean_checksum_mismatch"):
        processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)


def test_cleaner_version_change_rebuilds_blocks_and_extraction(inputs, monkeypatch):
    session, filing, store, tmp_path = inputs
    first = processing.clean_filing(session, filing, store)
    first_key = first.blob_key
    section = processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    first_signature = section.input_signature
    monkeypatch.setattr(processing, "CLEANER_VERSION", "clean-test-next")
    changed = processing.clean_filing(session, filing, store)
    assert changed.blob_key != first_key and store.exists(first_key)
    result = processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    assert result.cleaner_version == "clean-test-next"
    assert result.input_signature != first_signature


def test_offline_stage_cli_runs_without_sec_identity(inputs, monkeypatch, capsys):
    import sys

    import notsolazy.cli as cli

    session, filing, store, tmp_path = inputs
    session.add(
        FilingPair(
            id=filing.accession,
            cik=1,
            current_accession=filing.accession,
            prior_accession=None,
            pairing_method="first_filing",
            status="first_filing",
            flags=["first_filing"],
            discover_version="test",
        )
    )
    session.commit()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'stage.db'}")
    monkeypatch.setenv("DATA_DIR", str(store.root))
    monkeypatch.setenv("SEC_USER_AGENT", "")
    monkeypatch.setattr(
        cli, "SecClient", lambda *args: pytest.fail("Offline stages constructed SEC client")
    )
    monkeypatch.setattr(sys, "argv", ["nsl", "extract", "--ticker", "TEST"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["results"][0]["status"] == "review_required"
    for stage in ["clean", "extract"]:
        monkeypatch.setattr(sys, "argv", ["nsl", stage, "--ticker", "TEST"])
        cli.main()
        output = json.loads(capsys.readouterr().out)
        assert not output["results"][0]["quality_flags"]
    session.expire_all()
    assert (
        session.scalar(
            select(func.count()).select_from(ReviewEntry).where(ReviewEntry.resolved_at.is_(None))
        )
        == 0
    )


def test_reproduced_integrity_failure_reopens_review_after_repair(inputs):
    session, filing, store, tmp_path = inputs
    processing.clean_filing(session, filing, store)
    processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    pair = FilingPair(cik=1, current_accession=filing.accession, prior_accession=None)
    store.write(filing.raw_blob_key, b"corrupt")
    processing.process_pair(
        session, pair, store, RULE, stage="extract", force=False, cache_dir=tmp_path
    )
    entry = session.scalar(select(ReviewEntry))
    assert entry.resolved_at is None
    store.write(filing.raw_blob_key, RAW)
    processing.extract_filing(session, filing, store, RULE, cache_dir=tmp_path)
    assert entry.resolved_at is not None
    store.write(filing.raw_blob_key, b"corrupt again")
    processing.process_pair(
        session, pair, store, RULE, stage="extract", force=False, cache_dir=tmp_path
    )
    assert entry.resolved_at is None
    assert "Reopened" in entry.note
    assert session.scalar(select(func.count()).select_from(ReviewEntry)) == 1
