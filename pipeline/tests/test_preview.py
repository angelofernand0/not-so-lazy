import hashlib
import json

import pytest
from test_comparison import RULE, run_stages
from test_comparison import inputs as inputs

from notsolazy.models import CompanyAlias, DiffRecord, Section
from notsolazy.preview import export_preview, validate_spans
from notsolazy.processing import StageInputError


def prepared(inputs):
    session, pair, store = inputs
    session.add(CompanyAlias(ticker="TEST", cik=1))
    session.add(CompanyAlias(ticker="TST-A", cik=1))
    session.flush()
    run_stages(inputs)
    return session, pair, store


def test_snapshot_preserves_provenance_aliases_hashes_and_is_repeatable(inputs, tmp_path):
    session, pair, store = prepared(inputs)
    output = tmp_path / "site"
    meta = export_preview(session, store, RULE, ["TEST"], output)
    first = {p.relative_to(output): p.read_bytes() for p in output.rglob("*.json")}
    assert meta["company_count"] == meta["comparison_count"] == 1
    assert meta["filing_count"] == 2
    company = json.loads((output / "companies/TEST.json").read_text())
    assert company["current"]["source_url"] == "https://www.sec.gov/new"
    assert company["aliases"] == ["TEST", "TST-A"]
    assert company["status"] == "ready"
    raw = (output / "diffs/new.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == company["diff_sha256"]
    export_preview(session, store, RULE, ["TEST"], output)
    assert first == {p.relative_to(output): p.read_bytes() for p in output.rglob("*.json")}


@pytest.mark.parametrize("failure", ["section", "diff", "threshold"])
def test_failed_checks_remove_old_diff_and_never_expose_stale_counts(inputs, tmp_path, failure):
    session, pair, store = prepared(inputs)
    output = tmp_path / "site"
    export_preview(session, store, RULE, ["TEST"], output)
    threshold = 0.8
    if failure == "section":
        session.get(Section, ("new", RULE.item)).quality_flags = ["review"]
    if failure == "diff":
        store.write(session.get(DiffRecord, ("new", RULE.item)).blob_key, b"corrupt")
    if failure == "threshold":
        threshold = 0.9
    meta = export_preview(session, store, RULE, ["TEST"], output, threshold=threshold)
    company = json.loads((output / "companies/TEST.json").read_text())
    assert meta["comparison_count"] == 0
    assert company["status"] == "review_required" and company["counts"] is None
    assert company["diff_url"] is None and company["diff_sha256"] is None
    assert not (output / "diffs/new.json").exists()


def test_first_filing_no_prior_and_absent_pair_have_honest_states(inputs, tmp_path):
    session, pair, store = prepared(inputs)
    pair.prior_accession = None
    output = tmp_path / "site"
    export_preview(session, store, RULE, ["TEST"], output)
    assert json.loads((output / "companies/TEST.json").read_text())["status"] == "first_filing"
    pair.status = "superseded"
    export_preview(session, store, RULE, ["TEST"], output)
    assert json.loads((output / "companies/TEST.json").read_text())["status"] == "awaiting_filing"


def test_explicit_selection_cleans_only_previously_owned_snapshot_files(inputs, tmp_path):
    session, pair, store = prepared(inputs)
    output = tmp_path / "site"
    output.mkdir()
    (output / "unrelated.txt").write_text("keep")
    export_preview(session, store, RULE, ["TEST", "TST.A"], output)
    export_preview(session, store, RULE, ["TEST"], output)
    assert not (output / "companies/TST.A.json").exists()
    assert (output / "unrelated.txt").read_text() == "keep"
    assert (output / "diffs/new.json").exists()
    for tickers in [[], ["../escape"], ["MISSING"]]:
        with pytest.raises(ValueError):
            export_preview(session, store, RULE, tickers, output)


def test_invalid_unicode_offsets_cannot_enter_site_payload():
    payload = {
        "factors": [
            {
                "prior": {"text": "a🧠b"},
                "current": None,
                "diff": {"ops": [{"prior": [0, 4], "current": None}]},
            }
        ]
    }
    with pytest.raises(StageInputError, match="invalid_diff_offsets"):
        validate_spans(payload)
