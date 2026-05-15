"""SQLAlchemy engine + session factory."""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _normalize_db_url(url: str) -> str:
    """Force the psycopg v3 driver on bare postgres:// URLs.

    DigitalOcean's managed Postgres add-on injects DATABASE_URL as
    `postgres://...` or `postgresql://...` (no explicit driver), but SQLAlchemy
    2.x prefers an explicit driver to avoid picking psycopg2 by default. We
    install psycopg v3 in the Dockerfile, so route everything to it.
    """
    if url.startswith("postgresql+"):
        return url  # already explicit
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


engine = create_engine(
    _normalize_db_url(settings().database_url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for scripts/scrapers (commits on success)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
