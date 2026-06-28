"""Wrapper for wto_fish_crawler — site crawl pipeline (www.wto.org fish pages)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..base import BaseCrawler, CrawlResult
from ..config import get_config


class WtoSiteCrawler(BaseCrawler):
    name = "wto_site"
    description = "WTO fisheries subsidies agreement main site and subpages → Markdown corpus"

    def run(
        self,
        output_dir: str | None = None,
        *,
        max_depth: int = 4,
        concurrency: int = 4,
        delay: float = 1.0,
        include_docs: bool = False,
        max_pages: int | None = None,
        pdf_backend: str = "pymupdf",
        resume: bool = False,
        seeds: list[str] | None = None,
        **_extra,
    ) -> CrawlResult:
        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        src_dir = cfg.get_src_dir(self.name)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")

        cmd: list[str] = [
            sys.executable, str(src_dir / "run.py"), "crawl",
            "--out", str(out),
            "--max-depth", str(max_depth),
            "--concurrency", str(concurrency),
            "--delay", str(delay),
            "--pdf-backend", pdf_backend,
        ]
        if include_docs:
            cmd.append("--include-docs")
        if resume:
            cmd.append("--resume")
        if max_pages is not None:
            cmd += ["--max-pages", str(max_pages)]
        for s in (seeds or []):
            cmd += ["--seed", s]

        result = subprocess.run(cmd, env=env, cwd=str(src_dir),
                                capture_output=True, text=True)
        log = result.stdout + result.stderr
        if result.returncode == 0:
            return CrawlResult(success=True, output_dir=str(out), log=log)
        return CrawlResult(success=False, output_dir=str(out), log=log,
                           error=f"exit code {result.returncode}")
