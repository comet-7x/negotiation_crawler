"""Hub configuration — loads config.yaml for default output dirs and API settings."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_DEFAULT_CONFIG = Path(__file__).parent.parent / "config.yaml"


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or Path(
            os.environ.get("NEGOTIATION_CRAWLER_CONFIG", str(_DEFAULT_CONFIG))
        )
        self._data = _load(path.resolve())

    def get_default_out(self, crawler_name: str) -> str:
        return self._data["defaults"][crawler_name]

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
