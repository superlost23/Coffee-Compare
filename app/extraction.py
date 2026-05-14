"""Hybrid field extraction. See ARCHITECTURE.md §5.

Pipeline order:
  1. Pre-filled structured fields (from Shopify metafields, JSON-LD).
  2. Regex on the description body.
  3. LLM fallback if ≥2 critical fields still missing.

Each extraction records its method and a confidence score.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.normalize import (
    normalize_country,
    normalize_name,
    normalize_process,
    normalize_varietal,
)

log = logging.getLogger(__name__)

CRITICAL_FIELDS = ("producer", "varietal", "process", "country")


@dataclass
class ExtractedFields:
    producer: str | None = None
    farm: str | None = None
    country: str | None = None
    region: str | None = None
    varietal: str | None = None
    process: str | None = None
    method: str = "none"
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)

    def critical_missing(self) -> int:
        return sum(1 for f in CRITICAL_FIELDS if not getattr(self, f))


# --- Regex patterns -------------------------------------------------------

# Looks for "Label: value" lines (the common case). Tuned to be greedy on
# the value side until end-of-line / next label.
LABEL_RE = re.compile(
    r"(?im)^\s*(?P<label>producer|farm(?:er)?|origin|country|region|varietal|variety|cultivar|process(?:ing)?|method)\s*[:\-–]\s*(?P<value>[^\n\r]+?)\s*$"
)

LABEL_MAP = {
    "producer": "producer",
    "farm": "farm",
    "farmer": "producer",
    "origin": "country",
    "country": "country",
    "region": "region",
    "varietal": "varietal",
    "variety": "varietal",
    "cultivar": "varietal",
    "process": "process",
    "processing": "process",
    "method": "process",
}

# Inline pipe/bullet format: "Huila, Colombia • Pink Bourbon • Washed"
BULLET_RE = re.compile(r"\s*[•|·]\s*")


def _strip_html(text: str) -> str:
    """Lightweight HTML stripping; we don't need a full parser here."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_via_regex(description: str) -> ExtractedFields:
    """Stage 2 of the pipeline. Returns whatever it can find; never raises."""
    out = ExtractedFields(method="regex")
    if not description:
        return out
    text = _strip_html(description)

    # Pass 1: explicit "Label: value" lines
    for m in LABEL_RE.finditer(text):
        label = m.group("label").lower()
        value = m.group("value").strip()
        # strip trailing junk like "(Heirloom)"
        value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
        canonical = LABEL_MAP.get(label)
        if not canonical or not value:
            continue
        if not getattr(out, canonical):
            setattr(out, canonical, value)
            out.sources.append(f"regex:{label}")

    # Pass 2: country/region from "Region, Country" patterns when origin
    # was just a single line we already captured.
    if out.country and not out.region and "," in out.country:
        parts = [p.strip() for p in out.country.split(",")]
        if len(parts) == 2:
            out.region, out.country = parts[0], parts[1]
            out.sources.append("regex:split-origin")

    # Confidence: 0.85 if we got all 4 critical, scale down by missing.
    found_critical = 4 - out.critical_missing()
    out.confidence = round(0.5 + 0.1 * found_critical, 2)
    return out


# --- LLM fallback ---------------------------------------------------------

LLM_PROMPT = """You are extracting structured fields from a specialty coffee product description.

Return ONLY a JSON object with these keys (use null for unknown):
  producer  (the farmer or person who grew the coffee, e.g. "Edilberto Coronado")
  farm      (the farm or estate name, e.g. "Finca Bellavista")
  country   (single country name, e.g. "Colombia")
  region    (sub-national region, e.g. "Huila")
  varietal  (primary coffee varietal, e.g. "Pink Bourbon")
  process   (e.g. "Washed", "Natural", "Anaerobic Natural", "Thermal Shock")

Rules:
- Return *only* the JSON, no prose, no markdown fences.
- If multiple varietals are listed, return the first / primary one.
- If the description names a co-operative or washing station rather than a single
  producer, put the co-op name in "producer".
- Don't invent values. If unsure, use null.

Description to extract from:
---
{description}
---
"""


def extract_via_llm(description: str) -> ExtractedFields:
    """Stage 3: only called when regex misses ≥2 critical fields.

    Lazy-imports the Anthropic client so the module doesn't fail to import
    when the API key isn't configured (e.g. in tests).
    """
    out = ExtractedFields(method="llm", confidence=0.0)
    if not description.strip():
        return out
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError:
        log.warning("anthropic library not available; skipping LLM extraction")
        return out

    api_key = settings().anthropic_api_key
    if not api_key:
        log.info("ANTHROPIC_API_KEY not set; skipping LLM extraction")
        return out

    client = Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=settings().extraction_model,
            max_tokens=500,
            messages=[{"role": "user", "content": LLM_PROMPT.format(description=description[:6000])}],
        )
        # Concatenate text blocks
        text = "".join(getattr(b, "text", "") for b in resp.content)
        # Be defensive: strip code fences if the model returns them anyway
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        data = json.loads(text)
        for k in ("producer", "farm", "country", "region", "varietal", "process"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                setattr(out, k, v.strip())
        out.sources.append("llm")
        # Confidence: 0.8 baseline, +0.05 per critical field present
        found = 4 - out.critical_missing()
        out.confidence = round(0.6 + 0.05 * found, 2)
    except Exception as e:  # noqa: BLE001
        log.warning("LLM extraction failed: %s", e)
    return out


# --- Public entry point ---------------------------------------------------


def merge(primary: ExtractedFields, fallback: ExtractedFields) -> ExtractedFields:
    """primary wins; fallback fills gaps. Method/confidence reflect contribution."""
    out = ExtractedFields()
    used_fallback = False
    for f in ("producer", "farm", "country", "region", "varietal", "process"):
        pv = getattr(primary, f)
        fv = getattr(fallback, f)
        if pv:
            setattr(out, f, pv)
        elif fv:
            setattr(out, f, fv)
            used_fallback = True
    if used_fallback and primary.method != "none":
        out.method = f"{primary.method}+{fallback.method}"
        out.confidence = round((primary.confidence + fallback.confidence) / 2, 2)
    elif used_fallback:
        out.method = fallback.method
        out.confidence = fallback.confidence
    else:
        out.method = primary.method
        out.confidence = primary.confidence
    out.sources = primary.sources + fallback.sources
    return out


def extract(
    description: str,
    prefilled: ExtractedFields | None = None,
    use_llm: bool = True,
) -> ExtractedFields:
    """Run the full pipeline.

    Args:
        description: raw HTML or text body of the product page.
        prefilled: any structured fields already known (Shopify metafields, etc.).
        use_llm: set False in tests to avoid network.
    """
    base = prefilled or ExtractedFields(method="prefilled", confidence=0.95)

    if base.critical_missing() == 0:
        # Already complete; just normalize and return
        return _normalize_fields(base)

    regex_out = extract_via_regex(description)
    merged = merge(base, regex_out)

    if use_llm and merged.critical_missing() >= 2:
        llm_out = extract_via_llm(description)
        merged = merge(merged, llm_out)

    return _normalize_fields(merged)


def _normalize_fields(e: ExtractedFields) -> ExtractedFields:
    e.producer = normalize_name(e.producer)
    e.farm = normalize_name(e.farm)
    e.country = normalize_country(e.country)
    e.region = normalize_name(e.region)
    e.varietal = normalize_varietal(e.varietal)
    e.process = normalize_process(e.process)
    return e
