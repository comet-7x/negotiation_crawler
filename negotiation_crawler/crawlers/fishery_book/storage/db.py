"""SQLite manifest: persist one row per seed so runs are resumable and idempotent."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..models import BookRecord, Status

_SCHEMA = """
CREATE TABLE IF NOT EXISTS manifest (
    seed_id        TEXT PRIMARY KEY,
    category       TEXT,
    year           INTEGER,
    title          TEXT,
    filename       TEXT,
    download_url   TEXT,
    pages          INTEGER,
    size_kb        REAL,
    fmt            TEXT,
    status         TEXT,
    match_score    REAL,
    handle         TEXT,
    item_uuid      TEXT,
    bitstream_uuid TEXT,
    source         TEXT,
    local_path     TEXT,
    note           TEXT,
    raw            TEXT,
    updated_at     TEXT DEFAULT (datetime('now'))
);
"""


class Manifest:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Manifest":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def completed_seed_ids(self) -> set[str]:
        """Seeds already resolved to a downloadable/legacy file (safe to skip)."""
        rows = self.conn.execute(
            "SELECT seed_id FROM manifest WHERE status IN (?, ?)",
            (Status.FOUND.value, Status.LEGACY.value),
        ).fetchall()
        return {r["seed_id"] for r in rows}

    def upsert(self, rec: BookRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO manifest (
                seed_id, category, year, title, filename, download_url, pages,
                size_kb, fmt, status, match_score, handle, item_uuid,
                bitstream_uuid, source, local_path, note, raw, updated_at
            ) VALUES (
                :seed_id, :category, :year, :title, :filename, :download_url, :pages,
                :size_kb, :fmt, :status, :match_score, :handle, :item_uuid,
                :bitstream_uuid, :source, :local_path, :note, :raw, datetime('now')
            )
            ON CONFLICT(seed_id) DO UPDATE SET
                category=excluded.category, year=excluded.year, title=excluded.title,
                filename=excluded.filename, download_url=excluded.download_url,
                pages=excluded.pages, size_kb=excluded.size_kb, fmt=excluded.fmt,
                status=excluded.status, match_score=excluded.match_score,
                handle=excluded.handle, item_uuid=excluded.item_uuid,
                bitstream_uuid=excluded.bitstream_uuid, source=excluded.source,
                local_path=excluded.local_path, note=excluded.note, raw=excluded.raw,
                updated_at=datetime('now')
            """,
            {
                "seed_id": rec.seed_id,
                "category": rec.category,
                "year": rec.year,
                "title": rec.title,
                "filename": rec.filename,
                "download_url": rec.download_url,
                "pages": rec.pages,
                "size_kb": rec.size_kb,
                "fmt": rec.fmt,
                "status": rec.status.value,
                "match_score": rec.match_score,
                "handle": rec.handle,
                "item_uuid": rec.item_uuid,
                "bitstream_uuid": rec.bitstream_uuid,
                "source": rec.source,
                "local_path": rec.local_path,
                "note": rec.note,
                "raw": json.dumps(rec.to_dict(), ensure_ascii=False),
            },
        )
        self.conn.commit()

    def all_records(self) -> list[BookRecord]:
        rows = self.conn.execute("SELECT * FROM manifest ORDER BY category, year, seed_id").fetchall()
        out: list[BookRecord] = []
        for r in rows:
            out.append(
                BookRecord(
                    category=r["category"],
                    year=r["year"],
                    filename=r["filename"],
                    title=r["title"],
                    download_url=r["download_url"],
                    pages=r["pages"],
                    size_kb=r["size_kb"],
                    fmt=r["fmt"],
                    seed_id=r["seed_id"],
                    status=Status(r["status"]),
                    match_score=r["match_score"],
                    handle=r["handle"],
                    item_uuid=r["item_uuid"],
                    bitstream_uuid=r["bitstream_uuid"],
                    source=r["source"],
                    local_path=r["local_path"],
                    note=r["note"] or "",
                )
            )
        return out
