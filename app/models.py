"""ORM models. See ARCHITECTURE.md §3 for schema rationale."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Roaster(Base):
    __tablename__ = "roasters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    website: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(32), default="unknown")
    scraper_module: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    offerings: Mapped[list["Offering"]] = relationship(back_populates="roaster")


class Offering(Base):
    __tablename__ = "offerings"
    __table_args__ = (
        UniqueConstraint("roaster_id", "product_url", "size_grams", name="uq_offering_url_size"),
        Index("ix_offering_country_process", "country", "process"),
        Index("ix_offering_in_stock", "in_stock"),
        # pg_trgm GIN indexes are created in the Alembic migration (raw DDL)
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    roaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roasters.id", ondelete="CASCADE"), index=True
    )
    product_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)

    producer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    farm: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    varietal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    process: Mapped[str | None] = mapped_column(String(128), nullable=True)

    size_grams: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_per_oz: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(32), default="regex")
    extraction_conf: Mapped[float] = mapped_column(Numeric(3, 2), default=0.5)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    roaster: Mapped[Roaster] = relationship(back_populates="offerings")


class SearchLog(Base):
    """GDPR-safe: hour-truncated timestamps, no IP, no UA, no session."""

    __tablename__ = "search_logs"
    __table_args__ = (
        CheckConstraint(
            "query_type IN ('url','producer','varietal','country','farm','process','region','freeform')",
            name="ck_query_type",
        ),
        Index("ix_search_logs_ts_type", "ts_hour", "query_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    query_type: Mapped[str] = mapped_column(String(16))
    query_norm: Mapped[str] = mapped_column(String(255))
    matched_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    had_exact: Mapped[bool] = mapped_column(Boolean, default=False)
    top_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    roaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roasters.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    products_seen: Mapped[int] = mapped_column(Integer, default=0)
    products_new: Mapped[int] = mapped_column(Integer, default=0)
    products_updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
