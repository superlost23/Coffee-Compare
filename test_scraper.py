"""Standalone scraper smoke-test — no DB or Meilisearch required.

Usage (from the coffee_compare/coffee_compare/ directory):
    python test_scraper.py superlost [--max 5]
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape a roaster without needing the DB.")
    parser.add_argument("slug", nargs="?", default="superlost")
    parser.add_argument("--max", type=int, default=5, help="Max products to parse (default 5)")
    args = parser.parse_args()

    # Late import so logging is configured first
    from app.extraction import ExtractedFields, extract
    from app.scrapers.registry import get as get_scraper

    cls = get_scraper(args.slug)
    if cls is None:
        log.error("No scraper registered for slug=%r", args.slug)
        return 1

    log.info("Testing scraper: %s (%s)", cls.name, cls.base_url)

    errors = 0
    with cls() as scraper:  # type: ignore[abstract]
        # --- 1. List products -----------------------------------------------
        log.info("Fetching product list …")
        try:
            refs = scraper.list_products()
        except Exception as exc:
            log.exception("list_products() failed: %s", exc)
            return 1

        log.info("Found %d products", len(refs))
        if not refs:
            log.warning("No products returned — check is_coffee() filter or site URL")
            return 1

        # --- 2. Parse first N products --------------------------------------
        sample = refs[: args.max]
        log.info("Parsing first %d …", len(sample))
        for i, ref in enumerate(sample, 1):
            log.info("  [%d/%d] %s", i, len(sample), ref.url)
            try:
                raw = scraper.parse_product(ref)
            except Exception as exc:
                log.error("    parse_product() raised: %s", exc)
                errors += 1
                continue

            if raw is None:
                log.warning("    → skipped (parse_product returned None)")
                continue

            # --- 3. Field extraction (mirror run.py logic; no LLM) ----------
            pre = ExtractedFields(
                producer=raw.producer,
                farm=raw.farm,
                country=raw.country,
                region=raw.region,
                varietal=raw.varietal,
                process=raw.process,
                method="prefilled" if any((raw.producer, raw.varietal, raw.process)) else "none",
                confidence=0.9 if any((raw.producer, raw.varietal)) else 0.0,
            )
            fields = extract(raw.description_html, prefilled=pre, use_llm=False)

            # --- 4. Pretty-print result -------------------------------------
            print()
            print("-" * 60)
            print(f"  Title   : {raw.title}")
            print(f"  URL     : {raw.url}")
            print(f"  Variants: {len(raw.variants)}")
            for v in raw.variants:
                price_str = f"${v.price_cents / 100:.2f}" if v.price_cents else "?"
                stock_str = "in-stock" if v.available else "OOS"
                grams_str = f"{v.grams:.0f}g" if v.grams else "?g"
                print(f"    - {v.title:25s}  {grams_str:8s}  {price_str:8s}  [{stock_str}]")
            print(f"  --- Extracted fields ({fields.method}, conf={fields.confidence}) ---")
            print(f"  Producer : {fields.producer or '(none)'}")
            print(f"  Farm     : {fields.farm or '(none)'}")
            print(f"  Country  : {fields.country or '(none)'}")
            print(f"  Region   : {fields.region or '(none)'}")
            print(f"  Varietal : {fields.varietal or '(none)'}")
            print(f"  Process  : {fields.process or '(none)'}")

    print()
    print(f"Done. Errors: {errors}/{len(sample)}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
