"""Crawl orchestration: SQLite-backed frontier, link discovery, content storage.

Main loop: pop pending URL → fetch → discover links → persist → repeat until
frontier is empty or max_pages reached. All state lives in SQLite, so a
killed process can resume by re-running with the same out_dir.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..classifier import classify
from ..config import Config
from ..fetch import Fetcher
from ..fetch.urlrules import canonicalize, classify_url
from ..storage.db import DB
from .extract import (
    content_hash, decode_bytes, extract_links, front_matter,
    get_title, looks_like_js_shell, to_markdown,
)

log = logging.getLogger(__name__)


def _slug(url: str, ext: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", urlsplit(url).path.strip("/")) or "index"
    s = s[:120].strip("_")
    if ext and not s.endswith(ext):
        s += ext
    return s


class Crawler:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.out = Path(cfg.out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.db = DB(str(self.out / "crawl.db"))
        self.fetcher = Fetcher(cfg)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _folder(self, doctype: str) -> Path:
        sub = self.cfg.doctype_folders.get(doctype, self.cfg.doctype_folders["other"])
        return self.out / sub

    def _save_markdown(self, url: str, doctype: str, md_body: str,
                       meta: dict) -> tuple[str, int]:
        folder = self._folder(doctype) / "markdown"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / _slug(url, ".md")
        text = front_matter(meta) + md_body + "\n"
        path.write_text(text, encoding="utf-8")
        return str(path), len(text.encode("utf-8"))

    def _save_file(self, url: str, doctype: str, content: bytes) -> tuple[str, int]:
        folder = self._folder(doctype) / "files"
        folder.mkdir(parents=True, exist_ok=True)
        parsed = urlsplit(url)
        ext = Path(parsed.path).suffix or ".bin"

        # WTO document gateway: restore filename from query param
        if ext.lower() in (".aspx", ".php", ".asp"):
            fn = parse_qs(parsed.query).get("filename", [""])[0]
            if fn and "." in fn:
                fname = re.sub(r"[^a-zA-Z0-9._-]+", "_", fn.lstrip("q:/"))
            else:
                fname = _slug(url, ext)
        else:
            orig = Path(parsed.path).name
            fname = orig if (orig and "." in orig) else _slug(url, ext)

        # Collision handling: same name but different content → numeric suffix
        path = folder / fname
        if path.exists() and path.read_bytes() != content:
            stem, suf = Path(fname).stem, Path(fname).suffix
            for i in range(1, 100):
                path = folder / f"{stem}_{i}{suf}"
                if not path.exists():
                    break

        path.write_bytes(content)
        return str(path), len(content)

    def _save_raw(self, url: str, raw: bytes) -> None:
        if not self.cfg.keep_raw_html:
            return
        folder = self.out / "_raw_html"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / _slug(url, ".html")).write_bytes(raw)

    # ── Link discovery ───────────────────────────────────────────────────────

    def _discover(self, from_id: int, page_url: str,
                  page_hops: int, html: str) -> None:
        for abs_url, anchor in extract_links(html, page_url):
            canon = canonicalize(abs_url)
            dec = classify_url(canon, page_hops, self.cfg)
            to_id = self.db.upsert_url(canon, abs_url, dec.kind, dec.action,
                                       dec.reason, dec.child_hops)
            self.db.add_link(from_id, to_id, anchor)

    # ── Per-URL processing ───────────────────────────────────────────────────

    def _process(self, row) -> None:
        url, url_id = row["url_raw"], row["id"]

        if not self.fetcher.allowed(url):
            self.db.mark(url_id, fetch_status="skipped",
                         error="blocked by robots.txt")
            return

        r = self.fetcher.get(url)
        if r is None or r.status_code >= 400:
            self.db.mark(
                url_id, fetch_status="failed",
                http_status=(r.status_code if r else None),
                error="fetch failed",
            )
            return

        ctype = r.headers.get("content-type", "")
        raw = r.content

        # Content-type correction: declared as page but actually returns PDF bytes
        is_file_row = row["scope_action"] == "collect" or row["kind"] == "file"
        if is_file_row or "application/pdf" in ctype:
            doctype = classify(url, "", "", "file")
            path, size = self._save_file(url, doctype, raw)
            self.db.mark(
                url_id, fetch_status="done", http_status=r.status_code,
                content_type=ctype, doctype=doctype, local_path=path,
                size_bytes=size,
                content_hash=hashlib.sha1(raw).hexdigest(),
                fetched_at=time.time(),
            )
            return

        # HTML page: decode → discover links → convert to Markdown
        charset = None
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip()
        html = decode_bytes(raw, charset)
        self._save_raw(url, raw)

        title = get_title(html)
        self._discover(url_id, url, row["hops_outside"], html)

        needs_render = looks_like_js_shell(html, self.cfg.js_shell_text_threshold)
        md_body, method = to_markdown(html, url)
        chash = content_hash(md_body)

        dup = self.db.seen_hash(chash, url_id)
        doctype = classify(url, title, md_body, "page")
        meta = {
            "source_url":   url,
            "title":        title,
            "doctype":      doctype,
            "crawled_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
            "content_hash": chash,
            "conversion":   method,
            "needs_render": str(needs_render).lower(),
            "duplicate_of": dup or "",
        }
        path, size = self._save_markdown(url, doctype, md_body, meta)
        self.db.mark(
            url_id, fetch_status="done", http_status=r.status_code,
            content_type=ctype, doctype=doctype, title=title,
            local_path=path, size_bytes=size, content_hash=chash,
            needs_render=int(needs_render), fetched_at=time.time(),
        )

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self) -> dict:
        seed_c = canonicalize(self.cfg.seed_url)
        self.db.upsert_url(seed_c, self.cfg.seed_url, "page", "fetch", "seed", 0)

        for extra in self.cfg.extra_seeds:
            extra_c = canonicalize(extra)
            dec = classify_url(extra_c, 0, self.cfg)
            self.db.upsert_url(extra_c, extra, dec.kind, dec.action,
                               f"extra_seed ({dec.reason})", 0)

        processed = 0
        while True:
            if self.cfg.max_pages is not None and processed >= self.cfg.max_pages:
                break
            row = self.db.next_pending()
            if row is None:
                break
            try:
                self._process(row)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.db.mark(row["id"], fetch_status="failed",
                             error=str(exc)[:300])
            processed += 1
            if processed % 25 == 0:
                c = self.db.counts()
                log.info("[%d] done=%d pending=%d",
                         processed, c["done"], c["pending"])

        return self.db.counts()

    def close(self) -> None:
        self.fetcher.close()
        self.db.close()
