"""Generic Shopify scraper.

Most specialty roasters run on Shopify and expose two convenient endpoints:
  /products.json?limit=250&page=N  → paginated product list with all metadata
  /products/{handle}.js            → single product as JSON

Subclasses can override:
  - is_coffee(product_dict)              # filter merch, subscriptions, etc.
  - parse_size(variant_title)            # site-specific size labels
  - extra_fields_from_body(body_html)    # if site has unique prose conventions
"""
from __future__ import annotations

import logging
from typing import Any

from app.pricing import parse_size
from app.scrapers.base import BaseRoasterScraper, ProductRef, RawOffering, RawVariant

log = logging.getLogger(__name__)

NON_COFFEE_KEYWORDS = (
    "subscription",
    "gift card",
    "gift-card",
    "merch",
    "tote",
    "t-shirt",
    "tshirt",
    "mug",
    "hat",
    "sticker",
    "book",
    "equipment",
    "filter",
    "grinder",
    "kettle",
    "scale",
    "dripper",
)


class ShopifyScraper(BaseRoasterScraper):
    """Default behavior. Override `slug`, `name`, `base_url` per roaster."""

    products_per_page: int = 250
    max_pages: int = 20  # safety: stop after this many empty pages

    def list_products(self) -> list[ProductRef]:
        refs: list[ProductRef] = []
        for page in range(1, self.max_pages + 1):
            try:
                resp = self.get(f"/products.json?limit={self.products_per_page}&page={page}")
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] products.json page %d failed: %s", self.slug, page, e)
                break
            data = resp.json()
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                if not self.is_coffee(p):
                    continue
                handle = p.get("handle")
                refs.append(
                    ProductRef(
                        url=f"{self.base_url.rstrip('/')}/products/{handle}",
                        handle=handle,
                        raw=p,
                    )
                )
            if len(products) < self.products_per_page:
                break
        return refs

    def is_coffee(self, product: dict[str, Any]) -> bool:
        """Filter out merch/subscriptions. Override for tighter rules."""
        title = (product.get("title") or "").lower()
        ptype = (product.get("product_type") or "").lower()
        tags = " ".join(product.get("tags", []) if isinstance(product.get("tags"), list) else [product.get("tags") or ""]).lower()
        haystack = f"{title} {ptype} {tags}"
        return not any(kw in haystack for kw in NON_COFFEE_KEYWORDS)

    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        # /products.json already gave us most of what we need
        p = ref.raw or {}
        if not p:
            try:
                resp = self.get(f"/products/{ref.handle}.js")
                p = resp.json()
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] product fetch failed for %s: %s", self.slug, ref.url, e)
                return None

        variants_raw = p.get("variants", [])
        variants: list[RawVariant] = []
        for v in variants_raw:
            title = v.get("title") or v.get("option1") or ""
            price = v.get("price")
            # Shopify prices are sometimes strings ("19.00") and sometimes ints (1900 cents)
            price_cents = self._coerce_price_cents(price)
            available = bool(v.get("available", True))
            sz = parse_size(title)
            variants.append(
                RawVariant(
                    title=title,
                    price_cents=price_cents,
                    available=available,
                    grams=sz.grams if sz else None,
                )
            )
        if not variants:
            return None

        body_html = p.get("body_html") or ""

        return RawOffering(
            url=ref.url,
            title=p.get("title") or "Untitled",
            description_html=body_html,
            variants=variants,
        )

    @staticmethod
    def _coerce_price_cents(price: Any) -> int | None:
        if price is None:
            return None
        if isinstance(price, int):
            # Could be cents (1900) or whole-units (19) — heuristic: > 1000 → cents
            return price if price >= 1000 else price * 100
        if isinstance(price, (float,)):
            return int(round(price * 100))
        if isinstance(price, str):
            try:
                # Shopify product.json gives "19.00" — dollars
                return int(round(float(price) * 100))
            except ValueError:
                return None
        return None
