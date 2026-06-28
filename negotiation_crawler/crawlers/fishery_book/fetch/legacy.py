"""Legacy fallback for the handful of documents that are not (cleanly) in DSpace.

Most older titles were migrated into openknowledge.fao.org, so the DSpace path
already covers them. This fallback exists only for the residual gap — typically
pre-2005 technical guidelines that still live in the old corporate document
repository at ``fao.org/3/{docid}/{docid}.pdf``.

Because the legacy repo has no clean search API, we don't try to *discover* docs
here: instead a seed may carry an explicit ``legacy_url`` (filled in manually for
known gaps). This keeps the fallback honest and deterministic rather than guessing
document ids.
"""

from __future__ import annotations

import httpx
from loguru import logger

from ..models import Bitstream, DSpaceItem, Seed


async def resolve_legacy(seed: Seed, client: httpx.AsyncClient) -> DSpaceItem | None:
    """If the seed pins a legacy_url, HEAD it and wrap it as a one-bitstream item."""
    if not seed.legacy_url:
        return None
    try:
        r = await client.head(seed.legacy_url, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("legacy HEAD failed for {}: {}", seed.seed_id, exc)
        return None

    size = r.headers.get("content-length")
    mimetype = r.headers.get("content-type", "").split(";")[0] or None
    name = seed.legacy_url.rsplit("/", 1)[-1] or f"{seed.seed_id}.pdf"
    bitstream = Bitstream(
        uuid="",
        name=name,
        size_bytes=int(size) if size and size.isdigit() else None,
        mimetype=mimetype,
        content_url=str(r.url),
        bundle="ORIGINAL",
    )
    return DSpaceItem(
        uuid="",
        name=seed.title,
        handle=None,
        title=seed.title,
        issued=str(seed.year) if seed.year else None,
        language=seed.lang,
        dtype="legacy",
        extent=None,
        bitstreams=[bitstream],
    )
