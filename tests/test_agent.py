from cmg_agent.agent import CMGDeepClaudeAgent
from cmg_agent.eval_runner import run_eval
from cmg_agent.schemas import AgentRequest, WorkflowKind
from pathlib import Path


def test_comparative_briefing_offline():
    agent = CMGDeepClaudeAgent(offline=True, traces_dir=None)
    report = agent.run(
        AgentRequest(
            query="Compare Keytruda and Opdivo labels and trials for medical-affairs review.",
            workflow=WorkflowKind.COMPARATIVE_BRIEFING,
            drugs=["Keytruda", "Opdivo"],
        )
    )
    assert report.citations
    assert report.tool_trace
    assert any(f.severity == "warn" for f in report.human_review_flags)


def test_workflow_adaptation():
    agent = CMGDeepClaudeAgent(offline=True, traces_dir=None)
    label = agent.adapt_workflow(WorkflowKind.DRUG_LABEL)
    trials = agent.adapt_workflow(WorkflowKind.CLINICAL_TRIALS)
    assert "label_extraction" in label["skills"]
    assert "evidence_synthesis" in trials["skills"]
    assert label["tools"] == trials["tools"]


def test_golden_suite_offline():
    path = Path(__file__).resolve().parents[1] / "evals" / "golden" / "tasks.json"
    result = run_eval(path, offline=True)
    assert result["n"] == 8
    assert result["passed"] == result["n"], result
