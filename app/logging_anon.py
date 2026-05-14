"""GDPR-safe search logging. See ARCHITECTURE.md §11.

Strict rules enforced here:
- Hour-truncated timestamps (no minute/second granularity)
- Never accept IP, user-agent, session, or any other request identifier
- Query strings are *normalized* before storage (lowercase, accent-stripped)
- We don't store the raw URL the user pasted — only the extracted fields
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import SearchLog
from app.normalize import slug_for_match


def _hour_now() -> datetime:
    """Returns current time truncated to the hour, in UTC."""
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def log_search(
    db: Session,
    *,
    query_type: str,
    query_value: str,
    matched_id: uuid.UUID | None = None,
    had_exact: bool = False,
    top_score: int | None = None,
) -> None:
    """Insert a single anonymous log row. No-op if query_value is empty."""
    norm = slug_for_match(query_value)
    if not norm:
        return
    row = SearchLog(
        ts_hour=_hour_now(),
        query_type=query_type,
        query_norm=norm[:255],
        matched_id=matched_id,
        had_exact=had_exact,
        top_score=top_score,
    )
    db.add(row)
    db.commit()
