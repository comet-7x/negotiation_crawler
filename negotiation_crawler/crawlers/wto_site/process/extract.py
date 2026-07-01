"""HTML processing: link extraction and HTML → Markdown conversion.

Link extraction uses selectolax (fast; handles lazy-load data-* attrs).
Markdown conversion uses bs4 + markdownify (quality-first; handles complex tables).

Risk points addressed:
1. Encoding: Content-Type header → <meta charset> → common fallbacks → utf-8(replace).
2. Noise: script/style/noscript/template/svg stripped before conversion.
3. Relative links: all href/src rewritten to absolute URLs.
4. Complex tables: rowspan/colspan/nested tables kept as inline HTML (info over beauty).
5. JS shell pages: very short body + many scripts → flagged as needs_render.
6. Entities: decoded by bs4 (&amp; &nbsp; &#8217; etc.).
7. Content extraction: conservative — prefers keeping boilerplate over losing content.
8. Lazy-load: data-href / data-url attributes extracted statically.
"""
from __future__ import annotations

import hashlib
import re

from selectolax.parser import HTMLParser

from ..fetch.urlrules import to_absolute

# Tags and attributes where links may be hidden (including lazy-load data-*).
_LINK_ATTRS = [
    ("a", "href"), ("area", "href"), ("iframe", "src"), ("frame", "src"),
    ("a", "data-href"), ("div", "data-href"), ("div", "data-url"),
    ("a", "data-url"), ("link", "href"),
]
_NOISE_TAGS = ["script", "style", "noscript", "template", "svg", "head"]

# WTO-specific: href="javascript:linkdoldoc('WT/MIN22/33.pdf', '')"
# The JS function name maps a document symbol to a docs.wto.org direct-download URL.
_LINKDOLDOC_RE = re.compile(r"linkdoldoc\(\s*['\"]([^'\"]+)['\"]\s*,")


def decode_bytes(raw: bytes, header_charset: str | None) -> str:
    """Robust decoding: HTTP charset → meta charset → common fallbacks → utf-8(replace)."""
    if header_charset:
        try:
            return raw.decode(header_charset)
        except (LookupError, UnicodeDecodeError):
            pass
    head = raw[:2048].decode("ascii", "ignore").lower()
    m = re.search(r'charset=["\']?([a-z0-9_\-]+)', head)
    if m:
        try:
            return raw.decode(m.group(1))
        except (LookupError, UnicodeDecodeError):
            pass
    for enc in ("utf-8", "windows-1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def extract_links(html: str, page_url: str) -> list[tuple[str, str]]:
    """Return [(absolute_url, anchor_text)] for all discovered links."""
    tree = HTMLParser(html)
    base = page_url
    base_node = tree.css_first("base[href]")
    if base_node:
        b = to_absolute(page_url, base_node.attributes.get("href", ""))
        if b:
            base = b

    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for tag, attr in _LINK_ATTRS:
        for node in tree.css(f"{tag}[{attr}]"):
            href = node.attributes.get(attr)
            abs_url = to_absolute(base, href or "")
            if abs_url and abs_url not in seen:
                seen.add(abs_url)
                out.append((abs_url, (node.text() or "").strip()[:200]))

    # WTO-specific: extract docs.wto.org direct links from javascript:linkdoldoc(…)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if "linkdoldoc" not in href:
            continue
        m = _LINKDOLDOC_RE.search(href)
        if not m:
            continue
        symbol = m.group(1)
        abs_url = f"https://docs.wto.org/dol2fe/Pages/SS/directdoc.aspx?filename=q:/{symbol}"
        if abs_url not in seen:
            seen.add(abs_url)
            out.append((abs_url, (node.text() or "").strip()[:200]))

    return out


def get_title(html: str) -> str:
    tree = HTMLParser(html)
    t = tree.css_first("title")
    if t and t.text():
        return t.text().strip()[:300]
    h1 = tree.css_first("h1")
    return (h1.text().strip()[:300] if h1 and h1.text() else "")


def looks_like_js_shell(html: str, threshold: int) -> bool:
    """True if the page looks like a JS-rendered shell with almost no static text."""
    tree = HTMLParser(html)
    for node in tree.css("script,style"):
        node.decompose()
    body = tree.css_first("body")
    text_len = len((body.text() if body else tree.text() or "").strip())
    script_count = len(HTMLParser(html).css("script"))
    return text_len < threshold and script_count >= 3


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def to_markdown(html: str, page_url: str) -> tuple[str, str]:
    """Convert HTML to Markdown. Returns (markdown_body, conversion_method)."""
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    soup = BeautifulSoup(html, "html.parser")

    # Strip noise tags
    for tag in _NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Rewrite relative links to absolute
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if isinstance(href, str):
            ab = to_absolute(page_url, href)
            if ab:
                a["href"] = ab
    for img in soup.find_all("img", src=True):
        src = img.get("src")
        if isinstance(src, str):
            ab = to_absolute(page_url, src)
            if ab:
                img["src"] = ab

    # Complex tables → placeholder → re-insert as inline HTML after conversion
    placeholders: dict[str, str] = {}
    for i, table in enumerate(soup.find_all("table")):
        if _is_complex_table(table):
            token = f"CPLXTABLEMARKER{i}END"
            placeholders[token] = _clean_table_html(table)
            table.replace_with(token)

    method = "markdownify-full"
    container = _pick_main(soup)
    if container is not None:
        method = "markdownify-main"
        target_html = str(container)
    else:
        body = soup.find("body")
        target_html = str(body) if body else str(soup)

    text = md(target_html, heading_style="ATX", bullets="-", strip=["script", "style"])

    for token, table_html in placeholders.items():
        text = text.replace(token, "\n\n" + table_html + "\n\n")

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, method


def _is_complex_table(table) -> bool:
    if table.find("table"):
        return True
    for cell in table.find_all(["td", "th"]):
        if cell.get("rowspan") and cell.get("rowspan") not in (None, "1"):
            return True
        if cell.get("colspan") and cell.get("colspan") not in (None, "1"):
            return True
    return False


def _clean_table_html(table) -> str:
    keep = {"rowspan", "colspan"}
    for el in table.find_all(True):
        el.attrs = {k: v for k, v in el.attrs.items() if k in keep}
    return str(table)


def _pick_main(soup):
    """Conservative main-content selector; returns None if nothing clear found."""
    for sel in ("main", "article", "#main-content", "#content", ".content"):
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 200:
            return node
    return None


def front_matter(meta: dict) -> str:
    lines = ["---"]
    for k, v in meta.items():
        sval = str(v).replace("\n", " ")
        lines.append(f"{k}: {sval}")
    lines.append("---\n")
    return "\n".join(lines)
