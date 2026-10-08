"""CMS coverage-policy MCP-style tools (public CMS coverage data)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from cmg_agent.schemas import Citation, SourceKind, ToolCallRecord


class CMSTools:
    name = "cms_mcp"
    # CMS Coverage API (public). Falls back to offline fixtures when unavailable.
    BASE = "https://www.cms.gov/medicare-coverage-database"

    def __init__(self, client: httpx.Client | None = None, offline: bool = False):
        self.client = client or httpx.Client(timeout=20.0)
        self.offline = offline

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "cms_coverage_lookup",
                "description": "Look up CMS coverage policy context for a therapy or condition keyword.",
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
                tool=tool, args=args, ok=True, latency_ms=ms, result_preview=str(result)[:400]
            )
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - start) * 1000
            return {"error": str(exc)}, ToolCallRecord(
                tool=tool, args=args, ok=False, latency_ms=ms, error=str(exc)
            )

    def coverage_lookup(self, topic: str) -> dict[str, Any]:
        # Live CMS endpoints vary by product; for a reproducible public prototype we
        # primarily use curated offline fixtures grounded in public CMS documentation URLs,
        # optionally verifying the CMS host is reachable.
        if not self.offline:
            try:
                resp = self.client.get("https://www.cms.gov/", follow_redirects=True)
                reachable = resp.status_code < 500
            except Exception:  # noqa: BLE001
                reachable = False
        else:
            reachable = False

        policy = {
            "topic": topic,
            "summary": (
                f"Public CMS coverage resources should be reviewed for {topic}. "
                "National and local coverage determinations may limit settings of care, "
                "documentation, and billed indications. This prototype returns a citation "
                "pointer for human medical-affairs review rather than an autonomous "
                "coverage determination."
            ),
            "status": "review_required",
            "cms_reachable": reachable,
            "citation": Citation(
                source=SourceKind.CMS,
                title="CMS Medicare Coverage Database",
                url="https://www.cms.gov/medicare-coverage-database",
                excerpt=f"Coverage review pointer for topic: {topic}",
            ).model_dump(),
        }
        return policy
