"""FastAPI HTTP server for negotiation_crawler.

Start with:
    python -m negotiation_crawler serve [--host 0.0.0.0] [--port 8000]

Java client example:
    POST  http://localhost:8000/run/iotc
    Body: {"output_dir": "/data/out", "params": {"enrich": true, "build_xlsx": true}}

    GET   http://localhost:8000/tasks/{task_id}
    GET   http://localhost:8000/crawlers
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .base import CrawlResult, TaskInfo, TaskState

app = FastAPI(title="Negotiation Crawler API", version="0.1.0")

# In-memory task store (sufficient for scheduled single-machine use)
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


@app.get("/crawlers", summary="List available crawler modules")
def list_crawlers():
    from . import crawlers as reg
    return [
        {"name": name, "description": c.description}
        for name, c in reg.all_crawlers().items()
    ]


@app.post("/run/{crawler_name}", response_model=RunResponse,
          summary="Start a crawler task (async — returns task_id immediately)")
def run_crawler(crawler_name: str, req: RunRequest):
    from . import crawlers as reg
    from .config import get_config

    try:
        crawler = reg.get(crawler_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    cfg = get_config()
    output_dir = req.output_dir or cfg.get_default_out(crawler_name)

    task_id = str(uuid.uuid4())
    info = TaskInfo(task_id=task_id, crawler=crawler_name,
                    state=TaskState.PENDING,
                    params={"output_dir": output_dir, **req.params})

    with _lock:
        _tasks[task_id] = info

    def _worker():
        with _lock:
            _tasks[task_id].state = TaskState.RUNNING
        try:
            result: CrawlResult = crawler.run(output_dir, **req.params)
            with _lock:
                _tasks[task_id].state = TaskState.DONE if result.success else TaskState.FAILED
                _tasks[task_id].result = result
        except Exception as exc:
            err_result = CrawlResult(success=False, output_dir=output_dir, error=str(exc))
            with _lock:
                _tasks[task_id].state = TaskState.FAILED
                _tasks[task_id].result = err_result

    threading.Thread(target=_worker, daemon=True).start()
    return RunResponse(task_id=task_id, crawler=crawler_name, state=TaskState.PENDING)


@app.get("/tasks/{task_id}", response_model=TaskResponse,
         summary="Poll crawler task status and result")
def get_task(task_id: str):
    with _lock:
        info = _tasks.get(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    result = info.result
    return TaskResponse(
        task_id=info.task_id,
        crawler=info.crawler,
        state=info.state,
        output_dir=result.output_dir if result else None,
        error=result.error if result else None,
        log=result.log if result else None,
    )


@app.get("/tasks", summary="List all tasks")
def list_tasks():
    with _lock:
        snapshot = list(_tasks.values())
    return [{"task_id": t.task_id, "crawler": t.crawler, "state": t.state}
            for t in snapshot]


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}
