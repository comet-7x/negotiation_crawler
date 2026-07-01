"""Synchronous HTTP fetcher with per-host throttling, retry/backoff,
and optional robots.txt enforcement."""
from __future__ import annotations

import time
import urllib.robotparser as robotparser
from urllib.parse import urlsplit

import httpx

from ..config import Config


class Fetcher:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = httpx.Client(
            headers={"User-Agent": cfg.user_agent},
            timeout=cfg.timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last_fetch: dict[str, float] = {}

    def allowed(self, url: str) -> bool:
        if not self.cfg.respect_robots:
            return True
        host = urlsplit(url).netloc
        # Distinguish between "not yet fetched" and "fetched but no robots"
        if host not in self._robots:
            rp: robotparser.RobotFileParser | None
            rp = robotparser.RobotFileParser()
            scheme = urlsplit(url).scheme
            try:
                rp.set_url(f"{scheme}://{host}/robots.txt")
                rp.read()
            except Exception:
                rp = None
            self._robots[host] = rp

        rp = self._robots[host]
        if rp is None:
            return True
        return rp.can_fetch(self.cfg.user_agent, url)

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_fetch.get(host, 0.0)
        wait = self.cfg.request_delay - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_fetch[host] = time.time()

    def get(self, url: str) -> httpx.Response | None:
        for attempt in range(self.cfg.max_retries):
            try:
                self._throttle(url)
                r = self.client.get(url)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(self.cfg.backoff_base ** attempt)
                    continue
                return r
            except httpx.HTTPError:
                time.sleep(self.cfg.backoff_base ** attempt)
        return None

    def close(self) -> None:
        self.client.close()
