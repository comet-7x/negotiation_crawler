"""iotc crawler — IOTC Drupal document repository."""

from __future__ import annotations

import logging
from pathlib import Path

from ...base import BaseCrawler, CrawlResult
from ...config import get_config

log = logging.getLogger("iotc")


class IotcCrawler(BaseCrawler):
    name = "iotc"
    description = "IOTC (Indian Ocean Tuna Commission) documents — all 31 document types"

    def run(
        self,
        output_dir: str | None = None,
        *,
        skip_manifest: bool = False,
        list_only: bool = False,
        enrich: bool = True,
        build_xlsx: bool = True,
        all_langs: bool = False,
        limit: int | None = None,
        only: str | None = None,
        pdf_dir: str | None = None,   # override default {out}/pdfs/
        **_extra,
    ) -> CrawlResult:
        from .fetch.crawler import build_manifest, enrich_metadata, download_pdfs
        from .process.xlsx_builder import build_xlsx as _build_xlsx
        from .storage.db import init_db, get_stats

        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        db_path        = out / "manifest.sqlite"
        resolved_pdfs  = Path(pdf_dir).resolve() if pdf_dir else out / "pdfs"
        xlsx_path      = out / "index.xlsx"

        try:
            xlsx_only = build_xlsx and not enrich and not list_only

            if not skip_manifest and not xlsx_only:
                log.info("=== Phase 1: build manifest ===")
                build_manifest(db_path=db_path, english_only=not all_langs, limit=limit)

            if enrich:
                log.info("=== Phase 2: enrich metadata ===")
                enrich_metadata(db_path=db_path, limit=limit, doc_type_filter=only)

            if not list_only and not xlsx_only:
                log.info("=== Phase 3: download PDFs ===")
                download_pdfs(db_path=db_path, pdf_dir=resolved_pdfs,
                              limit=limit, doc_type_filter=only)

            if build_xlsx or list_only:
                log.info("=== Phase 4: build Excel report ===")
                _build_xlsx(db_path, xlsx_path)

            conn = init_db(db_path)
            stats = get_stats(conn)
            conn.close()
            log.info("Done. total=%d downloaded=%d pending=%d failed=%d",
                     stats["total"], stats["downloaded"], stats["pending"], stats["failed"])
            return CrawlResult(success=True, output_dir=str(out))
        except Exception as exc:
            return CrawlResult(success=False, output_dir=str(out), error=str(exc))
