"""Derive page counts: prefer DSpace metadata, fall back to reading the PDF."""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

_EXTENT = re.compile(r"(\d{1,5})\s*(?:p\.?|pages|pp\.?)", re.IGNORECASE)


def pages_from_extent(extent: str | None) -> int | None:
    """Parse strings like '266 p.', 'xii, 244 p.', '120 pages'."""
    if not extent:
        return None
    matches = _EXTENT.findall(extent)
    if not matches:
        return None
    # take the largest number found (Roman-numeral front matter is small)
    return max(int(m) for m in matches)


def pages_from_pdf(path: Path) -> int | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed; cannot count pages from PDF")
        return None
    try:
        reader = PdfReader(str(path))
        return len(reader.pages)
    except Exception as exc:  # corrupt/encrypted PDFs
        logger.warning("could not read pages from {}: {}", path, exc)
        return None
