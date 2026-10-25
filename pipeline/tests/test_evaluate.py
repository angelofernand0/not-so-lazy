"""Metric accounting and label integrity; synthetic cases are not accuracy evidence."""

import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from notsolazy.align import Match
from notsolazy.evaluate import (
    Manifest,
    checked_source,
    evaluate,
    heading_mapping,
    load_manifest,
    markdown_report,
    measure,
)
from notsolazy.segment import Factor

TESTS = Path(__file__).parent


def synthetic_manifest(tmp_path: Path) -> Manifest:
    """Two risks split into three; a removed risk remains explicitly labeled."""
    headings = {
        "prior": ["Competition threatens our business.", "Floods can damage our properties."],
        "current": ["Competition threatens our business.", "Droughts disrupt our supply chain."],
    }
    sources = {}
    for i, side in enumerate(("prior", "current")):
        start = "These are the material risks that investors should consider carefully."
        end = (
            "This risk could significantly damage our financial condition "
            "and our future operations."
        )
        raw = (
            "<html><body><h2>Item 1A. Risk Factors</h2><p>"
            + start
            + "</p>"
            + "".join(
                f"<p><b>{heading}</b></p><p>Body for risk number {n}. {end}</p>"
                for n, heading in enumerate(headings[side])
            )
            + "<h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p></body></html>"
        ).encode()
        filename = side + ".html.gz"
        (tmp_path / filename).write_bytes(gzip.compress(raw, mtime=0))
        sources[side] = {
            "accession": f"0000000001-{24 + i}-000001",
            "report_date": f"{2024 + i}-12-31",
            "source_url": f"https://www.sec.gov/Archives/edgar/data/1/{side}.htm",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "fixture": filename,
            "section_start": start,
            "section_end": "Body for risk number 1. " + end,
            "factors": [
                {"id": side[0] + str(n), "heading": heading}
                for n, heading in enumerate(headings[side])
            ],
        }
    return Manifest.model_validate(
        {
            "schema_version": 1,
            "label_version": "synthetic-test-only",
            "review": {"limitations": ["Synthetic accounting case, not accuracy evidence."]},
            "pairs": [
                {
                    "id": "SYNTHETIC",
                    "notes": "Synthetic split and removal.",
                    **sources,
                    "relations": [
                        {"prior": ["p0"], "current": ["c0", "c1"], "kind": "split"},
                        {"prior": ["p1"], "current": [], "kind": "removed"},
                    ],
                }
            ],
        }
    )


def test_reference_fixtures_and_heading_order_are_independent_of_predictions() -> None:
    manifest = load_manifest(TESTS / "golden/pilot.json")
    assert len(manifest.pairs) == 5
    assert manifest.review["independent_human_adjudication"] is False
    assert sum(len(s.factors) for p in manifest.pairs for s in (p.prior, p.current)) == 262
    for pair in manifest.pairs:
        for source in (pair.prior, pair.current):
            checked_source(source, TESTS)


def test_zero_denominators_and_false_predictions() -> None:
    assert measure(set(), set()) == {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "precision": None,
        "recall": None,
        "f1": None,
    }
    assert measure({"a", "b"}, {"a", "wrong"})["recall"] == 0.5
    assert measure(set(), {"wrong"})["precision"] == 0
    assert measure({"missing"}, set())["recall"] == 0


def test_heading_inside_a_merged_body_is_a_miss(tmp_path: Path) -> None:
    pair = synthetic_manifest(tmp_path).pairs[0]
    first, second = pair.prior.factors
    merged = Factor(
        "merged",
        pair.prior.accession,
        "1A",
        0,
        "",
        first.heading,
        second.heading,
        first.heading + "\n\n" + second.heading,
        "hash",
        "heading",
        "risk",
        0,
        100,
    )
    mapping, score, errors = heading_mapping(pair.prior.factors, [merged])
    assert mapping == {"merged": "p0"}
    assert score["fn"] == 1
    assert errors[0]["reference"] == "p1"


@pytest.mark.parametrize("mutation", ["checksum", "anchor", "order", "traversal"])
def test_bad_reference_sources_are_rejected(tmp_path: Path, mutation: str) -> None:
    source = synthetic_manifest(tmp_path).pairs[0].prior
    if mutation == "checksum":
        source.sha256 = "0" * 64
    elif mutation == "anchor":
        source.section_end = "A nonexistent ending anchor that must not be silently accepted."
    elif mutation == "order":
        source.factors.reverse()
    else:
        source.fixture = "../outside.html.gz"
    with pytest.raises(ValueError):
        checked_source(source, tmp_path)


def test_missing_or_repeated_relation_labels_are_rejected(tmp_path: Path) -> None:
    manifest = synthetic_manifest(tmp_path).model_dump(mode="json")
    manifest["pairs"][0]["relations"].pop()
    with pytest.raises(ValidationError, match="exactly one relation"):
        Manifest.model_validate(manifest)


def test_duplicate_documents_and_invalid_relation_shapes_are_rejected(tmp_path: Path) -> None:
    manifest = synthetic_manifest(tmp_path).model_dump(mode="json")
    manifest["pairs"].append({**manifest["pairs"][0], "id": "DUPLICATE"})
    with pytest.raises(ValidationError, match="Repeated filing"):
        Manifest.model_validate(manifest)
    manifest = synthetic_manifest(tmp_path).model_dump(mode="json")
    manifest["pairs"][0]["relations"][0]["kind"] = "match"
    with pytest.raises(ValidationError, match="relation shape"):
        Manifest.model_validate(manifest)


def test_full_metric_accounting_includes_splits_and_flagged_extractions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import notsolazy.evaluate as evaluation

    manifest = synthetic_manifest(tmp_path)

    def fixed_matches(prior, current, encoder, **kwargs):
        # Deliberately return a one-to-one prediction for the labeled split.
        # This tests accounting, not the accuracy of an artificial encoder.
        assert len(prior) == len(current) == 2
        return [
            Match(prior[0].id, current[0].id, "exact_heading", 1),
            Match(prior[1].id, None, "unmatched", None),
            Match(None, current[1].id, "unmatched", None),
        ]

    monkeypatch.setattr(evaluation, "align", fixed_matches)
    report = evaluate(
        manifest, tmp_path, tmp_path / "cache", lambda texts: np.zeros((len(texts), 2))
    )
    summary = report["summary"]
    assert summary["documents_flagged"] == 2  # Too short, but never excluded.
    assert summary["heading_starts"]["tp"] == 4
    assert summary["alignment"]["links_end_to_end"]["tp"] == 1
    assert summary["alignment"]["links_end_to_end"]["fn"] == 1
    assert summary["alignment"]["added"]["fp"] == 1
    assert summary["alignment"]["removed"]["tp"] == 1
    assert "false_added" in summary["error_categories"]
    assert "independent human adjudication is pending" in markdown_report(report)


def test_unresolved_relations_do_not_become_spurious_additions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import notsolazy.evaluate as evaluation

    data = synthetic_manifest(tmp_path).model_dump(mode="json")
    data["pairs"][0]["relations"] = [
        {"prior": ["p0"], "current": ["c0"], "kind": "match"},
        {"prior": ["p1"], "current": ["c1"], "kind": "unresolved", "note": "Needs review."},
    ]

    def fixed_matches(prior, current, encoder, **kwargs):
        return [
            Match(prior[0].id, current[0].id, "exact_heading", 1),
            Match(prior[1].id, None, "unmatched", None),
            Match(None, current[1].id, "unmatched", None),
        ]

    monkeypatch.setattr(evaluation, "align", fixed_matches)
    report = evaluate(
        Manifest.model_validate(data),
        tmp_path,
        tmp_path / "cache",
        lambda texts: np.zeros((len(texts), 2)),
    )
    metrics = report["summary"]["alignment"]
    assert metrics["unresolved_reference_factors"] == 2
    assert metrics["added"]["fp"] == metrics["removed"]["fp"] == 0
    assert metrics["links_end_to_end"]["recall"] == 1


def test_cli_evaluates_without_database_model_or_sec_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import notsolazy.cli as cli

    manifest = synthetic_manifest(tmp_path)
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json())
    output, markdown = tmp_path / "results.json", tmp_path / "results.md"
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SEC_USER_AGENT", "")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///should-not-exist.db")

    def forbidden(*args, **kwargs):
        pytest.fail("Evaluation must not construct a database or embedding encoder.")

    monkeypatch.setattr(cli, "make_engine", forbidden)
    monkeypatch.setattr(cli, "LocalEncoder", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nsl",
            "evaluate",
            "--manifest",
            str(path),
            "--fixtures",
            str(tmp_path),
            "--output",
            str(output),
            "--report",
            str(markdown),
            "--extraction-only",
        ],
    )
    cli.main()
    assert json.loads(output.read_text())["summary"]["alignment"] is None
    assert "Alignment was not run" in markdown.read_text()
    assert json.loads(capsys.readouterr().out)["pairs"] == 1
    # The JSON is still written when a real error makes the optional gate fail.
    monkeypatch.setattr(
        cli,
        "evaluate",
        lambda *args, **kwargs: {
            **json.loads(output.read_text()),
            "summary": {"error_categories": {"section_boundary": 1}},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nsl",
            "evaluate",
            "--manifest",
            str(path),
            "--fixtures",
            str(tmp_path),
            "--output",
            str(output),
            "--extraction-only",
            "--fail-on-errors",
        ],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert json.loads(output.read_text())["summary"]["error_categories"]
