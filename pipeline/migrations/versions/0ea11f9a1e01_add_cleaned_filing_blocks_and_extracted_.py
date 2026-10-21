"""Add cleaned filing blocks and extracted sections"""

import sqlalchemy as sa
from alembic import op

revision = "0ea11f9a1e01"
down_revision = "fc15b6167f75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cleaned_filings",
        sa.Column("accession", sa.String(length=20), nullable=False),
        sa.Column("blob_key", sa.String(length=250), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("blocks_sha256", sa.String(length=64), nullable=False),
        sa.Column("block_count", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("cleaner_version", sa.String(length=50), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["accession"],
            ["filings.accession"],
        ),
        sa.PrimaryKeyConstraint("accession"),
    )
    op.create_table(
        "sections",
        sa.Column("accession", sa.String(length=20), nullable=False),
        sa.Column("item", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("extractor", sa.String(length=30), nullable=False),
        sa.Column("extractor_version", sa.String(length=50), nullable=False),
        sa.Column("primary_version", sa.String(length=50), nullable=False),
        sa.Column("cleaner_version", sa.String(length=50), nullable=False),
        sa.Column("input_signature", sa.String(length=64), nullable=False),
        sa.Column("prior_word_count", sa.Integer(), nullable=True),
        sa.Column("start_block", sa.Integer(), nullable=True),
        sa.Column("end_block", sa.Integer(), nullable=True),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("candidates_blob_key", sa.String(length=250), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["accession"],
            ["filings.accession"],
        ),
        sa.PrimaryKeyConstraint("accession", "item"),
    )


def downgrade() -> None:
    op.drop_table("sections")
    op.drop_table("cleaned_filings")
