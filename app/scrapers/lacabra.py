"""La Cabra scraper.

Pattern on the product page: <p><strong>{Label}</strong> {Value}</p>
Labels seen: Producer, Region, Altitude, Varietal, Process, Harvest.

Note "Producer" here often contains a *paragraph* of prose ("Produced by three
brothers; Jose, Miguel and Jesus Burbano…") not just a name. We accept it
anyway — it's still useful for matching, though we cap the length.
"""
from __future__ import annotations

import logging
import re

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

_LABEL_RE = re.compile(
    r"<p[^>]*>\s*<strong>\s*([^<]+?)\s*</strong>\s*(.+?)\s*</p>",
    re.DOTALL | re.IGNORECASE,
)

_LABEL_TO_FIELD = {
    "producer": "producer",
    "farm": "farm",
    "region": "region",
    "country": "country",
    "origin": "country",
    "varietal": "varietal",
    "variety": "varietal",
    "process": "process",
}


def _parse(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _LABEL_RE.finditer(html):
        label = m.group(1).strip().rstrip(":").lower()
        field = _LABEL_TO_FIELD.get(label)
        if not field or field in out:
            continue
        value = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        value = re.sub(r"\s+", " ", value)
        if not value:
            continue
        # Producer often contains a whole sentence ("Produced by three brothers…").
        # Truncate aggressively if it's prose-length.
        if len(value) > 80 and field == "producer":
            # Take the first proper-noun-y phrase before a comma or period
            first = re.split(r"[.,;]", value, 1)[0].strip()
            value = first if 3 <= len(first) <= 80 else value[:80]
        if len(value) < 200:
            out[field] = value
    return out


class LaCabraScraper(ShopifyScraper):
    slug = "la_cabra"
    name = "La Cabra"
    base_url = "https://lacabra.dk"

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None
        try:
            html = self.get(f"/products/{ref.handle}").text
        except Exception as exc:
            log.warning("[la_cabra] page fetch failed for %s: %s", ref.url, exc)
            return raw
        fields = _parse(html)
        if fields:
            raw.producer = fields.get("producer") or raw.producer
            raw.farm = fields.get("farm") or raw.farm
            raw.country = fields.get("country") or raw.country
            raw.region = fields.get("region") or raw.region
            raw.varietal = fields.get("varietal") or raw.varietal
            raw.process = fields.get("process") or raw.process
        return raw
