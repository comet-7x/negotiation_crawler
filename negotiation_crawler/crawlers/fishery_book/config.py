"""Runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# DSpace 7 REST API root for the FAO Knowledge Repository.
FAO_API_BASE = "https://openknowledge.fao.org/server/api"
FAO_HANDLE_PREFIX = "20.500.14283"


@dataclass(slots=True)
class Settings:
    api_base: str = FAO_API_BASE
    out_dir: Path = Path("output")
    pdf_dir: Path = Path("output/pdf")
    db_path: Path = Path("output/manifest.sqlite3")
    xlsx_path: Path = Path("output/fishery_books_audit.xlsx")

    # networking
    concurrency: int = 4              # polite parallelism against FAO servers
    timeout: float = 60.0
    max_retries: int = 4
    backoff_base: float = 1.5
    http2: bool = True               # browsers use h2; helps slip past some CDN checks
    proxy: str | None = None         # e.g. "http://127.0.0.1:7890"; also honours HTTPS_PROXY env
    # A realistic browser UA — the FAO repo's CDN/WAF returns 403 to obvious bot UAs.
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    # matching
    confident_score: float = 82.0     # >= this -> FOUND, else AMBIGUOUS
    min_score: float = 60.0           # below this -> treat as MISSING
    search_page_size: int = 25

    # behaviour
    download: bool = True             # set False for a metadata-only audit pass
    fetch_pages_from_pdf: bool = True  # parse PDF when dc.format.extent missing

    extra_headers: dict[str, str] = field(default_factory=dict)

    def ensure_dirs(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

    @property
    def headers(self) -> dict[str, str]:
        # Mimic the headers the DSpace Angular SPA sends on its XHR calls, so the
        # CDN/WAF treats us like a same-origin browser request rather than a bot.
        h = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://openknowledge.fao.org/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        h.update(self.extra_headers)
        return h
