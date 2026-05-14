"""Try common URL variants for each roaster to find the live Shopify endpoint."""
from __future__ import annotations

import httpx

UA = {"User-Agent": "CoffeeCompareBot/0.1"}
TIMEOUT = 10.0

# (slug, list of (display_name, candidate_base_urls)) — first to return valid products.json wins.
CANDIDATES: dict[str, list[str]] = {
    "aviary":        ["https://aviarycoffee.com", "https://www.aviarycoffee.com", "https://aviaryroasters.com", "https://aviarycoffeeroasters.com"],
    "dak":           ["https://dakcoffeeroasters.com", "https://www.dakcoffeeroasters.com", "https://dak.coffee"],
    "picky_chemist": ["https://pickychemist.com", "https://thepickychemist.com", "https://pickychemistcoffee.com", "https://www.pickychemist.com"],
    "big_sur":       ["https://bigsurroasters.com", "https://www.bigsurroasters.com", "https://bigsurcoffee.com", "https://bigsurcoffeeroasters.com"],
    "sw":            ["https://swcoffee.co", "https://swcoffeeroasters.com", "https://swroasters.com", "https://swcoffeeroasting.com", "https://shorewavecoffee.com"],
    "hydrangea":     ["https://hydrangeacoffee.com", "https://hydrangearoasters.com", "https://hydrangeacoffeeroasters.com", "https://www.hydrangearoasting.com"],
    "substance":     ["https://substance.coffee", "https://substancecoffee.com", "https://substanceroasters.com", "https://www.substance.coffee"],
    "moxie":         ["https://moxieroasters.com", "https://moxiecoffeeroasters.com", "https://drinkmoxie.com", "https://moxieroasting.com"],
    "hs":            ["https://handsons.com", "https://handsoms.com", "https://hscoffee.com", "https://hsroasters.com", "https://heritageandstandard.com"],
    "brandywine":    ["https://brandywinecoffeeroasters.com", "https://brandywine.coffee", "https://brandywineroasters.com", "https://www.brandywinecoffeeroasters.com"],
    "luminous":      ["https://luminouscoffee.com", "https://luminouscoffeeroasters.com", "https://luminousroasters.com", "https://wearelumins.com"],
    "lf_coffee":     ["https://lfcoffee.com", "https://lfcoffeeroasters.com", "https://littlefoxcoffee.com"],
    "little_wolf":   ["https://littlewolfcoffee.com", "https://www.littlewolfcoffee.com", "https://littlewolfroasters.com"],
    "ten_speed":     ["https://10speedcoffee.com", "https://tenspeedcoffee.com", "https://www.tenspeedcoffee.com"],
    "september":     ["https://septembercoffee.com", "https://www.septembercoffee.com", "https://septembercoffeeco.com", "https://septembercoffeeroasters.com"],
    "driftaway":     ["https://driftaway.coffee", "https://www.driftaway.coffee", "https://driftawaycoffee.com"],
}


def try_one(url: str) -> tuple[bool, str, int]:
    """Returns (is_shopify, message, products_count)."""
    try:
        with httpx.Client(headers=UA, timeout=TIMEOUT, follow_redirects=True, verify=False) as c:
            r = c.get(f"{url}/products.json?limit=5")
        if r.status_code != 200:
            return False, f"http {r.status_code}", 0
        try:
            data = r.json()
        except Exception:
            return False, "not json (probably html storefront)", 0
        products = data.get("products", [])
        return True, "OK", len(products)
    except httpx.ConnectError:
        return False, "DNS / connect fail", 0
    except httpx.ConnectTimeout:
        return False, "timeout", 0
    except Exception as e:
        return False, f"{type(e).__name__}", 0


def main() -> int:
    print(f"Probing {sum(len(v) for v in CANDIDATES.values())} URL variants across {len(CANDIDATES)} roasters...\n")
    winners: dict[str, str] = {}
    for slug, urls in CANDIDATES.items():
        found = None
        for u in urls:
            ok, msg, n = try_one(u)
            status = "OK" if ok else "x "
            print(f"  {status}  {slug:14s}  {u:55s}  {msg}  ({n} products)" if ok else f"  {status}  {slug:14s}  {u:55s}  {msg}")
            if ok and n > 0:
                found = u
                break
        if found:
            winners[slug] = found
        print()
    print("=" * 70)
    print(f"\nFound working URLs for {len(winners)}/{len(CANDIDATES)}:")
    for slug, url in winners.items():
        print(f"  {slug:14s}  {url}")
    print(f"\nStill missing: {sorted(set(CANDIDATES) - set(winners))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
