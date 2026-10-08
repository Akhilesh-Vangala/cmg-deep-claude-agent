"""Run the agent on headless Claude Code (``claude -p``) as the agent runtime.

Each run gets its own directory with an MCP config, an evidence log written by
the MCP server, the raw stream-json transcript, and the parsed answer. Config
knobs (model, tools, skills) are what the ablation study varies.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_SKILLS = ROOT / "agent_workspace"
WORKSPACE_PLAIN = ROOT / "agent_workspace_noskills"

SYSTEM_PROMPT = """You are a healthcare evidence agent supporting Commercial, Medical, and Government Affairs teams at a biotech company.
Answer only from evidence returned by your tools in this session, never from memory. Use the tools before answering.
Your final answer must follow the JSON schema. Each claim needs a plain-English statement, the source_id of the tool result it rests on, and a quote copied from that result.
If skills are available, load the relevant ones before you start."""

CLOSED_BOOK_PROMPT = """You are a healthcare evidence agent supporting Commercial, Medical, and Government Affairs teams at a biotech company.
You have no tools in this session. Answer from your own knowledge.
Your final answer must follow the JSON schema. For each claim give a plain-English statement, a source_id naming where the fact comes from, and a short supporting quote."""

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "not_found", "refused"]},
        "summary": {"type": "string", "description": "2 to 5 sentence answer for the requester."},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "source_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["statement", "source_id", "quote"],
            },
        },
        "needs_human_review": {"type": "boolean"},
        "review_reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "claims", "needs_human_review", "review_reasons"],
}


@dataclass
class AgentConfig:
    name: str = "C_tools_skills"
    model: str = "claude-haiku-5-5"
    use_tools: bool = True
    use_skills: bool = True
    effort: str = "medium"
    timeout_s: int = 420


@dataclass
class RunResult:
    run_id: str
    config: dict[str, Any]
    query: str
    answer: dict[str, Any] | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    skills_loaded: list[str] = field(default_factory=list)
    num_turns: int | None = None
    latency_s: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd_list_price: float | None = None
    error: str | None = None
    run_dir: str = ""


def find_claude() -> str:
    exe = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if exe:
        return exe
    hits = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude")))
    if not hits:
        raise FileNotFoundError("Claude Code CLI not found; set CLAUDE_BIN")
    return hits[-1]


def run(query: str, cfg: AgentConfig, runs_dir: Path | str = ROOT / "runs") -> RunResult:
    run_id = f"{cfg.name}-{uuid.uuid4().hex[:8]}"
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = run_dir / "evidence.jsonl"
    evidence_path.touch()

    cmd = [
        find_claude(), "-p", query,
        "--output-format", "stream-json", "--verbose",
        "--model", cfg.model,
        "--effort", cfg.effort,
        "--json-schema", json.dumps(ANSWER_SCHEMA),
        "--no-session-persistence",
        "--permission-mode", "dontAsk",
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--system-prompt", SYSTEM_PROMPT if cfg.use_tools else CLOSED_BOOK_PROMPT,
        "--tools", "Skill" if cfg.use_skills else "",
    ]
    allowed = ["Skill"] if cfg.use_skills else []
    if cfg.use_tools:
        mcp_cfg = {"mcpServers": {"cmg": {
            "command": sys.executable,
            "args": ["-m", "cmg_agent.mcp_server"],
            "env": {"CMG_EVIDENCE_PATH": str(evidence_path), "PYTHONPATH": str(ROOT / "src")},
        }}}
        (run_dir / "mcp.json").write_text(json.dumps(mcp_cfg, indent=2))
        cmd += ["--mcp-config", str(run_dir / "mcp.json")]
        allowed.append("mcp__cmg")
    if allowed:
        cmd += ["--allowedTools", *allowed]

    cwd = WORKSPACE_SKILLS if cfg.use_skills else WORKSPACE_PLAIN
    start = time.perf_counter()
    result = RunResult(run_id=run_id, config=asdict(cfg), query=query, answer=None, run_dir=str(run_dir))
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=cfg.timeout_s)
        stdout = proc.stdout
        if proc.returncode != 0 and not stdout:
            result.error = proc.stderr[-2000:] or f"exit {proc.returncode}"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        result.error = f"timeout after {cfg.timeout_s}s"
    result.latency_s = round(time.perf_counter() - start, 2)
    (run_dir / "transcript.jsonl").write_text(stdout or "")
    _parse_stream(stdout or "", result)
    (run_dir / "result.json").write_text(json.dumps(asdict(result), indent=2))
    return result


def _parse_stream(stdout: str, result: RunResult) -> None:
    pending: dict[str, dict[str, Any]] = {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    if name == "Skill":
                        result.skills_loaded.append(str(block.get("input", {}).get("skill", "")))
                    call = {"tool": name, "input": block.get("input", {}), "ok": None}
                    pending[block.get("id", "")] = call
                    result.tool_calls.append(call)
        elif ev.get("type") == "user":
            content = ev.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                    pending[block["tool_use_id"]]["ok"] = not block.get("is_error", False)
        elif ev.get("type") == "result":
            result.num_turns = ev.get("num_turns")
            result.usage = ev.get("usage", {}) or {}
            result.cost_usd_list_price = ev.get("total_cost_usd")
            answer = ev.get("structured_output")
            if answer is None and ev.get("result"):
                try:
                    answer = json.loads(ev["result"])
                except (json.JSONDecodeError, TypeError):
                    answer = None
            result.answer = answer
            if ev.get("is_error") and not result.error:
                result.error = str(ev.get("result") or ev.get("subtype"))
