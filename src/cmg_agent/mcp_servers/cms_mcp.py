"""CMS coverage pointers — live HTTP probe + structured review escalation."""

from __future__ import annotations

import time
from typing import Any

import httpx

from cmg_agent.http_cache import USER_AGENT
from cmg_agent.schemas import Citation, SourceKind, ToolCallRecord


class CMSTools:
    name = "cms_mcp"
    # CMS MCD search UI (HTML). We probe reachability and return a structured
    # human-review pointer — we do not fabricate coverage determinations.
    MCD_URL = "https://www.cms.gov/medicare-coverage-database/search.aspx"

    def __init__(self, offline: bool = False):
        self.offline = offline
        self.client = httpx.Client(
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "cms_coverage_lookup",
                "description": (
                    "Probe CMS Medicare Coverage Database and return a review pointer "
                    "for a therapy/condition topic (never an autonomous determination)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                },
            }
        ]

    def call(self, tool: str, args: dict[str, Any]) -> tuple[Any, ToolCallRecord]:
        start = time.perf_counter()
        try:
            if tool != "cms_coverage_lookup":
                raise ValueError(f"Unknown CMS tool: {tool}")
            result = self.coverage_lookup(args["topic"])
            ms = (time.perf_counter() - start) * 1000
            return result, ToolCallRecord(
                tool=tool,
                args=args,
                ok=True,
                latency_ms=ms,
                result_preview=str(result)[:500],
            )
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - start) * 1000
            return {"error": str(exc)}, ToolCallRecord(
                tool=tool, args=args, ok=False, latency_ms=ms, error=str(exc)
            )

    def coverage_lookup(self, topic: str) -> dict[str, Any]:
        if self.offline:
            status_code, latency_ms, reachable = 0, 0.1, False
        else:
            start = time.perf_counter()
            resp = self.client.get(self.MCD_URL)
            latency_ms = (time.perf_counter() - start) * 1000
            status_code = resp.status_code
            reachable = resp.status_code < 500

        cite = Citation(
            source=SourceKind.CMS,
            title="CMS Medicare Coverage Database search",
            url=self.MCD_URL,
            excerpt=f"Live CMS MCD probe for topic '{topic}' (HTTP {status_code}).",
            retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        return {
            "topic": topic,
            "summary": (
                f"CMS Medicare Coverage Database is reachable={reachable} "
                f"(HTTP {status_code}, {latency_ms:.0f} ms). "
                f"Human medical-affairs / reimbursement review is required for '{topic}'. "
                "This tool returns a citation pointer only — not a coverage determination."
            ),
            "status": "review_required",
            "cms_http_status": status_code,
            "cms_reachable": reachable,
            "latency_ms": latency_ms,
            "live": not self.offline,
            "citation": cite.model_dump(),
        }
