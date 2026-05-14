"""Pull the actual HTML around each detected label pattern so we can write
exact regexes for the per-roaster scrapers."""
from __future__ import annotations

import re
import sys

import httpx

UA = {"User-Agent": "CoffeeCompareBot/0.1"}

TARGETS = {
    "la_cabra":     ("https://lacabra.dk",                           ["producer", "region", "varietal", "process"]),
    "broadsheets":  ("https://broadsheetcoffee.com",                 ["producer", "origin", "process", "varietal"]),
    "assembly":     ("https://assemblycoffee.co.uk",                 ["producer", "region", "variety", "process"]),
    "onyx":         ("https://onyxcoffeelab.com",                    ["farm", "process", "producer", "varietal", "origin", "region"]),
    "george_howell":("https://georgehowellcoffee.com",               ["farm", "producer", "varietal", "process", "origin"]),
    "rogue_wave":   ("https://roguewavecoffee.ca",                   ["farm", "producer", "varietal", "process", "origin"]),
    "yellowbrick":  ("https://yellowbrickcoffee.com",                ["region", "producer", "varietal", "process"]),
}

COFFEE_HINT = re.compile(r"(washed|natural|honey|anaerobic|colombia|ethiopia|kenya|brazil|guatemala|costa rica|el salvador|huila|cauca|sidamo)", re.I)


def is_coffee(p): return COFFEE_HINT.search((p.get("title","") + " " + ((p.get("body_html") or "")[:1000])))


def main() -> int:
    with httpx.Client(headers=UA, timeout=15.0, follow_redirects=True, verify=False) as c:
        for slug, (base, labels) in TARGETS.items():
            print(f"\n{'='*70}\n{slug.upper()}  ({base})\n{'='*70}")
            try:
                products = c.get(f"{base}/products.json?limit=50").json().get("products", [])
            except Exception as e:
                print(f"  ERROR: {e}")
                continue
            coffees = [p for p in products if is_coffee(p)]
            if not coffees:
                print("  no coffees found")
                continue
            sample = coffees[0]
            print(f"  Sample: {sample.get('title')!r}")
            page = c.get(f"{base}/products/{sample['handle']}").text
            # For each requested label, grab 200 chars of context around the FIRST occurrence
            for label in labels:
                m = re.search(rf"(?i)(.{{0,80}}\b{label}\b.{{0,200}})", page)
                if m:
                    s = m.group(1).replace("\n", " ").strip()
                    s = re.sub(r"\s+", " ", s)
                    print(f"  [{label}]  …{s[:280]}…")
                else:
                    print(f"  [{label}]  (not in page HTML)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
