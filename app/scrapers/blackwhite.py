"""Black & White Roasters scraper.

Shopify-based.  Structured fields live on the rendered product page in
<p><strong>Label |</strong> Value</p> blocks (NOT in body_html, which only
has the prose story).  We fetch the product page and parse those blocks.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

# Match: <strong>Producer |</strong> Nestor Lasso</p>
# The label is anything up to the pipe; the value is everything to </p>.
_LABEL_RE = re.compile(
    r"<strong>([^<|]+?)\s*\|</strong>(.*?)</p>",
    re.DOTALL | re.IGNORECASE,
)

_LABEL_TO_FIELD = {
    "producer": "producer",
    "farm": "farm",
    "origin": "country",
    "country": "country",
    "region": "region",
    "process": "process",
    "varietal": "varietal",
    "variety": "varietal",
}


def _parse_page(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _LABEL_RE.finditer(html):
        label = m.group(1).strip().lower()
        field = _LABEL_TO_FIELD.get(label)
        if not field or field in out:
            continue
        value = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        value = re.sub(r"\s+", " ", value)
        # B&W has prose paragraphs starting with phrases like "MEET THE PRODUCER"
        # — those slip past the label match if we're not picky. Cap length.
        if value and len(value) < 100:
            out[field] = value
    return out


class BlackWhiteScraper(ShopifyScraper):
    slug = "bw"
    name = "Black & White"
    base_url = "https://www.blackwhiteroasters.com"

    # B&W uses product_type to bucket their catalog cleanly. Anything outside
    # these is merch, drinkware, equipment, instant coffee, subscriptions, etc.
    _COFFEE_TYPES = frozenset({
        "Retail SO",       # single-origin retail
        "Retail YR",       # year-round retail (decafs, blends — still real coffee)
        "Wholesale SO",
        "Wholesale YR",
    })

    def is_coffee(self, product: dict[str, Any]) -> bool:
        return product.get("product_type", "") in self._COFFEE_TYPES

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None

        try:
            resp = self.get(f"/products/{ref.handle}")
            fields = _parse_page(resp.text)
        except Exception as exc:
            log.warning("[bw] page fetch failed for %s: %s", ref.url, exc)
            return raw

        # If the page exposes no structured coffee fields at all, treat it as
        # not-a-coffee and skip it. (Catches the few non-coffee items that
        # squeak through the product_type filter — e.g. blends with no producer.)
        if not fields:
            return None

        # "country" may carry a "Region, Country" string — split if so
        country = fields.get("country")
        if country and "," in country and not fields.get("region"):
            parts = [p.strip() for p in country.split(",", 1)]
            raw.region = parts[0]
            raw.country = parts[1]
        elif country:
            raw.country = country

        raw.region = raw.region or fields.get("region")
        raw.varietal = fields.get("varietal")
        raw.process = fields.get("process")
        raw.producer = fields.get("producer")
        raw.farm = fields.get("farm")

        return raw
