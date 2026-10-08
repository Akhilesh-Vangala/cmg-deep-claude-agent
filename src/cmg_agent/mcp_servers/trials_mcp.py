"""ClinicalTrials.gov MCP-style tools — live API v2 with disk cache."""

from __future__ import annotations

import time
from typing import Any

from cmg_agent.http_cache import CachedClient
from cmg_agent.schemas import Citation, SourceKind, ToolCallRecord


class TrialsTools:
    name = "trials_mcp"
    BASE = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self, offline: bool = False, cache: CachedClient | None = None):
        self.offline = offline
        self.cache = cache or CachedClient()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "trials_search",
                "description": "Search ClinicalTrials.gov studies by intervention/condition (live API v2).",
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
            meta = result.pop("_meta", {})
            return result, ToolCallRecord(
                tool=tool,
                args=args,
                ok=True,
                latency_ms=float(meta.get("latency_ms", ms)),
                result_preview=str(result)[:500],
            )
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - start) * 1000
            return {"error": str(exc)}, ToolCallRecord(
                tool=tool, args=args, ok=False, latency_ms=ms, error=str(exc)
            )

    def search(self, query: str, page_size: int = 5) -> dict[str, Any]:
        if self.offline:
            # Minimal CI fixture only — production demos should run live.
            study = {
                "nct_id": "NCT00000000",
                "title": f"[CI FIXTURE] Study related to {query}",
                "overall_status": "COMPLETED",
                "phases": ["PHASE3"],
                "url": "https://clinicaltrials.gov/",
                "citation": Citation(
                    source=SourceKind.CLINICALTRIALS,
                    title=f"[CI FIXTURE] {query}",
                    url="https://clinicaltrials.gov/",
                    excerpt=f"CI fixture trial for {query}",
                ).model_dump(),
            }
            return {
                "query": query,
                "studies": [study],
                "live": False,
                "_meta": {"cache": "fixture", "latency_ms": 0.1},
            }

        data, meta = self.cache.get_json(
            self.BASE,
            params={"query.term": query, "pageSize": page_size, "format": "json"},
        )
        studies = []
        for study in data.get("studies", [])[:page_size]:
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status = proto.get("statusModule", {})
            design = proto.get("designModule", {})
            nct = ident.get("nctId", "")
            title = ident.get("briefTitle", "")
            phase = design.get("phases") or design.get("phaseList", {}).get("phases")
            studies.append(
                {
                    "nct_id": nct,
                    "title": title,
                    "overall_status": status.get("overallStatus"),
                    "phases": phase,
                    "url": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
                    "source_api": self.BASE,
                    "citation": Citation(
                        source=SourceKind.CLINICALTRIALS,
                        title=title or nct,
                        url=f"https://clinicaltrials.gov/study/{nct}" if nct else "https://clinicaltrials.gov/",
                        excerpt=title[:280],
                        retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    ).model_dump(),
                }
            )
        if not studies:
            raise RuntimeError(f"ClinicalTrials.gov returned 0 studies for '{query}'")
        return {
            "query": query,
            "studies": studies,
            "live": True,
            "total_count": data.get("totalCount"),
            "_meta": meta,
        }
