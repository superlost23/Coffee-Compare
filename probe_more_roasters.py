"""Probe ~30 additional top specialty coffee roasters for Shopify-ness +
structured metadata patterns."""
from __future__ import annotations

import re
import sys

import httpx

UA = {"User-Agent": "CoffeeCompareBot/0.1"}
TIMEOUT = 12.0

# Top specialty roasters not in our current registry.
# Mix of US, UK, EU, Canada, Australia.
CANDIDATES: dict[str, list[str]] = {
    # --- US ---
    "heart":          ["https://www.heartroasters.com", "https://heartcoffee.com"],
    "stumptown":      ["https://www.stumptowncoffee.com"],
    "counterculture": ["https://counterculturecoffee.com"],
    "coava":          ["https://coavacoffee.com"],
    "verve":          ["https://www.vervecoffee.com"],
    "sightglass":     ["https://sightglasscoffee.com"],
    "ritual":         ["https://www.ritualcoffee.com"],
    "madcap":         ["https://madcapcoffee.com"],
    "klatch":         ["https://klatchroasting.com"],
    "equator":        ["https://www.equatorcoffees.com"],
    "devocion":       ["https://devocion.com"],
    "joe_coffee":     ["https://www.joecoffeecompany.com"],
    "blue_bottle":    ["https://bluebottlecoffee.com"],
    "intelligentsia": ["https://www.intelligentsia.com", "https://intelligentsiacoffee.com"],
    "bird_rock":      ["https://birdrockcoffee.com"],
    "ruby":           ["https://rubycoffeeroasters.com"],
    "metric":         ["https://metriccoffee.com"],
    # --- UK ---
    "workshop":       ["https://workshopcoffee.com"],
    "square_mile":    ["https://shop.squaremilecoffee.com", "https://squaremilecoffee.com"],
    "origin_uk":      ["https://www.origincoffee.co.uk"],
    "round_hill":     ["https://www.roundhillroastery.com"],
    "kiss_the_hippo": ["https://kissthehippo.com"],
    # --- EU ---
    "april":          ["https://aprilcoffeeroasters.com"],
    "friedhats":      ["https://friedhats.com"],
    "the_barn":       ["https://www.thebarn.de"],
    "coffee_collective": ["https://coffeecollective.dk"],
    "manhattan_coffee": ["https://www.manhattancoffeeroasters.com"],
    "drop_coffee":    ["https://www.dropcoffee.com"],
    "tim_wendelboe":  ["https://www.timwendelboe.no"],
    "five_elephant":  ["https://fiveelephant.com"],
    "bonanza":        ["https://bonanzacoffee.de", "https://www.bonanzacoffee.de"],
    "passenger":      ["https://passengercoffee.com"],
    # --- Canada / AU ---
    "phil_sebastian": ["https://philsebastian.com"],
    "fortyninth":     ["https://49thcoffee.com"],
    "pilot":          ["https://pilotcoffeeroasters.com"],
    "proud_mary":     ["https://proudmarycoffee.com"],
    "market_lane":    ["https://marketlane.com.au"],
    "small_batch":    ["https://smallbatchroasting.com.au"],
}

COFFEE_HINT = re.compile(r"(washed|natural|honey|anaerobic|colombia|ethiopia|kenya|brazil|guatemala|costa rica|el salvador|huila|cauca|sidamo|panama|peru|gesha|geisha)", re.I)

PATTERNS = {
    "strong_pipe":   re.compile(r"<strong>\s*(producer|farm|varietal|variety|process|origin|region)\s*[:|]", re.I),
    "strong_colon":  re.compile(r"<strong>\s*(producer|farm|varietal|variety|process|origin|region)\s*:?\s*</strong>", re.I),
    "meta_div":      re.compile(r'class="meta[-_]\w+', re.I),
    "h3_label":      re.compile(r"<h[3-6][^>]*>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "dt_label":      re.compile(r"<dt[^>]*>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "data_attr":     re.compile(r'data-(?:coffee|metafield)-(producer|farm|varietal|variety|process|origin|region)', re.I),
    "label_class":   re.compile(r'class="[^"]*\b(producer|farm|varietal|variety|process|origin|region)\b', re.I),
    "p_strong":      re.compile(r"<p[^>]*>\s*<strong>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "li_strong":     re.compile(r"<li[^>]*>\s*<strong>\s*(producer|farm|varietal|variety|process|origin|region)", re.I),
    "tag_prefix":    re.compile(r'"(?:origin|process|varietal|variety|producer):'),  # Shopify tag-prefix convention (Onyx-style)
}


def probe_one(base: str, c: httpx.Client) -> dict:
    """Returns: {ok, products, coffees, body_label_hits, body_len_avg, patterns}."""
    try:
        r = c.get(f"{base}/products.json?limit=50")
        if r.status_code != 200:
            return {"ok": False, "msg": f"http {r.status_code}"}
        try:
            data = r.json()
        except Exception:
            return {"ok": False, "msg": "not shopify (no json)"}
        products = data.get("products", [])
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}"}

    if not products:
        return {"ok": True, "msg": "no products", "products": 0, "coffees": 0}

    coffees = []
    for p in products:
        title = (p.get("title") or "").lower()
        ptype = (p.get("product_type") or "").lower()
        if any(b in title + " " + ptype for b in ("shirt", "tee", "mug", "hat", "tote", "sticker", "subscription", "gift card", "book", "equipment", "grinder", "dripper", "scale")):
            continue
        body = p.get("body_html") or ""
        if COFFEE_HINT.search(title + " " + body[:1500]):
            coffees.append(p)

    if not coffees:
        return {"ok": True, "msg": "shopify but no coffees", "products": len(products), "coffees": 0}

    # Sample 2 coffee pages
    body_label_hits = 0
    body_lens = []
    pattern_hits: dict[str, set[str]] = {k: set() for k in PATTERNS}
    for p in coffees[:2]:
        body = p.get("body_html") or ""
        body_lens.append(len(body))
        if re.search(r"\b(producer|farm|varietal|variety|process|origin|region)\s*[:|]", body, re.I):
            body_label_hits += 1
        try:
            page = c.get(f"{base}/products/{p['handle']}").text
            for name, rx in PATTERNS.items():
                for m in rx.finditer(page):
                    if m.lastindex:
                        pattern_hits[name].add(m.group(1).lower())
                    else:
                        pattern_hits[name].add("yes")
        except Exception:
            pass

    return {
        "ok": True,
        "products": len(products),
        "coffees": len(coffees),
        "body_label_hits": body_label_hits,
        "body_len_avg": sum(body_lens) // max(len(body_lens), 1),
        "patterns": {k: sorted(v) for k, v in pattern_hits.items() if v},
    }


def main() -> int:
    print(f"Probing {len(CANDIDATES)} new specialty roaster candidates...\n", file=sys.stderr)
    results = {}
    with httpx.Client(headers=UA, timeout=TIMEOUT, follow_redirects=True, verify=False) as c:
        for slug, urls in CANDIDATES.items():
            chosen = None
            best_result = None
            for url in urls:
                r = probe_one(url, c)
                if r.get("ok") and r.get("coffees", 0) > 0:
                    chosen = url
                    best_result = r
                    break
                elif r.get("ok") and not best_result:
                    best_result = r
                    chosen = url
            results[slug] = (chosen, best_result or {})
            r = best_result or {}
            if r.get("coffees", 0):
                pat_summary = ", ".join(f"{k}={v}" for k, v in r.get("patterns", {}).items() if v) or "(no patterns)"
                print(f"  OK   {slug:18s} {chosen:55s}  {r['coffees']:3d} coffees  body_label={r.get('body_label_hits',0)} body_len={r.get('body_len_avg',0)}  {pat_summary[:100]}")
            else:
                msg = r.get("msg", "no data") if r else "no data"
                print(f"  X    {slug:18s} {(chosen or urls[0]):55s}  {msg}")

    print()
    print("=" * 90)
    working = {s: (u, r) for s, (u, r) in results.items() if r.get("coffees", 0) > 0}
    print(f"\nWorking: {len(working)}/{len(CANDIDATES)}\n")

    body_ok = [s for s, (u, r) in working.items() if r.get("body_label_hits", 0) >= 1]
    page_meta = [s for s, (u, r) in working.items() if not r.get("body_label_hits") and r.get("patterns")]
    thin = [s for s, (u, r) in working.items() if not r.get("body_label_hits") and not r.get("patterns")]

    print(f"Generic scraper should work (body_html has labels): {body_ok}")
    print(f"Need custom HTML scrapers (rich page metadata):     {page_meta}")
    print(f"Thin pages (Shopify only / need LLM):               {thin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
