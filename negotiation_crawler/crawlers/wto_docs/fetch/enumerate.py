"""Enumerate a docs.wto.org document series via the scripted-search endpoint.

Uses FE_S_S006.aspx with Context=FomerScriptedSearch — plain HTTP POST,
no Playwright. Walks every page via ASP.NET postback (__VIEWSTATE + lnkNext).

Produces JSONL with: symbol, text, english_url, access, fisheries (bool).
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from urllib.parse import quote

import httpx

BASE = "https://docs.wto.org/dol2fe/Pages/FE_Search/FE_S_S006.aspx"
UA   = "wto-fish-corpus-bot/1.0 (research; contact: research@example.com)"

FISH_RE = re.compile(
    r"fish|fisher|fishing|overfish|overcapacit|IUU|illegal[,\s].{0,20}unreported|"
    r"marine\s+capture|subsidies\s+(?:to|for)\s+fish",
    re.IGNORECASE,
)

HIDDEN_RE = {k: re.compile(r'id="%s"\s+value="([^"]*)"' % k) for k in
             ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")}
TOTAL_RE   = re.compile(r'hdntotalresults"\s*value="(\d+)"')
CURPAGE_RE = re.compile(r'ctl00_MainPlaceHolder_hdnCurrentPage"\s*value="(\d+)"')
ACCESS_RE  = re.compile(r'Access:\s*(?:<[^>]+>\s*)*(\w+)', re.S)
ENLINK_RE  = re.compile(
    r'class="hitEnFileLink".*?directdoc\.aspx\?filename=([^"&]+)', re.S | re.I)


def _hidden(html: str, name: str) -> str:
    m = HIDDEN_RE[name].search(html)
    return m.group(1) if m else ""


def _clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def parse_page(html: str) -> list[dict]:
    recs = []
    for raw in html.split('class="hitContainer"')[1:]:
        am = ACCESS_RE.search(raw)
        chunk = raw[: am.start()] if am else raw
        access = am.group(1) if am else ""
        m = ENLINK_RE.search(raw)
        filename = m.group(1) if m else None
        symbol = (
            re.sub(r"^[A-Za-z]:/", "", filename).replace(".pdf", "")
            if filename else None
        )
        text = _clean(chunk).lstrip("> ").strip()
        english_url = (
            f"https://docs.wto.org/dol2fe/Pages/SS/directdoc.aspx?"
            f"filename={quote(filename, safe='')}&Open=True"
            if filename else None
        )
        recs.append({
            "symbol":      symbol,
            "text":        text,
            "english_url": english_url,
            "access":      access,
            "fisheries":   bool(FISH_RE.search(text)),
        })
    return recs


def enumerate_series(
    query: str,
    delay: float = 1.0,
    fisheries_only: bool = False,
) -> list[dict]:
    """Walk every page of a symbol query on FE_S_S006.aspx.

    Args:
        query: DOL symbol query, e.g. ``(@Symbol= TN/RL/*)``.
        delay: seconds between page requests.
        fisheries_only: if True, only keep records whose title flags fisheries.
    """
    url = (f"{BASE}?Query={quote(query)}"
           f"&Language=ENGLISH&Context=FomerScriptedSearch&languageUIChanged=true")
    out: dict[str, dict] = {}

    with httpx.Client(headers={"User-Agent": UA},
                      follow_redirects=True, timeout=90.0) as c:
        html  = c.get(url).text
        total_match = TOTAL_RE.search(html)
        total = int(total_match.group(1)) if total_match else 0
        pages = max(1, math.ceil(total / 10))
        print(f"  total={total} (~{pages} pages)")
        page  = 0
        while True:
            for r in parse_page(html):
                key = r["symbol"] or r["text"][:40]
                out.setdefault(key, r)
            cur = CURPAGE_RE.search(html)
            cur = int(cur.group(1)) if cur else page
            print(f"    page {cur + 1}/{pages}: {len(out)} records so far")
            if cur + 1 >= pages:
                break
            data = {
                "__EVENTTARGET":        "ctl00$MainPlaceHolder$lnkNext",
                "__EVENTARGUMENT":      "",
                "__VIEWSTATE":          _hidden(html, "__VIEWSTATE"),
                "__VIEWSTATEGENERATOR": _hidden(html, "__VIEWSTATEGENERATOR"),
                "__EVENTVALIDATION":    _hidden(html, "__EVENTVALIDATION"),
            }
            time.sleep(delay)
            html = c.post(url, data=data).text
            page = cur + 1
            if page > pages + 2:
                break

    result = list(out.values())
    if fisheries_only:
        result = [r for r in result if r["fisheries"]]
    return result


def run(
    query: str,
    out_path: Path,
    delay: float = 1.0,
    fisheries_only: bool = False,
) -> list[dict]:
    recs = enumerate_series(query, delay=delay, fisheries_only=fisheries_only)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    fish = sum(1 for r in recs if r["fisheries"])
    print(f"  saved {len(recs)} records (fisheries-flagged: {fish}) → {out_path}")
    return recs
