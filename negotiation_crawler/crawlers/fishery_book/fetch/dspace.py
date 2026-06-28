"""Async client for the FAO Knowledge Repository DSpace 7 REST API.

Why an API client instead of an HTML scraper: openknowledge.fao.org is a DSpace 7
Angular SPA. The rendered HTML carries almost no structured data — titles, years,
file sizes and download links all live behind the REST API. The API also hands us
``sizeBytes`` for every bitstream, so we get the "size (KB)" column without
downloading a single file.

Key endpoints used:
  GET /discover/search/objects?query=..&dsoType=item   -> search
  GET /core/items/{uuid}?embed=bundles/bitstreams      -> item + files in one call
  GET /core/bitstreams/{uuid}/content                  -> the actual download
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger

from ..config import Settings
from ..models import Bitstream, DSpaceItem


def _first(metadata: dict[str, Any], key: str) -> str | None:
    vals = metadata.get(key)
    if isinstance(vals, list) and vals:
        return vals[0].get("value")
    return None


def _parse_bitstreams(item_json: dict[str, Any]) -> list[Bitstream]:
    """Dig bitstreams out of the (deeply nested) embedded bundles structure."""
    out: list[Bitstream] = []
    bundles = (
        item_json.get("_embedded", {})
        .get("bundles", {})
        .get("_embedded", {})
        .get("bundles", [])
    )
    for bundle in bundles:
        bundle_name = bundle.get("name", "")
        bstreams = (
            bundle.get("_embedded", {})
            .get("bitstreams", {})
            .get("_embedded", {})
            .get("bitstreams", [])
        )
        for b in bstreams:
            md = b.get("metadata", {}) or {}
            content_href = b.get("_links", {}).get("content", {}).get("href", "")
            out.append(
                Bitstream(
                    uuid=b.get("uuid") or b.get("id", ""),
                    name=b.get("name", ""),
                    size_bytes=b.get("sizeBytes"),
                    mimetype=_first(md, "dc.format.mimetype"),
                    content_url=content_href,
                    bundle=bundle_name,
                )
            )
    return out


def _item_from_json(j: dict[str, Any]) -> DSpaceItem:
    md = j.get("metadata", {}) or {}
    return DSpaceItem(
        uuid=j.get("uuid") or j.get("id", ""),
        name=j.get("name", ""),
        handle=j.get("handle"),
        title=_first(md, "dc.title") or j.get("name", ""),
        issued=_first(md, "dc.date.issued"),
        language=_first(md, "dc.language.iso"),
        dtype=_first(md, "dc.type"),
        extent=_first(md, "dc.format.extent"),
        bitstreams=_parse_bitstreams(j),
    )


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class WAFBlocked(RuntimeError):
    """Raised on a 403 that almost always means a CDN/WAF rejected the request."""


class DSpaceClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.s = settings
        self.http = client

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET JSON. Retries only transient failures; 403/4xx fail fast."""
        last_exc: Exception | None = None
        for attempt in range(1, self.s.max_retries + 1):
            try:
                r = await self.http.get(url, params=params)
            except httpx.HTTPStatusError:
                raise
            except Exception as exc:  # transport OR protocol (h2/proxy) error -> retry
                # A bare GET only fails here on transport/protocol issues (an HTTP status
                # never raises). Proxies frequently corrupt HTTP/2 streams, surfacing as
                # h2.exceptions.ProtocolError — which is NOT an httpx.RequestError, so we
                # must catch broadly. (KeyboardInterrupt/CancelledError derive from
                # BaseException and are intentionally not caught.)
                last_exc = exc
                if attempt == self.s.max_retries:
                    break
                wait = self.s.backoff_base ** attempt
                logger.warning("GET {} transport/protocol error (attempt {}/{}): {} — retry in {:.1f}s",
                               url, attempt, self.s.max_retries, type(exc).__name__, wait)
                await asyncio.sleep(wait)
                continue

            if r.status_code == 403:
                raise WAFBlocked(
                    f"403 Forbidden from {r.url}. The FAO repo is behind a CDN/WAF that blocks "
                    "non-browser requests. Run `python tests/probe_api.py` to find a header set "
                    "that returns 200; if even that fails, install curl_cffi and use the "
                    "impersonate fallback (see README)."
                )
            if r.status_code in _RETRYABLE_STATUS:
                last_exc = httpx.HTTPStatusError(
                    f"transient {r.status_code}", request=r.request, response=r
                )
                if attempt == self.s.max_retries:
                    break
                wait = self.s.backoff_base ** attempt
                logger.warning("GET {} -> {} (attempt {}/{}) — retry in {:.1f}s",
                               url, r.status_code, attempt, self.s.max_retries, wait)
                await asyncio.sleep(wait)
                continue

            r.raise_for_status()  # any other 4xx: deterministic, do not retry
            try:
                return r.json()
            except ValueError as exc:
                raise RuntimeError(f"non-JSON response from {r.url}: {exc}") from exc

        assert last_exc is not None
        raise last_exc

    async def search_items(
        self, query: str, *, size: int | None = None, max_results: int = 25
    ) -> list[DSpaceItem]:
        """Full-text discover search, returning lightweight items (no bitstreams)."""
        size = size or self.s.search_page_size
        url = f"{self.s.api_base}/discover/search/objects"
        params = {"query": query, "dsoType": "item", "size": size, "page": 0}
        data = await self._get(url, params)
        objects = (
            data.get("_embedded", {})
            .get("searchResult", {})
            .get("_embedded", {})
            .get("objects", [])
        )
        items: list[DSpaceItem] = []
        for obj in objects[:max_results]:
            idx = obj.get("_embedded", {}).get("indexableObject")
            if idx:
                items.append(_item_from_json(idx))
        logger.debug("search '{}' -> {} items", query, len(items))
        return items

    async def get_item_with_files(self, uuid: str) -> DSpaceItem:
        """Fetch a single item together with its bundles/bitstreams in one call."""
        url = f"{self.s.api_base}/core/items/{uuid}"
        data = await self._get(url, {"embed": "bundles/bitstreams"})
        return _item_from_json(data)

    async def resolve_handle(self, handle: str) -> DSpaceItem | None:
        """Resolve a full handle like '20.500.14283/cc0461en' to an item."""
        url = f"{self.s.api_base}/pid/find"
        try:
            data = await self._get(url, {"id": f"hdl:{handle}"})
        except httpx.HTTPError:
            return None
        return _item_from_json(data)
