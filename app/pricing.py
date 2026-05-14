"""Size and price normalization. See ARCHITECTURE.md §8."""
from __future__ import annotations

import re
from dataclasses import dataclass

GRAMS_PER_OZ = 28.3495231

# Common size strings → grams. Add to this as new variants appear.
NAMED_SIZES: dict[str, float] = {
    "8 oz": 8 * GRAMS_PER_OZ,
    "8oz": 8 * GRAMS_PER_OZ,
    "8.8 oz": 250.0,  # marketing-rounded label for 250g
    "10 oz": 10 * GRAMS_PER_OZ,
    "10oz": 10 * GRAMS_PER_OZ,
    "12 oz": 12 * GRAMS_PER_OZ,
    "12oz": 12 * GRAMS_PER_OZ,
    "1/2 lb": 8 * GRAMS_PER_OZ,
    "half pound": 8 * GRAMS_PER_OZ,
    "1 lb": 16 * GRAMS_PER_OZ,
    "1lb": 16 * GRAMS_PER_OZ,
    "one pound": 16 * GRAMS_PER_OZ,
    "200g": 200.0,
    "250g": 250.0,
    "340g": 340.0,
    "454g": 16 * GRAMS_PER_OZ,
    "500g": 500.0,
    "1kg": 1000.0,
}

# The negative lookbehind (?<!\/) prevents matching the "2" in "1/2lb".
# The num group optionally accepts a fractional form like "1/2".
SIZE_RE = re.compile(
    r"(?<![\d/])(?P<num>\d+(?:/\d+)?(?:\.\d+)?)\s*(?P<unit>kg|g|oz|lbs?|pound|pounds)\b",
    re.IGNORECASE,
)


@dataclass
class ParsedSize:
    grams: float
    canonical_label: str  # what we'll show in the UI


def parse_size(raw: str | None) -> ParsedSize | None:
    """Parse a size string into grams. Returns None if unparseable."""
    if not raw:
        return None
    s = raw.strip().lower()
    # Direct named size
    if s in NAMED_SIZES:
        return ParsedSize(grams=NAMED_SIZES[s], canonical_label=raw.strip())
    # Try regex
    m = SIZE_RE.search(s)
    if not m:
        return None
    num_str = m.group("num")
    if "/" in num_str:
        numer, denom = num_str.split("/")
        num = float(numer) / float(denom)
    else:
        num = float(num_str)
    unit = m.group("unit").lower()
    if unit == "kg":
        grams = num * 1000
        label = f"{num:g} kg"
    elif unit == "g":
        grams = num
        label = f"{num:g} g"
    elif unit == "oz":
        grams = num * GRAMS_PER_OZ
        label = f"{num:g} oz"
    elif unit in ("lb", "lbs", "pound", "pounds"):
        grams = num * 16 * GRAMS_PER_OZ
        label = f"{num:g} lb"
    else:
        return None
    return ParsedSize(grams=grams, canonical_label=label)


def price_per_oz(price_cents: int, size_grams: float) -> float | None:
    """Returns cents per ounce. None if size invalid."""
    if size_grams <= 0:
        return None
    oz = size_grams / GRAMS_PER_OZ
    return round(price_cents / oz, 2)


def format_price_per_oz(cents_per_oz: float | None, currency: str = "USD") -> str:
    if cents_per_oz is None:
        return "—"
    sym = "$" if currency == "USD" else f"{currency} "
    return f"{sym}{cents_per_oz / 100:.2f}/oz"


def smaller_size(a: float | None, b: float | None) -> float | None:
    """Returns the smaller of two sizes, ignoring Nones."""
    vals = [v for v in (a, b) if v is not None]
    return min(vals) if vals else None
