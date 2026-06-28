"""wto_site crawler — WTO fisheries subsidies site pages → Markdown corpus."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ...base import BaseCrawler, CrawlResult
from ...config import get_config

log = logging.getLogger("wto_site")


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
        from . import config
        from .process.pipeline import Crawler, load_visited

        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )

        try:
            crawler = Crawler(
                out,
                max_depth=max_depth,
                concurrency=concurrency,
                delay_s=delay,
                include_docs=include_docs,
                max_pages=max_pages,
                pdf_backend=pdf_backend,
            )
            if resume:
                n, retry = load_visited(out, crawler)
                log.info("resume: %d done URLs skipped, %d errored will retry", n, retry)

            run_seeds = seeds if seeds else config.SEEDS
            asyncio.run(crawler.run(run_seeds))
            log.info("done. kept=%d", crawler.kept)

            try:
                from .process import build_xlsx
                xlsx = build_xlsx(out)
                if xlsx:
                    log.info("xlsx -> %s", xlsx)
            except Exception as exc:
                log.warning("xlsx build failed (non-fatal): %s", exc)

            return CrawlResult(success=True, output_dir=str(out))
        except Exception as exc:
            return CrawlResult(success=False, output_dir=str(out), error=str(exc))
