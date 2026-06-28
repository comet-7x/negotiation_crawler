"""wto_docs crawler — WTO Documents Online (TN/RL, WT/MIN, WT/L series).

Two-phase pipeline:
  Phase 1 (harvest):  harvest.py — Playwright browser search enumeration.
                      Requires: pip install playwright && playwright install chromium
  Phase 2 (fetch):    fetch.py — directdoc PDF download (no Playwright needed).

Skip either phase with skip_harvest / skip_fetch flags.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...base import BaseCrawler, CrawlResult
from ...config import get_config

log = logging.getLogger("wto_docs")


class WtoDocsCrawler(BaseCrawler):
    name = "wto_docs"
    description = "WTO Documents Online — TN/RL, WT/MIN, WT/L fisheries series download"

    def run(
        self,
        output_dir: str | None = None,
        *,
        # Phase 1
        query: str = "fisheries subsidies",
        query_type: str = "fulltext",
        max_pages: int = 50,
        headed: bool = False,
        login: bool = False,
        skip_harvest: bool = False,
        # Phase 2
        extra_symbols: list[str] | None = None,
        skip_fetch: bool = False,
        delay: float = 0.5,
        **_extra,
    ) -> CrawlResult:
        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        logs: list[str] = []

        # Phase 1: Playwright browser harvest
        if not skip_harvest:
            try:
                from .fetch.harvest import run as harvest_run
                harvest_run(
                    query=query,
                    by_symbol=(query_type == "symbol"),
                    out_dir=out,
                    headed=headed,
                    login=login,
                    max_pages=max_pages,
                )
                logs.append("harvest OK")
            except Exception as exc:
                return CrawlResult(
                    success=False, output_dir=str(out),
                    log="\n".join(logs),
                    error=f"harvest failed: {exc}",
                )

        # Phase 2: directdoc symbol download
        if not skip_fetch:
            try:
                import httpx
                import json
                from .fetch.fetch import probe_symbol, DEFAULT_SYMBOLS

                symbols = DEFAULT_SYMBOLS + (extra_symbols or [])
                manifest_dir = out / "docs_manifest"
                manifest_dir.mkdir(parents=True, exist_ok=True)
                man_path = manifest_dir / "docs_manifest.jsonl"

                recs = []
                with httpx.Client(
                    headers={"User-Agent": "wto-fish-corpus-bot/1.0 (research)"},
                    timeout=60.0, follow_redirects=True,
                ) as client:
                    for sym in symbols:
                        rec = probe_symbol(client, sym, out)
                        recs.append(rec)
                        flag = "OK  " if rec["downloadable"] else "FAIL"
                        log.info("[%s] %s", flag, sym)

                with man_path.open("w", encoding="utf-8") as f:
                    for rec in recs:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

                ok = sum(1 for r in recs if r["downloadable"])
                logs.append(f"fetch OK: {ok}/{len(recs)} symbols resolved")
            except Exception as exc:
                return CrawlResult(
                    success=False, output_dir=str(out),
                    log="\n".join(logs),
                    error=f"fetch failed: {exc}",
                )

        return CrawlResult(success=True, output_dir=str(out), log="\n".join(logs))
