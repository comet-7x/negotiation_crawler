"""Build the xlsx index for wto_site crawled pages.

Reads manifest.jsonl from the crawl output dir and writes:
  * index.xlsx — one "全部" sheet + one sheet per category
"""

from __future__ import annotations

import json
from pathlib import Path

CATEGORY_ZH: dict[str, str] = {
    "overview":               "概览",
    "introduction":           "导论",
    "legal_text":             "法律文本",
    "ratification":           "接受与批准",
    "implementation":         "履约",
    "fish_fund":              "渔业基金",
    "publication":            "出版物",
    "news":                   "新闻",
    "ministerial":            "部长会简报",
    "case_story":             "案例故事",
    "international_instrument": "国际文书",
    "negotiation_submission": "谈判",
    "multimedia":             "音视频",
    "committee":              "委员会",
    "mandate_decision":       "部长决定与议定书",
    "uncategorized":          "未分类",
}

CATEGORY_ORDER = list(CATEGORY_ZH.keys())

XLSX_HEADERS = ["序号", "类别", "标题", "类型", "状态", "本地路径", "来源URL"]


def load_manifest(out_dir: Path) -> list[dict]:
    """Read manifest.jsonl; skip duplicates and hard failures."""
    manifest = out_dir / "manifest.jsonl"
    if not manifest.exists():
        return []
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("duplicate_of"):
            continue
        if r.get("error") and "access-gated" not in (r.get("error") or ""):
            continue
        rows.append(r)
    rows.sort(key=lambda r: (
        CATEGORY_ORDER.index(r.get("category", "uncategorized"))
        if r.get("category", "uncategorized") in CATEGORY_ORDER else 999,
        r.get("title") or r.get("url", ""),
    ))
    return rows


def _status(r: dict) -> str:
    if r.get("out_md_path"):
        return "已转Markdown"
    if "access-gated" in (r.get("error") or ""):
        return "受限（需浏览器）"
    if r.get("content_type") == "pdf":
        return "已下载PDF"
    if r.get("content_type") in ("html",):
        return "已下载HTML"
    if r.get("note"):
        return r["note"][:40]
    return "已下载"


def _kind(r: dict) -> str:
    ct = r.get("content_type") or ""
    if ct == "pdf":
        return "PDF"
    if ct == "html":
        return "HTML"
    if "video" in ct or (r.get("url", "").lower().endswith(".mp4")):
        return "视频"
    return ct or "?"


def _local(r: dict, out_dir: Path) -> str:
    p = r.get("out_md_path") or r.get("raw_path") or ""
    if not p:
        return ""
    full = Path(p)
    try:
        return str(full.relative_to(out_dir)).replace("\\", "/")
    except ValueError:
        return str(full).replace("\\", "/")


def _write_sheet(ws, rows: list[dict], out_dir: Path, start_seq: int = 1) -> None:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill("solid", fgColor="1F497D")
    header_font = Font(bold=True, color="FFFFFF", name="微软雅黑", size=10)
    body_font   = Font(name="微软雅黑", size=9)

    ws.append(XLSX_HEADERS)
    for cell in ws[1]:
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for i, r in enumerate(rows, start_seq):
        cat = r.get("category", "uncategorized")
        ws.append([
            i,
            CATEGORY_ZH.get(cat, cat),
            r.get("title") or r.get("url", "").split("/")[-1],
            _kind(r),
            _status(r),
            _local(r, out_dir),
            r.get("url", ""),
        ])

    col_widths = [6, 18, 55, 8, 18, 50, 70]
    for col_idx, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font      = body_font
            cell.alignment = Alignment(vertical="top", wrap_text=False)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def build_xlsx(out_dir: Path) -> Path | None:
    """Read manifest.jsonl and write index.xlsx.

    Returns the xlsx path, or None if manifest is missing/empty.
    """
    import openpyxl

    rows = load_manifest(out_dir)
    if not rows:
        print("wto_site: manifest.jsonl not found or empty — xlsx not written")
        return None

    xlsx_path = out_dir / "index.xlsx"

    wb = openpyxl.Workbook()
    ws_all = wb.active
    ws_all.title = "全部"
    _write_sheet(ws_all, rows, out_dir)

    # Per-category sheets in canonical order
    cats_seen = list(dict.fromkeys(
        r.get("category", "uncategorized") for r in rows
    ))
    cats_seen.sort(
        key=lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99
    )
    for cat in cats_seen:
        subset = [r for r in rows if r.get("category", "uncategorized") == cat]
        title  = CATEGORY_ZH.get(cat, cat)[:31]
        ws     = wb.create_sheet(title=title)
        _write_sheet(ws, subset, out_dir)

    wb.save(xlsx_path)
    dl  = sum(1 for r in rows if r.get("out_md_path") or r.get("raw_path"))
    print(f"wto_site index.xlsx: {len(rows)} rows  local={dl}")
    print(f"  XLSX -> {xlsx_path}")
    return xlsx_path
