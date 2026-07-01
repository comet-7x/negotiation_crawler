"""Listing page + landing page crawlers for IOTC."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin

import httpx
from selectolax.parser import HTMLParser

from ..config import (
    BASE_URL, VIEWS,
    REQUEST_DELAY, TIMEOUT, HEADERS,
    DOCUMENTS_PATH, YEAR_PARAM, LANG_PARAM, DOCTYPE_PARAM,
)
from ..storage.db import (
    init_db, upsert_row, update_enrichment, update_download,
    pending_downloads, pending_enrichment,
)

log = logging.getLogger("iotc.crawler")

_LANDING_LABELS = {
    "Type": "meta_type",
    "Year": "year",
    "Meeting": "meeting",
    "Meeting session": "session",
    "Authors": "authors",
}


def _is_french(pdf_url: str, reference: str) -> bool:
    fname = pdf_url.rsplit("/", 1)[-1]
    ref_up = reference.upper()
    return (
        bool(re.search(r"F\.pdf$", fname))
        or "CTOI" in ref_up
        or "CIRCULAIRE" in ref_up
    )


def _last_page(html: str) -> int:
    h = html.replace("&amp;", "&")
    nums = [int(n) for n in re.findall(r"[?&]page=(\d+)", h)]
    return max(nums) if nums else 0


def _parse_listing(html: str) -> list[dict]:
    tree = HTMLParser(html)
    rows: list[dict] = []
    for table in tree.css("table"):
        header = " ".join(th.text() for th in table.css("th")).lower()
        if "reference" not in header or "title" not in header:
            continue
        for tr in table.css("tr"):
            tds = tr.css("td")
            if not tds:
                continue
            ref = tds[0].text(strip=True)
            links = tr.css("a")
            landing = next(
                (a for a in links if not ((a.attributes.get("href") or "").lower().endswith(".pdf"))),
                None,
            )
            pdf = next(
                (a for a in links if (a.attributes.get("href") or "").lower().endswith(".pdf")),
                None,
            )
            if pdf is None:
                continue
            title = landing.text(strip=True) if landing else ref
            landing_url = urljoin(BASE_URL, landing.attributes["href"]) if landing else ""
            pdf_url = urljoin(BASE_URL, pdf.attributes["href"])
            date = ""
            for td in tds:
                t = td.text(strip=True)
                if re.match(r"\d{2}/\d{2}/\d{4}", t):
                    date = t
                    break
            rows.append(
                dict(reference=ref, title=title, landing_url=landing_url,
                     pdf_url=pdf_url, circulated=date)
            )
    return rows


def _enrich_from_landing(html: str) -> dict[str, str]:
    lines = [ln.strip() for ln in HTMLParser(html).text(separator="\n").splitlines() if ln.strip()]
    out: dict[str, str] = {}
    for i, line in enumerate(lines[:-1]):
        label = line[:-1].strip() if line.endswith(":") else None
        if label in _LANDING_LABELS:
            out[_LANDING_LABELS[label]] = lines[i + 1]
    return out


def _year_from_url_or_ref(pdf_url: str, reference: str) -> str:
    m = re.search(r"/(\d{4})/", pdf_url) or re.search(r"\b(20\d{2}|19\d{2})\b", reference or "")
    return m.group(1) if m else "unknown"


def build_manifest(
    db_path: Path,
    english_only: bool = True,
    limit: int | None = None,
) -> None:
    """Phase 1: crawl all 31 document-type listing pages and populate the manifest."""
    conn = init_db(db_path)
    total_new = 0

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for view in VIEWS:
            doc_type       = view["doc_type"]
            doc_type_zh    = view["doc_type_zh"]
            category_group = view["category_group"]
            tid            = view["tid"]

            params: dict[str, str] = {DOCTYPE_PARAM: tid, YEAR_PARAM: "All"}
            if english_only:
                params[LANG_PARAM] = "en"

            def page_url(p: int) -> str:
                return f"{BASE_URL}{DOCUMENTS_PATH}?{urlencode({**params, 'page': p})}"

            log.info("[manifest] %s → %s", doc_type, page_url(0))
            try:
                html = client.get(page_url(0)).text
            except Exception as exc:
                log.warning("  fetch failed for %s: %s", doc_type, exc)
                continue

            total_pages = _last_page(html)
            view_new = 0

            for p in range(total_pages + 1):
                if p > 0:
                    try:
                        html = client.get(page_url(p)).text
                    except Exception as exc:
                        log.warning("  page %d fetch failed: %s", p, exc)
                        time.sleep(REQUEST_DELAY)
                        continue

                for row in _parse_listing(html):
                    if english_only and _is_french(row["pdf_url"], row["reference"]):
                        continue
                    inserted = upsert_row(
                        conn,
                        pdf_url=row["pdf_url"],
                        reference=row["reference"],
                        doc_type=doc_type,
                        doc_type_zh=doc_type_zh,
                        category_group=category_group,
                        title=row["title"],
                        landing_url=row["landing_url"],
                        circulated=row["circulated"],
                        language="en",
                    )
                    if inserted:
                        view_new += 1

                log.info("  page %d: +%d new", p, view_new)
                time.sleep(REQUEST_DELAY)

            total_new += view_new
            if limit and total_new >= limit:
                log.info("  limit %d reached", limit)
                break

    log.info("[manifest] done — %d new records inserted", total_new)
    conn.close()


def enrich_metadata(
    db_path: Path,
    limit: int | None = None,
    doc_type_filter: str | None = None,
) -> None:
    """Phase 2: fetch each landing page to fill in meta_type/year/meeting/session/authors."""
    try:
        from ..classifier.classifier import country_from_name as _cfn
    except Exception:
        _cfn = None  # type: ignore

    conn = init_db(db_path)
    rows = pending_enrichment(conn, doc_type_filter)
    if limit:
        rows = rows[:limit]

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for pdf_url, landing_url, title, cur_country in rows:
            try:
                meta = _enrich_from_landing(client.get(landing_url).text)
                if not cur_country and _cfn is not None:
                    c = _cfn(pdf_url, title or "")
                    if c:
                        meta["country"] = c
                update_enrichment(conn, pdf_url, meta)
                log.info("  enriched %s → %s", landing_url.rsplit("/", 1)[-1],
                         meta.get("meta_type", "?"))
            except Exception as exc:
                log.warning("  enrich failed %s: %s", landing_url, exc)
            time.sleep(REQUEST_DELAY)

    conn.close()


def download_pdfs(
    db_path: Path,
    pdf_dir: Path,
    limit: int | None = None,
    doc_type_filter: str | None = None,
) -> None:
    """Phase 3: download all pending PDFs into pdf_dir/<doc_type>/<year>/."""
    conn = init_db(db_path)
    rows = pending_downloads(conn, doc_type_filter)
    if limit:
        rows = rows[:limit]

    try:
        import pypdf  # noqa: F401
        _have_pypdf = True
    except ImportError:
        _have_pypdf = False

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for pdf_url, reference, doc_type, circulated in rows:
            year = _year_from_url_or_ref(pdf_url, reference)
            dest_dir = pdf_dir / doc_type / year
            dest_dir.mkdir(parents=True, exist_ok=True)
            fname = pdf_url.rsplit("/", 1)[-1]
            dest = dest_dir / fname

            try:
                data = client.get(pdf_url).content
                sha = hashlib.sha256(data).hexdigest()
                size_kb = round(len(data) / 1024, 1)

                dup = conn.execute(
                    "SELECT local_path FROM docs WHERE sha256=? AND local_path IS NOT NULL",
                    (sha,)
                ).fetchone()
                if dup:
                    local_path = dup[0]
                    log.info("  dup %s == %s", fname, Path(local_path).name)
                else:
                    dest.write_bytes(data)
                    local_path = str(dest)
                    log.info("  saved %s (%.1f KB)", fname, size_kb)

                pages = 0
                if _have_pypdf and dest.exists():
                    try:
                        import pypdf
                        with open(dest, "rb") as fh:
                            pages = len(pypdf.PdfReader(fh).pages)
                    except Exception:
                        pages = 0

                update_download(conn, pdf_url, local_path, sha, size_kb, pages, "downloaded")
            except Exception as exc:
                log.warning("  failed %s: %s", fname, exc)
                update_download(conn, pdf_url, "", "", 0.0, 0, "failed")

            time.sleep(REQUEST_DELAY)

    conn.close()
