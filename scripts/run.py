"""Orchestration: run a roaster's scraper end-to-end and upsert into Postgres + Meili.

This module is invoked by:
  - scripts.scrape_all (cron, daily)
  - scripts.scrape_one (debugging)
  - the on-demand path in main.py when a user pastes a URL from a new roaster

Failures inside a single product don't abort the run. Failures in
list_products() do (we can't know what to update).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import session_scope
from app.extraction import ExtractedFields, extract
from app.models import Offering, Roaster, ScrapeRun
from app.pricing import parse_size, price_per_oz, smaller_size
from app.scrapers.base import BaseRoasterScraper, ProductRef, RawOffering
from app.scrapers.registry import get as get_scraper
from app.search import ensure_index, index_offering, to_doc

log = logging.getLogger(__name__)


def _ensure_roaster_row(db: Session, slug: str) -> Roaster:
    cls = get_scraper(slug)
    if cls is None:
        raise ValueError(f"No scraper registered for slug={slug}")
    r = db.execute(select(Roaster).where(Roaster.slug == slug)).scalar_one_or_none()
    if r is None:
        r = Roaster(
            slug=slug,
            name=cls.name,
            website=cls.base_url,
            platform="shopify",  # default; non-Shopify scrapers can override
            scraper_module=f"app.scrapers.registry:{slug}",
            active=True,
        )
        db.add(r)
        db.flush()
    return r


def _smallest_variant(raw: RawOffering) -> tuple[float | None, int | None, bool]:
    """Pick the smallest size with a price. Returns (grams, price_cents, in_stock)."""
    candidates = [
        (v.grams, v.price_cents, v.available)
        for v in raw.variants
        if v.grams and v.price_cents is not None
    ]
    if not candidates:
        # fall back to first variant if we couldn't size anything
        for v in raw.variants:
            if v.price_cents is not None:
                return (None, v.price_cents, v.available)
        return (None, None, False)
    # smallest by grams; if tied, prefer in-stock
    candidates.sort(key=lambda t: (t[0] or 99999, 0 if t[2] else 1))
    return candidates[0]


def _upsert_offering(
    db: Session,
    roaster: Roaster,
    raw: RawOffering,
    fields: ExtractedFields,
) -> tuple[Offering, bool, bool]:
    """Insert or update. Returns (offering, was_new, was_updated)."""
    grams, price_cents, in_stock = _smallest_variant(raw)
    ppo = price_per_oz(price_cents, grams) if (price_cents and grams) else None

    # Look up existing
    existing = db.execute(
        select(Offering).where(
            Offering.roaster_id == roaster.id,
            Offering.product_url == raw.url,
            Offering.size_grams == grams,
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing is None:
        o = Offering(
            roaster_id=roaster.id,
            product_url=raw.url,
            title=raw.title,
            producer=fields.producer,
            farm=fields.farm,
            country=fields.country,
            region=fields.region,
            varietal=fields.varietal,
            process=fields.process,
            size_grams=grams,
            price_cents=price_cents,
            price_per_oz=ppo,
            in_stock=in_stock,
            raw_description=raw.description_html[:20000] if raw.description_html else None,
            extraction_method=fields.method,
            extraction_conf=fields.confidence,
            first_seen=now,
            last_seen=now,
            last_updated=now,
        )
        db.add(o)
        db.flush()
        return (o, True, False)

    # Update path
    changed = False
    for f in ("producer", "farm", "country", "region", "varietal", "process"):
        if getattr(existing, f) != getattr(fields, f) and getattr(fields, f):
            setattr(existing, f, getattr(fields, f))
            changed = True
    for f, v in (("title", raw.title), ("price_cents", price_cents), ("in_stock", in_stock), ("price_per_oz", ppo)):
        if getattr(existing, f) != v:
            setattr(existing, f, v)
            changed = True
    existing.last_seen = now
    if changed:
        existing.last_updated = now
        existing.extraction_method = fields.method
        existing.extraction_conf = fields.confidence
    return (existing, False, changed)


def run_one(slug: str, *, use_llm: bool = True) -> dict[str, Any]:
    """Run the full scrape pipeline for a single roaster.

    Returns a summary dict suitable for logging.
    """
    cls = get_scraper(slug)
    if cls is None:
        raise ValueError(f"No scraper for {slug}")

    ensure_index()

    summary = {"slug": slug, "seen": 0, "new": 0, "updated": 0, "errors": 0}

    with session_scope() as db:
        roaster = _ensure_roaster_row(db, slug)
        # Capture as plain ints — `roaster` becomes detached when this session
        # closes, and any later attribute access would trigger a refresh on a
        # closed session.
        roaster_id = roaster.id
        run = ScrapeRun(roaster_id=roaster_id, status="running")
        db.add(run)
        db.flush()
        run_id = run.id

    try:
        with cls() as scraper:  # type: ignore[abstract]
            refs: list[ProductRef] = scraper.list_products()
            log.info("[%s] discovered %d products", slug, len(refs))
            summary["seen"] = len(refs)

            for ref in refs:
                try:
                    raw = scraper.parse_product(ref)
                    if raw is None:
                        continue
                    # Build prefilled fields if scraper supplied any
                    pre = ExtractedFields(
                        producer=raw.producer,
                        farm=raw.farm,
                        country=raw.country,
                        region=raw.region,
                        varietal=raw.varietal,
                        process=raw.process,
                        method="prefilled" if any(
                            (raw.producer, raw.varietal, raw.process)
                        ) else "none",
                        confidence=0.9 if any((raw.producer, raw.varietal)) else 0.0,
                    )
                    fields = extract(raw.description_html, prefilled=pre, use_llm=use_llm)

                    with session_scope() as db:
                        # Re-attach roaster within this session
                        r = db.execute(
                            select(Roaster).where(Roaster.id == roaster_id)
                        ).scalar_one()
                        offering, is_new, is_upd = _upsert_offering(db, r, raw, fields)
                        if is_new:
                            summary["new"] += 1
                        if is_upd:
                            summary["updated"] += 1
                        # Index in Meilisearch
                        doc = to_doc(offering, r.slug, r.name)
                        doc["product_url"] = offering.product_url
                        try:
                            index_offering(doc)
                        except Exception as e:  # noqa: BLE001
                            log.warning("[%s] meili index failed: %s", slug, e)
                except Exception as e:  # noqa: BLE001
                    log.exception("[%s] failed product %s: %s", slug, ref.url, e)
                    summary["errors"] += 1
        # Mark run complete
        with session_scope() as db:
            run = db.get(ScrapeRun, run_id)
            if run:
                run.finished_at = datetime.now(timezone.utc)
                run.status = "ok" if summary["errors"] == 0 else "partial"
                run.products_seen = summary["seen"]
                run.products_new = summary["new"]
                run.products_updated = summary["updated"]
            r = db.execute(select(Roaster).where(Roaster.slug == slug)).scalar_one()
            r.last_scraped = datetime.now(timezone.utc)
    except Exception as e:  # noqa: BLE001
        log.exception("[%s] run aborted: %s", slug, e)
        with session_scope() as db:
            run = db.get(ScrapeRun, run_id)
            if run:
                run.finished_at = datetime.now(timezone.utc)
                run.status = "failed"
                run.error = str(e)[:2000]
        summary["errors"] += 1

    return summary
