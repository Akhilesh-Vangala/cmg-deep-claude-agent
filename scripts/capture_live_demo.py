#!/usr/bin/env python3
"""Hit real public APIs and save a demo briefing + metrics under examples/live/."""

from __future__ import annotations

import json
from pathlib import Path

from cmg_agent.agent import CMGDeepClaudeAgent
from cmg_agent.schemas import AgentRequest, WorkflowKind

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "live"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    agent = CMGDeepClaudeAgent(offline=False, traces_dir=ROOT / "traces")
    req = AgentRequest(
        query=(
            "Compare the labeled indications and major warnings of Keytruda and Opdivo, "
            "identify relevant clinical trials, summarize the supporting evidence, and "
            "prepare a cited briefing for medical-affairs review."
        ),
        workflow=WorkflowKind.COMPARATIVE_BRIEFING,
        drugs=["Keytruda", "Opdivo"],
    )
    report = agent.run(req)
    path = OUT / f"{report.task_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    tool_ms = [t.latency_ms for t in report.tool_trace]
    metrics = {
        "task_id": report.task_id,
        "live_claims": len(report.claims),
        "live_citations": len(report.citations),
        "tool_calls": len(report.tool_trace),
        "tools_ok": sum(1 for t in report.tool_trace if t.ok),
        "tool_latency_ms": {
            "sum": sum(tool_ms),
            "max": max(tool_ms) if tool_ms else 0,
            "per_tool": [
                {"tool": t.tool, "ok": t.ok, "latency_ms": round(t.latency_ms, 1), "error": t.error}
                for t in report.tool_trace
            ],
        },
        "review_flags": [f.model_dump() for f in report.human_review_flags],
        "citation_sources": sorted({c.source.value for c in report.citations}),
        "output": str(path.relative_to(ROOT)),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
