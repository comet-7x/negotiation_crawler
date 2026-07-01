"""URL normalisation and scope classification.

Two responsibilities:
  1. canonicalize / to_absolute — stable dedup keys
  2. classify_url — hop-based Decision (fetch | collect | skip)

English-only: any URL whose path or filename suffix identifies it as
French (/french/, _f.) or Spanish (/spanish/, _s.) is rejected before
all other checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from ..config import Config

# Tracking parameters that add no content information.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "source", "_ga",
}


# ── URL normalisation ────────────────────────────────────────────────────────

def to_absolute(base_url: str, href: str | None) -> str | None:
    """Resolve a (possibly relative) href against base_url.

    Returns None for non-http(s) pseudo-URIs (javascript:, mailto:, …).
    """
    if not href:
        return None
    href = href.strip()
    low = href.lower()
    if low.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
        return None
    abs_url = urljoin(base_url, href)
    if not abs_url.lower().startswith(("http://", "https://")):
        return None
    return abs_url


def canonicalize(url: str) -> str:
    """Stable dedup key: lowercase scheme/host, drop fragment and tracking
    params, sort remaining query params, normalise index pages."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parts.path or "/"
    for idx in ("index.htm", "index.html", "default.htm", "default.html"):
        if path.endswith("/" + idx):
            path = path[: -len(idx)]
            break

    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in _TRACKING_PARAMS]
    q.sort()
    query = urlencode(q)

    return urlunsplit((scheme, netloc, path, query, ""))


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


# ── English-only filter ──────────────────────────────────────────────────────

def is_english_url(url: str) -> bool:
    """Return False for URLs clearly in French or Spanish.

    WTO language signals:
      - path segment: /french/  or /spanish/
      - filename suffix before extension: _f  or _s  (e.g. fish_f.htm, fish_s.pdf)
    URLs with no language marker are treated as English-eligible.
    """
    path = path_of(url).lower()
    if "/french/" in path or "/spanish/" in path:
        return False
    # Isolate the filename stem (everything before the first dot in the last segment)
    last_seg = path.rsplit("/", 1)[-1]
    stem = last_seg.split(".")[0] if "." in last_seg else last_seg
    if stem.endswith("_f") or stem.endswith("_s"):
        return False
    return True


# ── Scope classification ─────────────────────────────────────────────────────

@dataclass
class Decision:
    kind: str        # "page" | "file"
    action: str      # "fetch" | "collect" | "skip"
    child_hops: int  # hops_outside value assigned to this URL's children
    reason: str      # human-readable audit trail


def _ext(url: str) -> str:
    """Return the effective file extension, resolving dynamic gateways."""
    path = path_of(url).lower()
    dot = path.rfind(".")
    slash = path.rfind("/")
    if dot <= slash:
        return ""
    ext = path[dot:]
    # WTO document gateway: directdoc.aspx?filename=q:/WT/MIN22/33.pdf → .pdf
    if ext in (".aspx", ".php", ".asp"):
        fn = parse_qs(urlsplit(url).query).get("filename", [""])[0]
        if fn and "." in fn:
            return fn[fn.rfind("."):]
    return ext


def _same_domain(url: str, suffix: str) -> bool:
    host = host_of(url).split(":")[0]
    return host == suffix or host.endswith("." + suffix)


def classify_url(url: str, parent_hops: int, cfg: Config) -> Decision:
    """Determine how to handle a canonicalised absolute URL."""
    # English-only: reject French and Spanish URLs before anything else.
    if not is_english_url(url):
        ext = _ext(url)
        kind = "file" if ext in cfg.file_extensions else "page"
        return Decision(kind, "skip", parent_hops, "non-English URL (French/Spanish detected)")

    ext = _ext(url)
    path = path_of(url)

    is_file = ext in cfg.file_extensions
    is_page = (not is_file) and (ext in cfg.page_extensions)

    # ── Files: collect from any wto.org subdomain, never expand ──────────────
    if is_file:
        if _same_domain(url, cfg.file_host_suffix):
            return Decision("file", "collect", parent_hops,
                            f"file linked from in-scope page (ext={ext or 'none'})")
        return Decision("file", "skip", parent_hops,
                        "file on external host (out of collect scope)")

    # ── Pages: hop-based traversal ────────────────────────────────────────────
    if is_page:
        if not _same_domain(url, cfg.page_host_suffix):
            return Decision("page", "skip", parent_hops,
                            "page on external host (out of traverse scope)")
        in_core = path.startswith(cfg.core_prefix)
        if in_core:
            return Decision("page", "fetch", 0, "core subtree (under prefix)")
        child = parent_hops + 1
        if child <= cfg.max_hops_outside:
            return Decision("page", "fetch", child,
                            f"adjacent section (hops_outside={child})")
        return Decision("page", "skip", child,
                        f"beyond hop budget (hops_outside={child}>{cfg.max_hops_outside})")

    # ── Unknown extension: treat conservatively as page ───────────────────────
    if _same_domain(url, cfg.page_host_suffix):
        in_core = path.startswith(cfg.core_prefix)
        child = 0 if in_core else parent_hops + 1
        if child <= cfg.max_hops_outside:
            return Decision("page", "fetch", child,
                            f"unknown ext, treated as page (hops={child})")
    return Decision("page", "skip", parent_hops, "unknown ext, out of scope")
