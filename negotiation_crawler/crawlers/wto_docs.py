"""Wrapper for wto_fish_crawler — WTO Documents Online library (docs.wto.org).

Two-phase pipeline:
  Phase 1 (harvest):  docs_harvest.py — Playwright browser automation that searches
                      WTO Documents Online and writes docs_manifest.jsonl.
                      Requires: pip install playwright && playwright install chromium
  Phase 2 (fetch):    docs_fetch.py — downloads PDFs for known document symbols
                      (WT/MIN, WT/L, TN/RL series) via the directdoc endpoint.
                      Does NOT require Playwright.

Either phase can be skipped with skip_harvest / skip_fetch flags.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..base import BaseCrawler, CrawlResult
from ..config import get_config


class WtoDocsCrawler(BaseCrawler):
    name = "wto_docs"
    description = "WTO Documents Online — TN/RL, WT/MIN, WT/L fisheries series download"

    def run(
        self,
        output_dir: str | None = None,
        *,
        # Phase 1: docs_harvest.py (Playwright search enumeration)
        query: str = "fisheries subsidies",
        query_type: str = "fulltext",   # "fulltext" or "symbol"
        max_pages: int = 50,
        headed: bool = False,
        login: bool = False,
        skip_harvest: bool = False,
        # Phase 2: docs_fetch.py (directdoc PDF download)
        extra_symbols: list[str] | None = None,
        skip_fetch: bool = False,
        delay: float = 0.5,
        **_extra,
    ) -> CrawlResult:
        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        src_dir = cfg.get_src_dir(self.name)
        tools_dir = src_dir / "tools"

        env = os.environ.copy()
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")

        logs: list[str] = []

        # Phase 1: browser-driven search harvest (optional, needs Playwright)
        if not skip_harvest:
            harvest_cmd: list[str] = [
                sys.executable, str(tools_dir / "docs_harvest.py"),
                "--out", str(out),
                "--max-pages", str(max_pages),
            ]
            if query_type == "symbol":
                harvest_cmd += ["--symbol", query]
            else:
                harvest_cmd += ["--fulltext", query]
            if headed:
                harvest_cmd.append("--headed")
            if login:
                harvest_cmd.append("--login")

            r1 = subprocess.run(harvest_cmd, env=env, cwd=str(src_dir),
                                capture_output=True, text=True)
            logs.append(r1.stdout + r1.stderr)
            if r1.returncode != 0:
                return CrawlResult(
                    success=False, output_dir=str(out),
                    log="\n".join(logs),
                    error=f"docs_harvest.py failed (exit {r1.returncode})",
                )

        # Phase 2: directdoc PDF download (default symbols + any extras)
        if not skip_fetch:
            manifest_dir = out / "docs_manifest"
            fetch_cmd: list[str] = [
                sys.executable, str(tools_dir / "docs_fetch.py"),
                "--download",
                "--out", str(out),
                "--manifest", str(manifest_dir / "docs_manifest.jsonl"),
                "--delay", str(delay),
            ]
            for sym in (extra_symbols or []):
                fetch_cmd += ["--symbol", sym]

            r2 = subprocess.run(fetch_cmd, env=env, cwd=str(src_dir),
                                capture_output=True, text=True)
            logs.append(r2.stdout + r2.stderr)
            if r2.returncode != 0:
                return CrawlResult(
                    success=False, output_dir=str(out),
                    log="\n".join(logs),
                    error=f"docs_fetch.py failed (exit {r2.returncode})",
                )

        return CrawlResult(success=True, output_dir=str(out), log="\n".join(logs))
