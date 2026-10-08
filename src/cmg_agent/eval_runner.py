from __future__ import annotations

import argparse
import json
from pathlib import Path

from cmg_agent.agent import CMGDeepClaudeAgent
from cmg_agent.schemas import AgentRequest, EvalScore, WorkflowKind


def score_task(task: dict, report) -> EvalScore:
    expected_flags = set(task.get("expect_review_severities", []))
    got_flags = {f.severity for f in report.human_review_flags}
    review_ok = expected_flags.issubset(got_flags) if expected_flags else True

    claims = report.claims
    supported_rate = (
        sum(1 for c in claims if c.supported) / len(claims) if claims else 0.0
    )
    tool_ok = (
        sum(1 for t in report.tool_trace if t.ok) / len(report.tool_trace)
        if report.tool_trace
        else 0.0
    )

    min_supported = float(task.get("min_citation_supported_rate", 0.5))
    min_tools = float(task.get("min_tool_success_rate", 0.8))
    must_refuse_superiority = task.get("must_flag_unsupported_superiority", False)
    superiority_flagged = any(
        (c.review_flag and "superior" in (c.review_reason or "").lower())
        or ("superior" in c.claim.lower() and not c.supported)
        for c in claims
    )
    if must_refuse_superiority and not superiority_flagged:
        review_ok = False

    passed = (
        supported_rate >= min_supported
        and tool_ok >= min_tools
        and review_ok
        and len(report.citations) >= int(task.get("min_citations", 1))
    )
    return EvalScore(
        task_id=task["id"],
        passed=passed,
        citation_supported_rate=supported_rate,
        tool_success_rate=tool_ok,
        review_flags_correct=review_ok,
        notes=task.get("name", ""),
    )


def run_eval(path: Path, offline: bool = True) -> dict:
    tasks = json.loads(path.read_text(encoding="utf-8"))
    agent = CMGDeepClaudeAgent(offline=offline)
    scores: list[EvalScore] = []
    for task in tasks:
        report = agent.run(
            AgentRequest(
                query=task["query"],
                workflow=WorkflowKind(task.get("workflow", "comparative_briefing")),
                drugs=task.get("drugs", []),
            )
        )
        scores.append(score_task(task, report))

    passed = sum(1 for s in scores if s.passed)
    return {
        "n": len(scores),
        "passed": passed,
        "pass_rate": passed / len(scores) if scores else 0.0,
        "scores": [s.model_dump() for s in scores],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CMG golden eval suite")
    parser.add_argument(
        "--tasks",
        default=str(Path(__file__).resolve().parents[2] / "evals" / "golden" / "tasks.json"),
    )
    parser.add_argument("--offline", action="store_true", default=True)
    parser.add_argument("--live", action="store_true", help="Hit live public APIs")
    args = parser.parse_args()
    offline = not args.live
    result = run_eval(Path(args.tasks), offline=offline)
    print(json.dumps(result, indent=2))
    if result["passed"] < result["n"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
