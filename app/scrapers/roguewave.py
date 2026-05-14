"""Rogue Wave (Canada) scraper.

Pattern on product page: <p><span>{Label}</span>{Value}</p>
Labels seen: Origin, Region, Farms, Owner, Harvest, Elevation.

We treat:
  Owner -> producer  (Rogue Wave uses "Owner" for the farm/producer entity)
  Farms -> farm
  Origin -> country
  Region -> region
"""
from __future__ import annotations

import logging
import re

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

_LABEL_RE = re.compile(
    r"<p[^>]*>\s*<span[^>]*>\s*([^<]+?)\s*</span>\s*([^<]+?)\s*</p>",
    re.DOTALL | re.IGNORECASE,
)

_LABEL_TO_FIELD = {
    "producer": "producer",
    "owner": "producer",
    "farm": "farm",
    "farms": "farm",
    "origin": "country",
    "country": "country",
    "region": "region",
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
        value = m.group(2).strip()
        value = re.sub(r"\s+", " ", value)
        if value and len(value) < 200:
            out[field] = value
    return out


class RogueWaveScraper(ShopifyScraper):
    slug = "rogue_wave"
    name = "Rogue Wave"
    base_url = "https://roguewavecoffee.ca"

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None
        try:
            html = self.get(f"/products/{ref.handle}").text
        except Exception as exc:
            log.warning("[rogue_wave] page fetch failed for %s: %s", ref.url, exc)
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
