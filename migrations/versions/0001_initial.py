"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm is required for fuzzy similarity matching on producer/farm/varietal
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "roasters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("website", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("scraper_module", sa.String(128), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_scraped", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_roasters_slug", "roasters", ["slug"])
    op.create_index("ix_roasters_active", "roasters", ["active"])

    op.create_table(
        "offerings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("roaster_id", UUID(as_uuid=True), sa.ForeignKey("roasters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("producer", sa.String(255), nullable=True),
        sa.Column("farm", sa.String(255), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("region", sa.String(128), nullable=True),
        sa.Column("varietal", sa.String(255), nullable=True),
        sa.Column("process", sa.String(128), nullable=True),
        sa.Column("size_grams", sa.Numeric(8, 2), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("price_per_oz", sa.Numeric(8, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("raw_description", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(32), nullable=False, server_default="regex"),
        sa.Column("extraction_conf", sa.Numeric(3, 2), nullable=False, server_default="0.5"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("roaster_id", "product_url", "size_grams", name="uq_offering_url_size"),
    )
    op.create_index("ix_offerings_roaster_id", "offerings", ["roaster_id"])
    op.create_index("ix_offering_country_process", "offerings", ["country", "process"])
    op.create_index("ix_offering_in_stock", "offerings", ["in_stock"])

    # Trigram GIN indexes for fuzzy matching in SQL queries
    op.execute(
        "CREATE INDEX ix_offering_producer_trgm ON offerings "
        "USING gin (producer gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_offering_farm_trgm ON offerings "
        "USING gin (farm gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_offering_varietal_trgm ON offerings "
        "USING gin (varietal gin_trgm_ops)"
    )

    op.create_table(
        "search_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query_type", sa.String(16), nullable=False),
        sa.Column("query_norm", sa.String(255), nullable=False),
        sa.Column("matched_id", UUID(as_uuid=True), nullable=True),
        sa.Column("had_exact", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("top_score", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "query_type IN ('url','producer','varietal','country','farm','process','region','freeform')",
            name="ck_query_type",
        ),
    )
    op.create_index("ix_search_logs_ts_type", "search_logs", ["ts_hour", "query_type"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("roaster_id", UUID(as_uuid=True), sa.ForeignKey("roasters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("products_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("products_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("products_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_scrape_runs_roaster", "scrape_runs", ["roaster_id"])
    op.create_index("ix_scrape_runs_started", "scrape_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_scrape_runs_started", table_name="scrape_runs")
    op.drop_index("ix_scrape_runs_roaster", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_index("ix_search_logs_ts_type", table_name="search_logs")
    op.drop_table("search_logs")
    op.execute("DROP INDEX IF EXISTS ix_offering_varietal_trgm")
    op.execute("DROP INDEX IF EXISTS ix_offering_farm_trgm")
    op.execute("DROP INDEX IF EXISTS ix_offering_producer_trgm")
    op.drop_index("ix_offering_in_stock", table_name="offerings")
    op.drop_index("ix_offering_country_process", table_name="offerings")
    op.drop_index("ix_offerings_roaster_id", table_name="offerings")
    op.drop_table("offerings")
    op.drop_index("ix_roasters_active", table_name="roasters")
    op.drop_index("ix_roasters_slug", table_name="roasters")
    op.drop_table("roasters")
