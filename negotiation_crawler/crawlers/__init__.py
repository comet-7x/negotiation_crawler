"""Crawler registry — add new modules here to make them available everywhere."""

from __future__ import annotations

from ..base import BaseCrawler
from .fishery_book import FisheryBookCrawler
from .iotc import IotcCrawler
from .wto_site import WtoSiteCrawler
from .wto_docs import WtoDocsCrawler

_REGISTRY: dict[str, BaseCrawler] = {
    c.name: c()
    for c in [FisheryBookCrawler, IotcCrawler, WtoSiteCrawler, WtoDocsCrawler]
}


def get(name: str) -> BaseCrawler:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown crawler '{name}'. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]


def all_crawlers() -> dict[str, BaseCrawler]:
    return dict(_REGISTRY)
