"""CLI: insert/update roaster rows from the scraper registry.

Run once after first migration, then any time you add a new roaster to
app/scrapers/registry.py.
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from app.db import session_scope
from app.models import Roaster
from app.scrapers.registry import SEEDS

log = logging.getLogger("seed")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    inserted = 0
    updated = 0
    with session_scope() as db:
        for slug, cls in SEEDS.items():
            existing = db.execute(select(Roaster).where(Roaster.slug == slug)).scalar_one_or_none()
            if existing:
                if existing.website != cls.base_url or existing.name != cls.name:
                    existing.website = cls.base_url
                    existing.name = cls.name
                    updated += 1
            else:
                db.add(Roaster(
                    slug=slug,
                    name=cls.name,
                    website=cls.base_url,
                    platform="shopify",
                    scraper_module=f"app.scrapers.registry:{slug}",
                    active=True,
                ))
                inserted += 1
    log.info("Seed complete: %d inserted, %d updated", inserted, updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
