"""Open-weight agent: the same tools and skills driven by a local model through Ollama.

Ollama has no skill-loading mechanism, so the SKILL.md bodies are placed in the
system prompt up front. Tools are the same Python functions the MCP server
exposes, so evidence logging and grading are identical to the Claude runs.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from cmg_agent import sources
from cmg_agent.claude_runner import ANSWER_SCHEMA, ROOT, SYSTEM_PROMPT, RunResult

OLLAMA_CHAT = "http://localhost:11434/api/chat"

TOOL_SPECS = [
    {"name": "fda_search_labels", "description": "Find FDA drug labels by brand or generic name; returns candidate products, no text.",
     "parameters": {"type": "object", "properties": {"drug": {"type": "string"}}, "required": ["drug"]}},
    {"name": "fda_get_label_section", "description": "Read one label section (indications_and_usage, boxed_warning, warnings_and_cautions, contraindications, adverse_reactions, dosage_and_administration, use_in_specific_populations). Use offset=next_offset to read long sections.",
     "parameters": {"type": "object", "properties": {"set_id": {"type": "string"}, "section": {"type": "string"}, "offset": {"type": "integer"}}, "required": ["set_id", "section"]}},
    {"name": "trials_search", "description": "Search ClinicalTrials.gov by intervention, with optional condition, phase (e.g. PHASE3), recruiting_only.",
     "parameters": {"type": "object", "properties": {"intervention": {"type": "string"}, "condition": {"type": "string"}, "phase": {"type": "string"}, "recruiting_only": {"type": "boolean"}}, "required": ["intervention"]}},
    {"name": "trials_get", "description": "Fetch one ClinicalTrials.gov record by NCT ID.",
     "parameters": {"type": "object", "properties": {"nct_id": {"type": "string"}}, "required": ["nct_id"]}},
    {"name": "cms_ncd_search", "description": "Search Medicare National Coverage Determinations by title keywords.",
     "parameters": {"type": "object", "properties": {"keywords": {"type": "string"}}, "required": ["keywords"]}},
    {"name": "cms_ncd_get", "description": "Read one NCD's description and indications/limitations.",
     "parameters": {"type": "object", "properties": {"ncd_id": {"type": "integer"}, "version": {"type": "integer"}}, "required": ["ncd_id"]}},
]


def _skills_text() -> str:
    parts = []
    for p in sorted((ROOT / "agent_workspace/.claude/skills").glob("*/SKILL.md")):
        parts.append(re.sub(r"^---.*?---\s*", "", p.read_text(), flags=re.S))
    return "\n\n".join(parts)


def run(query: str, model: str = "qwen2.5:7b", max_steps: int = 10, runs_dir: Path | str = ROOT / "runs") -> RunResult:
    name = f"E_open_weight_{model.replace(':', '_').replace('.', '_')}"
    run_id = f"{name}-{uuid.uuid4().hex[:8]}"
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CMG_EVIDENCE_PATH"] = str(run_dir / "evidence.jsonl")
    (run_dir / "evidence.jsonl").touch()

    system = f"{SYSTEM_PROMPT}\n\nSkills (follow these):\n{_skills_text()}"
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": query}]
    tools = [{"type": "function", "function": t} for t in TOOL_SPECS]
    result = RunResult(run_id=run_id, config={"name": name, "model": model}, query=query, answer=None, run_dir=str(run_dir))
    start = time.perf_counter()
    in_tok = out_tok = 0
    try:
        for _ in range(max_steps):
            r = httpx.post(OLLAMA_CHAT, json={"model": model, "messages": messages, "tools": tools, "stream": False,
                                              "options": {"temperature": 0, "num_ctx": 16384}}, timeout=600).json()
            in_tok += r.get("prompt_eval_count", 0)
            out_tok += r.get("eval_count", 0)
            msg = r["message"]
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            for call in calls:
                fn = call["function"]["name"]
                args = call["function"].get("arguments") or {}
                rec = {"tool": f"mcp__cmg__{fn}", "input": args, "ok": True}
                try:
                    out = sources.TOOLS[fn](**args)
                except Exception as exc:  # noqa: BLE001
                    out, rec["ok"] = {"error": str(exc)}, False
                result.tool_calls.append(rec)
                messages.append({"role": "tool", "content": json.dumps(out)[:12000], "tool_name": fn})
        messages.append({"role": "user", "content": "Now give your final answer as JSON matching the required schema."})
        r = httpx.post(OLLAMA_CHAT, json={"model": model, "messages": messages, "stream": False, "format": ANSWER_SCHEMA,
                                          "options": {"temperature": 0, "num_ctx": 16384}}, timeout=600).json()
        in_tok += r.get("prompt_eval_count", 0)
        out_tok += r.get("eval_count", 0)
        result.answer = json.loads(r["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        result.error = repr(exc)
    result.latency_s = round(time.perf_counter() - start, 2)
    result.usage = {"input_tokens": in_tok, "output_tokens": out_tok}
    result.cost_usd_list_price = 0.0
    result.num_turns = len([m for m in messages if m.get("role") == "assistant"])
    (run_dir / "transcript.json").write_text(json.dumps(messages, indent=2)[:2_000_000])
    from dataclasses import asdict
    (run_dir / "result.json").write_text(json.dumps(asdict(result), indent=2))
    return result
