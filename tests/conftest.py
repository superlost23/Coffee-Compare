"""Shared pytest configuration.

We don't spin up Postgres or Meilisearch here — pure-Python tests for the
matching, extraction, and pricing modules. Integration tests that hit the
real services live separately (not in this initial test suite).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the project root importable so `import app.matching` works without
# needing an installed package during local pytest runs.
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Avoid the LLM extraction code path attempting to construct a real client.
os.environ.setdefault("ANTHROPIC_API_KEY", "")
