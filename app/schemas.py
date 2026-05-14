"""Pydantic models for API I/O."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CoffeeQuery(BaseModel):
    """Either a URL to look up, or explicit fields. URL takes precedence."""

    url: HttpUrl | None = None
    producer: str | None = None
    farm: str | None = None
    country: str | None = None
    region: str | None = None
    varietal: str | None = None
    process: str | None = None
    free: str | None = Field(default=None, description="Free-text fallback search")


class OfferingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    roaster_name: str
    roaster_slug: str
    product_url: str
    title: str
    producer: str | None
    farm: str | None
    country: str | None
    region: str | None
    varietal: str | None
    process: str | None
    size_grams: float | None
    price_cents: int | None
    price_per_oz: float | None
    currency: str
    in_stock: bool
    last_seen: datetime


class MatchResult(BaseModel):
    offering: OfferingOut
    score: int = Field(ge=0, le=100)
    score_label: str  # "Exact match", "Very similar", "Alternative"
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    field_match: dict[str, bool]  # which fields matched


class SearchResponse(BaseModel):
    query: CoffeeQuery
    resolved_query: dict[str, str | None]  # what we extracted from the URL/inputs
    exact: list[MatchResult]
    similar: list[MatchResult]
    alternatives: list[MatchResult]
    total_candidates_examined: int
