"""Command-line interface for negotiation_crawler.

Usage:
    python -m negotiation_crawler list
    python -m negotiation_crawler run fishery_book --out /data/out
    python -m negotiation_crawler run iotc --out /data/out --set enrich=true
    python -m negotiation_crawler run iotc --out /data/out --set pdf_dir=/mnt/nas/pdfs
    python -m negotiation_crawler run wto_site --out /data/out --set max_depth=4
    python -m negotiation_crawler run wto_docs --out /data/out --set skip_harvest=true
    python -m negotiation_crawler run all --out /data/out
    python -m negotiation_crawler xlsx iotc --out /data/out
    python -m negotiation_crawler xlsx iotc --db /data/out/manifest.sqlite --xlsx /data/out/index.xlsx
    python -m negotiation_crawler dedup /data/out --dry-run
    python -m negotiation_crawler serve --port 8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parse_set_args(set_args: list[str] | None) -> dict:
    extra: dict = {}
    for kv in (set_args or []):
        if "=" not in kv:
            print(f"ERROR: --set expects key=value, got: {kv}", file=sys.stderr)
            sys.exit(2)
        k, v = kv.split("=", 1)
        if v.lower() == "true":
            extra[k] = True
        elif v.lower() == "false":
            extra[k] = False
        else:
            try:
                extra[k] = int(v)
            except ValueError:
                try:
                    extra[k] = float(v)
                except ValueError:
                    extra[k] = v
    return extra


def _cmd_list(_args: argparse.Namespace) -> int:
    from . import crawlers as reg
    print(f"{'Name':<16} Description")
    print("-" * 60)
    for name, crawler in reg.all_crawlers().items():
        print(f"{name:<16} {crawler.description}")
    return 0


def _run_one(crawler_name: str, out: str | None, extra: dict, verbose: bool) -> bool:
    from . import crawlers as reg
    crawler = reg.get(crawler_name)
    print(f"\n[{crawler_name}] starting...")
    result = crawler.run(out, **extra)
    if result.success:
        print(f"[{crawler_name}] OK → {result.output_dir}")
        if verbose and result.log:
            print(result.log)
        return True
    else:
        print(f"[{crawler_name}] FAILED: {result.error}", file=sys.stderr)
        if result.log:
            print(result.log, file=sys.stderr)
        return False


def _cmd_run(args: argparse.Namespace) -> int:
    extra = _parse_set_args(args.set)

    if args.crawler == "all":
        from . import crawlers as reg
        from .config import get_config
        from .dedup import deduplicate

        cfg = get_config()
        base = Path(args.out) if args.out else Path("./output")
        failures = []

        for name in reg.all_crawlers():
            crawler_out = str(base / name) if not args.out else args.out
            ok = _run_one(name, crawler_out, extra, args.verbose)
            if not ok:
                failures.append(name)

        # global cross-crawler deduplication
        print(f"\n[dedup] scanning {base} for cross-crawler duplicates...")
        try:
            stats = deduplicate(base, dry_run=args.dry_run)
            print(f"[dedup] {stats['total']} files, {stats['unique']} unique, "
                  f"{stats['removed']} {'would be removed' if args.dry_run else 'removed'}, "
                  f"{stats['saved_bytes']/1024/1024:.1f} MB freed")
        except Exception as exc:
            print(f"[dedup] warning: {exc}", file=sys.stderr)

        if failures:
            print(f"\nFailed crawlers: {failures}", file=sys.stderr)
            return 1
        return 0
    else:
        ok = _run_one(args.crawler, args.out, extra, args.verbose)
        return 0 if ok else 1


def _cmd_xlsx(args: argparse.Namespace) -> int:
    """Rebuild an index.xlsx from an existing manifest without re-crawling."""
    module = args.module

    if module == "iotc":
        from pathlib import Path
        from .crawlers.iotc.process.xlsx_builder import build_xlsx

        if args.db:
            db_path = Path(args.db).resolve()
        elif args.out:
            db_path = Path(args.out).resolve() / "manifest.sqlite"
        else:
            print("ERROR: provide --out or --db", file=sys.stderr)
            return 2

        if args.xlsx:
            xlsx_path = Path(args.xlsx).resolve()
        elif args.out:
            xlsx_path = Path(args.out).resolve() / "index.xlsx"
        else:
            xlsx_path = db_path.parent / "index.xlsx"

        if not db_path.exists():
            print(f"ERROR: manifest not found: {db_path}", file=sys.stderr)
            return 1

        print(f"[xlsx] reading  {db_path}")
        print(f"[xlsx] writing  {xlsx_path}")
        build_xlsx(db_path, xlsx_path)
        print(f"[xlsx] done → {xlsx_path}")
        return 0

    elif module == "wto_docs":
        from pathlib import Path
        from .crawlers.wto_docs.process import build_index

        out = Path(args.out).resolve() if args.out else None
        if not out:
            print("ERROR: --out required for wto_docs xlsx", file=sys.stderr)
            return 2
        manifest_dir = out / "docs_manifest"
        library_dir  = out / "library"
        if not manifest_dir.exists():
            print(f"ERROR: docs_manifest not found under {out}", file=sys.stderr)
            return 1
        idx = build_index(manifest_dir=manifest_dir, library_dir=library_dir, out_dir=out)
        print(f"[xlsx] done → {out}/index.xlsx  ({idx['total']} rows)")
        return 0

    elif module == "wto_site":
        from pathlib import Path
        from .crawlers.wto_site.process import build_xlsx

        out = Path(args.out).resolve() if args.out else None
        if not out:
            print("ERROR: --out required for wto_site xlsx", file=sys.stderr)
            return 2
        xlsx = build_xlsx(out)
        if xlsx:
            print(f"[xlsx] done → {xlsx}")
        else:
            print("[xlsx] no manifest.jsonl found — nothing to build", file=sys.stderr)
            return 1
        return 0

    elif module == "fishery_book":
        from pathlib import Path
        from .crawlers.fishery_book.process import build_xlsx

        out = Path(args.out).resolve() if args.out else None
        if not out:
            print("ERROR: --out required for fishery_book xlsx", file=sys.stderr)
            return 2
        db_path   = Path(args.db).resolve() if args.db else out / "manifest.sqlite"
        xlsx_path = Path(args.xlsx).resolve() if args.xlsx else out / "index.xlsx"
        if not db_path.exists():
            print(f"ERROR: manifest not found: {db_path}", file=sys.stderr)
            return 1
        print(f"[xlsx] reading  {db_path}")
        build_xlsx(db_path, xlsx_path)
        print(f"[xlsx] done → {xlsx_path}")
        return 0

    else:
        print(f"ERROR: xlsx not supported for module '{module}'", file=sys.stderr)
        return 2


def _cmd_export(args: argparse.Namespace) -> int:
    from pathlib import Path
    from .export.unified_db import MYSQL_DDL, import_all

    if args.ddl:
        print(MYSQL_DDL)
        return 0

    if not args.base:
        print("ERROR: --base <output_dir> is required", file=sys.stderr)
        return 2

    base    = Path(args.base).resolve()
    db_path = Path(args.db).resolve() if args.db else base / "unified.sqlite"
    modules = args.module or None   # None → all

    print(f"[export] base    : {base}")
    print(f"[export] dest db : {db_path}")
    print(f"[export] modules : {modules or 'all'}")

    results = import_all(base, db_path, modules=modules)
    total   = 0
    for mod, n in results.items():
        status = f"{n} rows" if n else "skipped (no xlsx found)"
        print(f"  [{mod}] {status}")
        total += n
    print(f"[export] done → {total} total rows in {db_path}")
    return 0


def _cmd_dedup(args: argparse.Namespace) -> int:
    from .dedup import deduplicate
    stats = deduplicate(Path(args.directory), dry_run=args.dry_run)
    print(f"total={stats['total']} unique={stats['unique']} "
          f"removed={stats['removed']} saved={stats['saved_bytes']/1024/1024:.1f}MB")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    from .api import app
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="negotiation-crawler",
        description="Unified crawler hub for fishery negotiation materials",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list available crawler modules")

    r = sub.add_parser("run", help="run one crawler or all of them")
    r.add_argument(
        "crawler",
        choices=["fishery_book", "iotc", "wto_site", "wto_docs", "all"],
        help="which module to run; 'all' runs every module then cross-deduplicates",
    )
    r.add_argument("--out", default=None,
                   help="output directory (overrides config.yaml default; "
                        "for 'all', this becomes the base dir with per-crawler subdirs)")
    r.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="pass extra options to the crawler (repeatable)")
    r.add_argument("--dry-run", action="store_true",
                   help="(only with 'all') report duplicates but do not delete")
    r.add_argument("-v", "--verbose", action="store_true")

    x = sub.add_parser("xlsx", help="rebuild index.xlsx from an existing manifest (no re-crawl)")
    x.add_argument(
        "module",
        choices=["iotc", "wto_docs", "wto_site", "fishery_book"],
        help="which module's xlsx to rebuild",
    )
    x.add_argument("--out", default=None,
                   help="output directory containing the manifest "
                        "(db and xlsx default to {out}/manifest.sqlite and {out}/index.xlsx)")
    x.add_argument("--db", default=None,
                   help="explicit path to manifest.sqlite (overrides --out for db location)")
    x.add_argument("--xlsx", default=None,
                   help="explicit output path for index.xlsx (overrides --out for xlsx location)")

    e = sub.add_parser("export", help="import all xlsx into a unified SQLite/MySQL document table")
    e.add_argument("--base", default=None,
                   help="base output directory (contains iotc/, wto_docs/, wto_site/, fishery_book/)")
    e.add_argument("--db", default=None,
                   help="destination SQLite path (default: {base}/unified.sqlite)")
    e.add_argument("--module", action="append", metavar="MODULE",
                   choices=["iotc", "wto_docs", "wto_site", "fishery_book"],
                   help="import only specific modules (repeatable; default: all)")
    e.add_argument("--ddl", action="store_true",
                   help="print MySQL DDL and exit (for creating table in MySQL)")

    d = sub.add_parser("dedup", help="deduplicate already-downloaded files by SHA-256")
    d.add_argument("directory", help="root output directory to scan")
    d.add_argument("--dry-run", action="store_true",
                   help="report duplicates without deleting")

    s = sub.add_parser("serve", help="start FastAPI HTTP server for Java integration")
    s.add_argument("--host", default=None)
    s.add_argument("--port", type=int, default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "list":
        return _cmd_list(args)
    elif args.cmd == "run":
        return _cmd_run(args)
    elif args.cmd == "xlsx":
        return _cmd_xlsx(args)
    elif args.cmd == "export":
        return _cmd_export(args)
    elif args.cmd == "dedup":
        return _cmd_dedup(args)
    elif args.cmd == "serve":
        from .config import get_config
        cfg = get_config()
        if args.host is None:
            args.host = cfg.api_host()
        if args.port is None:
            args.port = cfg.api_port()
        return _cmd_serve(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
