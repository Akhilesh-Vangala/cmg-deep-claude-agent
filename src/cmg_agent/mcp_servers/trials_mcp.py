"""ClinicalTrials.gov MCP-style tools."""

from __future__ import annotations

import time
from typing import Any

import httpx

from cmg_agent.schemas import Citation, SourceKind, ToolCallRecord


class TrialsTools:
    name = "trials_mcp"
    BASE = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self, client: httpx.Client | None = None, offline: bool = False):
        self.client = client or httpx.Client(timeout=20.0)
        self.offline = offline

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "trials_search",
                "description": "Search ClinicalTrials.gov studies by intervention/condition.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page_size": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            }
        ]

    def call(self, tool: str, args: dict[str, Any]) -> tuple[Any, ToolCallRecord]:
        start = time.perf_counter()
        try:
            if tool != "trials_search":
                raise ValueError(f"Unknown trials tool: {tool}")
            result = self.search(args["query"], int(args.get("page_size", 5)))
            ms = (time.perf_counter() - start) * 1000
            return result, ToolCallRecord(
                tool=tool, args=args, ok=True, latency_ms=ms, result_preview=str(result)[:400]
            )
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - start) * 1000
            return {"error": str(exc)}, ToolCallRecord(
                tool=tool, args=args, ok=False, latency_ms=ms, error=str(exc)
            )

    def search(self, query: str, page_size: int = 5) -> dict[str, Any]:
        if self.offline:
            return self._offline(query)
        resp = self.client.get(
            self.BASE,
            params={
                "query.term": query,
                "pageSize": page_size,
                "format": "json",
            },
        )
        if resp.status_code >= 400:
            return self._offline(query)
        data = resp.json()
        studies = []
        for study in data.get("studies", [])[:page_size]:
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status = proto.get("statusModule", {})
            nct = ident.get("nctId", "")
            title = ident.get("briefTitle", "")
            studies.append(
                {
                    "nct_id": nct,
                    "title": title,
                    "overall_status": status.get("overallStatus"),
                    "url": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
                    "citation": Citation(
                        source=SourceKind.CLINICALTRIALS,
                        title=title or nct,
                        url=f"https://clinicaltrials.gov/study/{nct}" if nct else "https://clinicaltrials.gov/",
                        excerpt=title[:280],
                    ).model_dump(),
                }
            )
        if not studies:
            return self._offline(query)
        return {"query": query, "studies": studies}

    def _offline(self, query: str) -> dict[str, Any]:
        studies = [
            {
                "nct_id": "NCT01234567",
                "title": f"Phase 3 oncology study related to {query}",
                "overall_status": "COMPLETED",
                "url": "https://clinicaltrials.gov/study/NCT01234567",
                "citation": Citation(
                    source=SourceKind.CLINICALTRIALS,
                    title=f"Phase 3 oncology study related to {query}",
                    url="https://clinicaltrials.gov/study/NCT01234567",
                    excerpt=f"Offline fixture trial for query: {query}",
                ).model_dump(),
            },
            {
                "nct_id": "NCT07654321",
                "title": f"Immunotherapy comparative study for {query}",
                "overall_status": "RECRUITING",
                "url": "https://clinicaltrials.gov/study/NCT07654321",
                "citation": Citation(
                    source=SourceKind.CLINICALTRIALS,
                    title=f"Immunotherapy comparative study for {query}",
                    url="https://clinicaltrials.gov/study/NCT07654321",
                    excerpt=f"Offline fixture recruiting trial for {query}",
                ).model_dump(),
            },
        ]
        return {"query": query, "studies": studies, "offline": True}
