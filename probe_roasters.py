"""Probe each roaster URL: does products.json work? Is there a Behind-the-Bean-style
metadata block on the product page that needs a custom scraper?"""
from __future__ import annotations

import re
import sys

import httpx

from app.scrapers.registry import SEEDS

UA = {"User-Agent": "CoffeeCompareBot/0.1"}
TIMEOUT = 15.0

# Patterns that signal "structured metadata is in the page HTML, not body_html"
META_HINTS = (
    re.compile(r'class="meta-\w+"', re.I),
    re.compile(r"behind the bean", re.I),
    re.compile(r"<h3>\s*(producer|varietal|process|farm|origin)\s*:", re.I),
    re.compile(r'data-coffee-(producer|varietal|process|farm|origin)', re.I),
)


def probe(slug: str, cls: type) -> dict:
    base = cls.base_url.rstrip("/")
    out = {"slug": slug, "name": cls.name, "base_url": base}
    with httpx.Client(headers=UA, timeout=TIMEOUT, follow_redirects=True) as c:
        try:
            r = c.get(f"{base}/products.json?limit=5")
            out["status"] = r.status_code
            if r.status_code != 200:
                out["note"] = "products.json failed (probably not Shopify)"
                return out
            data = r.json()
            products = data.get("products", [])
            out["products_seen"] = len(products)
            if not products:
                out["note"] = "Shopify but no products on page 1"
                return out
            # Pick first product, fetch its page, sniff for metadata block
            handle = products[0].get("handle")
            body_html = products[0].get("body_html") or ""
            out["body_html_len"] = len(body_html)
            out["body_has_labels"] = bool(
                re.search(r"\b(producer|varietal|process)\s*:", body_html, re.I)
            )
            try:
                pr = c.get(f"{base}/products/{handle}")
                page = pr.text
                hints = [p.pattern for p in META_HINTS if p.search(page)]
                out["page_meta_hints"] = hints[:3]
            except Exception as e:
                out["page_err"] = str(e)[:80]
        except Exception as e:
            out["err"] = type(e).__name__ + ": " + str(e)[:120]
    return out


def main() -> int:
    print(f"Probing {len(SEEDS)} roasters...\n")
    rows = []
    for slug, cls in SEEDS.items():
        r = probe(slug, cls)
        rows.append(r)
        # Compact one-line status
        if r.get("err"):
            verdict = f"ERR  {r['err']}"
        elif r.get("status") != 200:
            verdict = f"FAIL {r.get('status')} — {r.get('note', '')}"
        else:
            n = r.get("products_seen", 0)
            body = "body+labels" if r.get("body_has_labels") else f"body={r.get('body_html_len', 0)}b"
            page = "+page-meta" if r.get("page_meta_hints") else ""
            verdict = f"OK   shopify  {n} products  {body}  {page}"
        print(f"  {slug:18s} {verdict}")
    print()
    # Summary buckets
    ok = [r for r in rows if r.get("status") == 200 and r.get("products_seen", 0) > 0]
    fail = [r for r in rows if r not in ok]
    print(f"Working: {len(ok)}/{len(rows)}")
    print(f"Failed:  {len(fail)}/{len(rows)}")
    print()
    print("Roasters with structured page metadata (need custom scraper for full fields):")
    for r in ok:
        if r.get("page_meta_hints"):
            print(f"  - {r['slug']}: {r['page_meta_hints']}")
    print()
    print("Roasters where body_html already has labels (regex extractor will work):")
    for r in ok:
        if r.get("body_has_labels"):
            print(f"  - {r['slug']}")
    print()
    print("Roasters with thin/empty body_html and no page metadata (LLM or custom needed):")
    for r in ok:
        if not r.get("body_has_labels") and not r.get("page_meta_hints"):
            print(f"  - {r['slug']}: body_html={r.get('body_html_len', 0)}b")
    return 0


if __name__ == "__main__":
    sys.exit(main())
