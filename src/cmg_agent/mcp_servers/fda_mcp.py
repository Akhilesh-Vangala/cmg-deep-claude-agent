"""FDA / openFDA MCP-style tools — live API with disk cache (fixtures only for CI)."""

from __future__ import annotations

import time
from typing import Any

from cmg_agent.http_cache import CachedClient
from cmg_agent.schemas import Citation, SourceKind, ToolCallRecord


class FDATools:
    name = "fda_mcp"
    BASE = "https://api.fda.gov/drug/label.json"

    def __init__(self, offline: bool = False, cache: CachedClient | None = None):
        self.offline = offline
        self.cache = cache or CachedClient()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "fda_search_label",
                "description": "Search openFDA drug labels by brand or generic name (live API).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "drug": {"type": "string"},
                        "limit": {"type": "integer", "default": 3},
                    },
                    "required": ["drug"],
                },
            },
            {
                "name": "fda_get_warnings",
                "description": "Extract boxed warnings / warnings / adverse reactions from openFDA.",
                "input_schema": {
                    "type": "object",
                    "properties": {"drug": {"type": "string"}},
                    "required": ["drug"],
                },
            },
        ]

    def call(self, tool: str, args: dict[str, Any]) -> tuple[Any, ToolCallRecord]:
        start = time.perf_counter()
        try:
            if tool == "fda_search_label":
                result = self.search_label(args["drug"], int(args.get("limit", 3)))
            elif tool == "fda_get_warnings":
                result = self.get_warnings(args["drug"])
            else:
                raise ValueError(f"Unknown FDA tool: {tool}")
            ms = (time.perf_counter() - start) * 1000
            meta = result.pop("_meta", {}) if isinstance(result, dict) else {}
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

    def search_label(self, drug: str, limit: int = 3) -> dict[str, Any]:
        if self.offline:
            return self._fixture_label(drug)

        data, meta = self.cache.get_json(
            self.BASE,
            params={
                "search": f'openfda.brand_name:"{drug}" OR openfda.generic_name:"{drug}"',
                "limit": limit,
            },
        )
        results = []
        for item in data.get("results", [])[:limit]:
            openfda = item.get("openfda", {})
            brand = (openfda.get("brand_name") or [drug])[0]
            generic = (openfda.get("generic_name") or [""])[0]
            indications = " ".join(item.get("indications_and_usage") or [""])[:1500]
            set_id = item.get("set_id")
            results.append(
                {
                    "brand": brand,
                    "generic": generic,
                    "indications_and_usage": indications,
                    "set_id": set_id,
                    "effective_time": item.get("effective_time"),
                    "source_api": self.BASE,
                    "citation": Citation(
                        source=SourceKind.OPENFDA,
                        title=f"openFDA label: {brand}",
                        url=(
                            f"https://api.fda.gov/drug/label.json?search=set_id:{set_id}"
                            if set_id
                            else self.BASE
                        ),
                        excerpt=indications[:280],
                        retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    ).model_dump(),
                }
            )
        if not results:
            raise RuntimeError(f"openFDA returned 0 labels for '{drug}'")
        return {"drug": drug, "results": results, "live": True, "_meta": meta}

    def get_warnings(self, drug: str) -> dict[str, Any]:
        if self.offline:
            return self._fixture_warnings(drug)

        data, meta = self.cache.get_json(
            self.BASE,
            params={
                "search": f'openfda.brand_name:"{drug}" OR openfda.generic_name:"{drug}"',
                "limit": 1,
            },
        )
        item = (data.get("results") or [None])[0]
        if not item:
            raise RuntimeError(f"openFDA returned 0 labels for warnings on '{drug}'")
        boxed = " ".join(item.get("boxed_warning") or [])[:1500]
        warnings = " ".join(item.get("warnings") or item.get("warnings_and_cautions") or [])[:1500]
        adverse = " ".join(item.get("adverse_reactions") or [])[:1500]
        brand = (item.get("openfda", {}).get("brand_name") or [drug])[0]
        text = boxed or warnings
        cite = Citation(
            source=SourceKind.OPENFDA,
            title=f"openFDA warnings: {brand}",
            url="https://open.fda.gov/apis/drug/label/",
            excerpt=(text or adverse)[:280],
            retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        return {
            "drug": drug,
            "boxed_warning": boxed,
            "warnings": warnings,
            "adverse_reactions": adverse,
            "citations": [cite.model_dump()],
            "live": True,
            "_meta": meta,
        }

    def _fixture_label(self, drug: str) -> dict[str, Any]:
        """CI-only fixture — never used in default live mode."""
        row = {
            "brand": drug.upper(),
            "generic": drug.lower(),
            "indications_and_usage": f"[CI FIXTURE] Labeled indications placeholder for {drug}.",
            "set_id": "ci-fixture",
            "citation": Citation(
                source=SourceKind.OPENFDA,
                title=f"CI fixture label: {drug}",
                url=self.BASE,
                excerpt=f"CI fixture for {drug}",
            ).model_dump(),
        }
        return {"drug": drug, "results": [row], "live": False, "_meta": {"cache": "fixture", "latency_ms": 0.1}}

    def _fixture_warnings(self, drug: str) -> dict[str, Any]:
        cite = Citation(
            source=SourceKind.OPENFDA,
            title=f"CI fixture warnings: {drug}",
            url=self.BASE,
            excerpt=f"CI fixture warnings for {drug}",
        )
        return {
            "drug": drug,
            "boxed_warning": f"[CI FIXTURE] Warning placeholder for {drug}.",
            "warnings": "",
            "adverse_reactions": f"[CI FIXTURE] Adverse reactions placeholder for {drug}.",
            "citations": [cite.model_dump()],
            "live": False,
            "_meta": {"cache": "fixture", "latency_ms": 0.1},
        }
