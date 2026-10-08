"""Tiny disk cache for public API responses — real calls, replayable demos."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "http"
USER_AGENT = "cmg-deep-claude-agent/0.1 (+https://github.com/Akhilesh-Vangala/cmg-deep-claude-agent; research prototype)"


class CachedClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_seconds: int = 60 * 60 * 24 * 7,
        timeout: float = 30.0,
    ):
        self.cache_dir = cache_dir or DEFAULT_CACHE
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (payload, meta) where meta includes cache hit/miss and latency."""
        key = hashlib.sha256(
            json.dumps({"url": url, "params": params or {}}, sort_keys=True).encode()
        ).hexdigest()
        path = self.cache_dir / f"{key}.json"
        now = time.time()
        if path.exists():
            blob = json.loads(path.read_text(encoding="utf-8"))
            if now - blob.get("saved_at", 0) <= self.ttl:
                return blob["data"], {
                    "cache": "hit",
                    "latency_ms": 0.0,
                    "url": url,
                    "status_code": blob.get("status_code", 200),
                }

        start = time.perf_counter()
        resp = self.client.get(url, params=params)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{resp.status_code} for {url}", request=resp.request, response=resp
            )
        data = resp.json()
        path.write_text(
            json.dumps(
                {
                    "saved_at": now,
                    "status_code": resp.status_code,
                    "url": url,
                    "params": params,
                    "data": data,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return data, {
            "cache": "miss",
            "latency_ms": latency_ms,
            "url": url,
            "status_code": resp.status_code,
        }
