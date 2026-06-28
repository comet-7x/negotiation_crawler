"""Base classes shared across all crawler modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class CrawlResult:
    success: bool
    output_dir: str
    log: str = ""
    error: str = ""


@dataclass
class TaskInfo:
    task_id: str
    crawler: str
    state: TaskState = TaskState.PENDING
    result: CrawlResult | None = None
    params: dict = field(default_factory=dict)


class BaseCrawler(ABC):
    """All crawler modules implement this interface."""

    name: str          # unique slug, e.g. "fishery_book"
    description: str   # one-line human description

    @abstractmethod
    def run(self, output_dir: str, **kwargs) -> CrawlResult:
        """Run the crawler synchronously and return the result."""
        ...
