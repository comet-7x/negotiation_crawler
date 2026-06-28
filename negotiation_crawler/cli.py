"""Command-line interface for negotiation_crawler.

Usage:
    python -m negotiation_crawler list
    python -m negotiation_crawler run fishery_book --out /data/out
    python -m negotiation_crawler run iotc --out /data/out --set enrich=true --set build_xlsx=true
    python -m negotiation_crawler run wto_site --out /data/out --set max_depth=4
    python -m negotiation_crawler run wto_docs --out /data/out --set skip_harvest=true
    python -m negotiation_crawler serve --port 8000
"""

from __future__ import annotations

import argparse
import sys


def _cmd_list(_args: argparse.Namespace) -> int:
    from . import crawlers as reg
    print(f"{'Name':<16} Description")
    print("-" * 60)
    for name, crawler in reg.all_crawlers().items():
        print(f"{name:<16} {crawler.description}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from . import crawlers as reg
    crawler = reg.get(args.crawler)

    extra: dict = {}
    for kv in (args.set or []):
        if "=" not in kv:
            print(f"ERROR: --set expects key=value, got: {kv}", file=sys.stderr)
            return 2
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

    result = crawler.run(args.out, **extra)

    if result.success:
        print(f"[OK] output: {result.output_dir}")
        if args.verbose and result.log:
            print(result.log)
        return 0
    else:
        print(f"[FAILED] {result.error}", file=sys.stderr)
        if result.log:
            print(result.log, file=sys.stderr)
        return 1


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

    r = sub.add_parser("run", help="run a crawler module")
    r.add_argument("crawler",
                   choices=["fishery_book", "iotc", "wto_site", "wto_docs"],
                   help="which crawler to run")
    r.add_argument("--out", default=None,
                   help="output directory (overrides config.yaml default)")
    r.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="pass extra options to the crawler (repeatable)")
    r.add_argument("-v", "--verbose", action="store_true",
                   help="print full crawler log on success")

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
