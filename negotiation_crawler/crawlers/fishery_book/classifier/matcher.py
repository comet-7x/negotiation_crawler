"""Match a seed against DSpace search candidates and pick the best item.

Scoring blends a fuzzy title ratio with heuristics. The decisive one is the
**year gate**: for series whose identity includes a year (SOFIA, Yearbook — i.e.
the seed's own title contains its year), a candidate is *disqualified* unless its
title carries that exact year. This stops the fuzzy ratio from matching e.g. the
2008 yearbook to a request for 2010 (their long trilingual titles differ only in
the year, so partial_ratio scores both ~100). For titles with no identifying year
(management/technical guidelines), we fall back to the soft issued-date proximity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from ..models import DSpaceItem, Seed

_YEAR = re.compile(r"(?:19|20)\d{2}")
_DISQUALIFY = -1000.0


@dataclass(slots=True)
class Match:
    item: DSpaceItem
    score: float
    reason: str


_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    text = text.lower()
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text)
    return text.strip()


def years_in(text: str | None) -> set[str]:
    return set(_YEAR.findall(text or ""))


def _title_score(seed_title: str, cand_title: str) -> float:
    a, b = normalize(seed_title), normalize(cand_title)
    # token_sort_ratio is robust to word-order and the trailing year/subtitle noise.
    return max(fuzz.token_sort_ratio(a, b), fuzz.partial_ratio(a, b) * 0.95)


def score_candidate(seed: Seed, item: DSpaceItem) -> tuple[float, str]:
    base = _title_score(seed.title, item.title)
    reasons = [f"title={base:.0f}"]

    # --- year handling ---
    cand_title_years = years_in(item.title)
    year_is_identity = bool(seed.year and str(seed.year) in years_in(seed.title))

    if year_is_identity:
        # The seed's identity includes its year -> require an exact year in the title.
        if str(seed.year) in cand_title_years:
            base += 15
            reasons.append("year-exact+15")
        elif cand_title_years:
            base += _DISQUALIFY  # wrong-year edition of the same series
            reasons.append(f"YEAR-GATE-FAIL(got {sorted(cand_title_years)})")
        else:
            base -= 20  # series item with no year in title; can't confirm -> demote
            reasons.append("year-unconfirmed-20")
    elif seed.year and item.issued:
        # No identifying year in the title (guidelines): soft issued-date proximity.
        cand_year = item.issued[:4]
        if cand_year == str(seed.year):
            base += 8
            reasons.append("issued+8")
        elif cand_year.isdigit() and abs(int(cand_year) - seed.year) <= 1:
            base += 2
            reasons.append("issued~+2")
        else:
            base -= 6
            reasons.append("issued-6")

    # --- language preference ---
    if seed.lang and item.language:
        if item.language.lower().startswith(seed.lang.lower()):
            base += 4
            reasons.append("lang+4")
        elif item.language.lower() not in ("mul", "und", ""):
            base -= 5
            reasons.append("lang-5")

    # --- must-contain gate (e.g. Yearbook candidate must mention fishery/aquaculture) ---
    if seed.must_contain:
        cand_norm_full = normalize(item.title)
        if not any(normalize(t) in cand_norm_full for t in seed.must_contain):
            base += _DISQUALIFY
            reasons.append(f"MUST-CONTAIN-FAIL({seed.must_contain})")

    # --- exclude-term gate (report/draft/working paper/review/newsletter/version ...) ---
    # These mark a *different kind of document* (meeting report, draft, review, newsletter,
    # translated version) — never the instrument itself. Disqualify decisively.
    cand_norm = normalize(item.title)
    for term in seed.exclude_terms:
        if normalize(term) in cand_norm and normalize(term) not in normalize(seed.title):
            base += _DISQUALIFY
            reasons.append(f"EXCL[{term}]")
            break

    return base, ",".join(reasons)


def best_match(seed: Seed, candidates: list[DSpaceItem]) -> Match | None:
    best: Match | None = None
    for item in candidates:
        score, reason = score_candidate(seed, item)
        if best is None or score > best.score:
            best = Match(item=item, score=score, reason=reason)
    return best
