"""Deep-probe each known-working Shopify roaster.

For each, sample 3 coffee products and check:
  - Does body_html contain Producer:/Varietal:/Process: labels? (generic scraper works)
  - Does the product PAGE have a structured metadata block? (need custom scraper)
  - If neither, the data is in prose and we need LLM extraction.
"""
from __future__ import annotations

import re
import sys

import httpx

UA = {"User-Agent": "CoffeeCompareBot/0.1"}
TIMEOUT = 15.0

# (slug, base_url) — all known-working Shopify roasters
ROASTERS: dict[str, str] = {
    "sey":            "https://www.seycoffee.com",
    "onyx":           "https://onyxcoffeelab.com",
    "la_cabra":       "https://lacabra.dk",
    "george_howell":  "https://georgehowellcoffee.com",
    "rogue_wave":     "https://roguewavecoffee.ca",
    "nomad":          "https://www.nomadcoffee.es",
    "broadsheets":    "https://broadsheetcoffee.com",
    "cartel":         "https://cartelcoffeelab.com",
    "tandem":         "https://www.tandemcoffee.com",
    "yellowbrick":    "https://yellowbrickcoffee.com",
    "perc":           "https://perccoffee.com",
    "assembly":       "https://assemblycoffee.co.uk",
    "hs":             "https://hsroasters.com",
    "brandywine":     "https://www.brandywinecoffeeroasters.com",
}

# Patterns to look for in product page HTML
PATTERNS = {
    "strong_pipe":   re.compile(r"<strong>\s*(producer|farm|varietal|variety|process|origin|region)\s*[:|]", re.I),
    "strong_colon":  re.compile(r"<strong>\s*(producer|farm|varietal|variety|process|origin|region)\s*:?\s*</strong>", re.I),
    "meta_div":      re.compile(r'class="meta[-_]\w+', re.I),
    "h3_label":      re.compile(r"<h[3-6][^>]*>\s*(producer|farm|varietal|variety|process|origin|region)\s*:", re.I),
    "dt_label":      re.compile(r"<dt[^>]*>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "td_label":      re.compile(r"<td[^>]*>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "data_attr":     re.compile(r'data-coffee-(producer|farm|varietal|variety|process|origin|region)', re.I),
    "label_class":   re.compile(r'class="[^"]*\b(producer|farm|varietal|variety|process|origin|region)\b', re.I),
    "li_strong":     re.compile(r"<li[^>]*>\s*<strong>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "p_strong":      re.compile(r"<p[^>]*>\s*<strong>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
}

BODY_LABEL = re.compile(r"\b(producer|farm|varietal|variety|process|origin|region)\s*[:|]", re.I)

# Words that suggest a product is actually coffee (skip merch/equipment/etc.)
COFFEE_HINT = re.compile(r"(washed|natural|honey|anaerobic|coffee|colombia|ethiopia|kenya|brazil|guatemala|costa rica|el salvador|huila|cauca|sidamo)", re.I)


def is_real_coffee(p: dict) -> bool:
    title = p.get("title", "").lower()
    ptype = p.get("product_type", "").lower()
    blob = f"{title} {ptype}"
    bad = ("shirt", "tee", "mug", "hat", "sticker", "book", "equipment", "grinder", "kettle",
           "scale", "dripper", "subscription", "gift card", "tote", "merch", "mailer",
           "instant", "drinkware", "apparel", "accessor")
    if any(b in blob for b in bad):
        return False
    # If body_html or title mentions coffee origin words, it's probably coffee
    body = (p.get("body_html") or "")[:2000]
    return bool(COFFEE_HINT.search(title + " " + body))


def probe(slug: str, base_url: str) -> dict:
    with httpx.Client(headers=UA, timeout=TIMEOUT, follow_redirects=True, verify=False) as c:
        try:
            r = c.get(f"{base_url.rstrip('/')}/products.json?limit=50")
            products = r.json().get("products", [])
        except Exception as e:
            return {"slug": slug, "error": str(e)[:80]}

        coffees = [p for p in products if is_real_coffee(p)]
        if not coffees:
            return {"slug": slug, "total_products": len(products), "coffees": 0}

        # Sample up to 3 coffees, fetch their pages
        body_label_hits = 0
        body_lens = []
        pattern_hits: dict[str, set[str]] = {k: set() for k in PATTERNS}
        for p in coffees[:3]:
            body = p.get("body_html") or ""
            body_lens.append(len(body))
            if BODY_LABEL.search(body):
                body_label_hits += 1
            try:
                page = c.get(f"{base_url.rstrip('/')}/products/{p['handle']}").text
            except Exception:
                continue
            for name, rx in PATTERNS.items():
                for m in rx.finditer(page):
                    pattern_hits[name].add(m.group(1).lower())

        # Verdict
        good_patterns = {k: sorted(v) for k, v in pattern_hits.items() if v}
        return {
            "slug": slug,
            "base_url": base_url,
            "total_products": len(products),
            "coffees": len(coffees),
            "body_label_hits": body_label_hits,
            "body_len_avg": sum(body_lens) // max(len(body_lens), 1),
            "patterns": good_patterns,
        }


def main() -> int:
    results = []
    for slug, url in ROASTERS.items():
        print(f"Probing {slug} ({url}) …", file=sys.stderr)
        results.append(probe(slug, url))

    print()
    print(f"{'slug':14s} {'#prods':>6s} {'#coffees':>8s} {'body-labels':>11s} {'body-len':>8s}  pattern hits")
    print("-" * 110)
    for r in results:
        if "error" in r:
            print(f"{r['slug']:14s} ERROR: {r['error']}")
            continue
        pat = r.get("patterns", {})
        # Find best pattern (one with most fields detected)
        if pat:
            best_name, best_fields = max(pat.items(), key=lambda kv: len(kv[1]))
            pat_summary = f"{best_name}={best_fields}"
        else:
            pat_summary = "(none)"
        print(
            f"{r['slug']:14s} {r.get('total_products',0):6d} {r.get('coffees',0):8d} "
            f"{r.get('body_label_hits',0):11d} {r.get('body_len_avg',0):8d}  {pat_summary}"
        )

    print()
    print("Buckets:")
    body_ok = [r for r in results if r.get("body_label_hits", 0) >= 2]
    page_meta = [r for r in results if r.get("patterns") and r not in body_ok]
    thin = [r for r in results if not r.get("body_label_hits") and not r.get("patterns") and "error" not in r]
    print(f"  Generic scraper works (body_html has labels): {[r['slug'] for r in body_ok]}")
    print(f"  Needs custom page-HTML scraper:               {[r['slug'] for r in page_meta]}")
    print(f"  Thin / needs LLM:                             {[r['slug'] for r in thin]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
