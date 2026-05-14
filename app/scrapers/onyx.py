"""Onyx Coffee Lab scraper.

Onyx encodes coffee metadata in Shopify product *tags* with a prefix scheme:
    "origin:Colombia", "process:Dry Washed", "method:Espresso", "type:single origin"

The producer + varietal are typically in the product title, which follows the
pattern "{Country} {Producer Name} {Varietal}" — e.g. "Colombia Diego Horta
Pink Bourbon".  We try to parse those from the title against a list of known
varietals.

This means we don't need a second HTTP request per product — everything we
need is already in /products.json.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

# Common varietals to look for in the title. Order matters: longer multi-word
# names first so they win over single-word substrings.
_KNOWN_VARIETALS = (
    "Pink Bourbon", "Yellow Bourbon", "Red Bourbon", "Orange Bourbon",
    "Bourbon Sidra", "Bourbon Aji", "Ethiopian Heirloom", "Pacamara",
    "Tipica Mejorada", "Yellow Catuai", "Red Catuai", "Mundo Novo",
    "SL28", "SL34", "Ruiru 11", "Wush Wush", "Castillo", "Caturra",
    "Catuai", "Geisha", "Gesha", "Typica", "Bourbon", "Pacas",
    "Java", "Maragogipe", "Chiroso", "Sidra", "Tabi",
    "74158", "74110", "74112", "74165", "74140",
)
_VARIETAL_RE = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in _KNOWN_VARIETALS) + r")\b",
    re.IGNORECASE,
)


def _parse_tags(tags: list[str]) -> dict[str, str]:
    """Tags like 'origin:Colombia' -> {country: 'Colombia'}."""
    out: dict[str, str] = {}
    for t in tags or []:
        if ":" not in t:
            continue
        key, _, val = t.partition(":")
        key = key.strip().lower()
        val = val.strip().replace("&nbsp;", " ")  # Onyx sometimes encodes spaces
        if not val:
            continue
        if key in ("origin", "country"):
            out["country"] = val
        elif key == "process":
            out["process"] = val
        elif key in ("region",):
            out["region"] = val
        elif key in ("variety", "varietal"):
            out["varietal"] = val
    return out


def _parse_title(title: str, country: str | None) -> tuple[str | None, str | None]:
    """Return (producer, varietal) extracted from title.

    Title pattern: "{Country} {Producer Words} {Varietal}".
    We strip the country from the front, find a known varietal at the end,
    and treat the middle as producer.
    """
    if not title:
        return (None, None)
    t = title.strip()
    if country and t.lower().startswith(country.lower()):
        t = t[len(country):].strip()
    # Find the LAST varietal mention (often at the end of the title)
    varietal = None
    matches = list(_VARIETAL_RE.finditer(t))
    if matches:
        m = matches[-1]
        varietal = m.group(1)
        # Producer is everything before the matched varietal
        producer_part = t[: m.start()].strip().rstrip("-—|")
        # Clean up trailing punctuation/words
        producer_part = re.sub(r"\s+", " ", producer_part).strip()
        producer = producer_part if 2 <= len(producer_part) <= 80 else None
    else:
        # No varietal recognized — use everything as producer (still useful for matching)
        producer = t if 2 <= len(t) <= 80 else None

    return (producer, varietal)


class OnyxScraper(ShopifyScraper):
    slug = "onyx"
    name = "Onyx Coffee Lab"
    base_url = "https://onyxcoffeelab.com"

    def is_coffee(self, product: dict[str, Any]) -> bool:
        # Onyx tags every coffee product with the "coffee" tag and uses product_type "Coffee"
        ptype = (product.get("product_type") or "").lower()
        tags = product.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        tags_lower = [t.lower() for t in tags]
        if "coffee" != ptype.lower() and "coffee" not in tags_lower:
            return False
        # Skip merch within coffee category if any
        title = (product.get("title") or "").lower()
        if any(bad in title for bad in ("gift card", "subscription", "merch")):
            return False
        return True

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None

        tags = (ref.raw or {}).get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        fields = _parse_tags(tags)
        country = fields.get("country")
        producer, varietal = _parse_title(raw.title, country)

        raw.country = country or raw.country
        raw.region = fields.get("region") or raw.region
        raw.process = fields.get("process") or raw.process
        raw.varietal = fields.get("varietal") or varietal or raw.varietal
        raw.producer = producer or raw.producer

        return raw
