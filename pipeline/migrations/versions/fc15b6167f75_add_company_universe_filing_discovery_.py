"""Add company universe filing discovery fetch and review records"""

import sqlalchemy as sa
from alembic import op

revision = "fc15b6167f75"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("cik", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=False),
        sa.Column("fiscal_year_end", sa.String(length=4), nullable=True),
        sa.Column("in_sp500", sa.Boolean(), nullable=False),
        sa.Column("universe_version", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("cik"),
    )
    op.create_table(
        "company_aliases",
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("cik", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cik"],
            ["companies.cik"],
        ),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index(op.f("ix_company_aliases_cik"), "company_aliases", ["cik"], unique=False)
    op.create_table(
        "filings",
        sa.Column("accession", sa.String(length=20), nullable=False),
        sa.Column("cik", sa.Integer(), nullable=False),
        sa.Column("form", sa.String(length=10), nullable=False),
        sa.Column("filed_at", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("primary_doc_url", sa.String(length=1000), nullable=True),
        sa.Column("raw_blob_key", sa.String(length=250), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("amendment_item_status", sa.String(length=30), nullable=True),
        sa.Column("amendment_checked_item", sa.String(length=10), nullable=True),
        sa.Column("amendment_probe_version", sa.String(length=50), nullable=True),
        sa.Column("discover_version", sa.String(length=50), nullable=False),
        sa.Column("fetch_version", sa.String(length=50), nullable=True),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cik"],
            ["companies.cik"],
        ),
        sa.PrimaryKeyConstraint("accession"),
    )
    op.create_index(op.f("ix_filings_cik"), "filings", ["cik"], unique=False)
    op.create_table(
        "filing_pairs",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("cik", sa.Integer(), nullable=False),
        sa.Column("current_accession", sa.String(length=20), nullable=False),
        sa.Column("prior_accession", sa.String(length=20), nullable=True),
        sa.Column("pairing_method", sa.String(length=50), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("discover_version", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["cik"],
            ["companies.cik"],
        ),
        sa.ForeignKeyConstraint(
            ["current_accession"],
            ["filings.accession"],
        ),
        sa.ForeignKeyConstraint(
            ["prior_accession"],
            ["filings.accession"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_filing_pairs_cik"), "filing_pairs", ["cik"], unique=False)
    op.create_table(
        "review_queue",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("accession", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=250), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("code_version", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["accession"],
            ["filings.accession"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("review_queue")
    op.drop_index(op.f("ix_filing_pairs_cik"), table_name="filing_pairs")
    op.drop_table("filing_pairs")
    op.drop_index(op.f("ix_filings_cik"), table_name="filings")
    op.drop_table("filings")
    op.drop_index(op.f("ix_company_aliases_cik"), table_name="company_aliases")
    op.drop_table("company_aliases")
    op.drop_table("companies")
