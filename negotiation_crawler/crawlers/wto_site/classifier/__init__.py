"""Document-type classification.

Priority: URL filename keywords > WTO document symbol > title/body keywords > extension fallback.
"""
from __future__ import annotations

import re

# ── WTO document symbol patterns ────────────────────────────────────────────
_SYMBOL_RE = re.compile(r"\b(TN/RL|WT/MIN|WT/L|G/SCM|JOB/RL|RD/TN)\b", re.I)

# ── URL filename keyword rules (first match wins) ────────────────────────────
_URL_RULES: list[tuple[str, re.Pattern]] = [
    ("international_instrument", re.compile(
        r"/(vclt|unclos|unfsa|fao_ccrf|fao_|ipoa_iuu|psma|vg_fsp|vg_cds|ssf)[^/]*\.pdf",
        re.I,
    )),
    ("publication", re.compile(
        r"/(impfishag|fishagree|implementfishagreement|fish_factsheet|booksp_e/)[^/]*\.(pdf|htm)",
        re.I,
    )),
    ("legal_text", re.compile(
        r"/(24-scm|scm|fish_e\.htm|agreement_fisheries_subsidies)[^/]*\.(pdf|htm)",
        re.I,
    )),
    ("ministerial", re.compile(r"WT[/_]MIN", re.I)),
]

# ── Title / body keyword rules ───────────────────────────────────────────────
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("legal_text", [
        "agreement on fisheries subsidies", "legal text",
        "agreement text", "treaty text",
    ]),
    ("ministerial", [
        "ministerial declaration", "ministerial decision",
        "ministerial conference", "doha declaration",
        "hong kong", "annex d",
    ]),
    ("submission", [
        "submission", "communication from", "proposal by",
        "delegation", "negotiating group",
    ]),
    ("meeting_doc", [
        "minutes", "report of the meeting", "agenda",
        "summary report", "chair",
    ]),
    ("briefing", [
        "briefing note", "fact sheet", "factsheet",
        "introduction to", "background note",
    ]),
    ("news", ["news", "press", "/news_e/", "speech"]),
]


def classify(url: str, title: str, body_text: str, kind: str) -> str:
    """Return the doctype key (matches keys in Config.doctype_folders)."""
    # 1) URL filename keywords (most precise)
    for doctype, pat in _URL_RULES:
        if pat.search(url):
            return doctype

    # 2) WTO document symbol in URL or title
    if _SYMBOL_RE.search(url) or _SYMBOL_RE.search(title):
        if re.search(r"WT/MIN", url + title, re.I):
            return "ministerial"
        return "submission"

    # 3) Title / body keywords
    hay = f"{url}\n{title}\n{body_text[:1500]}".lower()
    for doctype, kws in _KEYWORD_RULES:
        if any(kw in hay for kw in kws):
            return doctype

    # 4) Fallback
    return "navigation" if kind == "page" else "other"
