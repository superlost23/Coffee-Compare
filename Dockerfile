FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# system deps for psycopg & playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e .

# Playwright is in pyproject.toml for future use but we don't need the browser
# binaries at runtime yet — skip them to keep image small (~150MB savings).
# Re-enable when a roaster needs JS-rendered HTML.

COPY . .

# DigitalOcean App Platform sets $PORT; fall back to 8000 for local docker-compose.
# Run migrations before starting the server so a fresh deploy auto-creates the
# schema. Safe to run on every boot: alembic upgrade head is idempotent.
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
