from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notsolazy.config import Settings
from notsolazy.discover import amendment_item_status, annual_rows, choose_pair, discover_company
from notsolazy.models import Base, Company, Filing, FilingPair, ReviewEntry, make_engine
from notsolazy.sec_client import SecClient
from notsolazy.storage import LocalBlobStore


def filing(period: str, filed: str, accession: str, form: str = "10-K") -> Filing:
    return Filing(
        accession=accession,
        cik=1,
        report_date=date.fromisoformat(period),
        filed_at=date.fromisoformat(filed),
        fiscal_year=int(period[:4]),
        form=form,
        status="discovered",
        discover_version="test",
        flags=[],
    )


def test_pair_uses_prior_fiscal_year_not_previous_filing() -> None:
    current = filing("2025-12-31", "2026-02-01", "current")
    prior = filing("2024-12-31", "2025-02-01", "prior")
    unrelated_amendment = filing("2023-12-31", "2026-03-01", "amend", "10-K/A")
    assert choose_pair([current, prior, unrelated_amendment])[:3] == (
        current,
        prior,
        "prior_fiscal_year",
    )


def test_normal_53_week_drift_not_fiscal_year_change() -> None:
    current = filing("2025-09-27", "2025-11-01", "current")
    prior = filing("2024-09-28", "2024-11-01", "prior")
    assert choose_pair([current, prior])[3] == []


def test_transition_and_fiscal_year_change_are_flagged() -> None:
    current = filing("2025-06-30", "2025-08-01", "current", "10-KT")
    prior = filing("2024-12-31", "2025-02-01", "prior")
    chosen = choose_pair([current, prior])
    assert chosen[1] is prior
    assert {"transition_period", "irregular_annual_period", "fiscal_year_end_changed"} <= set(
        chosen[3]
    )


def test_first_filing_and_missing_year() -> None:
    current = filing("2025-12-31", "2026-02-01", "current")
    assert choose_pair([current])[1:3] == (None, "first_filing")
    older = filing("2023-12-31", "2024-02-01", "old")
    assert "missing_prior_fiscal_year" in choose_pair([current, older])[3]


def test_item_amendment_replaces_original_only_when_present() -> None:
    current = filing("2025-12-31", "2026-02-01", "current")
    amendment = filing("2025-12-31", "2026-04-01", "amended", "10-K/A")
    prior = filing("2024-12-31", "2025-02-01", "prior")
    amendment.amendment_item_status = "absent"
    assert choose_pair([current, prior, amendment])[0] is current
    amendment.amendment_item_status = "present"
    assert choose_pair([current, prior, amendment])[0] is amendment


def test_amendment_presence_rejects_toc_and_routes_short_body_to_review() -> None:
    assert amendment_item_status(b"<p>Item 10 Directors</p>", "1A") == "absent"
    assert (
        amendment_item_status(b"<p>Item 1A Risk Factors 10 Item 1B Comments</p>", "1A")
        == "needs_review"
    )
    body = (
        "<p>Item <b>1A.</b> Risk Factors</p><p>"
        + "risk evidence " * 200
        + "</p><p>Item 1C Cybersecurity</p>"
    ).encode()
    assert amendment_item_status(body, "1A") == "present"
    hidden = b'<div style="display:none">' + body + b"</div><p>Item 10 Directors</p>"
    assert amendment_item_status(hidden, "1A") == "absent"


def columns(rows: list[tuple[str, str, str, str]]) -> dict[str, list[str]]:
    return {
        "accessionNumber": [r[0] for r in rows],
        "reportDate": [r[1] for r in rows],
        "filingDate": [r[2] for r in rows],
        "form": [r[3] for r in rows],
        "primaryDocument": ["report.htm" for r in rows],
    }


def test_submissions_rejects_malformed_columns_and_path_traversal() -> None:
    with pytest.raises(ValueError, match="columns"):
        annual_rows(1, {"form": []})
    data = columns([("0000000001-26-000001", "2025-12-31", "2026-02-01", "10-K")])
    data["primaryDocument"] = ["../../private"]
    with pytest.raises(ValueError, match="path"):
        annual_rows(1, data)


def test_history_shard_prevents_false_first_filing_and_rerun_is_idempotent(tmp_path: Path) -> None:
    recent = columns([("0000000001-26-000001", "2025-12-31", "2026-02-01", "10-K")])
    history = columns([("0000000001-25-000001", "2024-12-31", "2025-02-01", "10-K")])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=(
                history
                if "submissions-001" in request.url.path
                else {
                    "fiscalYearEnd": "1231",
                    "filings": {
                        "recent": recent,
                        "files": [{"name": "CIK0000000001-submissions-001.json"}],
                    },
                }
            ),
        )

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None, sec_user_agent="NotSoLazy/0.1 test@example.org", data_dir=tmp_path
    )
    with (
        Session(engine) as session,
        SecClient(
            settings, LocalBlobStore(tmp_path), transport=httpx.MockTransport(handler)
        ) as client,
    ):
        company = Company(
            cik=1, ticker="TEST", name="Test", sector="Test", in_sp500=True, universe_version="test"
        )
        session.add(company)
        session.flush()
        for _ in range(2):
            pair = discover_company(session, company, client, item="1A")
            assert pair.prior_accession == "0000000001-25-000001"
            assert pair.status == "paired"
        assert session.scalar(select(func.count()).select_from(Filing)) == 2
        assert session.scalar(select(func.count()).select_from(FilingPair)) == 1
        assert session.scalar(select(func.count()).select_from(ReviewEntry)) == 0
        malformed = columns([("0000000001-26-000002", "", "2026-03-01", "10-K")])
        ancient = columns([("0000000001-99-000001", "1998-12-31", "1999-02-01", "10-K")])
        ancient["primaryDocument"] = [""]
        for key in recent:
            recent[key].extend(malformed[key])
            history[key].extend(ancient[key])
        pair = discover_company(session, company, client, item="1A", refresh=True)
        assert pair.status == "review_required"
        assert "recent_annual_missing_report_date" in pair.flags
        assert session.scalar(select(func.count()).select_from(ReviewEntry)) == 1
        assert session.scalar(select(ReviewEntry.reason)) == "missing_report_date"
    engine.dispose()


def test_same_calendar_year_fiscal_change_uses_closest_annual_period() -> None:
    current = filing("2025-12-31", "2026-02-01", "current")
    nearest = filing("2025-06-30", "2025-08-01", "nearest")
    older = filing("2024-06-30", "2024-08-01", "older")
    pair = choose_pair([current, nearest, older])
    assert pair[1] is nearest
    assert pair[2] == "closest_prior_annual_period"
    assert "fiscal_year_end_changed" in pair[3]


def test_saved_apple_submissions_fixture_has_real_annual_periods() -> None:
    import json

    data = json.loads((Path(__file__).parent / "fixtures/aapl-annual-submissions.json").read_text())
    rows = annual_rows(320193, data["data"]["filings"]["recent"])
    assert [row["report_date"] for row in rows] == [date(2025, 9, 27), date(2024, 9, 28)]
    assert rows[0]["accession"] == "0000320193-25-000079"
