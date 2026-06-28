"""wto_docs crawler — WTO Documents Online (docs.wto.org) fisheries series.

Pipeline (all plain HTTP, no Playwright required):
  Phase 1 (detail):   enumerate each series via FE_S_S006.aspx subject+collection
                      facet → docs_manifest/detail_{LABEL}.jsonl
  Phase 2 (download): download all downloadable PDFs via directdoc endpoint
                      → library/{series_folder}/

Optional Phase 0 (harvest): Playwright browser search (skip_harvest=True by default).

8 document series covered:
  G/FS   — 渔业补贴委员会
  TN/RL  — 谈判
  WT/MIN — 部长会
  WT/L   — 法律文本
  WT/LET — 接受书
  G/SCM  — 补贴通报
  WT/GC  — 总理事会
  JOB/RL — 室文件
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...base import BaseCrawler, CrawlResult
from ...config import get_config

log = logging.getLogger("wto_docs")

# Series definition: label, output folder name, detail filter (key+val), enum query.
SERIES = [
    {
        "label":            "GFS",
        "folder":           "01_G-FS_渔业补贴委员会",
        "detail_key":       "SymbolList",
        "detail_val":       '"G/FS*"',
        "enum_query":       "(@Symbol= G/FS/*)",
    },
    {
        "label":            "TN",
        "folder":           "02_TN_谈判",
        "detail_key":       "CollectionList",
        "detail_val":       '"TN"',
        "enum_query":       "(@Symbol= TN/RL/*)",
    },
    {
        "label":            "WTMIN",
        "folder":           "03_WT-MIN_部长会",
        "detail_key":       "SymbolList",
        "detail_val":       '"WT/MIN*"',
        "enum_query":       "(@Symbol= WT/MIN*)",
    },
    {
        "label":            "WTL",
        "folder":           "04_WT-L_法律文本",
        "detail_key":       "SymbolList",
        "detail_val":       '"WT/L*"',
        "enum_query":       "(@Symbol= WT/L/*)",
    },
    {
        "label":            "WTLET",
        "folder":           "05_WT-LET_接受书",
        "detail_key":       "SymbolList",
        "detail_val":       '"WT/LET*"',
        "enum_query":       "(@Symbol= WT/LET/*)",
    },
    {
        "label":            "GSCM",
        "folder":           "06_G-SCM_补贴通报",
        "detail_key":       "SymbolList",
        "detail_val":       '"G/SCM*"',
        "enum_query":       "(@Symbol= G/SCM/*)",
    },
    {
        "label":            "WTGC",
        "folder":           "07_WT-GC_总理事会",
        "detail_key":       "SymbolList",
        "detail_val":       '"WT/GC*"',
        "enum_query":       "(@Symbol= WT/GC/*)",
    },
    {
        "label":            "JOBRL",
        "folder":           "09_JOB-RL_室文件",
        "detail_key":       "SymbolList",
        "detail_val":       '"JOB/RL*"',
        "enum_query":       "(@Symbol= JOB/RL/*)",
    },
]


class WtoDocsCrawler(BaseCrawler):
    name        = "wto_docs"
    description = "WTO Documents Online — 8 fisheries series, plain-HTTP enumeration + directdoc download"

    def run(
        self,
        output_dir: str | None = None,
        *,
        # Phase 1
        skip_detail: bool = False,
        only_series: str | None = None,       # run only one series label, e.g. "GFS"
        delay: float = 0.8,
        resume: bool = True,
        # Phase 2
        skip_download: bool = False,
        fisheries_only: bool = False,
        # Optional Phase 0 (Playwright)
        skip_harvest: bool = True,            # disabled by default; needs playwright
        query: str = "fisheries subsidies",
        headed: bool = False,
        max_harvest_pages: int = 50,
        **_extra,
    ) -> CrawlResult:
        from .fetch.detail import run as detail_run
        from .fetch.download import download_listing

        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        manifest_dir = out / "docs_manifest"
        library_dir  = out / "library"
        manifest_dir.mkdir(parents=True, exist_ok=True)

        # ── Optional Phase 0: Playwright harvest ────────────────────────────────
        if not skip_harvest:
            try:
                from .fetch.harvest import run as harvest_run
                harvest_run(
                    query=query,
                    by_symbol=False,
                    out_dir=out,
                    headed=headed,
                    login=False,
                    max_pages=max_harvest_pages,
                )
                log.info("[harvest] done")
            except Exception as exc:
                log.warning("[harvest] failed (skipping): %s", exc)

        # ── Phase 1: enumerate + metadata via FE_S_S006 (plain HTTP) ────────────
        series_to_run = [s for s in SERIES
                         if only_series is None or s["label"] == only_series.upper()]
        logs: list[str] = []

        if not skip_detail:
            for s in series_to_run:
                jsonl = manifest_dir / f"detail_{s['label']}.jsonl"
                if resume and jsonl.exists():
                    log.info("[detail] %s: existing manifest found, skipping enumeration", s["label"])
                    logs.append(f"[{s['label']}] skipped (resume)")
                    continue
                log.info("[detail] %s: enumerating ...", s["label"])
                try:
                    recs = detail_run(
                        filter_key=s["detail_key"],
                        filter_val=s["detail_val"],
                        label=s["label"],
                        out_path=jsonl,
                        delay=delay,
                    )
                    dl = sum(1 for r in recs if r.get("downloadable"))
                    logs.append(f"[{s['label']}] {len(recs)} docs ({dl} downloadable)")
                except Exception as exc:
                    log.warning("[detail] %s failed: %s", s["label"], exc)
                    logs.append(f"[{s['label']}] FAILED: {exc}")

        # ── Phase 2: download PDFs ───────────────────────────────────────────────
        if not skip_download:
            for s in series_to_run:
                jsonl = manifest_dir / f"detail_{s['label']}.jsonl"
                if not jsonl.exists():
                    log.info("[download] %s: no manifest, skipping", s["label"])
                    continue
                dest = library_dir / s["folder"]
                log.info("[download] %s → %s", s["label"], dest)
                try:
                    stats = download_listing(
                        listing_path=jsonl,
                        dest_dir=dest,
                        delay=delay,
                        fisheries_only=fisheries_only,
                        resume=resume,
                    )
                    logs.append(
                        f"[{s['label']}] download ok={stats['ok']} failed={stats['failed']}"
                    )
                except Exception as exc:
                    log.warning("[download] %s failed: %s", s["label"], exc)
                    logs.append(f"[{s['label']}] download FAILED: {exc}")

        total_pdfs = sum(1 for _ in library_dir.rglob("*.pdf")) if library_dir.exists() else 0
        log.info("done. total PDFs in library: %d", total_pdfs)
        logs.append(f"total PDFs: {total_pdfs}")

        # ── Phase 3: build CSV + SQLite index ───────────────────────────────────
        if not skip_download and manifest_dir.exists():
            try:
                from .process import build_index
                idx = build_index(
                    manifest_dir=manifest_dir,
                    library_dir=library_dir,
                    out_dir=out,
                )
                logs.append(
                    f"[index] {idx['total']} rows  "
                    f"downloadable={idx['downloadable']}  restricted={idx['restricted']}"
                )
                log.info("[index] %d rows written", idx["total"])
            except Exception as exc:
                log.warning("[index] failed: %s", exc)
                logs.append(f"[index] FAILED: {exc}")

        return CrawlResult(success=True, output_dir=str(out), log="\n".join(logs))
