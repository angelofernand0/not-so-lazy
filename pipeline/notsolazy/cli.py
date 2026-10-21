"""Versioned, rerunnable discovery/fetch commands. All network access is explicit."""

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from notsolazy import __version__
from notsolazy.config import Settings, section_rule
from notsolazy.discover import DISCOVER_VERSION, NoAnnualReport, discover_company
from notsolazy.fetch import fetch_filing
from notsolazy.models import Company, CompanyAlias, Filing, FilingPair, ReviewEntry, make_engine
from notsolazy.processing import process_pair
from notsolazy.sec_client import SecClient
from notsolazy.storage import LocalBlobStore
from notsolazy.universe import load_snapshot, refresh_snapshot, symbol_key, sync_companies


def parser_for_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nsl", description="Not So Lazy filing pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report configuration without exposing secrets")
    doctor.add_argument("--require-sec", action="store_true", help="Validate contact for EDGAR")
    commands.add_parser("init-db", help="Apply Alembic migrations")
    universe = commands.add_parser(
        "universe", help="Maintain the cross-checked constituent snapshot"
    )
    universe.add_subparsers(dest="action", required=True).add_parser("refresh")
    for name in ("discover", "fetch", "clean", "extract"):
        stage = commands.add_parser(name)
        stage.add_argument(
            "--ticker", help="One current S&P 500 ticker (including share-class aliases)"
        )
        stage.add_argument(
            "--since", type=date.fromisoformat, help="Current filing date, YYYY-MM-DD"
        )
        if name in {"clean", "extract"}:
            stage.add_argument(
                "--force", action="store_true", help="Recompute this stage from cached inputs"
            )
        if name == "extract":
            stage.add_argument("--item", help="Section item (defaults to SECTION_ITEM)")
        if name == "discover":
            stage.add_argument(
                "--refresh", action="store_true", help="Refresh cached submissions JSON"
            )
    review = commands.add_parser("review", help="Inspect or resolve a review flag")
    review_actions = review.add_subparsers(dest="action", required=True)
    review_actions.add_parser("list")
    resolve = review_actions.add_parser("resolve")
    resolve.add_argument("id")
    resolve.add_argument("--note", required=True)
    return parser


def _companies(session: Session, ticker: str | None) -> list[Company]:
    query = select(Company).where(Company.in_sp500.is_(True)).order_by(Company.cik)
    if ticker:
        alias = session.get(CompanyAlias, symbol_key(ticker))
        if alias is None:
            raise ValueError(f"Ticker {ticker.upper()} is not in the committed universe.")
        query = query.where(Company.cik == alias.cik)
    companies = list(session.scalars(query))
    if not companies:
        raise ValueError("No current companies matched the request.")
    return companies


def _pair_payload(session: Session, company: Company, pair: FilingPair) -> dict[str, object]:
    def filing_payload(accession: str | None) -> dict[str, object] | None:
        filing = session.get(Filing, accession) if accession else None
        if filing is None:
            return None
        return {
            "accession": filing.accession,
            "form": filing.form,
            "report_date": str(filing.report_date),
            "filed_at": str(filing.filed_at),
            "url": filing.primary_doc_url,
            "raw_blob_key": filing.raw_blob_key,
            "sha256": filing.sha256,
            "size_bytes": filing.size_bytes,
        }

    return {
        "cik": company.cik,
        "ticker": company.ticker,
        "status": pair.status,
        "current": filing_payload(pair.current_accession),
        "prior": filing_payload(pair.prior_accession),
        "pairing_method": pair.pairing_method,
        "flags": pair.flags,
        "discover_version": pair.discover_version,
    }


def run_stage(args: argparse.Namespace, settings: Settings, session: Session) -> None:
    if settings.blob_backend != "local":
        raise ValueError(
            "R2 is introduced in Milestone 8; use BLOB_BACKEND=local for this milestone."
        )
    # Constructor validates identity before it creates a limiter or sends a request.
    with SecClient(settings, LocalBlobStore(settings.data_dir)) as client:
        if args.command == "universe":
            metadata = refresh_snapshot(client)
            sync_companies(session, load_snapshot())
            session.commit()
            print(json.dumps(metadata, indent=2))
            return
        sync_companies(session, load_snapshot())
        session.commit()
        for company in _companies(session, args.ticker):
            pair: FilingPair | None
            if args.command == "discover":
                try:
                    pair = discover_company(
                        session, company, client, item=settings.section_item, refresh=args.refresh
                    )
                except NoAnnualReport:
                    session.commit()
                    print(
                        json.dumps(
                            {
                                "cik": company.cik,
                                "ticker": company.ticker,
                                "status": "no_annual_filing",
                                "discover_version": DISCOVER_VERSION,
                            }
                        )
                    )
                    continue
            else:
                pair = session.scalar(
                    select(FilingPair)
                    .where(FilingPair.cik == company.cik, FilingPair.status != "superseded")
                    .order_by(FilingPair.current_accession.desc())
                )
                if pair is None:
                    if args.ticker:
                        raise ValueError(
                            f"No discovered pair for {company.ticker}; run discover first."
                        )
                    print(
                        json.dumps(
                            {
                                "cik": company.cik,
                                "ticker": company.ticker,
                                "status": "no_discovered_pair",
                            }
                        )
                    )
                    continue
            current = session.get(Filing, pair.current_accession)
            assert current is not None
            if args.since and current.filed_at < args.since:
                session.commit()
                continue
            if args.command == "fetch":
                for accession in (pair.prior_accession, pair.current_accession):
                    if accession:
                        filing = session.get(Filing, accession)
                        assert filing is not None
                        fetch_filing(filing, client)
            session.commit()
            print(json.dumps(_pair_payload(session, company, pair), indent=2))


def run_offline_stage(args: argparse.Namespace, settings: Settings, session: Session) -> None:
    if settings.blob_backend != "local":
        raise ValueError("Use BLOB_BACKEND=local until the R2 adapter arrives.")
    rule = section_rule(getattr(args, "item", None) or settings.section_item)
    store = LocalBlobStore(settings.data_dir)
    for company in _companies(session, args.ticker):
        pair = session.scalar(
            select(FilingPair).where(
                FilingPair.cik == company.cik, FilingPair.status != "superseded"
            )
        )
        if pair is None:
            if args.ticker:
                raise ValueError(f"No pair for {company.ticker}; run discover and fetch first.")
            continue
        current = session.get(Filing, pair.current_accession)
        assert current is not None
        if args.since and current.filed_at < args.since:
            continue
        results = process_pair(
            session,
            pair,
            store,
            rule,
            stage=args.command,
            force=args.force,
            cache_dir=settings.data_dir / "edgartools",
        )
        session.commit()
        print(
            json.dumps(
                {
                    "ticker": company.ticker,
                    "cik": company.cik,
                    "stage": args.command,
                    "results": results,
                },
                indent=2,
            )
        )


def main() -> None:
    parser = parser_for_cli()
    args = parser.parse_args()
    try:
        settings = Settings()
        if args.command == "doctor":
            if args.require_sec:
                settings.require_sec_identity()
            print(
                json.dumps(
                    {
                        "version": __version__,
                        "database_backend": make_url(
                            settings.database_url.get_secret_value()
                        ).get_backend_name(),
                        "blob_backend": settings.blob_backend,
                        "section_item": settings.section_item,
                        "sec_identity_configured": bool(settings.sec_user_agent.strip()),
                        "summaries_enabled": settings.summaries_enabled,
                        "milestone": 3,
                    },
                    indent=2,
                )
            )
            return
        url = make_url(settings.database_url.get_secret_value())
        if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        if args.command == "init-db":
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            command.upgrade(config, "head")
            print("Database migrations applied.")
            return
        engine = make_engine(settings.database_url.get_secret_value())
        try:
            with Session(engine) as session:
                if args.command == "review":
                    if args.action == "list":
                        rows = session.scalars(
                            select(ReviewEntry)
                            .where(ReviewEntry.resolved_at.is_(None))
                            .order_by(ReviewEntry.created_at)
                        )
                        print(
                            json.dumps(
                                [
                                    {
                                        "id": row.id,
                                        "accession": row.accession,
                                        "stage": row.stage,
                                        "reason": row.reason,
                                    }
                                    for row in rows
                                ],
                                indent=2,
                            )
                        )
                    else:
                        entry = session.get(ReviewEntry, args.id)
                        if entry is None:
                            raise ValueError("Review entry not found.")
                        if not args.note.strip():
                            raise ValueError("A nonempty resolution note is required.")
                        entry.resolved_at, entry.note = datetime.now(UTC), args.note
                        session.commit()
                        print("Review resolved. Correct the source and re-run its stage.")
                elif args.command in {"clean", "extract"}:
                    run_offline_stage(args, settings, session)
                else:
                    run_stage(args, settings, session)
        finally:
            engine.dispose()
    except ValidationError:
        parser.exit(2, "Invalid environment configuration; check .env.\n")
    except ValueError as error:
        parser.exit(2, f"{error}\n")
    except httpx.HTTPStatusError as error:
        parser.exit(
            1,
            f"HTTP {error.response.status_code} from {error.request.url.host}; "
            "no failed response was cached.\n",
        )
    except httpx.TransportError:
        parser.exit(
            1, "Network request failed after retry policy. Cached documents were retained.\n"
        )
    except SQLAlchemyError:
        parser.exit(1, "Database operation failed. Verify DATABASE_URL and run 'nsl init-db'.\n")


if __name__ == "__main__":
    main()
