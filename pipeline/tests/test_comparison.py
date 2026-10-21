import hashlib
import json
from datetime import date

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notsolazy import comparison
from notsolazy.clean import CLEANER_VERSION, clean_html
from notsolazy.config import section_rule
from notsolazy.extract import EXTRACTOR_VERSION
from notsolazy.models import (
    Alignment,
    Base,
    CleanedFiling,
    Company,
    Filing,
    FilingPair,
    RiskFactor,
    Section,
    make_engine,
)
from notsolazy.processing import BLOCKS, StageInputError, extraction_signature
from notsolazy.storage import LocalBlobStore

RULE = section_rule("1A")


@pytest.fixture
def inputs(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    store = LocalBlobStore(tmp_path / "blobs")
    with Session(engine) as session:
        session.add(
            Company(cik=1, ticker="TEST", name="Test", sector="Test", universe_version="test")
        )
        session.flush()
        for accession, year in [("old", 2024), ("new", 2025)]:
            raw = (
                f"<p>Item 1A. Risk Factors</p><p><b>Supply chains could harm our business.</b></p>"
                f"<p>In fiscal {year} we rely on suppliers.</p>"
            ).encode()
            key = f"raw/1/{accession}.html"
            store.write(key, raw)
            sha = hashlib.sha256(raw).hexdigest()
            session.add(
                Filing(
                    accession=accession,
                    cik=1,
                    form="10-K",
                    filed_at=date(year, 12, 31),
                    report_date=date(year, 12, 31),
                    raw_blob_key=key,
                    sha256=sha,
                    primary_doc_url=f"https://www.sec.gov/{accession}",
                    status="fetched",
                    discover_version="test",
                )
            )
            session.flush()
            blocks = clean_html(raw)
            data = BLOCKS.dump_json(blocks)
            key = f"clean/{accession}.json"
            store.write(key, data)
            session.add(
                CleanedFiling(
                    accession=accession,
                    blob_key=key,
                    source_sha256=sha,
                    blocks_sha256=hashlib.sha256(data).hexdigest(),
                    block_count=len(blocks),
                    word_count=20,
                    cleaner_version=CLEANER_VERSION,
                    quality_flags=[],
                    created_at=comparison.datetime.now(comparison.UTC),
                )
            )
            text = "\n\n".join(b.text for b in blocks)
            session.add(
                Section(
                    accession=accession,
                    item=RULE.item,
                    text=text,
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    word_count=20,
                    extractor="fallback",
                    extractor_version=EXTRACTOR_VERSION,
                    primary_version="test",
                    cleaner_version=CLEANER_VERSION,
                    input_signature=f"extract-{year}",
                    quality_flags=[],
                    warnings=[],
                    diagnostics=[],
                    candidates_blob_key="unused",
                    created_at=comparison.datetime.now(comparison.UTC),
                )
            )
        session.flush()
        for accession in ["old", "new"]:
            sec = session.get(Section, (accession, RULE.item))
            sec.input_signature = extraction_signature(
                session.get(Filing, accession), session.get(CleanedFiling, accession), RULE, None
            )
        pair = FilingPair(
            id="new",
            cik=1,
            current_accession="new",
            prior_accession="old",
            pairing_method="prior_fiscal_year",
            status="paired",
            flags=[],
            discover_version="test",
        )
        session.add(pair)
        session.flush()
        yield session, pair, store
    engine.dispose()


def run_stages(inputs):
    s, p, store = inputs
    for accession in ["old", "new"]:
        comparison.segment_filing(s, accession, store, RULE)
    comparison.align_pair(s, p, store, RULE, lambda texts: np.eye(len(texts)))
    return comparison.diff_pair(s, p, store, RULE)


def test_stored_pipeline_is_idempotent_and_original_text_reconstructs(inputs, monkeypatch):
    session, pair, store = inputs
    artifact = run_stages(inputs)
    created = artifact.created_at
    payload = json.loads(store.read(artifact.blob_key))
    assert payload["current"]["source_url"] == "https://www.sec.gov/new"
    assert payload["factors"][0]["change_type"] == "unchanged"
    assert any(op["trivial"] for op in payload["factors"][0]["diff"]["ops"])
    monkeypatch.setattr(comparison, "segment", lambda *a: pytest.fail("reran segment"))
    monkeypatch.setattr(comparison, "align", lambda *a, **k: pytest.fail("reran alignment"))
    monkeypatch.setattr(comparison, "diff_text", lambda *a: pytest.fail("reran diff"))
    assert run_stages(inputs).created_at == created
    assert session.scalar(select(func.count()).select_from(RiskFactor)) == 2
    assert session.scalar(select(func.count()).select_from(Alignment)) == 1
    assert store.read("diffs/new.json") == store.read(artifact.blob_key)


def test_changed_segmentation_invalidates_alignment_and_diff(inputs, monkeypatch):
    s, p, store = inputs
    artifact = run_stages(inputs)
    monkeypatch.setattr(comparison, "SEGMENTER_VERSION", "segment-test-v2")
    comparison.segment_filing(s, "new", store, RULE)
    assert artifact.input_signature == ""
    assert s.scalar(select(func.count()).select_from(Alignment)) == 0
    with pytest.raises(StageInputError, match="segment_stage_missing_or_stale"):
        comparison.diff_pair(s, p, store, RULE)


@pytest.mark.parametrize("corrupt", ["section", "raw", "clean", "factor", "alignment"])
def test_corrupt_upstream_evidence_cannot_be_reused(inputs, corrupt):
    s, p, store = inputs
    run_stages(inputs)
    if corrupt == "section":
        s.get(Section, ("new", RULE.item)).text += "changed"
    elif corrupt == "raw":
        store.write("raw/1/new.html", b"bad")
    elif corrupt == "clean":
        store.write("clean/new.json", b"bad")
    elif corrupt == "factor":
        s.scalar(select(RiskFactor).where(RiskFactor.accession == "new")).body += "bad"
    else:
        s.scalar(select(Alignment)).change_type = "added"
    s.flush()
    with pytest.raises(StageInputError, match="checksum_mismatch"):
        comparison.diff_pair(s, p, store, RULE)


def test_quality_flag_and_missing_prior_gate_comparison(inputs):
    s, p, store = inputs
    run_stages(inputs)
    s.get(Section, ("new", RULE.item)).quality_flags = ["too_few_words"]
    with pytest.raises(StageInputError, match="extraction_requires_review"):
        comparison.diff_pair(s, p, store, RULE)
    p.prior_accession = None
    with pytest.raises(StageInputError, match="first_filing"):
        comparison.align_pair(s, p, store, RULE, lambda texts: np.eye(len(texts)))


def test_corrupt_diff_blob_is_rebuilt(inputs):
    s, p, store = inputs
    artifact = run_stages(inputs)
    expected = store.read(artifact.blob_key)
    store.write(artifact.blob_key, b"corrupt")
    assert store.read(comparison.diff_pair(s, p, store, RULE).blob_key) == expected


def test_threshold_change_requires_realignment(inputs):
    s, p, store = inputs
    run_stages(inputs)
    with pytest.raises(StageInputError, match="align_stage_missing_or_stale"):
        comparison.diff_pair(s, p, store, RULE, threshold=0.9)


def test_force_segment_rebuild_does_not_break_foreign_keys(inputs):
    s, p, store = inputs
    run_stages(inputs)
    comparison.segment_filing(s, "old", store, RULE, force=True)
    comparison.align_pair(s, p, store, RULE, lambda texts: np.eye(len(texts)))
    assert comparison.diff_pair(s, p, store, RULE).input_signature


def test_comparison_cli_is_offline_and_integrity_errors_invalidate_artifacts(
    inputs, monkeypatch, capsys
):
    import sys

    import notsolazy.cli as cli
    from notsolazy.models import CompanyAlias

    s, p, store = inputs
    s.add(CompanyAlias(ticker="TEST", cik=1))
    s.commit()
    monkeypatch.setenv("DATABASE_URL", str(s.get_bind().url))
    monkeypatch.setenv("DATA_DIR", str(store.root))
    monkeypatch.setenv("SEC_USER_AGENT", "")
    monkeypatch.setattr(cli, "SecClient", lambda *a: pytest.fail("SEC client constructed"))
    for stage in ["segment", "align", "diff"]:
        monkeypatch.setattr(sys, "argv", ["nsl", stage, "--ticker", "TEST"])
        cli.main()
        result = json.loads(capsys.readouterr().out)
        assert all(
            r["status"] == {"segment": "segmented", "align": "aligned", "diff": "diffed"}[stage]
            for r in result["results"]
        )
    store.write("raw/1/new.html", b"corrupt")
    monkeypatch.setattr(sys, "argv", ["nsl", "diff", "--ticker", "TEST"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["results"][0]["quality_flags"] == [
        "raw_checksum_mismatch"
    ]
    s.expire_all()
    from notsolazy.models import DiffRecord

    assert s.get(DiffRecord, ("new", RULE.item)).input_signature == ""


def test_updated_source_and_clean_blob_cannot_reuse_old_extraction(inputs):
    s, p, store = inputs
    run_stages(inputs)
    filing = s.get(Filing, "new")
    clean = s.get(CleanedFiling, "new")
    changed = store.read(filing.raw_blob_key) + b"<p>Extra.</p>"
    store.write(filing.raw_blob_key, changed)
    filing.sha256 = clean.source_sha256 = hashlib.sha256(changed).hexdigest()
    with pytest.raises(StageInputError, match="extraction_stale"):
        comparison.diff_pair(s, p, store, RULE)
