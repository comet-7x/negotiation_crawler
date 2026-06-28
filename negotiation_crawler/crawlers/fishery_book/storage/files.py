"""Stream bitstreams to disk, skipping files already present with the right size."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from loguru import logger

from ..models import Bitstream, Seed

_SAFE = re.compile(r"[^0-9A-Za-z._-]+")


def safe_filename(seed: Seed, bitstream: Bitstream) -> str:
    """Prefer the repository's own filename; otherwise build one from the seed."""
    name = bitstream.name.strip()
    if not name:
        ext = bitstream.ext or "pdf"
        name = f"{seed.seed_id}.{ext}"
    # prefix with category+year for tidy on-disk grouping
    prefix = f"{seed.category}_{seed.year or 'NA'}_"
    cleaned = _SAFE.sub("_", name)
    return prefix + cleaned


async def download_bitstream(
    seed: Seed,
    bitstream: Bitstream,
    dest_dir: Path,
    client: httpx.AsyncClient,
) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / safe_filename(seed, bitstream)

    if target.exists() and bitstream.size_bytes and target.stat().st_size == bitstream.size_bytes:
        logger.debug("skip (already complete): {}", target.name)
        return target

    tmp = target.with_suffix(target.suffix + ".part")
    try:
        async with client.stream("GET", bitstream.content_url, follow_redirects=True) as r:
            r.raise_for_status()
            with tmp.open("wb") as fh:
                async for chunk in r.aiter_bytes(chunk_size=1 << 16):
                    fh.write(chunk)
        tmp.replace(target)
        logger.info("downloaded {} ({:.1f} KB)", target.name, target.stat().st_size / 1024)
        return target
    except httpx.HTTPError as exc:
        logger.error("download failed for {}: {}", seed.seed_id, exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return None
