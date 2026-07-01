"""SQLite storage layer — deduplication, frontier queue, and audit evidence.

Design:
- urls.url_canonical UNIQUE → database guarantees each URL is fetched once.
- Nodes (urls) and edges (links) are stored separately; a URL may be
  discovered by multiple parents but is only fetched once.
- All state is persisted: interrupt and resume at any time.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS urls (
    id              INTEGER PRIMARY KEY,
    url_canonical   TEXT UNIQUE NOT NULL,
    url_raw         TEXT NOT NULL,
    kind            TEXT,            -- page | file
    scope_action    TEXT,            -- fetch | collect | skip
    scope_reason    TEXT,
    hops_outside    INTEGER DEFAULT 0,
    fetch_status    TEXT DEFAULT 'pending',  -- pending | done | failed | skipped
    http_status     INTEGER,
    content_type    TEXT,
    content_hash    TEXT,            -- body sha1, used for content-level dedup
    doctype         TEXT,
    title           TEXT,
    local_path      TEXT,
    size_bytes      INTEGER,
    needs_render    INTEGER DEFAULT 0,
    error           TEXT,
    discovered_at   REAL,
    fetched_at      REAL,
    human_verdict   TEXT             -- audit column: keep | drop | recheck
);
CREATE TABLE IF NOT EXISTS links (
    from_id     INTEGER NOT NULL,
    to_id       INTEGER NOT NULL,
    anchor      TEXT,
    PRIMARY KEY (from_id, to_id)
);
CREATE INDEX IF NOT EXISTS idx_fetch_status ON urls(fetch_status);
CREATE INDEX IF NOT EXISTS idx_content_hash ON urls(content_hash);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_url(self, canonical: str, raw: str, kind: str, action: str,
                   reason: str, hops: int) -> int:
        """Register a discovered URL. Ignores duplicates; returns the row id."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO urls "
            "(url_canonical,url_raw,kind,scope_action,scope_reason,hops_outside,"
            " fetch_status,discovered_at) VALUES (?,?,?,?,?,?,?,?)",
            (canonical, raw, kind, action, reason, hops,
             "pending" if action in ("fetch", "collect") else "skipped",
             time.time()),
        )
        if cur.lastrowid:
            self.conn.commit()
            return cur.lastrowid
        row = self.conn.execute(
            "SELECT id FROM urls WHERE url_canonical=?", (canonical,)
        ).fetchone()
        return row["id"]

    def add_link(self, from_id: int, to_id: int, anchor: str) -> None:
        if from_id == to_id:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO links (from_id,to_id,anchor) VALUES (?,?,?)",
            (from_id, to_id, (anchor or "")[:300]),
        )

    def next_pending(self):
        return self.conn.execute(
            "SELECT * FROM urls WHERE fetch_status='pending' "
            "ORDER BY hops_outside ASC, id ASC LIMIT 1"
        ).fetchone()

    def seen_hash(self, content_hash: str, exclude_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT local_path FROM urls WHERE content_hash=? AND id!=? "
            "AND content_hash IS NOT NULL LIMIT 1",
            (content_hash, exclude_id),
        ).fetchone()
        return row["local_path"] if row else None

    def mark(self, url_id: int, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [url_id]
        self.conn.execute(f"UPDATE urls SET {cols} WHERE id=?", vals)
        self.conn.commit()

    def counts(self) -> dict:
        return {
            "total":   self.conn.execute("SELECT COUNT(*) c FROM urls").fetchone()["c"],
            "pending": self.conn.execute(
                "SELECT COUNT(*) c FROM urls WHERE fetch_status='pending'"
            ).fetchone()["c"],
            "done":    self.conn.execute(
                "SELECT COUNT(*) c FROM urls WHERE fetch_status='done'"
            ).fetchone()["c"],
        }

    def all_rows(self):
        return self.conn.execute("SELECT * FROM urls ORDER BY id").fetchall()

    def close(self):
        self.conn.commit()
        self.conn.close()
