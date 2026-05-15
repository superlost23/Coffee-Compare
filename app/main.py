"""FastAPI entry. Public routes live here; admin routes are mounted from app.admin."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app import admin
from app.config import settings
from app.db import get_db
from app.logging_anon import log_search
from app.matching import CoffeeFields, ScoredMatch, label_for, score
from app.models import Offering, Roaster, SearchLog
from app.normalize import (
    normalize_country,
    normalize_name,
    normalize_process,
    normalize_varietal,
)
from app.pricing import format_price_per_oz
from app.search import search_candidates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Coffee Compare", docs_url=None, redoc_url=None)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["format_price_per_oz"] = format_price_per_oz

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Mount admin (uses ADMIN_PATH_TOKEN from env so the URL isn't enumerable)
admin.attach(app)


# ---------------------------------------------------------------------------
# Trending / popular helpers (powers the homepage "Explore" section)
# ---------------------------------------------------------------------------

_TREND_TYPES = ("country", "varietal", "producer")
_TREND_MIN = 3  # need at least this many searches before we call it "trending"
_TREND_DAYS = 30


def _trending_searches(db: Session, query_type: str, limit: int = 6) -> list[dict]:
    """Recent search activity for a given type. Empty if no searches yet."""
    since = datetime.now(timezone.utc) - timedelta(days=_TREND_DAYS)
    rows = (
        db.query(
            SearchLog.query_norm,
            func.count(SearchLog.id).label("n"),
        )
        .filter(
            SearchLog.ts_hour >= since,
            SearchLog.query_type == query_type,
            SearchLog.query_norm != "",
        )
        .group_by(SearchLog.query_norm)
        .order_by(desc("n"))
        .limit(limit)
        .all()
    )
    return [{"value": r[0], "count": int(r[1])} for r in rows]


def _popular_in_catalog(db: Session, column, limit: int = 6) -> list[dict]:
    """Most common values for a column across all indexed offerings.
    Fallback for when we don't have enough search history yet."""
    rows = (
        db.query(column, func.count(Offering.id).label("n"))
        .filter(column.isnot(None), column != "")
        .group_by(column)
        .order_by(desc("n"))
        .limit(limit)
        .all()
    )
    return [{"value": r[0], "count": int(r[1])} for r in rows]


_EMPTY_EXPLORE = {
    "sections": {
        "country":  {"mode": "popular", "items": []},
        "varietal": {"mode": "popular", "items": []},
        "producer": {"mode": "popular", "items": []},
    },
    "stats": {"offerings": 0, "in_stock": 0, "roasters": 0, "countries": 0, "varietals": 0},
}


def _homepage_explore(db: Session) -> dict:
    """Bundle three trending/popular lists + headline stats for the homepage.

    Each section returns:
        {"mode": "trending"|"popular", "items": [{"value": ..., "count": ..., "weight": 1..5}, ...]}

    `weight` is a 1-5 size bucket relative to the top item, used by the
    template to scale chip text size for a tag-cloud effect.

    Returns an empty-but-valid shape if the underlying tables don't yet
    exist (e.g. very first deploy before migrations run) so the homepage
    can still render rather than 500.
    """
    try:
        return _homepage_explore_impl(db)
    except ProgrammingError as e:
        log.warning("homepage explore queries failed (likely missing tables): %s", e)
        db.rollback()
        return _EMPTY_EXPLORE


def _homepage_explore_impl(db: Session) -> dict:
    sections = {}
    column_map = {
        "country": (Offering.country, 8),
        "varietal": (Offering.varietal, 10),
        "producer": (Offering.producer, 10),
    }
    for qtype in _TREND_TYPES:
        searches = _trending_searches(db, qtype, limit=10)
        total_n = sum(s["count"] for s in searches)
        if total_n >= _TREND_MIN:
            items = searches
            mode = "trending"
        else:
            col, lim = column_map[qtype]
            items = _popular_in_catalog(db, col, limit=lim)
            mode = "popular"
        # Add a 1..5 size weight based on count relative to the top item.
        top = max((it["count"] for it in items), default=1) or 1
        for it in items:
            it["weight"] = 1 + min(4, int(4 * it["count"] / top))
        sections[qtype] = {"mode": mode, "items": items}

    # Catalog-wide stats for the headline banner
    total_offerings = db.query(func.count(Offering.id)).scalar() or 0
    in_stock = db.query(func.count(Offering.id)).filter(Offering.in_stock == True).scalar() or 0  # noqa: E712
    roasters = db.query(func.count(Roaster.id)).scalar() or 0
    distinct_countries = (
        db.query(func.count(func.distinct(Offering.country)))
        .filter(Offering.country.isnot(None), Offering.country != "")
        .scalar() or 0
    )
    distinct_varietals = (
        db.query(func.count(func.distinct(Offering.varietal)))
        .filter(Offering.varietal.isnot(None), Offering.varietal != "")
        .scalar() or 0
    )

    return {
        "sections": sections,
        "stats": {
            "offerings": total_offerings,
            "in_stock": in_stock,
            "roasters": roasters,
            "countries": distinct_countries,
            "varietals": distinct_varietals,
        },
    }


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"explore": _homepage_explore(db)},
    )


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "privacy.html")


@app.get("/healthz")
def healthz(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Lightweight health check for uptime monitoring."""
    db.execute(__import__("sqlalchemy").text("SELECT 1"))
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Search (HTMX-friendly: returns HTML partial)
# ---------------------------------------------------------------------------

def _resolve_query_from_url(db: Session, url: str) -> CoffeeFields:
    """Look up an offering by URL. If we already have it indexed, return its
    fields. Otherwise, attempt an on-demand fetch (Shopify-flavored, with a
    short timeout) so the user gets *some* result. See ARCHITECTURE.md §4.5.
    """
    url = url.strip()
    if not url:
        return CoffeeFields()
    offering = db.query(Offering).filter(Offering.product_url == url).first()
    if offering:
        return CoffeeFields(
            producer=offering.producer,
            farm=offering.farm,
            country=offering.country,
            region=offering.region,
            varietal=offering.varietal,
            process=offering.process,
        )
    # Not indexed — try a quick on-demand fetch.
    return _fetch_url_on_demand(url)


def _fetch_url_on_demand(url: str) -> CoffeeFields:
    """Best-effort: try the Shopify /products/{handle}.js sibling endpoint,
    fall back to fetching the HTML and running the extraction pipeline. We
    cap this at 10 seconds total — the user is waiting.
    """
    import urllib.parse

    import httpx

    from app.extraction import ExtractedFields, extract

    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme.startswith("http"):
            return CoffeeFields()
        ua = settings().scrape_user_agent
        with httpx.Client(
            headers={"User-Agent": ua}, timeout=10.0, follow_redirects=True
        ) as client:
            description = ""
            prefilled = ExtractedFields(method="prefilled", confidence=0.0)
            # Shopify shortcut: /products/{handle}.js
            if "/products/" in parsed.path:
                handle = parsed.path.rsplit("/products/", 1)[1].rstrip("/").split("/")[0]
                json_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.js"
                try:
                    resp = client.get(json_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        description = data.get("description") or data.get("body_html") or ""
                except Exception:
                    pass
            # Fallback: scrape the rendered HTML page
            if not description:
                try:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        description = resp.text
                except Exception:
                    return CoffeeFields()

            fields = extract(description, prefilled=prefilled, use_llm=False)
            return CoffeeFields(
                producer=fields.producer,
                farm=fields.farm,
                country=fields.country,
                region=fields.region,
                varietal=fields.varietal,
                process=fields.process,
            )
    except Exception:
        return CoffeeFields()


def _meili_query_string(q: CoffeeFields) -> str:
    """Build the text query for Meilisearch.

    Includes every searchable field the user provided. Previously this
    omitted `process` and `region`, which meant a process-only search
    (e.g. "Washed") sent an empty query to Meili — Meili then returned
    50 arbitrary docs, and scoring couldn't surface the actual washed
    coffees because they weren't in the candidate set.
    """
    parts = [v for v in (q.producer, q.farm, q.varietal, q.country, q.region, q.process) if v]
    return " ".join(parts).strip()


def _run_match(db: Session, query: CoffeeFields) -> dict:
    """Search Meili → score in Python → return grouped results dict."""
    if query.is_empty():
        return {"exact": [], "similar": [], "alternatives": [], "examined": 0}

    qstr = _meili_query_string(query)
    # Wider net when the query is sparse (one or two fields): popular terms
    # like "Washed" or "Colombia" match thousands of offerings, and a 50-doc
    # limit risks all results coming from one or two roasters.
    fields_set = sum(1 for f in ("producer", "farm", "varietal", "country", "region", "process") if getattr(query, f))
    candidate_limit = 150 if fields_set <= 2 else 50
    hits = search_candidates(qstr, limit=candidate_limit)

    exact: list[tuple[ScoredMatch, dict]] = []
    similar: list[tuple[ScoredMatch, dict]] = []
    alternatives: list[tuple[ScoredMatch, dict]] = []

    for hit in hits:
        candidate = CoffeeFields(
            producer=hit.get("producer") or None,
            farm=hit.get("farm") or None,
            country=hit.get("country") or None,
            region=hit.get("region") or None,
            varietal=hit.get("varietal") or None,
            process=hit.get("process") or None,
        )
        sm = score(query, candidate)
        if sm.score >= 95:
            exact.append((sm, hit))
        elif sm.score >= 75:
            similar.append((sm, hit))
        elif sm.score >= 50:
            alternatives.append((sm, hit))
        # else: drop

    # Sort: in-stock first, then score desc, then price asc
    def sort_key(item: tuple[ScoredMatch, dict]) -> tuple:
        sm, h = item
        in_stock = 0 if h.get("in_stock") else 1
        ppo = h.get("price_per_oz") or 9999
        return (in_stock, -sm.score, ppo)

    exact.sort(key=sort_key)
    similar.sort(key=sort_key)
    alternatives.sort(key=sort_key)

    return {
        "exact": [_render_match(sm, h) for sm, h in exact[:10]],
        "similar": [_render_match(sm, h) for sm, h in similar[:10]],
        "alternatives": [_render_match(sm, h) for sm, h in alternatives[:10]],
        "examined": len(hits),
    }


def _render_match(sm: ScoredMatch, hit: dict) -> dict:
    """Shape a hit + score into the dict the template expects."""
    return {
        "score": sm.score,
        "score_label": label_for(sm.score),
        "field_match": sm.field_match,
        "title": hit.get("title"),
        "roaster_name": hit.get("roaster_name"),
        "roaster_slug": hit.get("roaster_slug"),
        "producer": hit.get("producer"),
        "farm": hit.get("farm"),
        "country": hit.get("country"),
        "region": hit.get("region"),
        "varietal": hit.get("varietal"),
        "process": hit.get("process"),
        "price_per_oz": hit.get("price_per_oz"),
        "in_stock": hit.get("in_stock"),
        "url": hit.get("product_url") or "",
    }


@app.post("/search", response_class=HTMLResponse)
def search_post(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Form()] = "",
    producer: Annotated[str, Form()] = "",
    farm: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "",
    varietal: Annotated[str, Form()] = "",
    process: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Single endpoint that handles both URL paste and field search."""
    query = CoffeeFields()
    log_type = "freeform"
    log_value = ""

    if url.strip():
        query = _resolve_query_from_url(db, url)
        log_type = "url"
        log_value = url.strip()
    else:
        query = CoffeeFields(
            producer=normalize_name(producer.strip()) if producer else None,
            farm=normalize_name(farm.strip()) if farm else None,
            country=normalize_country(country.strip()) if country else None,
            varietal=normalize_varietal(varietal.strip()) if varietal else None,
            process=normalize_process(process.strip()) if process else None,
        )
        # Pick the first non-empty field for log_type (matches user intent)
        for f in ("producer", "varietal", "farm", "country", "process"):
            v = getattr(query, f)
            if v:
                log_type = f
                log_value = v
                break

    results = _run_match(db, query)

    # Log anonymously
    top_score = max(
        [m["score"] for m in results["exact"] + results["similar"] + results["alternatives"]] or [0]
    )
    had_exact = len(results["exact"]) > 0
    if log_value:
        log_search(
            db,
            query_type=log_type,
            query_value=log_value if log_type != "url" else (query.producer or query.varietal or "url-paste"),
            had_exact=had_exact,
            top_score=top_score or None,
        )

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "query": query,
            "results": results,
            "had_query": not query.is_empty(),
        },
    )


# ---------------------------------------------------------------------------
# JSON API (for future integrations / power users)
# ---------------------------------------------------------------------------

@app.get("/api/search")
def api_search(
    db: Annotated[Session, Depends(get_db)],
    producer: str | None = None,
    farm: str | None = None,
    country: str | None = None,
    varietal: str | None = None,
    process: str | None = None,
) -> JSONResponse:
    query = CoffeeFields(
        producer=normalize_name(producer) if producer else None,
        farm=normalize_name(farm) if farm else None,
        country=normalize_country(country) if country else None,
        varietal=normalize_varietal(varietal) if varietal else None,
        process=normalize_process(process) if process else None,
    )
    return JSONResponse(_run_match(db, query))
