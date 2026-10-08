"""FDA / openFDA MCP-style tools for drug labels and warnings."""

from __future__ import annotations

import time
from typing import Any

import httpx

from cmg_agent.schemas import Citation, SourceKind, ToolCallRecord


class FDATools:
    name = "fda_mcp"
    BASE = "https://api.fda.gov/drug/label.json"

    def __init__(self, client: httpx.Client | None = None, offline: bool = False):
        self.client = client or httpx.Client(timeout=20.0)
        self.offline = offline

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "fda_search_label",
                "description": "Search openFDA drug labels by brand or generic name.",
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
                "description": "Extract boxed warnings and adverse reactions from a label result.",
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
            return result, ToolCallRecord(
                tool=tool,
                args=args,
                ok=True,
                latency_ms=ms,
                result_preview=str(result)[:400],
            )
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - start) * 1000
            return {"error": str(exc)}, ToolCallRecord(
                tool=tool,
                args=args,
                ok=False,
                latency_ms=ms,
                error=str(exc),
            )

    def search_label(self, drug: str, limit: int = 3) -> dict[str, Any]:
        if self.offline:
            return self._offline_label(drug)
        query = f'openfda.brand_name:"{drug}" OR openfda.generic_name:"{drug}"'
        resp = self.client.get(self.BASE, params={"search": query, "limit": limit})
        if resp.status_code == 404:
            return self._offline_label(drug)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:limit]:
            openfda = item.get("openfda", {})
            brand = (openfda.get("brand_name") or [drug])[0]
            generic = (openfda.get("generic_name") or [""])[0]
            indications = (item.get("indications_and_usage") or [""])[0][:1200]
            results.append(
                {
                    "brand": brand,
                    "generic": generic,
                    "indications_and_usage": indications,
                    "set_id": item.get("set_id"),
                    "citation": Citation(
                        source=SourceKind.OPENFDA,
                        title=f"openFDA label: {brand}",
                        url=f"https://api.fda.gov/drug/label.json?search=set_id:{item.get('set_id')}",
                        excerpt=indications[:280],
                    ).model_dump(),
                }
            )
        return {"drug": drug, "results": results or [self._offline_label(drug)["results"][0]]}

    def get_warnings(self, drug: str) -> dict[str, Any]:
        label = self.search_label(drug, limit=1)
        if not label.get("results"):
            return {"drug": drug, "boxed_warning": "", "adverse_reactions": "", "citations": []}
        # Prefer live fields when present; offline fixture otherwise
        if self.offline or "boxed_warning" in label["results"][0]:
            row = label["results"][0]
            return {
                "drug": drug,
                "boxed_warning": row.get("boxed_warning", ""),
                "adverse_reactions": row.get("adverse_reactions", ""),
                "citations": [row.get("citation")],
            }
        # Live path: re-fetch first result raw fields via search again with richer extract
        query = f'openfda.brand_name:"{drug}" OR openfda.generic_name:"{drug}"'
        resp = self.client.get(self.BASE, params={"search": query, "limit": 1})
        if resp.status_code >= 400:
            return self._offline_warnings(drug)
        item = resp.json().get("results", [{}])[0]
        boxed = " ".join(item.get("boxed_warning") or item.get("warnings") or [""])[:1500]
        adverse = " ".join(item.get("adverse_reactions") or [""])[:1500]
        brand = (item.get("openfda", {}).get("brand_name") or [drug])[0]
        cite = Citation(
            source=SourceKind.OPENFDA,
            title=f"openFDA warnings: {brand}",
            url="https://open.fda.gov/apis/drug/label/",
            excerpt=boxed[:280] or adverse[:280],
        )
        return {
            "drug": drug,
            "boxed_warning": boxed,
            "adverse_reactions": adverse,
            "citations": [cite.model_dump()],
        }

    def _offline_label(self, drug: str) -> dict[str, Any]:
        fixtures = {
            "keytruda": {
                "brand": "KEYTRUDA",
                "generic": "pembrolizumab",
                "indications_and_usage": (
                    "KEYTRUDA is a PD-1 blocking antibody indicated for multiple oncology "
                    "uses including melanoma, NSCLC, and other labeled solid tumors as "
                    "described in the FDA-approved prescribing information."
                ),
                "boxed_warning": "Immune-mediated adverse reactions can be severe or fatal.",
                "adverse_reactions": "Fatigue, rash, diarrhea, and immune-mediated toxicities.",
            },
            "opdivo": {
                "brand": "OPDIVO",
                "generic": "nivolumab",
                "indications_and_usage": (
                    "OPDIVO is a PD-1 blocking antibody indicated for multiple oncology "
                    "uses including melanoma, NSCLC, and other labeled indications per FDA PI."
                ),
                "boxed_warning": "Immune-mediated adverse reactions can be severe or fatal.",
                "adverse_reactions": "Fatigue, rash, musculoskeletal pain, pruritus.",
            },
        }
        key = drug.strip().lower()
        row = fixtures.get(key) or {
            "brand": drug.upper(),
            "generic": drug.lower(),
            "indications_and_usage": f"Labeled oncology indications for {drug} (offline fixture).",
            "boxed_warning": f"Review FDA label warnings for {drug}.",
            "adverse_reactions": f"See adverse reactions section for {drug}.",
        }
        cite = Citation(
            source=SourceKind.OPENFDA,
            title=f"openFDA label fixture: {row['brand']}",
            url="https://open.fda.gov/apis/drug/label/",
            excerpt=row["indications_and_usage"][:280],
        )
        row["citation"] = cite.model_dump()
        return {"drug": drug, "results": [row], "offline": True}

    def _offline_warnings(self, drug: str) -> dict[str, Any]:
        label = self._offline_label(drug)["results"][0]
        return {
            "drug": drug,
            "boxed_warning": label["boxed_warning"],
            "adverse_reactions": label["adverse_reactions"],
            "citations": [label["citation"]],
            "offline": True,
        }
