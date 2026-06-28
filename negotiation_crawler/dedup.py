"""Cross-crawler global deduplication by SHA-256.

Scans a root output directory for downloaded files, groups them by content hash,
and removes duplicate copies — keeping the alphabetically-first path as canonical.

Usage (programmatic):
    from negotiation_crawler.dedup import deduplicate
    report = deduplicate(Path("/data/output"))

Usage (CLI):
    python -m negotiation_crawler dedup /data/output
    python -m negotiation_crawler dedup /data/output --dry-run
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger("negotiation_crawler.dedup")

_DEDUP_SUFFIXES = {".pdf", ".doc", ".docx", ".xlsx", ".xls", ".ppt", ".pptx"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def deduplicate(
    root: Path,
    suffixes: set[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Scan root for duplicate files by SHA-256.

    Args:
        root:      Directory to scan (recursively).
        suffixes:  File extensions to check. Defaults to PDF + Office formats.
        dry_run:   If True, report but do not delete anything.

    Returns a dict with keys: total, unique, removed, saved_bytes, report.
    """
    suffixes = suffixes or _DEDUP_SUFFIXES
    groups: dict[str, list[Path]] = defaultdict(list)

    log.info("scanning %s ...", root)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in suffixes:
            continue
        try:
            h = sha256_file(path)
            groups[h].append(path)
        except OSError as e:
            log.warning("could not hash %s: %s", path, e)

    total = sum(len(v) for v in groups.values())
    unique = len(groups)
    removed = 0
    saved_bytes = 0
    report_rows: list[dict] = []

    for h, paths in groups.items():
        if len(paths) == 1:
            continue
        canonical = paths[0]   # alphabetically first (sorted above)
        for dup in paths[1:]:
            size = dup.stat().st_size
            report_rows.append({
                "sha256": h,
                "canonical": str(canonical),
                "duplicate": str(dup),
                "size_bytes": size,
            })
            if not dry_run:
                try:
                    dup.unlink()
                    removed += 1
                    saved_bytes += size
                    log.info("removed dup: %s == %s", dup.name, canonical.name)
                except OSError as e:
                    log.warning("could not remove %s: %s", dup, e)
            else:
                removed += 1
                saved_bytes += size
                log.info("[dry-run] would remove: %s == %s", dup.name, canonical.name)

    # Write report alongside the output
    report_path = root / "dedup_report.json"
    report_path.write_text(
        json.dumps(
            {"dry_run": dry_run, "total": total, "unique": unique,
             "removed": removed, "saved_bytes": saved_bytes,
             "duplicates": report_rows},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    log.info(
        "dedup done: %d files scanned, %d unique, %d %s, %.1f MB %s",
        total, unique, removed,
        "would be removed" if dry_run else "removed",
        saved_bytes / 1024 / 1024,
        "(dry-run)" if dry_run else "freed",
    )
    return {
        "total": total, "unique": unique,
        "removed": removed, "saved_bytes": saved_bytes,
        "report": report_rows,
    }
