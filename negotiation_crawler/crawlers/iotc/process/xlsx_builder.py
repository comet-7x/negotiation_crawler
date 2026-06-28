"""
data_builder/xlsx_builder.py — Build the Excel report from the SQLite manifest.

Output columns (one sheet per category_group, plus an "All" master sheet):
  类别         | 年份 | 文件名 | 标题 | 下载链接 | 页数 | 大小(KB) | 格式
  (doc_type_zh | year | fname  | title| pdf_url  | page | size     | fmt )

Additional columns appended for analysts:
  Reference | 会议 | 届次 | 国家(仅国家报告) | 状态
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("iotc.processor")

# Column header order and source mapping
# (header_zh, db_column_or_callable)
_COL_DEFS = [
    ("类别",      "doc_type_zh"),
    ("文档类型组", "category_group"),
    ("年份",      "year"),
    ("文件名",    "_fname"),          # computed from pdf_url
    ("标题",      "title"),
    ("Reference", "reference"),
    ("会议",      "meeting"),
    ("届次",      "session"),
    ("下载链接",  "pdf_url"),
    ("页数",      "page_count"),
    ("大小(KB)",  "file_size_kb"),
    ("格式",      "_fmt"),            # computed from pdf_url
    ("国家",      "country"),
    ("发布日期",  "circulated"),
    ("作者",      "authors"),
    ("状态",      "status"),
]

_HEADERS = [h for h, _ in _COL_DEFS]
_FIELDS  = [f for _, f in _COL_DEFS]


def _clean(v: object) -> object:
    """Strip control characters that openpyxl cannot write to cells."""
    if not isinstance(v, str):
        return v
    import re
    # Remove all ASCII control chars except tab (\x09) and newline (\x0a)
    v = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", v)
    return v.strip()

def _row_to_values(row: sqlite3.Row) -> list:
    d = dict(row)
    vals = []
    for field in _FIELDS:
        if field == "_fname":
            url = d.get("pdf_url") or ""
            vals.append(_clean(url.rsplit("/", 1)[-1] if url else ""))
        elif field == "_fmt":
            url = d.get("pdf_url") or ""
            ext = url.rsplit(".", 1)[-1].upper() if "." in url else "PDF"
            vals.append(_clean(ext))
        else:
            vals.append(_clean(d.get(field) or ""))
    return vals


def build_xlsx(db_path: Path, xlsx_path: Path) -> None:
    """
    Read all English docs from the manifest and write an Excel workbook.

    Sheets:
      - "全部"  : master sheet with all records
      - one sheet per category_group (e.g. "会议报告类", "合规报告类", …)
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError(
            "openpyxl is required for Excel output. "
            "Install it with: pip install openpyxl"
        )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM docs WHERE language='en' ORDER BY category_group, doc_type, year, reference"
    ).fetchall()
    conn.close()

    if not rows:
        log.warning("No English documents found in manifest — xlsx not written.")
        return

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default sheet

    # Group rows by category_group
    groups: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        g = r["category_group"] or "其他"
        groups.setdefault(g, []).append(r)

    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", fgColor="1F497D")
    center       = Alignment(horizontal="center", vertical="center", wrap_text=False)
    link_font    = Font(color="0563C1", underline="single")

     # Column index (1-based) for the hyperlink column
    _URL_COL_IDX = _HEADERS.index("下载链接") + 1

    def _write_sheet(ws, sheet_rows):
        ws.append(_HEADERS)
        for cell in ws[1]:
            cell.font  = header_font
            cell.fill  = header_fill
            cell.alignment = center

        for row_idx, r in enumerate(sheet_rows, start=2):
            vals = _row_to_values(r)
            ws.append(vals)
            # Set hyperlink on the 下载链接 cell
            url = dict(r).get("pdf_url") or ""
            if url:
                cell = ws.cell(row=row_idx, column=_URL_COL_IDX)
                cell.hyperlink = url
                cell.value     = url
                cell.font      = link_font

        # Auto-width (capped at 60)
        for col_idx, header in enumerate(_HEADERS, 1):
            col_letter = get_column_letter(col_idx)
            max_len = len(header)
            for cell in ws.iter_rows(
                min_row=2, max_row=min(ws.max_row, 200),
                min_col=col_idx, max_col=col_idx
            ):
                v = str(cell[0].value or "")
                max_len = max(max_len, min(len(v), 60))
            ws.column_dimensions[col_letter].width = max_len + 2

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    # Master sheet
    ws_all = wb.create_sheet("全部")
    _write_sheet(ws_all, rows)
    log.info("  sheet '全部': %d rows", len(rows))

    # Per-group sheets
    for group_name, group_rows in sorted(groups.items()):
        # Excel sheet names ≤ 31 chars
        sheet_name = group_name[:31]
        ws = wb.create_sheet(sheet_name)
        _write_sheet(ws, group_rows)
        log.info("  sheet '%s': %d rows", sheet_name, len(group_rows))

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)
    log.info("Saved %s (%d total rows)", xlsx_path, len(rows))
