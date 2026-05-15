"""Maps roaster slug → scraper class. Edit this when adding a new roaster.

Most roasters use the generic ShopifyScraper with just a slug/name/base_url.
For roasters that need custom behavior, create a dedicated module and import
its class here.
"""
from __future__ import annotations

from app.scrapers.base import BaseRoasterScraper
from app.scrapers.assembly import AssemblyScraper
from app.scrapers.blackwhite import BlackWhiteScraper
from app.scrapers.labeled_strong import make as _labeled
from app.scrapers.lacabra import LaCabraScraper
from app.scrapers.onyx import OnyxScraper
from app.scrapers.roguewave import RogueWaveScraper
from app.scrapers.shopify import ShopifyScraper
from app.scrapers.superlost import SuperlostScraper


def _shopify(slug: str, name: str, base_url: str) -> type[BaseRoasterScraper]:
    """Dynamically build a ShopifyScraper subclass with the given identity.

    This avoids 30+ near-identical files for vanilla Shopify roasters; each
    roaster gets a real module only if it needs custom logic.
    """
    cls = type(
        f"Shopify_{slug}",
        (ShopifyScraper,),
        {"slug": slug, "name": name, "base_url": base_url},
    )
    return cls


# Initial seed list. Verify base_urls during first scrape — a few roasters
# may have moved domains since this list was compiled.
SEEDS: dict[str, type[BaseRoasterScraper]] = {
    "superlost": SuperlostScraper,
    "sey": _shopify("sey", "Sey", "https://www.seycoffee.com"),
    "prodigal": _shopify("prodigal", "Prodigal", "https://getprodigal.com"),
    "aviary": _shopify("aviary", "Aviary", "https://www.aviarycoffee.com"),
    "onyx": OnyxScraper,
    "dak": _shopify("dak", "DAK", "https://dakcoffeeroasters.com"),
    "picky_chemist": _shopify("picky_chemist", "Picky Chemist", "https://pickychemist.com"),
    "big_sur": _shopify("big_sur", "Big Sur", "https://bigsurcoffee.com"),
    "sw": _shopify("sw", "S&W", "https://swcoffee.co"),
    "hydrangea": _shopify("hydrangea", "Hydrangea", "https://hydrangeacoffee.com"),
    "la_cabra": LaCabraScraper,
    "george_howell": _shopify("george_howell", "George Howell", "https://georgehowellcoffee.com"),
    "botz": _shopify("botz", "Botz", "https://botzcoffee.com"),
    "rogue_wave": RogueWaveScraper,
    "nomad": _shopify("nomad", "Nomad", "https://www.nomadcoffee.es"),
    "substance": _shopify("substance", "Substance", "https://substance.coffee"),
    "moxie": _shopify("moxie", "Moxie", "https://moxieroasters.com"),
    "datura": _shopify("datura", "Datura", "https://daturacoffee.com"),
    "hs": _shopify("hs", "H&S", "https://hsroasters.com"),
    "bw": BlackWhiteScraper,
    "brandywine": _shopify("brandywine", "Brandywine", "https://www.brandywinecoffeeroasters.com"),
    "luminous": _shopify("luminous", "Luminous", "https://luminouscoffee.com"),
    "lf_coffee": _shopify("lf_coffee", "LF Coffee", "https://lfcoffee.com"),
    "little_wolf": _shopify("little_wolf", "Little Wolf", "https://littlewolfcoffee.com"),
    "ten_speed": _shopify("ten_speed", "10 Speed Coffee", "https://10speedcoffee.com"),
    "broadsheets": _shopify("broadsheets", "Broadsheets", "https://broadsheetcoffee.com"),
    "cartel": _shopify("cartel", "Cartel", "https://cartelcoffeelab.com"),
    "tandem": _shopify("tandem", "Tandem", "https://www.tandemcoffee.com"),
    "yellowbrick": _shopify("yellowbrick", "YellowBrick", "https://yellowbrickcoffee.com"),
    "perc": _shopify("perc", "PERC", "https://perccoffee.com"),
    "september": _shopify("september", "September", "https://www.septembercoffee.com"),
    "assembly": AssemblyScraper,
    "dark_arts": _shopify("dark_arts", "Dark Arts", "https://www.darkartscoffee.co.uk"),
    "driftaway": _shopify("driftaway", "Driftaway", "https://www.driftaway.coffee"),

    # --- Wave 2: top-tier US/UK/EU/CA/AU specialty roasters added Nov 2025. ---
    # Rich page metadata (labeled_strong handles <strong>Label|</strong>value):
    "devocion":          _labeled("devocion",         "Devoción",        "https://devocion.com"),
    "the_barn":          _labeled("the_barn",         "The Barn",        "https://www.thebarn.de"),
    "drop_coffee":       _labeled("drop_coffee",      "Drop Coffee",     "https://www.dropcoffee.com"),
    "bonanza":           _labeled("bonanza",          "Bonanza",         "https://bonanzacoffee.de"),
    "april":             _labeled("april",            "April",           "https://aprilcoffeeroasters.com"),
    "origin_uk":         _labeled("origin_uk",        "Origin (UK)",     "https://www.origincoffee.co.uk"),
    "pilot":             _labeled("pilot",            "Pilot",           "https://pilotcoffeeroasters.com"),
    # US single-origin powerhouses (generic — body_html or title-based, still useful):
    "heart":             _shopify("heart",            "Heart",           "https://www.heartroasters.com"),
    "stumptown":         _shopify("stumptown",        "Stumptown",       "https://www.stumptowncoffee.com"),
    "counterculture":    _shopify("counterculture",   "Counter Culture", "https://counterculturecoffee.com"),
    "verve":             _shopify("verve",            "Verve",           "https://www.vervecoffee.com"),
    "sightglass":        _shopify("sightglass",       "Sightglass",      "https://sightglasscoffee.com"),
    "madcap":            _shopify("madcap",           "Madcap",          "https://madcapcoffee.com"),
    "klatch":            _shopify("klatch",           "Klatch",          "https://klatchroasting.com"),
    "equator":           _shopify("equator",          "Equator",         "https://www.equatorcoffees.com"),
    "joe_coffee":        _shopify("joe_coffee",       "Joe Coffee",      "https://www.joecoffeecompany.com"),
    "intelligentsia":    _shopify("intelligentsia",   "Intelligentsia",  "https://www.intelligentsia.com"),
    "bird_rock":         _shopify("bird_rock",        "Bird Rock",       "https://birdrockcoffee.com"),
    "ruby":              _shopify("ruby",             "Ruby",            "https://rubycoffeeroasters.com"),
    "metric":            _shopify("metric",           "Metric",          "https://metriccoffee.com"),
    # UK / EU specialty:
    "workshop":          _shopify("workshop",         "Workshop",        "https://workshopcoffee.com"),
    "square_mile":       _shopify("square_mile",      "Square Mile",     "https://shop.squaremilecoffee.com"),
    "round_hill":        _shopify("round_hill",       "Round Hill",      "https://www.roundhillroastery.com"),
    "kiss_the_hippo":    _shopify("kiss_the_hippo",   "Kiss the Hippo",  "https://kissthehippo.com"),
    "coffee_collective": _shopify("coffee_collective","Coffee Collective","https://coffeecollective.dk"),
    "tim_wendelboe":     _shopify("tim_wendelboe",    "Tim Wendelboe",   "https://www.timwendelboe.no"),
    "five_elephant":     _shopify("five_elephant",    "Five Elephant",   "https://fiveelephant.com"),
    "passenger":         _shopify("passenger",        "Passenger",       "https://passengercoffee.com"),
    # CA / AU:
    "phil_sebastian":    _shopify("phil_sebastian",   "Phil & Sebastian","https://philsebastian.com"),
    "fortyninth":        _shopify("fortyninth",       "49th Parallel",   "https://49thcoffee.com"),
    "proud_mary":        _shopify("proud_mary",       "Proud Mary",      "https://proudmarycoffee.com"),
    "market_lane":       _shopify("market_lane",      "Market Lane",     "https://marketlane.com.au"),
}


def get(slug: str) -> type[BaseRoasterScraper] | None:
    return SEEDS.get(slug)


def all_slugs() -> list[str]:
    return list(SEEDS.keys())
