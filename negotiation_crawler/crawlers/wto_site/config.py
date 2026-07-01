"""Global configuration — all scope/boundary decisions live here.

Edit this file to change WHAT gets crawled; the rest of the code is mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Config:
    # ---- Seeds ----
    seed_url: str = "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_e.htm"
    # Extra seeds injected directly at hops=0, bypassing link discovery.
    # Use for pages that are in-scope but not linked from any crawled page.
    extra_seeds: list = field(default_factory=lambda: [
        "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/implementfishagreement22_e.htm",
        "https://www.wto.org/english/res_e/booksp_e/fishagree_e.htm",
        "https://www.wto.org/english/docs_e/legal_e/fish_e.htm",
        "https://www.wto.org/english/docs_e/legal_e/24-scm.pdf",
    ])

    # ---- Scope boundaries ----
    # Pages whose path starts with core_prefix are recursively followed (hops=0).
    core_prefix: str = "/english/tratop_e/rulesneg_e/fish_e/"
    # Budget for stepping outside the core prefix (1 = one adjacent section).
    max_hops_outside: int = 1
    # Page traversal is restricted to this registered domain.
    page_host_suffix: str = "wto.org"
    # Files (PDFs etc.) may be collected from any subdomain of this domain.
    file_host_suffix: str = "wto.org"

    # ---- Content-type boundaries ----
    # Extensions treated as "files": downloaded directly, never expanded.
    file_extensions: tuple = (
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".rar", ".7z", ".csv", ".rtf", ".txt",
    )
    # Extensions treated as "pages": parsed for links + converted to Markdown.
    page_extensions: tuple = (".htm", ".html", ".php", ".asp", ".aspx", "")

    # ---- Politeness / robustness ----
    user_agent: str = (
        "SteinsTechCorpusBot/1.0 (research; fisheries-subsidies corpus; "
        "contact: zhihao7946@gmail.com)"
    )
    respect_robots: bool = True
    request_delay: float = 1.0   # minimum seconds between requests to the same host
    timeout: float = 30.0
    max_retries: int = 3
    backoff_base: float = 2.0    # exponential back-off base: 2 s, 4 s, 8 s …
    max_pages: int | None = None  # None = unlimited; set a small value for smoke tests

    # ---- Conversion ----
    keep_raw_html: bool = True
    js_shell_text_threshold: int = 200  # body shorter than this + many scripts → needs_render

    # ---- Output ----
    out_dir: str = "output"

    # doctype → sub-folder name
    doctype_folders: dict = field(default_factory=lambda: {
        "legal_text":               "01_法律文本",
        "international_instrument": "02_国际文书",
        "publication":              "03_出版物",
        "ministerial":              "04_部长级文件",
        "submission":               "05_谈判提案",
        "meeting_doc":              "06_会议文件",
        "briefing":                 "07_简报",
        "news":                     "08_新闻",
        "navigation":               "09_参考页面",
        "other":                    "99_其他",
    })
