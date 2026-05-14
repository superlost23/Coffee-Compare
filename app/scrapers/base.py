"""Base classes & data structures for roaster scrapers.

Every roaster gets a module that subclasses BaseRoasterScraper. Most just
inherit from ShopifyScraper (in shopify.py) and override only the bits
that vary between sites.
"""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class ProductRef:
    """Lightweight pointer to a product page returned by list_products()."""

    url: str
    handle: str | None = None  # Shopify product handle
    raw: dict[str, Any] = field(default_factory=dict)  # whatever the listing gave us


@dataclass
class RawVariant:
    """One purchasable size variant."""

    title: str
    price_cents: int | None
    available: bool
    grams: float | None = None  # if we already know


@dataclass
class RawOffering:
    """Output of parse_product() — feeds into extraction + DB."""

    url: str
    title: str
    description_html: str
    variants: list[RawVariant]
    # Pre-filled fields if the page has structured metadata
    producer: str | None = None
    farm: str | None = None
    country: str | None = None
    region: str | None = None
    varietal: str | None = None
    process: str | None = None


class BaseRoasterScraper(ABC):
    slug: str = "override-me"
    name: str = "Override me"
    base_url: str = "https://example.com"

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": settings().scrape_user_agent},
            timeout=settings().scrape_timeout_s,
            follow_redirects=True,
        )
        self._last_request_at: float = 0.0
        self._robots: urllib.robotparser.RobotFileParser | None = None

    def __enter__(self) -> "BaseRoasterScraper":
        return self

    def __exit__(self, *args: Any) -> None:
        self._client.close()

    # --- HTTP helpers -----------------------------------------------------

    def _throttle(self) -> None:
        """Enforce per-roaster delay between requests."""
        delay = settings().scrape_request_delay_ms / 1000
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.monotonic()

    def _check_robots(self, url: str) -> bool:
        """Returns True if our user-agent is allowed to fetch this URL."""
        if self._robots is None:
            parsed = urlparse(self.base_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            self._robots = urllib.robotparser.RobotFileParser()
            try:
                self._robots.set_url(robots_url)
                self._robots.read()
            except Exception as e:  # noqa: BLE001
                log.debug("robots.txt fetch failed for %s: %s", self.base_url, e)
                return True  # be permissive on failure
        return self._robots.can_fetch(settings().scrape_user_agent, url)

    def get(self, url: str) -> httpx.Response:
        if not self._check_robots(url):
            raise PermissionError(f"robots.txt disallows fetching {url}")
        self._throttle()
        full = urljoin(self.base_url, url)
        log.debug("GET %s", full)
        resp = self._client.get(full)
        resp.raise_for_status()
        return resp

    # --- Subclass interface ----------------------------------------------

    @abstractmethod
    def list_products(self) -> list[ProductRef]:
        """Return every coffee currently listed on the roaster's site."""

    @abstractmethod
    def parse_product(self, ref: ProductRef) -> RawOffering | None:
        """Fetch + parse a single product. Return None to skip."""
