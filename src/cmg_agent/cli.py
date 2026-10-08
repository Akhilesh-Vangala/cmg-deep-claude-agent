from __future__ import annotations

import argparse
import json

from cmg_agent.agent import CMGDeepClaudeAgent
from cmg_agent.schemas import AgentRequest, WorkflowKind


def main() -> None:
    parser = argparse.ArgumentParser(description="CMG Deep Claude Agent CLI")
    parser.add_argument(
        "-q",
        "--query",
        required=True,
        help="Natural-language healthcare intelligence request",
    )
    parser.add_argument(
        "--workflow",
        choices=[w.value for w in WorkflowKind],
        default=WorkflowKind.COMPARATIVE_BRIEFING.value,
    )
    parser.add_argument("--drugs", nargs="+", default=[])
    parser.add_argument("--offline", action="store_true", help="Use offline fixtures")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    agent = CMGDeepClaudeAgent(offline=args.offline)
    report = agent.run(
        AgentRequest(
            query=args.query,
            workflow=WorkflowKind(args.workflow),
            drugs=args.drugs,
        )
    )
    payload = report.model_dump()
    if args.pretty:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))


if __name__ == "__main__":
    main()
