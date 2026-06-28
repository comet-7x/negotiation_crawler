"""Orchestrator: seed -> DSpace search -> match -> bitstream -> (download) -> record."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from loguru import logger

from .classifier.matcher import best_match
from .config import Settings
from .fetch.dspace import DSpaceClient
from .fetch.legacy import resolve_legacy
from .models import BookRecord, Seed, Status
from .process.audit_xlsx import build_audit_xlsx
from .process.pdf_meta import pages_from_extent, pages_from_pdf
from .storage.db import Manifest
from .storage.files import download_bitstream


def load_seeds(path: Path) -> list[Seed]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Seed.from_dict(d) for d in data]


def _miss(seed: Seed, status: Status, note: str) -> BookRecord:
    return BookRecord(
        category=seed.category, year=seed.year, filename=None, title=None,
        download_url=None, pages=None, size_kb=None, fmt=None,
        seed_id=seed.seed_id, seed_title=seed.title, status=status, note=note,
    )


async def resolve_seed(
    seed: Seed,
    dspace: DSpaceClient,
    http: httpx.AsyncClient,
    settings: Settings,
    sem: asyncio.Semaphore,
) -> BookRecord:
    async with sem:
        try:
            return await _resolve_seed_inner(seed, dspace, http, settings)
        except Exception as exc:  # never let one seed kill the run
            logger.exception("error resolving {}: {}", seed.seed_id, exc)
            return _miss(seed, Status.ERROR, f"{type(exc).__name__}: {exc}")


async def _resolve_seed_inner(
    seed: Seed, dspace: DSpaceClient, http: httpx.AsyncClient, settings: Settings
) -> BookRecord:
    # 0) pinned seed -> resolve the exact item, skip search entirely (deterministic)
    if seed.is_pinned:
        if seed.item_uuid:
            item = await dspace.get_item_with_files(seed.item_uuid)
        else:
            resolved = await dspace.resolve_handle(seed.handle)
            if resolved is None:
                return _miss(seed, Status.MISSING, f"pinned handle {seed.handle} did not resolve")
            item = await dspace.get_item_with_files(resolved.uuid)
        pdf = item.primary_pdf()
        if pdf is None:
            return BookRecord(
                category=seed.category, year=seed.year, filename=None, title=item.title,
                download_url=item.handle_url, pages=pages_from_extent(item.extent),
                size_kb=None, fmt=None, seed_id=seed.seed_id, seed_title=seed.title,
                status=Status.NO_PDF, handle=item.handle, item_uuid=item.uuid, source="pinned",
                note="pinned item has no PDF bitstream",
            )
        return await _record_from_item(
            seed, item, pdf, settings, http, status=Status.FOUND, score=None,
            source="pinned", reason="pinned",
        )

    # 1) search DSpace
    query = seed.title
    candidates = await dspace.search_items(query, max_results=settings.search_page_size)
    match = best_match(seed, candidates) if candidates else None

    # 2) legacy fallback if nothing usable
    if match is None or match.score < settings.min_score:
        legacy_item = await resolve_legacy(seed, http)
        if legacy_item is not None:
            return await _record_from_item(
                seed, legacy_item, legacy_item.primary_pdf(), settings, http,
                status=Status.LEGACY, score=None, source="legacy",
            )
        if match is None:
            return _miss(seed, Status.MISSING, "no DSpace candidates; no legacy_url")
        return _miss(
            seed, Status.MISSING,
            f"best score {match.score:.0f} < min {settings.min_score:.0f} ({match.reason})",
        )

    # 3) fetch the full item (with bitstreams) for the chosen candidate
    item = await dspace.get_item_with_files(match.item.uuid)
    pdf = item.primary_pdf()
    status = Status.FOUND if match.score >= settings.confident_score else Status.AMBIGUOUS
    if pdf is None:
        return BookRecord(
            category=seed.category, year=seed.year, filename=None, title=item.title,
            download_url=item.handle_url, pages=pages_from_extent(item.extent),
            size_kb=None, fmt=None, seed_id=seed.seed_id, seed_title=seed.title,
            status=Status.NO_PDF, match_score=match.score, handle=item.handle,
            item_uuid=item.uuid, source="dspace",
            note=f"item found, no PDF bitstream ({match.reason})",
        )
    return await _record_from_item(
        seed, item, pdf, settings, http, status=status, score=match.score,
        source="dspace", reason=match.reason,
    )


async def _record_from_item(
    seed: Seed,
    item,
    pdf,
    settings: Settings,
    http: httpx.AsyncClient,
    *,
    status: Status,
    score: float | None,
    source: str,
    reason: str = "",
) -> BookRecord:
    pages = pages_from_extent(item.extent)
    size_kb = (pdf.size_bytes / 1024) if pdf and pdf.size_bytes else None
    local_path: str | None = None

    if settings.download and pdf:
        path = await download_bitstream(seed, pdf, settings.pdf_dir, http)
        if path:
            local_path = str(path)
            if size_kb is None:
                size_kb = path.stat().st_size / 1024
            if pages is None and settings.fetch_pages_from_pdf:
                pages = pages_from_pdf(path)

    return BookRecord(
        category=seed.category,
        year=seed.year,
        filename=pdf.name if pdf else None,
        title=item.title,
        download_url=(pdf.content_url if pdf else item.handle_url),
        pages=pages,
        size_kb=size_kb,
        fmt=(pdf.ext.upper() if pdf and pdf.ext else None),
        seed_id=seed.seed_id,
        seed_title=seed.title,
        status=status,
        match_score=score,
        handle=item.handle,
        item_uuid=item.uuid or None,
        bitstream_uuid=pdf.uuid if pdf else None,
        source=source,
        local_path=local_path,
        note=reason,
    )


def flag_duplicate_handles(records: list[BookRecord]) -> int:
    """When several seeds resolved to the same handle, keep the best-scoring one as
    FOUND and downgrade the rest to AMBIGUOUS (so collisions are visible, not silently
    overwritten on disk). Returns the number of rows downgraded."""
    from collections import defaultdict

    groups: dict[str, list[BookRecord]] = defaultdict(list)
    for r in records:
        # pinned records (e.g. the three IPOAs sharing the combined volume) are
        # intentional and must not be downgraded.
        if r.source == "pinned":
            continue
        if r.handle and r.status in (Status.FOUND, Status.AMBIGUOUS):
            groups[r.handle].append(r)

    downgraded = 0
    for handle, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (r.match_score or 0), reverse=True)
        keeper = members[0]
        for dup in members[1:]:
            if dup.status != Status.AMBIGUOUS or "duplicate" not in dup.note:
                dup.status = Status.AMBIGUOUS
                dup.note = (f"duplicate match of {keeper.seed_id} (same handle {handle}); "
                            f"likely wrong — verify. " + (dup.note or "")).strip()
                downgraded += 1
    return downgraded


async def run(
    settings: Settings,
    seeds: list[Seed],
    *,
    resume: bool = True,
) -> list[BookRecord]:
    settings.ensure_dirs()
    manifest = Manifest(settings.db_path)
    try:
        done = manifest.completed_seed_ids() if resume else set()
        todo = [s for s in seeds if s.seed_id not in done]
        logger.info("{} seeds total, {} to resolve ({} already complete)",
                    len(seeds), len(todo), len(done))

        sem = asyncio.Semaphore(settings.concurrency)
        limits = httpx.Limits(max_connections=settings.concurrency * 2)
        client_kwargs: dict = {
            "headers": settings.headers,
            "timeout": settings.timeout,
            "limits": limits,
            "follow_redirects": True,
        }
        if settings.proxy:
            client_kwargs["proxy"] = settings.proxy
            logger.info("using proxy {}", settings.proxy)
        try:
            http = httpx.AsyncClient(http2=settings.http2, **client_kwargs)
        except ImportError:
            logger.warning("h2 not installed; falling back to HTTP/1.1 (run: uv pip install h2)")
            http = httpx.AsyncClient(http2=False, **client_kwargs)
        logger.info("HTTP/{} client ready", "2" if settings.http2 else "1.1")
        async with http:
            dspace = DSpaceClient(settings, http)
            tasks = [resolve_seed(s, dspace, http, settings, sem) for s in todo]
            for coro in asyncio.as_completed(tasks):
                rec = await coro
                manifest.upsert(rec)
                logger.info("[{}] {} -> {}", rec.status.value, rec.seed_id, rec.title or "—")

        records = manifest.all_records()
        dupes = flag_duplicate_handles(records)
        if dupes:
            for r in records:  # persist the downgrades
                manifest.upsert(r)
            logger.warning("{} duplicate-handle rows downgraded to AMBIGUOUS", dupes)
        build_audit_xlsx(records, settings.xlsx_path)
        logger.success("audit sheet written -> {}", settings.xlsx_path)
        return records
    finally:
        manifest.close()
