"""Subprocess helper: patches iotc config with a custom output directory, then runs.

Called exclusively by IotcCrawler.run() — not a public API.
Env var IOTC_SRC_DIR must point to the iotc_crawler project directory.

    python _iotc_runner.py --out /custom/out [--enrich] [--build-xlsx] ...
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-manifest", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--enrich", action="store_true")
    ap.add_argument("--build-xlsx", action="store_true")
    ap.add_argument("--all-langs", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", type=str, default=None)
    args = ap.parse_args()

    output_dir = Path(args.out).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    iotc_src = os.environ.get("IOTC_SRC_DIR")
    if not iotc_src:
        print("ERROR: IOTC_SRC_DIR env var not set", file=sys.stderr)
        return 1
    sys.path.insert(0, iotc_src)

    # Patch the config module before any other iotc imports touch it
    import config as iotc_config  # type: ignore[import]
    iotc_config.OUT_DIR = output_dir
    iotc_config.DB_PATH = output_dir / "manifest.sqlite"
    iotc_config.PDF_DIR = output_dir / "pdfs"
    iotc_config.XLSX_PATH = output_dir / "iotc_documents.xlsx"

    from main import run  # type: ignore[import]

    run_args = argparse.Namespace(
        self_test=False,
        skip_manifest=args.skip_manifest,
        list_only=args.list_only,
        enrich=args.enrich,
        build_xlsx=args.build_xlsx,
        fix_countries=False,
        all_langs=args.all_langs,
        limit=args.limit,
        only=args.only,
    )
    return run(run_args)


if __name__ == "__main__":
    raise SystemExit(main())
