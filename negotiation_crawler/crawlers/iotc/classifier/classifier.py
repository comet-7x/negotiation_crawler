"""
data_classify/classifier.py — Document classification utilities.

Provides:
  - country_from_name(): extract/normalize country from National Report filenames
  - classify_row(): derive a display-ready category label for each document
  - fix_manifest_countries(): backfill country column for all National Reports

This module re-uses the CPC normalization logic from the original cpc_normalize.py
but integrates it into the modular package structure.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote

# ----------------------------------------------------------------- CPC table ----
# Official CPC name → list of aliases (lower-cased)
CPCS: dict[str, list[str]] = {
    "Australia":                  ["australia"],
    "Bangladesh":                 ["bangladesh"],
    "China":                      ["china", "pr china", "p.r. china", "peoples republic of china"],
    "Comoros":                    ["comoros", "comores"],
    "European Union":             ["european union", "european community", "eu", "ec"],
    "France (Territories)":       ["france territories", "france (territories)", "france (ot)",
                                   "france ot", "franceot", "france oti", "france"],
    "India":                      ["india"],
    "Indonesia":                  ["indonesia"],
    "Iran (Islamic Rep. of)":     ["iran islamic", "islamic republic of iran", "iran"],
    "Japan":                      ["japan"],
    "Kenya":                      ["kenya"],
    "Rep. of Korea":              ["republic of korea", "rep. of korea", "rep of korea",
                                   "south korea", "korea", "rok"],
    "Madagascar":                 ["madagascar"],
    "Malaysia":                   ["malaysia"],
    "Maldives":                   ["maldives"],
    "Mauritius":                  ["mauritius"],
    "Mozambique":                 ["mozambique"],
    "Oman":                       ["oman"],
    "Pakistan":                   ["pakistan"],
    "Philippines":                ["philippines"],
    "Seychelles":                 ["seychelles"],
    "Somalia":                    ["somalia", "somali"],
    "South Africa":               ["south africa", "southafrica"],
    "Sri Lanka":                  ["sri lanka", "srilanka"],
    "Sudan":                      ["sudan"],
    "United Rep. of Tanzania":    ["united republic of tanzania", "united rep. of tanzania", "tanzania"],
    "Thailand":                   ["thailand"],
    "United Kingdom":             ["united kingdom", "great britain", "ukot", "uk"],
    "Yemen":                      ["yemen"],
    # CNCPs / historical
    "Liberia":                    ["liberia"],
    "Panama":                     ["panama"],
    "Senegal":                    ["senegal"],
    "Belize":                     ["belize"],
    "Guinea":                     ["guinea"],
    "Eritrea":                    ["eritrea"],
    "Sierra Leone":               ["sierra leone"],
    "Vanuatu":                    ["vanuatu"],
}

_TOKEN: dict[str, str] = {
    re.sub(r"[^a-z0-9]", "", alias): canon
    for canon, aliases in CPCS.items()
    for alias in aliases
}

_PHRASES = sorted(
    [
        (alias, canon)
        for canon, aliases in CPCS.items()
        for alias in aliases
        if len(alias) >= 4 and (" " in alias or len(alias) >= 5)
    ],
    key=lambda x: -len(x[0]),
)


def _normalize(raw: str = "", title: str = "") -> str:
    if raw:
        key = re.sub(r"[^a-z0-9]", "", raw.lower())
        if key in _TOKEN:
            return _TOKEN[key]
        key2 = re.sub(r"(rev\d*|final|\d+)$", "", key)
        if key2 and key2 in _TOKEN:
            return _TOKEN[key2]
    if title:
        t = title.lower()
        for phrase, canon in _PHRASES:
            if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", t):
                return canon
    return ""


def _match_tokens(s: str) -> str:
    for tok in reversed(re.split(r"[-_.,\s–]+", s)):
        key = re.sub(r"[^a-z0-9]", "", tok.lower())
        key = re.sub(r"(rev\d*|final|annex|\d+)$", "", key)
        if key in _TOKEN:
            return _TOKEN[key]
    return ""


def country_from_name(pdf_url: str, title: str = "") -> str | None:
    """
    Extract and normalize the country name from a National Report PDF URL/filename.

    Returns:
      - Official CPC name string  (matched)
      - ""                        (is a National Report but country not matched)
      - None                      (not a National Report — no NR## in filename)
    """
    name = unquote(pdf_url.rsplit("/", 1)[-1]).removesuffix(".pdf")
    if not re.search(r"NR\d", name, re.I):
        return None
    return (
        _match_tokens(name)
        or _normalize(raw="", title=name)
        or _match_tokens(title or "")
        or _normalize(raw="", title=title or "")
    )


def classify_row(doc_type: str, meta_type: str, meeting: str, year: str) -> dict[str, str]:
    """
    Return a dict of derived classification fields for display / Excel use.

    Fields returned:
      - display_category: the most authoritative category label
      - meeting_abbr:     short meeting abbreviation extracted from meeting string
    """
    # meta_type (from landing page) is more authoritative than doc_type
    effective_type = meta_type.strip() if meta_type and meta_type.strip() else doc_type

    # Extract abbreviation like "(SC)", "(WPTT)" from meeting string
    meeting_abbr = ""
    if meeting:
        m = re.search(r"\(([A-Z][A-Z0-9\-]+)\)", meeting)
        meeting_abbr = m.group(1) if m else ""

    return {
        "display_category": effective_type,
        "meeting_abbr": meeting_abbr,
    }


def fix_manifest_countries(db_path: Path) -> None:
    """Backfill the country column for all National Report rows."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT pdf_url, title, country FROM docs WHERE doc_type LIKE '%National Report%'"
    ).fetchall()

    changed = recovered = not_nr = 0
    for pdf_url, title, old in rows:
        canon = country_from_name(pdf_url, title or "")
        if canon is None:
            not_nr += 1
            continue
        if canon and canon != old:
            conn.execute("UPDATE docs SET country=? WHERE pdf_url=?", (canon, pdf_url))
            changed += 1
            if not old:
                recovered += 1

    conn.commit()
    real_nr = len(rows) - not_nr
    empty = conn.execute(
        "SELECT count(*) FROM docs WHERE doc_type LIKE '%National Report%' "
        "AND (country IS NULL OR country='') AND pdf_url LIKE '%NR%'"
    ).fetchone()[0]

    print(f"National Reports: {len(rows)} total, {real_nr} real NRs, {not_nr} mis-tagged")
    print(f"Updated: {changed}, recovered from empty: {recovered}, still empty: {empty}")
    if empty:
        print("Still-empty NR filenames (add aliases for these):")
        for (u,) in conn.execute(
            "SELECT pdf_url FROM docs WHERE doc_type LIKE '%National Report%' "
            "AND (country IS NULL OR country='') AND pdf_url LIKE '%NR%' LIMIT 20"
        ):
            print("   ", u.rsplit("/", 1)[-1])
    conn.close()
