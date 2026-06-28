"""Wrapper for iotc_crawler (IOTC Drupal document repository)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..base import BaseCrawler, CrawlResult
from ..config import get_config

_RUNNER = Path(__file__).parent / "_iotc_runner.py"


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
        **_extra,
    ) -> CrawlResult:
        cfg = get_config()
        out = Path(output_dir or cfg.get_default_out(self.name)).resolve()
        out.mkdir(parents=True, exist_ok=True)

        src_dir = cfg.get_src_dir(self.name)

        env = os.environ.copy()
        env["IOTC_SRC_DIR"] = str(src_dir)

        cmd: list[str] = [sys.executable, str(_RUNNER), "--out", str(out)]
        if skip_manifest:
            cmd.append("--skip-manifest")
        if list_only:
            cmd.append("--list-only")
        if enrich:
            cmd.append("--enrich")
        if build_xlsx:
            cmd.append("--build-xlsx")
        if all_langs:
            cmd.append("--all-langs")
        if limit is not None:
            cmd += ["--limit", str(limit)]
        if only:
            cmd += ["--only", only]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        log = result.stdout + result.stderr
        if result.returncode == 0:
            return CrawlResult(success=True, output_dir=str(out), log=log)
        return CrawlResult(success=False, output_dir=str(out), log=log,
                           error=f"exit code {result.returncode}")
