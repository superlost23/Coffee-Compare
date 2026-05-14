"""Meilisearch index management.

We keep the Meilisearch index in sync with Postgres on every scrape upsert.
The index is the *retrieval* layer (fuzzy candidate selection); Postgres is
the source of truth and final price/stock state.
"""
from __future__ import annotations

import logging
from typing import Any

import meilisearch  # type: ignore

from app.config import settings

log = logging.getLogger(__name__)

INDEX_NAME = "offerings"

SEARCHABLE_ATTRIBUTES = [
    "producer",
    "farm",
    "varietal",
    "title",
    "country",
    "region",
    "process",
]
FILTERABLE_ATTRIBUTES = ["country", "process", "in_stock", "roaster_slug"]
SORTABLE_ATTRIBUTES = ["price_per_oz", "last_seen"]


def _client() -> meilisearch.Client:
    return meilisearch.Client(settings().meili_url, settings().meili_master_key)


def ensure_index() -> None:
    """Create the index and configure searchable/filterable attributes."""
    c = _client()
    try:
        c.create_index(INDEX_NAME, {"primaryKey": "id"})
    except Exception as e:  # noqa: BLE001
        # Already exists; that's fine
        log.debug("Index create returned: %s", e)
    idx = c.index(INDEX_NAME)
    idx.update_searchable_attributes(SEARCHABLE_ATTRIBUTES)
    idx.update_filterable_attributes(FILTERABLE_ATTRIBUTES)
    idx.update_sortable_attributes(SORTABLE_ATTRIBUTES)
    # Synonyms: handle the most common variants Meili wouldn't infer
    idx.update_synonyms({
        "gesha": ["geisha"],
        "geisha": ["gesha"],
        "wush wush": ["wushwush"],
    })


def index_offering(offering_doc: dict[str, Any]) -> None:
    """Upsert a single offering. Document shape produced by app.search.to_doc()."""
    _client().index(INDEX_NAME).add_documents([offering_doc])


def index_many(docs: list[dict[str, Any]]) -> None:
    if not docs:
        return
    _client().index(INDEX_NAME).add_documents(docs)


def remove_offering(offering_id: str) -> None:
    _client().index(INDEX_NAME).delete_document(offering_id)


def to_doc(offering: Any, roaster_slug: str, roaster_name: str) -> dict[str, Any]:
    """Build the Meilisearch document from an Offering ORM object."""
    return {
        "id": str(offering.id),
        "roaster_slug": roaster_slug,
        "roaster_name": roaster_name,
        "title": offering.title or "",
        "producer": offering.producer or "",
        "farm": offering.farm or "",
        "country": offering.country or "",
        "region": offering.region or "",
        "varietal": offering.varietal or "",
        "process": offering.process or "",
        "price_per_oz": float(offering.price_per_oz) if offering.price_per_oz else None,
        "in_stock": bool(offering.in_stock),
        "last_seen": offering.last_seen.isoformat() if offering.last_seen else None,
    }


def search_candidates(
    query_str: str,
    *,
    limit: int = 50,
    filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run a fuzzy search and return raw Meilisearch hits."""
    params: dict[str, Any] = {"limit": limit}
    if filters:
        params["filter"] = filters
    result = _client().index(INDEX_NAME).search(query_str, params)
    return result.get("hits", [])
