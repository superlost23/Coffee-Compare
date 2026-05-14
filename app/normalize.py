"""Normalization for matching.

These maps drive the *whole* match score quality. Update them aggressively
as you see new variants in scraped data. See ARCHITECTURE.md §6.

Kept as Python dicts (not TOML) for the initial build to keep file count down;
graduate to TOML when the maps grow past ~200 entries each.
"""
from __future__ import annotations

import re
import unicodedata


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _slug(s: str) -> str:
    s = _strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


# --- Countries -------------------------------------------------------------

COUNTRY_ALIASES: dict[str, str] = {
    "colombia": "Colombia",
    "republica de colombia": "Colombia",
    "ethiopia": "Ethiopia",
    "kenya": "Kenya",
    "rwanda": "Rwanda",
    "burundi": "Burundi",
    "tanzania": "Tanzania",
    "uganda": "Uganda",
    "drc": "DR Congo",
    "dr congo": "DR Congo",
    "democratic republic of the congo": "DR Congo",
    "guatemala": "Guatemala",
    "el salvador": "El Salvador",
    "honduras": "Honduras",
    "costa rica": "Costa Rica",
    "nicaragua": "Nicaragua",
    "panama": "Panama",
    "mexico": "Mexico",
    "peru": "Peru",
    "bolivia": "Bolivia",
    "ecuador": "Ecuador",
    "brazil": "Brazil",
    "indonesia": "Indonesia",
    "sumatra": "Indonesia",
    "papua new guinea": "Papua New Guinea",
    "yemen": "Yemen",
    "india": "India",
    "thailand": "Thailand",
    "myanmar": "Myanmar",
    "vietnam": "Vietnam",
    "china": "China",
    "taiwan": "Taiwan",
    "philippines": "Philippines",
    "timor leste": "Timor-Leste",
    "east timor": "Timor-Leste",
    "laos": "Laos",
}


def normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    key = _slug(raw)
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    # try matching the last token (e.g. "Huila, Colombia" → "colombia")
    parts = [p.strip() for p in raw.split(",")]
    for part in reversed(parts):
        k = _slug(part)
        if k in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[k]
    return raw.strip().title()


# --- Varietals -------------------------------------------------------------

VARIETAL_ALIASES: dict[str, str] = {
    "pink bourbon": "Pink Bourbon",
    "bourbon rosado": "Pink Bourbon",
    "bourbon": "Bourbon",
    "yellow bourbon": "Yellow Bourbon",
    "red bourbon": "Red Bourbon",
    "orange bourbon": "Orange Bourbon",
    "typica": "Typica",
    "caturra": "Caturra",
    "catuai": "Catuai",
    "yellow catuai": "Yellow Catuai",
    "red catuai": "Red Catuai",
    "mundo novo": "Mundo Novo",
    "geisha": "Geisha",
    "gesha": "Geisha",
    "sl28": "SL28",
    "sl 28": "SL28",
    "sl34": "SL34",
    "sl 34": "SL34",
    "ruiru 11": "Ruiru 11",
    "batian": "Batian",
    "k7": "K7",
    "pacamara": "Pacamara",
    "maragogipe": "Maragogipe",
    "maragogype": "Maragogipe",
    "pacas": "Pacas",
    "villa sarchi": "Villa Sarchi",
    "ethiopian heirloom": "Ethiopian Heirloom",
    "heirloom": "Ethiopian Heirloom",
    "landrace": "Ethiopian Heirloom",
    "74110": "74110",
    "74112": "74112",
    "74158": "74158",
    "74165": "74165",
    "74140": "74140",
    "wush wush": "Wush Wush",
    "java": "Java",
    "tabi": "Tabi",
    "castillo": "Castillo",
    "colombia": "Colombia (varietal)",  # the varietal, not country
    "tipica mejorada": "Tipica Mejorada",
    "kent": "Kent",
    "s795": "S795",
    "s 795": "S795",
    "chiroso": "Chiroso",
    "centroamericano": "Centroamericano",
    "h1": "H1",
    "marsellesa": "Marsellesa",
    "obata": "Obata",
}


def normalize_varietal(raw: str | None) -> str | None:
    if not raw:
        return None
    key = _slug(raw)
    if key in VARIETAL_ALIASES:
        return VARIETAL_ALIASES[key]
    return raw.strip().title()


def split_varietals(raw: str | None) -> list[str]:
    """Some products list multiple varietals; we keep the primary for matching
    but expose the rest. e.g. "Caturra, Castillo" → ["Caturra", "Castillo"]."""
    if not raw:
        return []
    parts = re.split(r"[,/&+]| and ", raw)
    out = []
    for p in parts:
        n = normalize_varietal(p.strip())
        if n:
            out.append(n)
    return out


# --- Processes -------------------------------------------------------------

PROCESS_ALIASES: dict[str, str] = {
    "washed": "Washed",
    "fully washed": "Washed",
    "wet": "Washed",
    "wet processed": "Washed",
    "natural": "Natural",
    "dry": "Natural",
    "dry processed": "Natural",
    "honey": "Honey",
    "yellow honey": "Yellow Honey",
    "red honey": "Red Honey",
    "black honey": "Black Honey",
    "white honey": "White Honey",
    "pulped natural": "Pulped Natural",
    "anaerobic": "Anaerobic",
    "anaerobic natural": "Anaerobic Natural",
    "anaerobic washed": "Anaerobic Washed",
    "carbonic maceration": "Carbonic Maceration",
    "cm": "Carbonic Maceration",
    "thermal shock": "Thermal Shock",
    "double anaerobic": "Double Anaerobic",
    "lactic": "Lactic",
    "lactic fermentation": "Lactic",
    "wet hulled": "Wet Hulled",
    "giling basah": "Wet Hulled",
    "experimental": "Experimental",
    "yeast": "Yeast Fermented",
    "yeast fermented": "Yeast Fermented",
    "tropical yeast": "Tropical Yeast",
    "koji": "Koji",
}


def normalize_process(raw: str | None) -> str | None:
    if not raw:
        return None
    key = _slug(raw)
    if key in PROCESS_ALIASES:
        return PROCESS_ALIASES[key]
    # combo handling: "thermal shock + tropical yeast" → keep the first
    for separator in [" + ", " / ", " & ", " and "]:
        if separator in raw.lower():
            first = raw.split(separator)[0]
            return normalize_process(first.strip())
    return raw.strip().title()


# --- Generic name normalization (producer/farm) ---------------------------

def normalize_name(raw: str | None) -> str | None:
    if not raw:
        return None
    s = _strip_accents(raw).strip()
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # title-case but keep ALLCAPS short tokens (SL28, etc.)
    return s.title() if not re.search(r"\b[A-Z]{2,}\d*\b", s) else s


def slug_for_match(s: str | None) -> str:
    """Returns lowercase, accent-stripped, alphanumeric-only — for cheap
    equality comparisons and Postgres trigram queries."""
    if not s:
        return ""
    return _slug(s)
