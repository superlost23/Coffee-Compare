"""Pricing & size parsing tests."""
from __future__ import annotations

import math

from app.pricing import GRAMS_PER_OZ, NAMED_SIZES, parse_size, price_per_oz


def test_named_sizes_round_trip() -> None:
    for label in NAMED_SIZES:
        result = parse_size(label)
        assert result is not None, f"failed to parse {label!r}"
        assert result.grams > 0


def test_parses_oz_with_decimal() -> None:
    s = parse_size("8.8 oz")
    assert s is not None
    # 8.8oz is the marketing label for 250g (a Shopify quirk we encode)
    assert math.isclose(s.grams, 250.0, rel_tol=1e-3)


def test_parses_grams() -> None:
    s = parse_size("250g")
    assert s is not None
    assert s.grams == 250.0


def test_parses_pounds() -> None:
    s = parse_size("1 lb")
    assert s is not None
    assert math.isclose(s.grams, 16 * GRAMS_PER_OZ, rel_tol=1e-3)


def test_parses_kilograms() -> None:
    s = parse_size("1kg")
    assert s is not None
    assert s.grams == 1000.0


def test_parses_oz_via_regex() -> None:
    s = parse_size("12 oz")
    assert s is not None
    assert math.isclose(s.grams, 12 * GRAMS_PER_OZ, rel_tol=1e-3)


def test_parse_unknown_returns_none() -> None:
    assert parse_size("fancy") is None
    assert parse_size("") is None
    assert parse_size(None) is None


def test_price_per_oz_basic() -> None:
    # $22 / 250g → about $2.49/oz → 249 cents/oz
    cpo = price_per_oz(2200, 250.0)
    assert cpo is not None
    assert 248 <= cpo <= 250


def test_price_per_oz_handles_8oz() -> None:
    # $25 / 8oz → exactly $3.125/oz → 312.5 cents/oz
    cpo = price_per_oz(2500, 8 * GRAMS_PER_OZ)
    assert cpo is not None
    assert 311 <= cpo <= 314


def test_price_per_oz_diego_example() -> None:
    """Spec example: $25/8oz vs $28/8oz — second is 12% more per oz."""
    a = price_per_oz(2500, 8 * GRAMS_PER_OZ)
    b = price_per_oz(2800, 8 * GRAMS_PER_OZ)
    assert a is not None and b is not None
    assert b > a
    assert math.isclose(b / a, 28 / 25, rel_tol=1e-3)


def test_price_per_oz_invalid_size() -> None:
    assert price_per_oz(2200, 0) is None
