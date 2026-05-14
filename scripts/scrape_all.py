"""CLI: scrape every active roaster in the registry.

Usage:
    python -m scripts.scrape_all              # all roasters, with LLM fallback
    python -m scripts.scrape_all --no-llm     # skip LLM (free, lower quality)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from app.scrapers.registry import all_slugs
from scripts.run import run_one

log = logging.getLogger("scrape_all")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM fallback")
    parser.add_argument("--only", nargs="*", help="Only run these slugs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    targets = args.only or all_slugs()
    log.info("Scraping %d roasters: %s", len(targets), ", ".join(targets))

    overall = {"new": 0, "updated": 0, "errors": 0, "seen": 0}
    started = time.time()
    for slug in targets:
        try:
            s = run_one(slug, use_llm=not args.no_llm)
            log.info("[%s] done: seen=%d new=%d updated=%d errors=%d",
                     slug, s["seen"], s["new"], s["updated"], s["errors"])
            for k in overall:
                overall[k] += s.get(k, 0)
        except Exception as e:  # noqa: BLE001
            log.exception("[%s] catastrophic: %s", slug, e)
            overall["errors"] += 1

    log.info(
        "All done in %.1fs — total seen=%d new=%d updated=%d errors=%d",
        time.time() - started, overall["seen"], overall["new"], overall["updated"], overall["errors"],
    )
    return 0 if overall["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
