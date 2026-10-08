"""Reusable healthcare intelligence agent (deterministic + optional Claude)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from cmg_agent.mcp_servers import CMSTools, FDATools, TrialsTools
from cmg_agent.review.flags import always_escalate_coverage, flag_claims
from cmg_agent.schemas import (
    AgentRequest,
    BriefingReport,
    Citation,
    EvidenceClaim,
    SourceKind,
    ToolCallRecord,
    WorkflowKind,
)
from cmg_agent.skills.loader import load_skills, skill_catalog


class CMGDeepClaudeAgent:
    """
    Reusable agent configuration for CMG-style healthcare intelligence workflows.

    The same runtime adapts across drug-label, clinical-trial, and coverage workflows
    by swapping skills + MCP tools, not rewriting the orchestrator.
    """

    def __init__(self, offline: bool = False, traces_dir: str | Path | None = "traces"):
        self.fda = FDATools(offline=offline)
        self.trials = TrialsTools(offline=offline)
        self.cms = CMSTools(offline=offline)
        self.skills = load_skills()
        self.traces_dir = Path(traces_dir) if traces_dir else None
        if self.traces_dir:
            self.traces_dir.mkdir(parents=True, exist_ok=True)

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for server in (self.fda, self.trials, self.cms):
            tools.extend(server.list_tools())
        return tools

    def run(self, request: AgentRequest) -> BriefingReport:
        task_id = f"cmg-{uuid.uuid4().hex[:10]}"
        drugs = request.drugs or self._infer_drugs(request.query)
        trace: list[ToolCallRecord] = []
        citations: list[Citation] = []
        claims: list[EvidenceClaim] = []

        # Skill-guided planning: always use label extraction for drug workflows.
        if request.workflow in {
            WorkflowKind.DRUG_LABEL,
            WorkflowKind.COMPARATIVE_BRIEFING,
        }:
            for drug in drugs:
                label, rec = self.fda.call("fda_search_label", {"drug": drug, "limit": 2})
                trace.append(rec)
                warn, wrec = self.fda.call("fda_get_warnings", {"drug": drug})
                trace.append(wrec)
                claims.extend(self._claims_from_label(drug, label, warn, citations))

        if request.workflow in {
            WorkflowKind.CLINICAL_TRIALS,
            WorkflowKind.COMPARATIVE_BRIEFING,
        }:
            q = " ".join(drugs) if drugs else request.query
            trials, trec = self.trials.call("trials_search", {"query": q, "page_size": 5})
            trace.append(trec)
            claims.extend(self._claims_from_trials(q, trials, citations))

        if request.workflow in {WorkflowKind.COVERAGE, WorkflowKind.COMPARATIVE_BRIEFING}:
            topic = drugs[0] if drugs else request.query
            cov, crec = self.cms.call("cms_coverage_lookup", {"topic": topic})
            trace.append(crec)
            claims.extend(self._claims_from_cms(topic, cov, citations))

        # Inject a deliberate review case if user asks for superiority language.
        if re.search(r"\b(better than|superior to|best in class)\b", request.query, re.I):
            claims.append(
                EvidenceClaim(
                    claim="One therapy is superior to the other based on this briefing alone.",
                    supported=False,
                    citations=[],
                    confidence=0.1,
                    review_flag=True,
                    review_reason="Unsupported comparative superiority claim",
                )
            )

        flags = flag_claims(claims)
        if request.workflow in {WorkflowKind.COVERAGE, WorkflowKind.COMPARATIVE_BRIEFING}:
            flags.append(always_escalate_coverage(drugs[0] if drugs else "topic"))

        summary = self._summarize(request, drugs, claims)
        report = BriefingReport(
            task_id=task_id,
            workflow=request.workflow,
            query=request.query,
            summary=summary,
            claims=claims,
            citations=self._unique_citations(citations),
            human_review_flags=flags,
            tool_trace=trace,
            mode="deterministic",
        )
        self._write_trace(report)
        return report

    def adapt_workflow(self, workflow: WorkflowKind) -> dict[str, Any]:
        """Show the same runtime can switch workflows without code rewrite."""
        mapping = {
            WorkflowKind.DRUG_LABEL: ["label_extraction", "source_verification", "escalation"],
            WorkflowKind.CLINICAL_TRIALS: ["evidence_synthesis", "source_verification", "escalation"],
            WorkflowKind.COVERAGE: ["source_verification", "escalation"],
            WorkflowKind.COMPARATIVE_BRIEFING: [
                "label_extraction",
                "evidence_synthesis",
                "source_verification",
                "escalation",
            ],
        }
        return {
            "workflow": workflow.value,
            "skills": mapping[workflow],
            "tools": [t["name"] for t in self.list_tools()],
            "available_skill_packs": skill_catalog(),
        }

    def _infer_drugs(self, query: str) -> list[str]:
        known = ["Keytruda", "Opdivo", "pembrolizumab", "nivolumab"]
        found = [d for d in known if re.search(rf"\b{re.escape(d)}\b", query, re.I)]
        # de-dupe brand/generic pairs crudely
        out: list[str] = []
        for d in found:
            if d.lower() in {"pembrolizumab"} and any(x.lower() == "keytruda" for x in out):
                continue
            if d.lower() in {"nivolumab"} and any(x.lower() == "opdivo" for x in out):
                continue
            out.append(d)
        return out[:3] or ["Keytruda", "Opdivo"]

    def _claims_from_label(
        self,
        drug: str,
        label: dict[str, Any],
        warn: dict[str, Any],
        citations: list[Citation],
    ) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        results = label.get("results") or []
        if results:
            row = results[0]
            cite = Citation.model_validate(row["citation"]) if row.get("citation") else None
            if cite:
                citations.append(cite)
            ind = row.get("indications_and_usage") or ""
            claims.append(
                EvidenceClaim(
                    claim=f"{drug} labeled indications (excerpt): {ind[:240]}",
                    supported=bool(ind and cite),
                    citations=[cite] if cite else [],
                    confidence=0.85 if ind and cite else 0.4,
                )
            )
        warning_text = (
            (warn.get("boxed_warning") or "")
            or (warn.get("warnings") or "")
            or (warn.get("adverse_reactions") or "")
        )
        wcites = [Citation.model_validate(c) for c in (warn.get("citations") or []) if c]
        citations.extend(wcites)
        claims.append(
            EvidenceClaim(
                claim=f"{drug} major warnings (excerpt): {warning_text[:240] or 'Label warnings not present in retrieved openFDA fields.'}",
                supported=bool(warning_text and wcites),
                citations=wcites,
                confidence=0.8 if warning_text and wcites else 0.45,
            )
        )
        return claims

    def _claims_from_trials(
        self, query: str, trials: dict[str, Any], citations: list[Citation]
    ) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        for study in trials.get("studies", [])[:3]:
            cite = Citation.model_validate(study["citation"])
            citations.append(cite)
            claims.append(
                EvidenceClaim(
                    claim=(
                        f"Relevant trial {study.get('nct_id')}: {study.get('title')} "
                        f"(status={study.get('overall_status')})."
                    ),
                    supported=True,
                    citations=[cite],
                    confidence=0.75,
                )
            )
        if not claims:
            claims.append(
                EvidenceClaim(
                    claim=f"No clinical trial records retrieved for '{query}'.",
                    supported=False,
                    citations=[],
                    confidence=0.3,
                    review_flag=True,
                    review_reason="Missing trial evidence",
                )
            )
        return claims

    def _claims_from_cms(
        self, topic: str, cov: dict[str, Any], citations: list[Citation]
    ) -> list[EvidenceClaim]:
        cite = Citation.model_validate(cov["citation"])
        citations.append(cite)
        return [
            EvidenceClaim(
                claim=cov.get("summary") or f"CMS coverage review required for {topic}.",
                supported=True,
                citations=[cite],
                confidence=0.6,
                review_flag=True,
                review_reason="Coverage always escalated",
            )
        ]

    def _summarize(
        self, request: AgentRequest, drugs: list[str], claims: list[EvidenceClaim]
    ) -> str:
        supported = sum(1 for c in claims if c.supported)
        return (
            f"Workflow={request.workflow.value}. Drugs={', '.join(drugs) or 'n/a'}. "
            f"Prepared an informational briefing with {len(claims)} claims "
            f"({supported} citation-supported). Skills loaded: {', '.join(skill_catalog())}. "
            "Human review required before external medical-affairs use."
        )

    def _unique_citations(self, citations: list[Citation]) -> list[Citation]:
        seen: set[str] = set()
        out: list[Citation] = []
        for c in citations:
            key = f"{c.source}:{c.url}:{c.title}"
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _write_trace(self, report: BriefingReport) -> None:
        if not self.traces_dir:
            return
        path = self.traces_dir / f"{report.task_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
