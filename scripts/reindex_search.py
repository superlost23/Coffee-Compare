"""CLI: rebuild the Meilisearch index from Postgres.

Run this after schema changes, or if the Meilisearch volume is lost. Postgres
is the source of truth; the index can always be regenerated.
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from app.db import session_scope
from app.models import Offering, Roaster
from app.search import ensure_index, index_many, to_doc

log = logging.getLogger("reindex")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    ensure_index()

    docs = []
    with session_scope() as db:
        offerings = db.execute(
            select(Offering, Roaster).join(Roaster, Roaster.id == Offering.roaster_id)
        ).all()
        for offering, roaster in offerings:
            doc = to_doc(offering, roaster.slug, roaster.name)
            doc["product_url"] = offering.product_url
            docs.append(doc)

    log.info("Indexing %d offerings into Meilisearch", len(docs))
    # Push in batches of 1000
    for i in range(0, len(docs), 1000):
        index_many(docs[i : i + 1000])
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
