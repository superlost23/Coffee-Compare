"""Reusable scraper for the `<strong>Label |</strong> value</p>` pattern.

Many specialty Shopify roasters render coffee metadata as paragraphs:
    <p><strong>Producer |</strong> Nestor Lasso</p>
    <p><strong>Process |</strong> Thermal Shock Natural</p>

or the colon variant:
    <p><strong>Producer:</strong> Nestor Lasso</p>

This class subclasses ShopifyScraper, fetches the rendered product page, and
parses any of the above. Subclasses only need to set slug / name / base_url.

Confirmed working for: bw, devocion, the_barn, drop_coffee, bonanza, april
(probed Nov 2025). Pattern handles both pipe and colon separators.
"""
from __future__ import annotations

import logging
import re

from app.scrapers.base import ProductRef, RawOffering
from app.scrapers.shopify import ShopifyScraper

log = logging.getLogger(__name__)

# Capture either "<strong>Label |</strong> value</p>" or "<strong>Label:</strong> value</p>"
_LABEL_RE = re.compile(
    r"<strong>\s*([A-Za-z][\w &]*?)\s*[:|]\s*</strong>(.*?)</p>",
    re.DOTALL | re.IGNORECASE,
)

_LABEL_TO_FIELD = {
    "producer": "producer",
    "farm": "farm",
    "farm name": "farm",
    "estate": "farm",
    "origin": "country",
    "country": "country",
    "region": "region",
    "process": "process",
    "processing": "process",
    "method": "process",
    "varietal": "varietal",
    "variety": "varietal",
    "cultivar": "varietal",
    "varieties": "varietal",
}


def parse_labeled_strong(html: str) -> dict[str, str]:
    """Extract coffee metadata from a labeled-<strong> product page."""
    out: dict[str, str] = {}
    for m in _LABEL_RE.finditer(html):
        label = m.group(1).strip().lower()
        field = _LABEL_TO_FIELD.get(label)
        if not field or field in out:
            continue
        value = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        value = re.sub(r"\s+", " ", value)
        # Drop prose paragraphs (sometimes "Producer:" precedes a story, not a name)
        if value and 1 <= len(value) <= 100:
            out[field] = value
    return out


class LabeledStrongScraper(ShopifyScraper):
    """Generic scraper for Shopify roasters using <strong>Label |</strong>value."""

    # Override these per-roaster:
    slug: str = "override-me"
    name: str = "Override me"
    base_url: str = "https://example.com"

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        raw = super().parse_product(ref)
        if raw is None:
            return None
        try:
            resp = self.get(f"/products/{ref.handle}")
            fields = parse_labeled_strong(resp.text)
        except Exception as exc:
            log.warning("[%s] page fetch failed for %s: %s", self.slug, ref.url, exc)
            return raw
        if not fields:
            return raw  # keep title+price even if no metadata found

        country = fields.get("country")
        if country and "," in country and not fields.get("region"):
            parts = [p.strip() for p in country.split(",", 1)]
            raw.region = parts[0]
            raw.country = parts[1]
        elif country:
            raw.country = country

        raw.region = fields.get("region") or raw.region
        raw.producer = fields.get("producer") or raw.producer
        raw.farm = fields.get("farm") or raw.farm
        raw.varietal = fields.get("varietal") or raw.varietal
        raw.process = fields.get("process") or raw.process
        return raw


def make(slug: str, name: str, base_url: str) -> type[LabeledStrongScraper]:
    """Dynamically build a LabeledStrongScraper subclass with the given identity."""
    return type(
        f"LabeledStrong_{slug}",
        (LabeledStrongScraper,),
        {"slug": slug, "name": name, "base_url": base_url},
    )
