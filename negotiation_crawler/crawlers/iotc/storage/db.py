"""
data_storer/db.py — SQLite manifest operations.

Schema is backwards-compatible with the original iotc_harvest.py manifest.sqlite.
New columns (doc_type_zh, category_group, file_size_kb, page_count) are added
via ALTER TABLE on first run so existing databases upgrade automatically.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS docs (
            pdf_url       TEXT PRIMARY KEY,
            reference     TEXT,
            doc_type      TEXT,
            doc_type_zh   TEXT,
            category_group TEXT,
            title         TEXT,
            landing_url   TEXT,
            circulated    TEXT,
            language      TEXT,
            meta_type     TEXT,
            meeting       TEXT,
            session       TEXT,
            year          TEXT,
            authors       TEXT,
            country       TEXT,
            local_path    TEXT,
            sha256        TEXT,
            file_size_kb  REAL,
            page_count    INTEGER,
            status        TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after v0 without breaking existing databases."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(docs)")}
    new_cols = [
        ("doc_type_zh",    "TEXT"),
        ("category_group", "TEXT"),
        ("file_size_kb",   "REAL"),
        ("page_count",     "INTEGER"),
    ]
    for col, typ in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE docs ADD COLUMN {col} {typ}")
    conn.commit()


def upsert_row(
    conn: sqlite3.Connection,
    pdf_url: str,
    reference: str,
    doc_type: str,
    doc_type_zh: str,
    category_group: str,
    title: str,
    landing_url: str,
    circulated: str,
    language: str,
) -> bool:
    """Insert if new; skip if already present. Returns True when inserted."""
    if conn.execute("SELECT 1 FROM docs WHERE pdf_url=?", (pdf_url,)).fetchone():
        return False
    conn.execute(
        """INSERT INTO docs
           (pdf_url, reference, doc_type, doc_type_zh, category_group,
            title, landing_url, circulated, language)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (pdf_url, reference, doc_type, doc_type_zh, category_group,
         title, landing_url, circulated, language),
    )
    conn.commit()
    return True


def update_enrichment(conn: sqlite3.Connection, pdf_url: str, fields: dict[str, str]) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE docs SET {sets} WHERE pdf_url=?", (*fields.values(), pdf_url))
    conn.commit()


def update_download(
    conn: sqlite3.Connection,
    pdf_url: str,
    local_path: str,
    sha256: str,
    file_size_kb: float,
    page_count: int,
    status: str,
) -> None:
    conn.execute(
        """UPDATE docs SET local_path=?, sha256=?, file_size_kb=?,
           page_count=?, status=? WHERE pdf_url=?""",
        (local_path, sha256, file_size_kb, page_count, status, pdf_url),
    )
    conn.commit()


def pending_downloads(
    conn: sqlite3.Connection,
    doc_type_filter: str | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return (pdf_url, reference, doc_type, circulated) for pending rows."""
    sql = "SELECT pdf_url, reference, doc_type, circulated FROM docs WHERE status='pending'"
    params: tuple = ()
    if doc_type_filter:
        sql += " AND doc_type=?"
        params = (doc_type_filter,)
    return conn.execute(sql, params).fetchall()


def pending_enrichment(
    conn: sqlite3.Connection,
    doc_type_filter: str | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return (pdf_url, landing_url, title, country) rows that still need enrichment."""
    sql = (
        "SELECT pdf_url, landing_url, title, country FROM docs "
        "WHERE landing_url!='' AND (meta_type IS NULL OR meta_type='')"
    )
    params: tuple = ()
    if doc_type_filter:
        sql += " AND doc_type=?"
        params = (doc_type_filter,)
    return conn.execute(sql, params).fetchall()


def get_stats(conn: sqlite3.Connection) -> dict[str, int]:
    total   = conn.execute("SELECT count(*) FROM docs").fetchone()[0]
    pending = conn.execute("SELECT count(*) FROM docs WHERE status='pending'").fetchone()[0]
    done    = conn.execute("SELECT count(*) FROM docs WHERE status='downloaded'").fetchone()[0]
    failed  = conn.execute("SELECT count(*) FROM docs WHERE status='failed'").fetchone()[0]
    return {"total": total, "pending": pending, "downloaded": done, "failed": failed}
