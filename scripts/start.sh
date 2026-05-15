#!/bin/sh
# Container entrypoint for the web service.
#
# We run migrations on startup so a fresh deploy auto-creates the schema, but
# we never let a migration failure crash the container — if alembic can't
# connect or the migration errors out, we still start uvicorn so we get logs
# from the runtime and the homepage can degrade gracefully.

set -u  # treat undefined vars as errors, but don't `set -e` — we want to continue past alembic failures.

echo "[start.sh] starting Coffee Compare web — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[start.sh] PORT=${PORT:-8000}"

if [ -n "${DATABASE_URL:-}" ]; then
    echo "[start.sh] running alembic upgrade head..."
    if alembic upgrade head; then
        echo "[start.sh] migrations OK"
    else
        echo "[start.sh] WARNING: alembic upgrade head failed (exit $?). Continuing — uvicorn will start anyway." >&2
    fi
else
    echo "[start.sh] WARNING: DATABASE_URL is unset, skipping migrations" >&2
fi

echo "[start.sh] launching uvicorn on 0.0.0.0:${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
