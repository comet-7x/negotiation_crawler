"""Download PDFs from a docs_manifest JSONL via the directdoc endpoint.

Input:  JSONL produced by detail.py or enumerate.py (must have ``url`` or
        ``english_url`` field and a ``symbol`` field).
Output: PDFs saved to ``library/{series_folder}/``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

UA = "wto-fish-corpus-bot/1.0 (research; contact: research@example.com)"


def _safe(symbol: str) -> str:
    name = symbol.replace("(", "").replace(")", "").replace("/", "_")
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()


def download_listing(
    listing_path: Path,
    dest_dir: Path,
    delay: float = 0.8,
    fisheries_only: bool = False,
    resume: bool = True,
) -> dict:
    """Download every downloadable record in *listing_path* to *dest_dir*.

    Reads ``english_url`` (from enumerate.py) or ``url`` (from detail.py).
    Skips records that already have ``downloaded=True`` when *resume* is True.
    Rewrites the listing in-place with updated ``downloaded`` / ``raw_path`` fields.

    Returns a summary dict: {total, ok, skipped, failed}.
    """
    rows = [
        json.loads(line)
        for line in listing_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    targets = [
        r for r in rows
        if (r.get("english_url") or r.get("url"))
        and r.get("downloadable", True)
        and (not fisheries_only or r.get("fisheries"))
        and (not resume or not r.get("downloaded"))
    ]

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {len(targets)} PDF(s) from {listing_path.name} → {dest_dir}")

    ok = skipped = failed = 0
    with httpx.Client(headers={"User-Agent": UA},
                      timeout=90.0, follow_redirects=True) as client:
        for i, r in enumerate(targets, 1):
            sym = r.get("symbol") or f"doc{i}"
            dl_url = r.get("english_url") or r.get("url")
            try:
                resp = client.get(dl_url)
            except httpx.HTTPError as e:
                r["downloaded"] = False
                r["error"] = str(e)[:120]
                failed += 1
                print(f"  [ERR ] {sym}: {e}")
                continue

            is_pdf = ("pdf" in resp.headers.get("content-type", "").lower()
                      or resp.content[:5] == b"%PDF-")
            if resp.status_code == 200 and is_pdf and len(resp.content) > 1000:
                path = dest_dir / f"{_safe(sym)}.pdf"
                path.write_bytes(resp.content)
                r["downloaded"] = True
                r["raw_path"]   = str(path)
                r["size"]       = len(resp.content)
                ok += 1
                if i % 25 == 0 or i == len(targets):
                    print(f"  {i}/{len(targets)} ok={ok} failed={failed}")
            else:
                r["downloaded"] = False
                r["error"]      = f"not a PDF (HTTP {resp.status_code})"
                failed += 1
                print(f"  [miss] {sym}: HTTP {resp.status_code}")

            time.sleep(delay)

    # rewrite listing with updated status
    with listing_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  done: ok={ok} skipped={skipped} failed={failed}")
    return {"total": len(targets), "ok": ok, "skipped": skipped, "failed": failed}
