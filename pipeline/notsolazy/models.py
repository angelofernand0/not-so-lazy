"""Stage-owned records, keyed on CIK and accession rather than ticker."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    cik: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(250))
    sector: Mapped[str] = mapped_column(String(100))
    fiscal_year_end: Mapped[str | None] = mapped_column(String(4))
    in_sp500: Mapped[bool] = mapped_column(Boolean, default=True)
    universe_version: Mapped[str] = mapped_column(String(50))


class CompanyAlias(Base):
    __tablename__ = "company_aliases"
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"), index=True)


class Filing(Base):
    __tablename__ = "filings"
    accession: Mapped[str] = mapped_column(String(20), primary_key=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"), index=True)
    form: Mapped[str] = mapped_column(String(10))
    filed_at: Mapped[date] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    primary_doc_url: Mapped[str | None] = mapped_column(String(1000))
    raw_blob_key: Mapped[str | None] = mapped_column(String(250))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40))
    amendment_item_status: Mapped[str | None] = mapped_column(String(30))
    amendment_checked_item: Mapped[str | None] = mapped_column(String(10))
    amendment_probe_version: Mapped[str | None] = mapped_column(String(50))
    discover_version: Mapped[str] = mapped_column(String(50))
    fetch_version: Mapped[str | None] = mapped_column(String(50))
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)


class FilingPair(Base):
    __tablename__ = "filing_pairs"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"), index=True)
    current_accession: Mapped[str] = mapped_column(ForeignKey("filings.accession"))
    prior_accession: Mapped[str | None] = mapped_column(ForeignKey("filings.accession"))
    pairing_method: Mapped[str] = mapped_column(String(50))
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30))
    discover_version: Mapped[str] = mapped_column(String(50))


class ReviewEntry(Base):
    __tablename__ = "review_queue"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    accession: Mapped[str] = mapped_column(ForeignKey("filings.accession"))
    stage: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(2000))
    code_version: Mapped[str] = mapped_column(String(50))


class CleanedFiling(Base):
    __tablename__ = "cleaned_filings"
    accession: Mapped[str] = mapped_column(ForeignKey("filings.accession"), primary_key=True)
    blob_key: Mapped[str] = mapped_column(String(250))
    source_sha256: Mapped[str] = mapped_column(String(64))
    blocks_sha256: Mapped[str] = mapped_column(String(64))
    block_count: Mapped[int] = mapped_column(Integer)
    word_count: Mapped[int] = mapped_column(Integer)
    cleaner_version: Mapped[str] = mapped_column(String(50))
    quality_flags: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Section(Base):
    __tablename__ = "sections"
    accession: Mapped[str] = mapped_column(ForeignKey("filings.accession"), primary_key=True)
    item: Mapped[str] = mapped_column(String(10), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    word_count: Mapped[int] = mapped_column(Integer)
    extractor: Mapped[str] = mapped_column(String(30))
    extractor_version: Mapped[str] = mapped_column(String(50))
    primary_version: Mapped[str] = mapped_column(String(50))
    cleaner_version: Mapped[str] = mapped_column(String(50))
    input_signature: Mapped[str] = mapped_column(String(64))
    prior_word_count: Mapped[int | None] = mapped_column(Integer)
    start_block: Mapped[int | None] = mapped_column(Integer)
    end_block: Mapped[int | None] = mapped_column(Integer)
    quality_flags: Mapped[list[str]] = mapped_column(JSON)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    diagnostics: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    candidates_blob_key: Mapped[str] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def make_engine(database_url: str, **kwargs: Any) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True, **kwargs)
    if engine.dialect.name == "sqlite":

        def enable_foreign_keys(connection: Any, _: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        event.listen(engine, "connect", enable_foreign_keys)
    return engine
