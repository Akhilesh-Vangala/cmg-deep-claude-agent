"""Golden-set evaluation for the Claude Code agent and the fixed-pipeline baseline.

Usage:
  cmg-eval-agent --configs C_tools_skills --repeats 1 --workers 4
  cmg-eval-agent --configs BASELINE C_tools_skills --tasks evals/golden/agent_tasks.json

Writes per-run artifacts under runs/ and a summary to reports/.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from cmg_agent import evidence
from cmg_agent.claude_runner import ROOT, AgentConfig, run
from cmg_agent.verify import grade

CONFIGS: dict[str, AgentConfig] = {
    "A_closed_book": AgentConfig(name="A_closed_book", use_tools=False, use_skills=False),
    "B_tools_only": AgentConfig(name="B_tools_only", use_tools=True, use_skills=False),
    "C_tools_skills": AgentConfig(name="C_tools_skills", use_tools=True, use_skills=True),
    "D_tools_skills_sonnet": AgentConfig(name="D_tools_skills_sonnet", model="claude-sonnet-5-5"),
}

OPEN_WEIGHT_MODEL = "qwen2.5:7b"  # config "E_open_weight": same tools and skills, local model via Ollama

CATEGORY_TO_WORKFLOW = {
    "trials": "clinical_trials",
    "coverage": "coverage",
}


def run_baseline(task: dict[str, Any], runs_dir: Path) -> dict[str, Any]:
    """Score the original fixed pipeline (no LLM) with the same grader.

    The pipeline's claims are label/trial excerpts, so they are written to an
    evidence log as-is and always 'verify'; it is graded on picking the right
    product, flagging review, and refusing or reporting not-found correctly.
    """
    from cmg_agent.agent import CMGDeepClaudeAgent
    from cmg_agent.schemas import AgentRequest, WorkflowKind

    agent = CMGDeepClaudeAgent(offline=False, traces_dir=None)
    wf = WorkflowKind(CATEGORY_TO_WORKFLOW.get(task.get("category", ""), "drug_label"))
    start = time.perf_counter()
    try:
        report = agent.run(AgentRequest(query=task["query"], workflow=wf, drugs=[]))
    except Exception as exc:  # noqa: BLE001
        return {"answer": None, "evidence": {}, "latency_s": time.perf_counter() - start, "error": str(exc)}
    ev: dict[str, dict[str, Any]] = {}
    claims = []
    for i, c in enumerate(report.claims):
        cite = c.citations[0] if c.citations else None
        quote = (cite.excerpt if cite else "") or ""
        kind, brand, section = "other", None, None
        if cite and cite.source.value == "openfda":
            kind = "fda_label"
            brand = re.sub(r"^openFDA (label|warnings): ", "", cite.title)
            section = "indications_and_usage" if "label" in cite.title else "warnings_and_cautions"
        elif cite and cite.source.value == "clinicaltrials":
            kind = "clinical_trial"
        sid = f"ctgov:{cite.url.rsplit('/', 1)[-1]}" if kind == "clinical_trial" else f"baseline:{i}"
        ev[sid] = {"source_id": sid, "kind": kind, "text": quote, "brand_name": brand, "section": section}
        claims.append({"statement": c.claim, "source_id": sid, "quote": quote[:300]})
    answer = {
        "status": "answered",
        "summary": report.summary,
        "claims": claims,
        "needs_human_review": bool(report.human_review_flags),
        "review_reasons": [f.reason for f in report.human_review_flags],
    }
    return {"answer": answer, "evidence": ev, "latency_s": round(time.perf_counter() - start, 2), "error": None}


def run_one(task: dict[str, Any], cfg_name: str, runs_dir: Path) -> dict[str, Any]:
    if cfg_name == "BASELINE":
        out = run_baseline(task, runs_dir)
        graded = grade(task, out["answer"], out["evidence"])
        return {**graded, "config": cfg_name, "latency_s": out["latency_s"], "cost_usd_list_price": 0.0,
                "error": out["error"], "tool_calls": None, "skills_loaded": [], "run_dir": None}
    if cfg_name.startswith("E_open_weight"):
        from cmg_agent import ollama_runner
        res = ollama_runner.run(task["query"], model=OPEN_WEIGHT_MODEL, runs_dir=runs_dir)
    else:
        res = run(task["query"], CONFIGS[cfg_name], runs_dir)
    ev = evidence.load(Path(res.run_dir) / "evidence.jsonl")
    graded = grade(task, res.answer, ev)
    mcp_calls = [c for c in res.tool_calls if c["tool"].startswith("mcp__")]
    return {
        **graded,
        "config": cfg_name,
        "latency_s": res.latency_s,
        "cost_usd_list_price": res.cost_usd_list_price,
        "input_tokens": (res.usage.get("input_tokens", 0) + res.usage.get("cache_read_input_tokens", 0)
                         + res.usage.get("cache_creation_input_tokens", 0)),
        "output_tokens": res.usage.get("output_tokens", 0),
        "num_turns": res.num_turns,
        "tool_calls": len(mcp_calls),
        "tool_errors": sum(1 for c in mcp_calls if c["ok"] is False),
        "skills_loaded": res.skills_loaded,
        "error": res.error,
        "run_dir": res.run_dir,
    }


def bootstrap_ci(values: list[float], n: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    if not values:
        return (float("nan"),) * 3
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(n))
    return statistics.fmean(values), means[int(0.025 * n)], means[int(0.975 * n) - 1]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cfg in sorted({r["config"] for r in rows}):
        rs = [r for r in rows if r["config"] == cfg]
        by_task: dict[str, list[float]] = {}
        for r in rs:
            by_task.setdefault(r["task_id"], []).append(1.0 if r["passed"] else 0.0)
        task_means = [statistics.fmean(v) for v in by_task.values()]
        mean, lo, hi = bootstrap_ci(task_means)
        prec = [r["claim_precision"] for r in rs if r.get("claim_precision") is not None]
        cats: dict[str, list[float]] = {}
        for r in rs:
            cats.setdefault(r.get("category") or "?", []).append(1.0 if r["passed"] else 0.0)
        check_fail: dict[str, int] = {}
        for r in rs:
            for k, ok in r["checks"].items():
                if not ok:
                    check_fail[k] = check_fail.get(k, 0) + 1
        costs = [r["cost_usd_list_price"] for r in rs if r.get("cost_usd_list_price") is not None]
        out[cfg] = {
            "n_runs": len(rs),
            "task_pass_rate": round(mean, 3),
            "task_pass_ci95": [round(lo, 3), round(hi, 3)],
            "claim_precision_mean": round(statistics.fmean(prec), 3) if prec else None,
            "invented_nct_runs": sum(1 for r in rs if r["hallucinated_ncts"]),
            "pass_rate_by_category": {k: round(statistics.fmean(v), 3) for k, v in sorted(cats.items())},
            "failed_checks": dict(sorted(check_fail.items(), key=lambda x: -x[1])),
            "latency_s_median": round(statistics.median(r["latency_s"] for r in rs), 1),
            "cost_usd_per_task_list_price": round(statistics.fmean(costs), 4) if costs else None,
            "errors": sum(1 for r in rs if r.get("error")),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--configs", nargs="+", default=["C_tools_skills"])
    ap.add_argument("--tasks", default=str(ROOT / "evals/golden/agent_tasks.json"))
    ap.add_argument("--only", nargs="*", help="task ids to run")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "reports"))
    args = ap.parse_args()

    tasks = json.loads(Path(args.tasks).read_text())
    if args.only:
        tasks = [t for t in tasks if t["id"] in set(args.only)]
    runs_dir = ROOT / "runs"
    jobs = [(t, c) for c in args.configs for t in tasks for _ in range(args.repeats)]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_one, t, c, runs_dir): (t["id"], c) for t, c in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            tid, cfg = futs[fut]
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                row = {"task_id": tid, "config": cfg, "passed": False, "checks": {"crashed": False},
                       "hallucinated_ncts": [], "latency_s": 0.0, "error": repr(exc)}
            rows.append(row)
            mark = "PASS" if row["passed"] else "FAIL"
            failed = [k for k, v in row["checks"].items() if not v]
            print(f"[{i}/{len(jobs)}] {cfg:<24} {tid:<4} {mark} {failed if failed else ''}", flush=True)

    summary = summarize(rows)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": stamp, "tasks_file": args.tasks, "n_tasks": len(tasks),
               "repeats": args.repeats, "summary": summary, "rows": rows}
    path = out_dir / f"eval-{'-'.join(args.configs)}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
