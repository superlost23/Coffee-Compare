"""Assembly Coffee (UK) scraper.

Pattern on product page:
  <div class="product-summary-item" data-key="producer">
    <span>Producer</span>
    <span>Carmen Estate</span>
  </div>

We extract via the data-key attribute and grab the last non-empty text segment
inside the div (the value).
"""
from __future__ import annotations

import logging
import re

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

_BLOCK_RE = re.compile(
    r'<div\s+class="product-summary-item"\s+data-key="([^"]+)"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)

_KEY_TO_FIELD = {
    "producer": "producer",
    "farm": "farm",
    "region": "region",
    "country": "country",
    "origin": "country",
    "variety": "varietal",
    "varietal": "varietal",
    "process": "process",
}


def _parse(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _BLOCK_RE.finditer(html):
        key = m.group(1).strip().lower()
        field = _KEY_TO_FIELD.get(key)
        if not field or field in out:
            continue
        inner = m.group(2)
        # Pull every text segment, drop the label, keep the value
        segments = [s.strip() for s in re.split(r"<[^>]+>", inner) if s.strip()]
        if not segments:
            continue
        # Label is usually the first segment (capitalized version of key); value is the rest joined
        if len(segments) >= 2 and segments[0].lower().startswith(key[:5]):
            value = " ".join(segments[1:])
        else:
            value = " ".join(segments)
        value = re.sub(r"\s+", " ", value).strip()
        if value and len(value) < 200:
            out[field] = value
    return out


class AssemblyScraper(ShopifyScraper):
    slug = "assembly"
    name = "Assembly"
    base_url = "https://assemblycoffee.co.uk"

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None
        try:
            html = self.get(f"/products/{ref.handle}").text
        except Exception as exc:
            log.warning("[assembly] page fetch failed for %s: %s", ref.url, exc)
            return raw
        fields = _parse(html)
        if fields:
            # If region looks like "Volcán Barú, Boquete" we might want to split,
            # but Assembly already provides country separately when it has one.
            raw.producer = fields.get("producer") or raw.producer
            raw.farm = fields.get("farm") or raw.farm
            raw.country = fields.get("country") or raw.country
            raw.region = fields.get("region") or raw.region
            raw.varietal = fields.get("varietal") or raw.varietal
            raw.process = fields.get("process") or raw.process
        return raw
