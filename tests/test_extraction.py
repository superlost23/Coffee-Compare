"""Extraction tests — regex layer only (use_llm=False).

We don't test the LLM fallback in the unit suite because it would require
hitting the Anthropic API. The extract() function honors use_llm=False and
the tests below assert the regex layer hits the common formatting patterns
specialty roasters use.
"""
from __future__ import annotations

from app.extraction import extract, extract_via_regex


LABELED_DESCRIPTION = """
<p>A bright, juicy lot from one of our favorite producers in southern Colombia.</p>
<p>
  Producer: Edilberto Coronado<br>
  Farm: Finca Bellavista<br>
  Region: Huila, Colombia<br>
  Varietal: Pink Bourbon<br>
  Process: Washed<br>
</p>
<p>Tasting notes: jasmine, peach, lemon zest.</p>
"""


def test_regex_extracts_all_labeled_fields() -> None:
    fields = extract(LABELED_DESCRIPTION, use_llm=False)
    assert fields.producer == "Edilberto Coronado"
    assert fields.farm == "Finca Bellavista"
    assert fields.varietal == "Pink Bourbon"
    assert fields.process == "Washed"
    # "Region: Huila, Colombia" should split into region + country
    assert fields.country == "Colombia"
    assert fields.region == "Huila"


def test_regex_handles_dash_separator() -> None:
    desc = """
    Producer - Diego Bermúdez
    Farm - Finca El Paraíso
    Varietal - Pink Bourbon
    Process - Thermal Shock
    Country - Colombia
    """
    fields = extract(desc, use_llm=False)
    assert fields.producer == "Diego Bermúdez"
    assert fields.varietal == "Pink Bourbon"
    assert fields.process == "Thermal Shock"
    assert fields.country == "Colombia"


def test_regex_normalizes_varietal_synonyms() -> None:
    fields = extract("Varietal: Gesha\nProcess: Natural\nProducer: Foo Bar\n", use_llm=False)
    assert fields.varietal == "Geisha"  # normalized via VARIETAL_ALIASES
    assert fields.process == "Natural"


def test_regex_normalizes_process_synonyms() -> None:
    fields = extract("Producer: X\nVarietal: Caturra\nProcess: Fully Washed\nCountry: Honduras\n", use_llm=False)
    assert fields.process == "Washed"


def test_regex_strips_html() -> None:
    desc = "<p><strong>Producer:</strong> Asefa Dukamo<br><strong>Country:</strong> Ethiopia</p>"
    fields = extract(desc, use_llm=False)
    assert fields.producer == "Asefa Dukamo"
    assert fields.country == "Ethiopia"


def test_regex_returns_empty_for_no_matches() -> None:
    """Pure prose with no labeled fields → regex finds nothing.
    With use_llm=False this should return a mostly-empty result."""
    desc = "A wonderful coffee from a great farmer who grew it well."
    fields = extract(desc, use_llm=False)
    assert fields.producer is None
    assert fields.varietal is None
    assert fields.process is None


def test_regex_partial_extraction_critical_missing() -> None:
    """If we only got producer, critical_missing should be 3."""
    fields = extract_via_regex("Producer: Foo Bar\n")
    assert fields.producer == "Foo Bar"
    assert fields.critical_missing() == 3  # missing: varietal, process, country


def test_country_normalization_via_origin_label() -> None:
    fields = extract("Origin: Republica de Colombia\n", use_llm=False)
    assert fields.country == "Colombia"
