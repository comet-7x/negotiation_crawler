"""Domain models for the fishery book crawler."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Resolution status for a seed, used to colour the audit sheet."""

    FOUND = "FOUND"            # matched an item AND found a downloadable PDF
    NO_PDF = "NO_PDF"          # matched an item but no PDF bitstream in ORIGINAL bundle
    AMBIGUOUS = "AMBIGUOUS"    # best candidate scored below the confident threshold
    LEGACY = "LEGACY"          # resolved via the legacy fao.org/3 fallback
    MISSING = "MISSING"        # nothing found in DSpace or legacy
    ERROR = "ERROR"            # an exception occurred while resolving


@dataclass(slots=True)
class Seed:
    seed_id: str
    category: str
    title: str
    year: int | None
    lang: str = "en"
    edition_note: str = ""
    exclude_terms: list[str] = field(default_factory=list)
    must_contain: list[str] = field(default_factory=list)  # candidate title must contain >=1
    item_uuid: str | None = None   # pin: resolve this exact DSpace item, skip search
    handle: str | None = None      # pin alternative: e.g. "20.500.14283/cc0461en"
    legacy_url: str | None = None  # optional manual fallback for known gaps

    @property
    def is_pinned(self) -> bool:
        return bool(self.item_uuid or self.handle)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Seed":
        return cls(
            seed_id=d["seed_id"],
            category=d["category"],
            title=d["title"],
            year=d.get("year"),
            lang=d.get("lang", "en"),
            edition_note=d.get("edition_note", ""),
            exclude_terms=d.get("exclude_terms", []),
            must_contain=d.get("must_contain", []),
            item_uuid=d.get("item_uuid"),
            handle=d.get("handle"),
            legacy_url=d.get("legacy_url"),
        )


@dataclass(slots=True)
class Bitstream:
    uuid: str
    name: str
    size_bytes: int | None
    mimetype: str | None
    content_url: str
    bundle: str = "ORIGINAL"

    @property
    def is_pdf(self) -> bool:
        if self.mimetype and "pdf" in self.mimetype.lower():
            return True
        return self.name.lower().endswith(".pdf")

    @property
    def ext(self) -> str:
        _, _, tail = self.name.rpartition(".")
        return tail.lower() if tail and tail != self.name else ""


@dataclass(slots=True)
class DSpaceItem:
    uuid: str
    name: str
    handle: str | None
    title: str
    issued: str | None
    language: str | None
    dtype: str | None
    extent: str | None  # e.g. "266 p."
    bitstreams: list[Bitstream] = field(default_factory=list)

    @property
    def handle_url(self) -> str | None:
        return f"https://openknowledge.fao.org/handle/{self.handle}" if self.handle else None

    def primary_pdf(self) -> Bitstream | None:
        """Pick the main PDF: largest PDF in the ORIGINAL bundle."""
        pdfs = [b for b in self.bitstreams if b.is_pdf and b.bundle.upper() == "ORIGINAL"]
        if not pdfs:
            pdfs = [b for b in self.bitstreams if b.is_pdf]
        if not pdfs:
            return None
        return max(pdfs, key=lambda b: b.size_bytes or 0)


@dataclass(slots=True)
class BookRecord:
    """One row of the final audit table."""

    # --- the 8 columns the audit sheet must show ---
    category: str
    year: int | None
    filename: str | None
    title: str | None
    download_url: str | None
    pages: int | None
    size_kb: float | None
    fmt: str | None
    # --- diagnostics ---
    seed_id: str = ""
    seed_title: str = ""
    status: Status = Status.MISSING
    match_score: float | None = None
    handle: str | None = None
    item_uuid: str | None = None
    bitstream_uuid: str | None = None
    source: str = "dspace"
    local_path: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
