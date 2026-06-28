"""Wrapper for fishery_book_crawler (FAO DSpace REST API)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..base import BaseCrawler, CrawlResult
from ..config import get_config


class FisheryBookCrawler(BaseCrawler):
    name = "fishery_book"
    description = "FAO fishery publications from the Knowledge Repository (DSpace)"

    def run(
        self,
        output_dir: str | None = None,
        *,
        no_download: bool = False,
        no_resume: bool = False,
        category: list[str] | None = None,
        limit: int | None = None,
        concurrency: int = 4,
        http1: bool = False,
        proxy: str | None = None,
        log_level: str = "INFO",
        seeds: str | None = None,
        **_extra,
    ) -> CrawlResult:
        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        src_dir = cfg.get_src_dir(self.name)
        # fishery_book_crawler package lives under <src_dir>/src/
        pkg_root = src_dir / "src"
        seeds_default = src_dir / "seeds" / "seeds.json"

        env = os.environ.copy()
        env["PYTHONPATH"] = str(pkg_root) + os.pathsep + env.get("PYTHONPATH", "")

        cmd: list[str] = [
            sys.executable, "-m", "fishery_book_crawler",
            "--out", str(out),
            "--log-level", log_level,
            "--concurrency", str(concurrency),
            "--seeds", seeds or str(seeds_default),
        ]
        if no_download:
            cmd.append("--no-download")
        if no_resume:
            cmd.append("--no-resume")
        if http1:
            cmd.append("--http1")
        if proxy:
            cmd += ["--proxy", proxy]
        if limit is not None:
            cmd += ["--limit", str(limit)]
        for cat in (category or []):
            cmd += ["--category", cat]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        log = result.stdout + result.stderr
        if result.returncode == 0:
            return CrawlResult(success=True, output_dir=str(out), log=log)
        return CrawlResult(success=False, output_dir=str(out), log=log,
                           error=f"exit code {result.returncode}")
