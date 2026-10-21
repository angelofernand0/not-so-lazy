"""Discover annual periods and pair by report date, with explicit review flags."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

from lxml import html
from sqlalchemy import select
from sqlalchemy.orm import Session

from notsolazy.fetch import fetch_filing
from notsolazy.models import Company, Filing, FilingPair, ReviewEntry
from notsolazy.sec_client import SecClient

DISCOVER_VERSION = "discover-v1"
ANNUAL_FORMS = frozenset({"10-K", "10-KT"})


class NoAnnualReport(ValueError):
    """An issuer can join the universe before its first annual filing."""


def submissions_url(cik: int) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik:010d}.json"


def annual_rows(cik: int, data: dict[str, Any]) -> list[dict[str, Any]]:
    columns = ("accessionNumber", "form", "filingDate", "reportDate", "primaryDocument")
    if not all(isinstance(data.get(key), list) for key in columns):
        raise ValueError("Malformed SEC submissions columns.")
    if len({len(data[key]) for key in columns}) != 1:
        raise ValueError("SEC submissions columns have different lengths.")
    records = []
    for values in zip(*(data[key] for key in columns), strict=True):
        row = dict(zip(columns, values, strict=True))
        if row["form"] not in ANNUAL_FORMS | {"10-K/A"}:
            continue
        accession = str(row["accessionNumber"])
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("Invalid SEC accession number.")
        report = date.fromisoformat(row["reportDate"]) if row["reportDate"] else None
        document = str(row["primaryDocument"])
        if document and ("/" in document or "\\" in document or document in {".", ".."}):
            raise ValueError("Unexpected primary document path.")
        records.append(
            {
                "accession": accession,
                "cik": cik,
                "form": row["form"],
                "filed_at": date.fromisoformat(row["filingDate"]),
                "report_date": report,
                "fiscal_year": report.year if report else None,
                "primary_doc_url": (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{accession.replace('-', '')}/{quote(document, safe='')}"
                    if document
                    else None
                ),
            }
        )
    return records


def queue_review(session: Session, filing: Filing, reason: str) -> None:
    key = hashlib.sha256(f"{filing.accession}:discover:{reason}".encode()).hexdigest()
    if session.get(ReviewEntry, key) is None:
        session.add(
            ReviewEntry(
                id=key,
                accession=filing.accession,
                stage="discover",
                reason=reason,
                created_at=datetime.now(UTC),
                code_version=DISCOVER_VERSION,
            )
        )


def amendment_item_status(payload: bytes, item: str) -> str:
    """Conservative presence check, not a substitute for Milestone 3 extraction.

    TOC-only mentions do not qualify. Short or unterminated bodies go to review.
    """
    tree = html.fromstring(payload)
    for node in tree.xpath("//script|//style|//*[local-name()='header']"):
        node.drop_tree()
    for node in list(tree.iter()):
        if "display:none" in node.get("style", "").replace(" ", "").lower():
            node.drop_tree()
    text = " ".join(" ".join(tree.itertext()).split())
    starts = list(
        re.finditer(rf"\bitem\s*{re.escape(item)}\s*[.:-]?\s*risk\s+factors\b", text, re.I)
    )
    if not starts:
        return "absent"
    for start in starts:
        tail = text[start.end() :]
        end = re.search(r"\bitem\s*(?:1b|1c|2)\s*[.:-]?(?:\s|$)", tail, re.I)
        if end and len(tail[: end.start()].split()) >= 250:
            return "present"
    return "needs_review"


def choose_pair(filings: list[Filing]) -> tuple[Filing, Filing | None, str, list[str]]:
    by_period: dict[date, Filing] = {}
    for filing in filings:
        if filing.report_date is None:
            continue
        if filing.form not in ANNUAL_FORMS and filing.amendment_item_status != "present":
            continue
        existing = by_period.get(filing.report_date)
        if existing is None or (filing.filed_at, filing.accession) > (
            existing.filed_at,
            existing.accession,
        ):
            by_period[filing.report_date] = filing
    if not by_period:
        raise NoAnnualReport("No annual report with a report date was found.")
    current_date = max(by_period)
    current = by_period[current_date]
    older = [filing for period, filing in by_period.items() if period < current_date]
    if not older:
        return current, None, "first_filing", ["first_filing"]
    flags: list[str] = []
    nearest = max(older, key=lambda value: value.report_date or date.min)
    transition = any(
        f.form == "10-KT" and f.report_date in {current_date, nearest.report_date} for f in filings
    )
    if transition or (nearest.report_date and nearest.report_date.year == current_date.year):
        prior = max(older, key=lambda value: value.report_date or date.min)
        method = "closest_prior_annual_period"
        if transition:
            flags.append("transition_period")
    else:
        prior_year = [
            filing
            for filing in older
            if filing.report_date and filing.report_date.year == current_date.year - 1
        ]
        prior = min(
            prior_year or older,
            key=lambda filing: abs((current_date - (filing.report_date or date.min)).days - 365),
        )
        method = "prior_fiscal_year" if prior_year else "closest_prior_annual_period"
        if not prior_year:
            flags.append("missing_prior_fiscal_year")
    assert prior.report_date is not None
    gap = (current_date - prior.report_date).days
    if not 330 <= gap <= 400:
        flags.append("irregular_annual_period")
    # 52/53-week fiscal calendars can drift several days without a year-end change.
    day_shift = abs((current_date.replace(year=2000) - prior.report_date.replace(year=2000)).days)
    if min(day_shift, 366 - day_shift) > 14:
        flags.append("fiscal_year_end_changed")
    if current.form == "10-K/A" or prior.form == "10-K/A":
        flags.append("item_amendment_used")
    return current, prior, method, flags


def discover_company(
    session: Session,
    company: Company,
    client: SecClient,
    *,
    item: str,
    refresh: bool = False,
) -> FilingPair:
    payload = client.get_json(submissions_url(company.cik), refresh=refresh)
    company.fiscal_year_end = payload.get("fiscalYearEnd") or None
    rows = annual_rows(company.cik, payload["filings"]["recent"])
    # Read every SEC-listed history shard. This prevents mislabeling an issuer as
    # first_filing when a prior period is outside the recent-filings window.
    for shard in payload["filings"].get("files", []):
        name = str(shard["name"])
        if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name):
            raise ValueError("Unexpected submissions history filename.")
        rows.extend(
            annual_rows(
                company.cik,
                client.get_json(f"https://data.sec.gov/submissions/{name}", refresh=refresh),
            )
        )
    filings: list[Filing] = []
    for row in {entry["accession"]: entry for entry in rows}.values():
        filing = session.get(Filing, row["accession"])
        if filing is None:
            filing = Filing(status="amendment_pending" if row["form"] == "10-K/A" else "discovered")
            session.add(filing)
        for key, value in row.items():
            setattr(filing, key, value)
        filing.discover_version = DISCOVER_VERSION
        filing.flags = []
        if filing.report_date is None:
            filing.flags = ["missing_report_date"]
        if filing.primary_doc_url is None:
            filing.flags = [*filing.flags, "missing_primary_document"]
        filings.append(filing)
    session.flush()
    original_current, original_prior, _, _ = choose_pair(
        [filing for filing in filings if filing.form in ANNUAL_FORMS]
    )
    relevant_periods = {f.report_date for f in (original_current, original_prior) if f is not None}
    for filing in filings:
        if filing.form == "10-K/A" and filing.report_date in relevant_periods:
            if (
                filing.amendment_checked_item != item
                or filing.amendment_probe_version != DISCOVER_VERSION
            ) and filing.primary_doc_url:
                filing.amendment_item_status = amendment_item_status(
                    fetch_filing(filing, client), item
                )
                filing.amendment_checked_item = item
                filing.amendment_probe_version = DISCOVER_VERSION
            if filing.amendment_item_status == "needs_review":
                queue_review(session, filing, "amendment_item_presence_uncertain")
            filing.status = "amendment_checked"
    current, prior, method, flags = choose_pair(filings)
    fresh_unknown = [
        f
        for f in filings
        if f.form in ANNUAL_FORMS and f.report_date is None and f.filed_at >= current.filed_at
    ]
    if fresh_unknown:
        flags.append("recent_annual_missing_report_date")
    for filing in filings:
        if (
            filing in (current, prior)
            or filing in fresh_unknown
            or (filing.form == "10-K/A" and filing.report_date in relevant_periods)
        ):
            for flag in filing.flags:
                queue_review(session, filing, flag)
    uncertain = any(
        (f.amendment_item_status == "needs_review" or f.primary_doc_url is None)
        and f.report_date in {current.report_date, prior.report_date if prior else None}
        for f in filings
    )
    if uncertain:
        flags.append("amendment_review_pending")
    selected_have_missing_document = any(f.primary_doc_url is None for f in (current, prior) if f)
    if selected_have_missing_document:
        flags.append("missing_primary_document")
    pair = session.get(FilingPair, current.accession)
    if pair is None:
        pair = FilingPair(id=current.accession)
        session.add(pair)
    pair.cik, pair.current_accession = company.cik, current.accession
    pair.prior_accession = prior.accession if prior else None
    pair.pairing_method, pair.flags = method, flags
    pair.status = (
        "first_filing"
        if prior is None
        else (
            "review_required"
            if uncertain or selected_have_missing_document or fresh_unknown
            else "paired"
        )
    )
    pair.discover_version = DISCOVER_VERSION
    for old_pair in session.scalars(
        select(FilingPair).where(FilingPair.cik == company.cik, FilingPair.id != pair.id)
    ):
        old_pair.status = "superseded"
    session.flush()
    return pair
