# Coffee Compare

Find identical coffees across specialty roasters and compare prices per ounce.

A web app that scrapes 34+ specialty coffee roasters, indexes their offerings by
producer, farm, varietal, process, and origin, and lets users find the same
coffee (or close alternatives) at other roasters with price comparisons.

## What it does

- **URL search**: Paste any coffee product URL → find the same coffee elsewhere
- **Field search**: Search by producer, farm, varietal, country, or process
- **Match scoring**: 1–100 score based on how exactly fields match
- **Alternatives**: When no exact match exists, suggest closest with confidence %
- **Price-per-ounce comparison**: Normalizes across 8oz, 250g, 12oz, etc.
- **Availability sort**: In-stock results surface first
- **Trend tracking**: Logs anonymous searches to surface popular coffees
- **Admin dashboard**: Hidden URL with search analytics + heat map

## Stack

- FastAPI (Python 3.11+)
- PostgreSQL with `pg_trgm` for fuzzy text similarity
- Meilisearch for typo-tolerant search
- Jinja2 + HTMX (server-rendered, no SPA build step)
- Playwright + httpx for scraping (Shopify JSON endpoints when available)
- Anthropic Claude API for LLM-fallback field extraction

## Quickstart

```bash
# 1. Copy env template
cp .env.example .env
# Fill in: DATABASE_URL, MEILI_MASTER_KEY, ANTHROPIC_API_KEY,
#          ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_PATH_TOKEN

# 2. Boot infrastructure
docker compose up -d

# 3. Run migrations
docker compose exec web alembic upgrade head

# 4. Run initial scrape (takes 30–60 min)
docker compose exec web python -m scripts.scrape_all

# 5. Visit http://localhost:8000
```

## Architecture

See `ARCHITECTURE.md` for the full build doc — every module, every decision,
every place to extend the system.

## License

Private / unreleased.
