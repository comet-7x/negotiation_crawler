"""fishery_book crawler — FAO DSpace REST API."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...base import BaseCrawler, CrawlResult
from ...config import get_config


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
        seeds: str | None = None,
        **_extra,
    ) -> CrawlResult:
        from .config import Settings
        from .pipeline import load_seeds, run as pipeline_run

        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        settings = Settings(
            out_dir=out,
            pdf_dir=out / "pdfs",
            db_path=out / "manifest.sqlite",
            xlsx_path=out / "index.xlsx",
            concurrency=concurrency,
            download=not no_download,
            http2=not http1,
            proxy=proxy,
        )

        seeds_path = Path(seeds) if seeds else Path(__file__).parent / "seeds.json"
        all_seeds = load_seeds(seeds_path)
        if category:
            wanted = {c.lower() for c in category}
            all_seeds = [s for s in all_seeds if s.category.lower() in wanted]
        if limit:
            all_seeds = all_seeds[:limit]

        if not all_seeds:
            return CrawlResult(success=False, output_dir=str(out),
                               error="no seeds selected")
        try:
            asyncio.run(pipeline_run(settings, all_seeds, resume=not no_resume))
            return CrawlResult(success=True, output_dir=str(out))
        except Exception as exc:
            return CrawlResult(success=False, output_dir=str(out), error=str(exc))
