"""Explicit, cross-checked S&P 500 snapshot; share-class aliases retain one CIK."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from lxml import html
from sqlalchemy import select
from sqlalchemy.orm import Session

from notsolazy.models import Company, CompanyAlias
from notsolazy.sec_client import SecClient

UNIVERSE_VERSION = "universe-v1"
CONSTITUENTS_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "sp500.csv"


@dataclass(frozen=True)
class Constituent:
    ticker: str
    name: str
    sector: str
    cik: int


def symbol_key(ticker: str) -> str:
    return ticker.upper().replace(".", "-")


def parse_constituents(payload: bytes) -> list[Constituent]:
    tree = html.fromstring(payload)
    tables = tree.xpath("//table[@id='constituents']")
    if len(tables) != 1:
        raise ValueError("Expected the Wikipedia constituents table; snapshot was not changed.")
    rows: list[Constituent] = []
    for row in tables[0].xpath(".//tr")[1:]:
        cells = [" ".join(cell.text_content().split()) for cell in row.xpath("./td")]
        if len(cells) < 7:
            raise ValueError("Malformed constituent row; snapshot was not changed.")
        rows.append(Constituent(cells[0], cells[1], cells[2], int(cells[6])))
    if len({row.ticker for row in rows}) != len(rows):
        raise ValueError("Duplicate constituent ticker.")
    return sorted(rows, key=lambda row: row.ticker)


def crosscheck(rows: list[Constituent], ticker_map: dict[str, Any]) -> list[str]:
    by_symbol = {symbol_key(str(row["ticker"])): int(row["cik_str"]) for row in ticker_map.values()}
    return [
        f"{row.ticker}: snapshot CIK {row.cik}, SEC CIK {by_symbol.get(symbol_key(row.ticker))}"
        for row in rows
        if by_symbol.get(symbol_key(row.ticker)) != row.cik
    ]


def refresh_snapshot(client: SecClient, target: Path = SNAPSHOT) -> dict[str, Any]:
    # This non-SEC source does not receive the operator's private contact address.
    response = httpx.get(
        CONSTITUENTS_URL,
        headers={"User-Agent": "NotSoLazy/0.1 (+https://github.com/angelofernand0/not-so-lazy)"},
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    rows = parse_constituents(response.content)
    if not 450 <= len(rows) <= 550:
        raise ValueError(f"Unexpected constituent count {len(rows)}; snapshot was not changed.")
    mismatches = crosscheck(rows, client.get_json(TICKERS_URL, refresh=True))
    if mismatches:
        raise ValueError(
            "CIK cross-check failed; snapshot was not changed:\n" + "\n".join(mismatches)
        )
    out = io.StringIO(newline="")
    writer = csv.DictWriter(
        out, fieldnames=["ticker", "name", "sector", "cik"], lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(asdict(row) for row in rows)
    payload = out.getvalue()
    metadata = {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source": CONSTITUENTS_URL,
        "crosschecked_against": TICKERS_URL,
        "security_count": len(rows),
        "issuer_count": len({row.cik for row in rows}),
        "sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "version": UNIVERSE_VERSION,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".csv.tmp")
    temporary.write_text(payload)
    temporary.replace(target)
    target.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def load_snapshot(path: Path = SNAPSHOT) -> list[Constituent]:
    if not path.exists():
        raise ValueError("No constituent snapshot. Run 'nsl universe refresh' first.")
    with path.open(newline="") as handle:
        return [
            Constituent(row["ticker"], row["name"], row["sector"], int(row["cik"]))
            for row in csv.DictReader(handle)
        ]


def sync_companies(session: Session, rows: list[Constituent]) -> None:
    content_version = (
        UNIVERSE_VERSION
        + ":"
        + hashlib.sha256(
            json.dumps(
                [asdict(row) for row in sorted(rows, key=lambda entry: entry.ticker)],
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12]
    )
    for previous_company in session.scalars(select(Company)):
        previous_company.in_sp500 = False
    # Deterministic canonical ticker; every alias remains searchable.
    for row in sorted(rows, key=lambda entry: entry.ticker, reverse=True):
        company = session.get(Company, row.cik)
        if company is None:
            company = Company(cik=row.cik)
            session.add(company)
        company.ticker, company.name, company.sector = row.ticker, row.name, row.sector
        company.in_sp500, company.universe_version = True, content_version
        session.flush()
        session.merge(CompanyAlias(ticker=symbol_key(row.ticker), cik=row.cik))
    session.flush()
