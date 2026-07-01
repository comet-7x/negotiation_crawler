"""wto_site crawler — WTO fisheries subsidies site pages → Markdown corpus."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ...base import BaseCrawler, CrawlResult
from ...config import get_config

log = logging.getLogger("wto_site")


def _setup_logging(out: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(out / "crawl.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


class WtoSiteCrawler(BaseCrawler):
    name = "wto_site"
    description = "WTO fisheries subsidies agreement main site → Markdown corpus (English only)"

    def run(
        self,
        output_dir: str | None = None,
        *,
        delay: float = 1.0,
        max_pages: int | None = None,
        resume: bool = False,
        respect_robots: bool = True,
        max_hops_outside: int = 1,
        **_extra,
    ) -> CrawlResult:
        from .config import Config
        from .process.pipeline import Crawler
        from .process import build_xlsx

        app_cfg = get_config()
        out = Path(output_dir or app_cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        _setup_logging(out)

        db_path = out / "crawl.db"
        if not resume and db_path.exists():
            db_path.unlink()
            log.info("removed existing crawl.db (use resume=True to continue a previous run)")

        cfg = Config(
            out_dir=str(out),
            request_delay=delay,
            max_pages=max_pages,
            respect_robots=respect_robots,
            max_hops_outside=max_hops_outside,
        )

        try:
            crawler = Crawler(cfg)
            counts = crawler.run()
            crawler.close()
            log.info("done. done=%d total=%d", counts.get("done", 0), counts.get("total", 0))

            try:
                xlsx = build_xlsx(out)
                if xlsx:
                    log.info("xlsx -> %s", xlsx)
            except Exception as exc:
                log.warning("xlsx build failed (non-fatal): %s", exc)

            return CrawlResult(success=True, output_dir=str(out))
        except Exception as exc:
            log.exception("crawl failed")
            return CrawlResult(success=False, output_dir=str(out), error=str(exc))
