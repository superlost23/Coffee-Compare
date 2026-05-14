"""Admin dashboard. Hidden behind a token-in-URL + HTTP basic auth.

The admin path is /admin-{ADMIN_PATH_TOKEN}, configured via env. There is no
public link to it anywhere in the app — consistent with the user's request
that visitors not even see the login button.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Offering, Roaster, ScrapeRun, SearchLog

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
security = HTTPBasic()


def _check_auth(creds: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    s = settings()
    user_ok = secrets.compare_digest(creds.username.encode(), s.admin_username.encode())
    pass_ok = secrets.compare_digest(creds.password.encode(), s.admin_password.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


def _trends(db: Session, query_type: str, days: int = 7, limit: int = 15) -> list[tuple[str, int, float]]:
    """Returns (query_norm, count, avg_top_score) tuples for a given type."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            SearchLog.query_norm,
            func.count(SearchLog.id).label("n"),
            func.avg(SearchLog.top_score).label("avg_score"),
        )
        .filter(SearchLog.ts_hour >= since, SearchLog.query_type == query_type)
        .group_by(SearchLog.query_norm)
        .order_by(desc("n"))
        .limit(limit)
        .all()
    )
    return [(r[0], int(r[1]), float(r[2] or 0)) for r in rows]


def _coverage(db: Session) -> list[dict]:
    """Per-roaster scrape stats."""
    out = []
    for r in db.query(Roaster).order_by(Roaster.name).all():
        n_total = db.query(Offering).filter(Offering.roaster_id == r.id).count()
        n_extracted = (
            db.query(Offering)
            .filter(
                Offering.roaster_id == r.id,
                Offering.producer.isnot(None),
                Offering.varietal.isnot(None),
                Offering.process.isnot(None),
            )
            .count()
        )
        last_run = (
            db.query(ScrapeRun)
            .filter(ScrapeRun.roaster_id == r.id)
            .order_by(desc(ScrapeRun.started_at))
            .first()
        )
        out.append(
            {
                "name": r.name,
                "slug": r.slug,
                "active": r.active,
                "platform": r.platform,
                "total": n_total,
                "extracted": n_extracted,
                "extracted_pct": round(100 * n_extracted / n_total) if n_total else 0,
                "last_scraped": r.last_scraped,
                "last_status": last_run.status if last_run else "never",
            }
        )
    return out


def _recent_runs(db: Session, limit: int = 50) -> list[dict]:
    rows = (
        db.query(ScrapeRun, Roaster.name)
        .join(Roaster, Roaster.id == ScrapeRun.roaster_id)
        .order_by(desc(ScrapeRun.started_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "roaster": name,
            "started": run.started_at,
            "finished": run.finished_at,
            "status": run.status,
            "seen": run.products_seen,
            "new": run.products_new,
            "updated": run.products_updated,
            "error": run.error,
        }
        for run, name in rows
    ]


def _heatmap_data(db: Session, days: int = 30) -> list[dict]:
    """Country/region search volume for the heat map.

    We don't store coordinates — just counts. The frontend has a static
    JSON of region → lat/lon and joins on the client.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    country_rows = (
        db.query(SearchLog.query_norm, func.count(SearchLog.id))
        .filter(
            SearchLog.ts_hour >= since,
            SearchLog.query_type == "country",
        )
        .group_by(SearchLog.query_norm)
        .all()
    )
    return [{"name": r[0], "count": int(r[1])} for r in country_rows]


def attach(app: FastAPI) -> None:
    """Register admin routes under the secret path prefix."""
    base = f"/admin-{settings().admin_path_token}"

    @app.get(base, response_class=HTMLResponse)
    def admin_home(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _user: Annotated[str, Depends(_check_auth)],
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "base": base,
                "trends_producer": _trends(db, "producer"),
                "trends_varietal": _trends(db, "varietal"),
                "trends_country": _trends(db, "country"),
                "trends_url": _trends(db, "url"),
                "coverage": _coverage(db),
                "runs": _recent_runs(db),
                "heatmap": _heatmap_data(db),
            },
        )
