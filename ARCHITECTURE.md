# Architecture & Build Documentation

This document explains exactly how Coffee Compare is built so you can extend it
later without re-deriving any decisions. It's organized as: high-level shape →
each module in detail → how to extend it → known limits.

---

## 1. High-level shape

```
                          ┌─────────────────┐
                          │   User browser  │
                          └────────┬────────┘
                                   │ HTTP (HTMX requests)
                                   ▼
   ┌───────────────────────────────────────────────────────────┐
   │                    FastAPI app (web)                      │
   │  • / search & URL-paste pages (Jinja2 + HTMX)             │
   │  • /api/search, /api/url-lookup, /api/log                 │
   │  • /admin-{token} dashboard (basic auth)                  │
   └─────────┬───────────────────────────┬─────────────────────┘
             │                           │
             ▼                           ▼
   ┌───────────────────┐      ┌──────────────────────┐
   │   PostgreSQL      │      │     Meilisearch      │
   │  • offerings      │      │  • offerings index   │
   │  • roasters       │      │    (fuzzy/typo)      │
   │  • search_logs    │      │                      │
   │  • pg_trgm        │      │                      │
   └─────────▲─────────┘      └──────────▲───────────┘
             │                            │
             └──────────┬─────────────────┘
                        │ writes
              ┌─────────┴──────────┐
              │   Scraper runner   │
              │  (cron, daily 4am) │
              │  • per-roaster     │
              │    adapter modules │
              │  • LLM fallback    │
              └────────────────────┘
```

Two long-running processes: **web** (FastAPI/uvicorn) and **scraper** (cron
inside the same container, or systemd timer on the VPS). They share the
Postgres + Meilisearch services via Docker Compose.

---

## 2. Repository layout

```
coffee_compare/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entry, route registration
│   ├── config.py                # env vars, settings
│   ├── db.py                    # SQLAlchemy engine, session
│   ├── models.py                # ORM models
│   ├── schemas.py               # Pydantic request/response models
│   ├── search.py                # Meilisearch client + indexing helpers
│   ├── matching.py              # Match-score algorithm (the core logic)
│   ├── extraction.py            # Regex + LLM hybrid field extractor
│   ├── normalize.py             # Country/varietal/process canonicalization
│   ├── pricing.py               # Price-per-ounce calculator
│   ├── logging_anon.py          # GDPR-safe search logging
│   ├── admin.py                 # Admin routes (basic auth, dashboard)
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseRoasterScraper abstract class
│   │   ├── shopify.py           # Generic Shopify /products.json scraper
│   │   ├── superlost.py         # ← per-roaster overrides (Shopify)
│   │   ├── sey.py
│   │   ├── prodigal.py
│   │   ├── ...                  # one file per roaster
│   │   └── registry.py          # roaster_slug → scraper class lookup
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html           # search/paste UI
│   │   ├── results.html         # search results (HTMX-rendered partial)
│   │   ├── _result_card.html    # single offering card partial
│   │   ├── admin.html           # dashboard
│   │   └── admin_heatmap.html   # heat map partial
│   └── static/
│       ├── css/main.css
│       └── js/app.js
├── scripts/
│   ├── scrape_all.py            # CLI: run every roaster scraper
│   ├── scrape_one.py            # CLI: run a single roaster (debugging)
│   ├── reindex_search.py        # rebuild Meilisearch from Postgres
│   └── seed_roasters.py         # populate roasters table from initial list
├── migrations/                  # Alembic
├── tests/
│   ├── test_matching.py
│   ├── test_extraction.py
│   ├── test_pricing.py
│   └── fixtures/                # sample HTML pages for scraper tests
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── README.md
└── ARCHITECTURE.md              # ← this file
```

---

## 3. Data model

Three core tables. Schema is in `app/models.py`; migrations in `migrations/`.

### `roasters`

| column         | type          | notes                                     |
|----------------|---------------|-------------------------------------------|
| id             | uuid PK       |                                           |
| slug           | text unique   | `superlost`, `sey`, etc.                  |
| name           | text          | Display name                              |
| website        | text          | Base URL                                  |
| platform       | text          | `shopify`, `squarespace`, `custom`        |
| scraper_module | text          | dotted path, e.g. `app.scrapers.superlost`|
| active         | bool          | toggle without deleting                   |
| last_scraped   | timestamptz   |                                           |

### `offerings`

This is the main table. One row per distinct coffee × size at a roaster.

| column           | type          | notes                                    |
|------------------|---------------|------------------------------------------|
| id               | uuid PK       |                                          |
| roaster_id       | uuid FK       |                                          |
| product_url      | text          | canonical URL                            |
| title            | text          | as displayed on the roaster site         |
| producer         | text          | `Edilberto Coronado`                     |
| farm             | text          | `Finca Bellavista`                       |
| country          | text          | normalized: `Colombia`, `Ethiopia`       |
| region           | text          | `Huila`, `Yirgacheffe`                   |
| varietal         | text          | normalized: `Pink Bourbon`, `Geisha`     |
| process          | text          | normalized: `Washed`, `Natural`,         |
|                  |               | `Anaerobic Natural`, `Thermal Shock`     |
| size_grams       | numeric       | smallest available size, in grams        |
| price_cents      | int           | smallest size, in USD cents              |
| price_per_oz     | numeric       | computed; cents per oz                   |
| currency         | text          | default `USD`                            |
| in_stock         | bool          |                                          |
| raw_description  | text          | original prose, kept for re-extraction   |
| extraction_method| text          | `shopify_metafield`, `regex`, `llm`      |
| extraction_conf  | numeric       | 0.0–1.0 confidence in extraction         |
| first_seen       | timestamptz   |                                          |
| last_seen        | timestamptz   | updated every scrape                     |
| last_updated     | timestamptz   | when fields changed                      |

Indexes (set in migration):
- `pg_trgm` GIN on `producer`, `farm`, `varietal` for fuzzy SQL fallback
- B-tree on `country`, `process`, `in_stock`, `roaster_id`
- Unique on `(roaster_id, product_url, size_grams)`

### `search_logs`

GDPR-safe. **Zero personal info.** No IP, no user agent, no session ID.

| column        | type        | notes                                       |
|---------------|-------------|---------------------------------------------|
| id            | bigserial   |                                             |
| ts_hour       | timestamptz | truncated to the hour, not minute/second    |
| query_type    | text        | `url`, `producer`, `varietal`, `country`,   |
|               |             | `farm`, `process`, `freeform`               |
| query_norm    | text        | normalized query (e.g. `pink bourbon`)      |
| matched_id    | uuid null   | the offering they clicked, if any           |
| had_exact     | bool        | did we find a 100-score match?              |
| top_score     | int null    | best match score returned                   |

Why hour-truncation: timestamps to the second can correlate with logged-in
sessions elsewhere, which is enough to be considered personal data under
GDPR. Hour-grain destroys that linkability while keeping trend data useful.

We also intentionally do **not** store the raw URL the user pasted — we
parse it, extract the fields, log the *fields*, and discard the URL.

---

## 4. Scraping pipeline

### 4.1 Per-roaster adapters

Each roaster has its own module in `app/scrapers/` because **every site is
different.** The `BaseRoasterScraper` abstract class enforces a common
interface:

```python
class BaseRoasterScraper(ABC):
    slug: str
    base_url: str

    @abstractmethod
    def list_products(self) -> list[ProductRef]:
        """Return URLs + minimal info for every coffee currently listed."""

    @abstractmethod
    def parse_product(self, ref: ProductRef) -> RawOffering:
        """Fetch a single product page and return raw fields + description."""
```

The scraper runner does:

1. `list_products()` → set of current product URLs
2. Diff against last run: new URLs, removed URLs (mark out of stock), existing
3. For each new/changed: `parse_product()` → `RawOffering`
4. Pass `RawOffering.description + raw fields` to `extraction.extract()`
5. Normalize via `normalize.py`
6. Upsert to `offerings`
7. Push to Meilisearch via `search.index_offering()`

### 4.2 Shopify shortcut

About 70% of specialty roasters run on Shopify and expose
`/products.json` and `/products/{handle}.js`, which return structured JSON
with title, vendor, variants (sizes + prices + availability), and the body
HTML. The `app/scrapers/shopify.py` generic scraper handles this — most
roaster files just inherit it and override `extract_fields_from_body()` for
site-specific prose conventions.

Roasters confirmed Shopify (most of the list): Superlost, Sey, Onyx, DAK,
Big Sur, Hydrangea, La Cabra, George Howell, Tandem, PERC, September,
Assembly. Verify each during initial setup — the seed script logs the
detected platform.

### 4.3 Non-Shopify roasters

Need bespoke parsers. Use Playwright (headless Chromium) for sites that
render product data client-side. Look at `app/scrapers/prodigal.py` as a
reference for the Playwright pattern.

### 4.4 Politeness & resilience

- 1 request/sec per roaster (configurable in `config.py`)
- Realistic User-Agent with a contact email
- Respect `robots.txt` via `urllib.robotparser` — checked once per scrape
- Retries with exponential backoff (httpx-retries)
- Per-roaster failures are logged but don't abort the whole run
- Each scrape writes a row to `scrape_runs` with status + counts

### 4.5 Adding a new roaster

When a user pastes a URL from a roaster not in the index:

1. `app/main.py` `/api/url-lookup` checks if the host matches a known roaster
2. If not: extract domain → create `roaster` row with `active=false` and
   `platform=unknown`
3. Try the generic Shopify scraper against `{domain}/products.json`
4. If that returns valid JSON: mark `platform=shopify`, set
   `scraper_module=app.scrapers.shopify`, set `active=true`, scrape just
   that one product synchronously (with a 10s timeout) so the user gets a
   result, then enqueue a full scrape for next cron run
5. If not Shopify: queue for manual adapter creation, return only the pasted
   URL's data extracted on the fly

---

## 5. Field extraction (`app/extraction.py`)

The hybrid pipeline. Order of preference:

1. **Structured metadata** (Shopify metafields, JSON-LD `Product` schema,
   OpenGraph). Free, near-100% accurate when present. ~25% of products.
2. **Regex patterns** against the description body. Looks for labeled lines:
   ```
   Producer: Edilberto Coronado
   Farm: Finca Bellavista
   Varietal: Pink Bourbon
   Process: Washed
   Region: Huila, Colombia
   ```
   Also handles the common "•" / "|" separated single-line format. ~50% of
   products fall here.
3. **LLM fallback** (Claude API, model `claude-sonnet-4-5` or whatever's
   current). Only invoked when ≥2 of {producer, varietal, process, country}
   are missing after steps 1–2. Prompt is in
   `app/extraction.py::LLM_PROMPT`. Returns strict JSON. We charge ~$0.01
   per product — for 34 roasters × ~30 products avg × 25% LLM fallback rate
   = ~$2.50 per full scrape. Trivial.

Each extraction stores `extraction_method` and `extraction_conf` so you can
later re-run extraction on low-confidence rows when the pipeline improves.

---

## 6. Normalization (`app/normalize.py`)

This is what makes matching work. Without it, "Pink Bourbon" and "pink
bourbon" and "P. Bourbon" all look different.

Three canonicalizers:

- **Country**: lowercase → ISO 3166 alpha-2 → display name. Handles
  `Colombia`/`COL`/`República de Colombia`.
- **Varietal**: hand-curated map of ~80 coffee varietals with aliases.
  Pink Bourbon, Geisha/Gesha, SL28, Bourbon Rosado→Pink Bourbon, etc.
  Unknown varietals pass through title-cased.
- **Process**: hand-curated. Washed, Natural, Honey (+ Yellow/Red/Black
  Honey), Anaerobic Natural, Thermal Shock, Carbonic Maceration,
  Lactic, Wet Hulled. Aliases handled (e.g. "fully washed" → "Washed").

The maps are TOML files (`app/normalize/varietals.toml`,
`processes.toml`, `countries.toml`) so they're editable without code
changes. They're the highest-leverage thing to keep updating as you see
new entries roll in.

---

## 7. Match scoring (`app/matching.py`)

The 1–100 score a user sees on each result.

```python
WEIGHTS = {
    "producer": 35,  # most distinctive
    "farm":     20,
    "varietal": 20,
    "process":  10,
    "country":  10,
    "region":    5,
}
```

For each field on the **query** side (URL or search):
- If query field is empty → field skipped, weight redistributed
- If exact normalized match → full points
- If fuzzy match (trigram similarity ≥ 0.85) → 80% of points
- If fuzzy match (≥ 0.7) → 50% of points
- Else → 0

Total is normalized to 0–100. Producer match is so much more distinctive
than process match that we weight it ~3.5×.

### Why exact same coffee → 100

In your example, both Diego Bermúdez listings have:
- producer = "Diego Bermúdez" (35) ✓
- varietal = "Pink Bourbon" (20) ✓
- process = "Thermal Shock" (10) ✓
- country = "Colombia" (10) ✓
- region = "Cauca" (5) ✓
- farm = "Finca El Paraíso" (20) ✓

That's 100. The Bellavista example shares producer (Edilberto Coronado,
35) and country (10) and farm (20), but varietal differs (0) and process
might match (10): ~75/100 — labeled "very similar, different varietal."

### Confidence vs. score

Score = how well the *fields match*.
Confidence = how sure we are the *fields are correct* (extraction_conf
on both sides averaged).

UI shows score prominently; confidence is a small badge ("80% confident
in extraction") only when below 0.75.

---

## 8. Price-per-ounce (`app/pricing.py`)

Everything is normalized to **cents per ounce** (US fluid? no — weight oz,
i.e. 28.3495 g). A 250g bag at $22 = 2200 / (250/28.3495) = $2.49/oz.

Sizes seen in the wild: 8 oz, 10 oz, 12 oz, 1/2 lb, 1 lb, 200g, 250g, 340g.
The pricing module has a parser that handles all of them and stores both
`size_grams` and `price_per_oz`.

The "smallest available size" rule: if a roaster offers 8oz and 12oz, we
index both as separate rows but only the 8oz is shown in default search
(it's almost always the better unit price for sampling). The user can
expand a row to see other sizes.

---

## 9. Search & matching flow

### 9.1 URL paste
```
POST /api/url-lookup  body={url}
```
1. Check if URL host is a known roaster
2. Look up offering by URL in Postgres
3. If found: use its (producer, farm, varietal, process, country, region)
   as the query
4. If not found: fetch + extract on the fly (rate-limited; 10s timeout),
   store with `extraction_method=on_demand`
5. Use those fields → run match search (9.3)
6. Log to `search_logs` with `query_type=url`

### 9.2 Field search
```
GET /api/search?producer=...&varietal=...&...
```
Same as above but skips the URL fetch.

### 9.3 Match search
1. Meilisearch query on combined fields with typo tolerance
2. Top 50 candidates returned
3. Score each candidate via `matching.score()`
4. Sort by `(in_stock DESC, score DESC, price_per_oz ASC)`
5. Group into "exact matches" (score ≥ 95), "very similar" (75–94),
   "alternatives" (50–74), drop below 50
6. Return top 20

### 9.4 No-match alternative recommendation
If top score < 50:
- Run three separate searches: producer-only, varietal-only, region-only
- Combine top 3 of each, dedupe
- Each is shown with confidence = score/100
- Caption: "We couldn't find this exact coffee, but you might like…"

---

## 10. Admin dashboard (`app/admin.py`)

Mounted at `/admin-{ADMIN_PATH_TOKEN}` — a random URL fragment from env so
it's not enumerable. Behind HTTP basic auth. **No link from public pages.**

Tabs:

1. **Trends** — most-searched producers, varietals, countries this week /
   month. Bar charts via Chart.js (vendored, no CDN).
2. **Heat map** — Leaflet map (vendored) with circles sized by search
   volume per origin region. Region → lat/lon via a static `regions.json`
   (we curate ~150 specialty regions; unknowns geocode to country
   centroid).
3. **Coverage** — per-roaster stats: products indexed, % with full
   extraction, last successful scrape, error rate.
4. **Scrape runs** — last 50 runs with status, duration, counts.

Read-only. No mutation endpoints in v1 — fewer ways for the admin URL
leaking to cause damage.

---

## 11. GDPR & privacy specifics

- No cookies set on public pages (HTMX uses no auth)
- No analytics scripts (no GA, no Plausible — all in-house from
  search_logs)
- No IP logging — we configure uvicorn with `proxy_headers=False` and
  override the access logger to drop the client field
- Hour-truncated timestamps (see §3)
- URL-paste raw URL is never stored
- `search_logs.query_norm` is a normalized query, not the raw input
- Privacy policy page (`/privacy`) explains all of this in plain English
- All this is documented in `app/logging_anon.py` so the privacy
  guarantees are co-located with the code that enforces them

---

## 12. How to extend it

### Add a new roaster
1. Create `app/scrapers/{slug}.py` inheriting from `ShopifyScraper` or
   `BaseRoasterScraper`
2. Add to `app/scrapers/registry.py`
3. Add a row to `roasters` table (or use `scripts/seed_roasters.py`)
4. Run `python -m scripts.scrape_one {slug}` to test
5. Add a fixture HTML in `tests/fixtures/{slug}/` and a test in
   `tests/test_extraction.py`

### Add a varietal/process synonym
Edit the relevant TOML in `app/normalize/`. No code change needed.

### Tune match weights
`WEIGHTS` dict in `app/matching.py`. Has unit tests in
`tests/test_matching.py` covering the example coffees from the spec.

### Add user accounts (future)
- Add `users` table, `auth.py` module with passwordless email login
- Add `watchlist` and `alert_subscription` tables
- Hook into the scraper diff-step: when a watched coffee comes back in
  stock, enqueue an email
- The schema and routing are designed so this can be slotted in without
  touching matching/extraction.

### Add price history
`offerings` already records `last_updated`. Add `offering_price_history`
table, write a row whenever `price_cents` changes during scraping. Use it
for sparkline charts in result cards.

---

## 13. Known limits / things to watch

- **Shopify variant naming is inconsistent.** Some roasters call the 250g
  bag "250g", some "Single", some "8.8 oz". The size parser tries hard
  but will mis-classify ~5% of variants. Manual cleanup table is at
  `app/normalize/size_overrides.toml`.
- **Producer disambiguation.** "Wilton Benitez" appears at multiple farms.
  We don't try to merge identities across farms; we treat
  (producer, farm) as the identity tuple. This is intentional — same
  producer, different farm = different coffee in this world.
- **Anti-bot.** None of the roasters on the initial list use Cloudflare
  Turnstile or similar. If one starts, switch that roaster to Playwright
  with stealth plugins, or fall back to RSS/Atom feeds where available.
- **LLM extraction drift.** Claude model versions change; the prompt is
  pinned to a specific model in `config.py`. Re-test extraction quality
  before bumping.
- **Price currency.** Roasters outside the US sell in their local
  currency. La Cabra (Denmark) lists DKK on the .com store but USD on
  /us/. The scraper checks for `/us/`-equivalent paths and prefers them.
  Mixed-currency offerings are converted to USD using a daily-cached
  rate from openexchangerates.org (free tier). See `app/pricing.py`.
- **Out-of-stock detection lag.** Up to 24h until next scrape. Acceptable
  for v1; if you want real-time, set up webhooks for the Shopify
  roasters (they support `products/update` webhooks).

---

## 14. Operational runbook

- **Scraper cron**: `0 4 * * * docker compose exec -T web python -m scripts.scrape_all >> /var/log/coffee_scrape.log 2>&1`
- **Backups**: nightly `pg_dump` to S3-compatible storage (Backblaze B2
  is fine). Meilisearch index can be rebuilt from Postgres via
  `scripts/reindex_search.py`, so we don't back it up.
- **Monitoring**: `/healthz` returns 200 if DB + Meili reachable. Point
  UptimeRobot at it. Scrape failures email the admin via Postmark
  (configured in `.env`).
- **Cost estimate (Hetzner CPX21, ~$8/mo)**: Postgres + Meili + web fit
  comfortably. LLM extraction ~$2–5/month at current scrape volume.
  Total ~$15/month all-in.
