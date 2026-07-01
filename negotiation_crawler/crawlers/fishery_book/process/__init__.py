"""processor package."""

from pathlib import Path


def build_xlsx(db_path: Path, xlsx_path: Path) -> Path:
    """Read all records from the SQLite manifest and write the audit XLSX."""
    from ..storage.db import Manifest
    from .audit_xlsx import build_audit_xlsx

    with Manifest(db_path) as manifest:
        records = manifest.all_records()
    return build_audit_xlsx(records, xlsx_path)
