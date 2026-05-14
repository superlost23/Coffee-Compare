"""Superlost scraper.

Superlost runs on Shopify, so we inherit the generic list/variant logic from
ShopifyScraper.  The only customisation is parse_product: the structured
coffee metadata (origin, varietal, process, producer, farm) lives in a
"Behind the Bean" section rendered via Shopify metafields on the product page
— it is NOT in the products.json body_html.  We fetch the product page HTML
and parse the <div class="meta-*"> blocks.
"""
from __future__ import annotations

import logging
import re

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

# Matches: <div class="meta-origin"> ... <h3>Origin:</h3> ... <h4>Cauca, Colombia</h4>
_META_RE = re.compile(
    r'<div\s+class="(meta-[\w]+)"[^>]*>.*?<h3>[^<]*</h3>\s*<h4>(.*?)</h4>',
    re.DOTALL | re.IGNORECASE,
)

_CLASS_TO_FIELD = {
    "meta-origin": "origin",
    "meta-varietal": "varietal",
    "meta-process": "process",
    "meta-producer": "producer",
    "meta-farm_name": "farm",
}


def _parse_behind_the_bean(html: str) -> dict[str, str]:
    """Return field-name → value dict for the Behind the Bean section."""
    out: dict[str, str] = {}
    for m in _META_RE.finditer(html):
        css_class = m.group(1).lower()
        field = _CLASS_TO_FIELD.get(css_class)
        if not field:
            continue
        value = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if value:
            out[field] = value
    return out


class SuperlostScraper(ShopifyScraper):
    slug = "superlost"
    name = "Superlost"
    base_url = "https://www.superlost.com"

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None

        # Fetch the rendered product page for the Behind the Bean metadata.
        try:
            resp = self.get(f"/products/{ref.handle}")
            fields = _parse_behind_the_bean(resp.text)
        except Exception as exc:
            log.warning("[superlost] page fetch failed for %s: %s", ref.url, exc)
            return raw  # return what we have from products.json

        if not fields:
            return raw

        # "origin" may be "Region, Country" — split it
        origin = fields.pop("origin", None)
        if origin and "," in origin:
            parts = [p.strip() for p in origin.split(",", 1)]
            raw.region = parts[0]
            raw.country = parts[1]
        elif origin:
            raw.country = origin

        raw.varietal = fields.get("varietal")
        raw.process = fields.get("process")
        raw.producer = fields.get("producer")
        raw.farm = fields.get("farm")

        return raw
