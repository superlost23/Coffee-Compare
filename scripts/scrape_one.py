"""CLI: scrape a single roaster (debugging / one-off updates).

Usage:
    python -m scripts.scrape_one superlost
    python -m scripts.scrape_one superlost --no-llm
"""
from __future__ import annotations

import argparse
import logging
import sys

from scripts.run import run_one


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    s = run_one(args.slug, use_llm=not args.no_llm)
    print(s)
    return 0 if s["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
