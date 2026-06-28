"""Configuration loading: YAML file → merged with runtime overrides.

Default config location: <repo_root>/config.yaml  (one level above this package)
Override via env var:    NEGOTIATION_CRAWLER_CONFIG=/path/to/config.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# config.yaml sits at the repo root, one directory above this package
_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or Path(
            os.environ.get("NEGOTIATION_CRAWLER_CONFIG", str(_DEFAULT_CONFIG))
        )
        self._path = path.resolve()
        self._data = _load_yaml(self._path)

    def get_src_dir(self, crawler_name: str) -> Path:
        """Absolute path to the original crawler's project directory."""
        raw = self._data["projects"][crawler_name]["src_dir"]
        p = Path(raw)
        # If absolute, use as-is; if relative, resolve against config file location
        return p if p.is_absolute() else (self._path.parent / p).resolve()

    def get_default_out(self, crawler_name: str) -> str:
        return self._data["projects"][crawler_name]["default_out"]

    def projects(self) -> dict[str, Any]:
        return self._data.get("projects", {})

    def api_host(self) -> str:
        return self._data.get("api", {}).get("host", "0.0.0.0")

    def api_port(self) -> int:
        return int(self._data.get("api", {}).get("port", 8000))


_cfg: Config | None = None


def get_config(config_path: Path | None = None) -> Config:
    global _cfg
    if _cfg is None or config_path is not None:
        _cfg = Config(config_path)
    return _cfg
