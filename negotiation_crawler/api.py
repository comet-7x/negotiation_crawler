"""FastAPI HTTP server — start with: python -m negotiation_crawler serve"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .base import CrawlResult, TaskInfo, TaskState

app = FastAPI(title="Negotiation Crawler API", version="0.1.0")

_tasks: dict[str, TaskInfo] = {}
_lock = threading.Lock()


class RunRequest(BaseModel):
    output_dir: str | None = None
    params: dict[str, Any] = {}


class RunResponse(BaseModel):
    task_id: str
    crawler: str
    state: str


class TaskResponse(BaseModel):
    task_id: str
    crawler: str
    state: str
    output_dir: str | None = None
    error: str | None = None
    log: str | None = None


@app.get("/crawlers")
def list_crawlers():
    from . import crawlers as reg
    return [{"name": n, "description": c.description}
            for n, c in reg.all_crawlers().items()]


@app.post("/run/{crawler_name}", response_model=RunResponse)
def run_crawler(crawler_name: str, req: RunRequest):
    from pathlib import Path
    from . import crawlers as reg
    from .config import get_config

    all_names = list(reg.all_crawlers())
    if crawler_name not in all_names and crawler_name != "all":
        raise HTTPException(
            status_code=404,
            detail=f"Unknown crawler '{crawler_name}'. Available: {all_names + ['all']}",
        )

    cfg = get_config()
    task_id = str(uuid.uuid4())
    info = TaskInfo(task_id=task_id, crawler=crawler_name, state=TaskState.PENDING,
                    params=req.params)
    with _lock:
        _tasks[task_id] = info

    def _worker_single(name: str, out: str) -> CrawlResult:
        crawler = reg.get(name)
        return crawler.run(out, **req.params)

    def _worker():
        with _lock:
            _tasks[task_id].state = TaskState.RUNNING
        try:
            if crawler_name == "all":
                from .dedup import deduplicate
                base = Path(req.output_dir or "./output")
                logs: list[str] = []
                all_ok = True
                for name in all_names:
                    out = str(base / name)
                    result = _worker_single(name, out)
                    logs.append(f"[{name}] {'OK' if result.success else 'FAILED'}: {result.error or result.output_dir}")
                    if not result.success:
                        all_ok = False
                stats = deduplicate(base)
                logs.append(f"[dedup] removed={stats['removed']} saved={stats['saved_bytes']}B")
                final = CrawlResult(
                    success=all_ok, output_dir=str(base),
                    log="\n".join(logs),
                    error="" if all_ok else "one or more crawlers failed",
                )
            else:
                output_dir = req.output_dir or cfg.get_default_out(crawler_name)
                final = _worker_single(crawler_name, output_dir)

            with _lock:
                _tasks[task_id].state = TaskState.DONE if final.success else TaskState.FAILED
                _tasks[task_id].result = final
        except Exception as exc:
            with _lock:
                _tasks[task_id].state = TaskState.FAILED
                _tasks[task_id].result = CrawlResult(
                    success=False, output_dir=req.output_dir or "", error=str(exc))

    threading.Thread(target=_worker, daemon=True).start()
    return RunResponse(task_id=task_id, crawler=crawler_name, state=TaskState.PENDING)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    with _lock:
        info = _tasks.get(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    result = info.result
    return TaskResponse(
        task_id=info.task_id, crawler=info.crawler, state=info.state,
        output_dir=result.output_dir if result else None,
        error=result.error if result else None,
        log=result.log if result else None,
    )


@app.get("/tasks")
def list_tasks():
    with _lock:
        snapshot = list(_tasks.values())
    return [{"task_id": t.task_id, "crawler": t.crawler, "state": t.state}
            for t in snapshot]


@app.get("/health")
def health():
    return {"status": "ok"}
