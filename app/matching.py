"""Match scoring: 0–100 based on field-by-field exactness.

See ARCHITECTURE.md §7 for the rationale on weights.

The algorithm is deliberately simple and explainable: every result returned
to the user can be debugged by looking at field_match.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.normalize import slug_for_match

# Weights sum to 100. Producer dominates because it's the most distinctive
# identifier for a coffee — same producer + same farm + same varietal almost
# always means the same lot.
WEIGHTS: dict[str, int] = {
    "producer": 35,
    "farm": 20,
    "varietal": 20,
    "process": 10,
    "country": 10,
    "region": 5,
}

# Fuzzy thresholds (RapidFuzz token_set_ratio, 0–100)
FUZZY_HIGH = 90  # ≥ this counts as 80% credit
FUZZY_LOW = 75   # ≥ this counts as 50% credit


@dataclass
class CoffeeFields:
    """A normalized coffee 'identity' usable for matching either side."""

    producer: str | None = None
    farm: str | None = None
    country: str | None = None
    region: str | None = None
    varietal: str | None = None
    process: str | None = None

    def is_empty(self) -> bool:
        return not any(getattr(self, f) for f in WEIGHTS)


def _field_score(query: str | None, candidate: str | None) -> tuple[float, bool]:
    """Returns (fraction in [0,1], exact_match_bool)."""
    if not query:
        return (0.0, False)  # query field absent → contributes nothing
    if not candidate:
        return (0.0, False)
    q = slug_for_match(query)
    c = slug_for_match(candidate)
    if q == c:
        return (1.0, True)
    ratio = fuzz.token_set_ratio(q, c)
    if ratio >= FUZZY_HIGH:
        return (0.8, False)
    if ratio >= FUZZY_LOW:
        return (0.5, False)
    return (0.0, False)


@dataclass
class ScoredMatch:
    score: int  # 0–100
    field_match: dict[str, bool]
    field_credit: dict[str, float]  # raw 0–1 per field, for debugging


def score(query: CoffeeFields, candidate: CoffeeFields) -> ScoredMatch:
    """Compute a 0–100 match score.

    Weights are *redistributed* over fields the query actually has, so a
    user pasting only a producer + varietal isn't penalized for the country
    they didn't specify. This is intentional: the score answers "how close
    is this candidate to what they asked for", not "how complete is this
    candidate's metadata".
    """
    if query.is_empty():
        return ScoredMatch(score=0, field_match={}, field_credit={})

    present_fields = [f for f in WEIGHTS if getattr(query, f)]
    total_weight = sum(WEIGHTS[f] for f in present_fields)
    if total_weight == 0:
        return ScoredMatch(score=0, field_match={}, field_credit={})

    field_match: dict[str, bool] = {}
    field_credit: dict[str, float] = {}
    earned = 0.0

    for f in present_fields:
        credit, exact = _field_score(getattr(query, f), getattr(candidate, f))
        field_credit[f] = credit
        field_match[f] = exact
        earned += credit * WEIGHTS[f]

    final = round((earned / total_weight) * 100)
    final = max(0, min(100, final))
    return ScoredMatch(score=final, field_match=field_match, field_credit=field_credit)


def label_for(score_value: int) -> str:
    """Human-readable bucket."""
    if score_value >= 95:
        return "Exact match"
    if score_value >= 75:
        return "Very similar"
    if score_value >= 50:
        return "Alternative"
    return "Loosely related"


def bucket(score_value: int) -> str:
    """For grouping in API response."""
    if score_value >= 95:
        return "exact"
    if score_value >= 75:
        return "similar"
    if score_value >= 50:
        return "alternatives"
    return "drop"
