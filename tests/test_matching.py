"""Match-scoring tests.

These tests directly exercise the two example scenarios the user gave:

  1. superlost.com Solo Sabado (Edilberto Coronado / Pink Bourbon /
     Washed / Huila Colombia / Finca Bellavista) compared with an
     every.coffee offering of the *same producer + farm* but a
     different varietal — expected score ~75 ("very similar").

  2. Diego Bermúdez Thermal Shock Pink Bourbon at superlost vs.
     Great Circle Coffee — same coffee, expected 100 ("exact match").
"""
from __future__ import annotations

from app.matching import CoffeeFields, WEIGHTS, label_for, score


def test_exact_match_is_100() -> None:
    """Diego Bermúdez Thermal Shock — every field aligned → 100."""
    query = CoffeeFields(
        producer="Diego Bermúdez",
        farm="Finca El Paraíso",
        country="Colombia",
        region="Cauca",
        varietal="Pink Bourbon",
        process="Thermal Shock",
    )
    candidate = CoffeeFields(
        producer="Diego Bermúdez",
        farm="Finca El Paraíso",
        country="Colombia",
        region="Cauca",
        varietal="Pink Bourbon",
        process="Thermal Shock",
    )
    sm = score(query, candidate)
    assert sm.score == 100
    assert label_for(sm.score) == "Exact match"
    # All present fields exact
    assert all(sm.field_match[f] for f in WEIGHTS)


def test_same_producer_same_farm_different_varietal() -> None:
    """Edilberto Coronado scenario: producer + farm + country + region
    match, but varietal differs (Pink Bourbon vs. Java) and process may
    differ. Expected score ≈ 75–85 (the user said ~75 is "right")."""
    query = CoffeeFields(
        producer="Edilberto Coronado",
        farm="Finca Bellavista",
        country="Colombia",
        region="Huila",
        varietal="Pink Bourbon",
        process="Washed",
    )
    candidate = CoffeeFields(
        producer="Edilberto Coronado",
        farm="Finca Bellavista",
        country="Colombia",
        region="Huila",
        varietal="Java",       # different
        process="Washed",      # same
    )
    sm = score(query, candidate)
    # Earned: 35 + 20 + 10 + 5 + 0 + 10 = 80 / 100
    assert 70 <= sm.score <= 85
    assert label_for(sm.score) == "Very similar"
    assert sm.field_match["producer"] is True
    assert sm.field_match["varietal"] is False


def test_only_producer_in_common_is_alternative() -> None:
    """Same producer but different farm, varietal, process → alternative."""
    query = CoffeeFields(
        producer="Wilton Benitez",
        farm="Granja Paraiso 92",
        country="Colombia",
        varietal="Geisha",
        process="Anaerobic Natural",
    )
    candidate = CoffeeFields(
        producer="Wilton Benitez",
        farm="El Diviso",       # different farm
        country="Colombia",
        varietal="Sidra",       # different varietal
        process="Washed",       # different process
    )
    sm = score(query, candidate)
    # Earned: 35 (producer) + 0 + 10 (country) + 0 + 0 = 45/100 (no farm/varietal/process)
    # Total weight present: 35+20+10+20+10 = 95 → 45/95 ≈ 47
    assert 35 <= sm.score <= 55
    assert label_for(sm.score) in ("Alternative", "Loosely related")


def test_completely_different_coffee_scores_low() -> None:
    query = CoffeeFields(
        producer="Edilberto Coronado",
        varietal="Pink Bourbon",
        country="Colombia",
    )
    candidate = CoffeeFields(
        producer="Asefa Dukamo",
        varietal="Heirloom",
        country="Ethiopia",
    )
    sm = score(query, candidate)
    assert sm.score < 30


def test_partial_query_redistributes_weights() -> None:
    """If the user only specifies a producer + varietal, missing fields
    should NOT penalize candidates that match those two fully."""
    query = CoffeeFields(
        producer="Diego Bermúdez",
        varietal="Pink Bourbon",
    )
    candidate = CoffeeFields(
        producer="Diego Bermúdez",
        farm="Finca El Paraíso",   # extra info on candidate
        country="Colombia",
        varietal="Pink Bourbon",
    )
    sm = score(query, candidate)
    # Both query fields exact → 100 (weights renormalized over present query fields)
    assert sm.score == 100


def test_fuzzy_producer_match_gets_partial_credit() -> None:
    query = CoffeeFields(producer="Edilberto Coronado", varietal="Pink Bourbon")
    candidate = CoffeeFields(producer="E. Coronado", varietal="Pink Bourbon")
    sm = score(query, candidate)
    # Should recognize the abbreviated form as fuzzily similar (token_set_ratio
    # treats the matching token "coronado" as overlap)
    assert sm.score >= 70


def test_empty_query_returns_zero() -> None:
    sm = score(CoffeeFields(), CoffeeFields(producer="Anyone"))
    assert sm.score == 0


def test_label_buckets() -> None:
    assert label_for(100) == "Exact match"
    assert label_for(95) == "Exact match"
    assert label_for(94) == "Very similar"
    assert label_for(75) == "Very similar"
    assert label_for(74) == "Alternative"
    assert label_for(50) == "Alternative"
    assert label_for(49) == "Loosely related"
