from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class WorkflowKind(str, Enum):
    DRUG_LABEL = "drug_label"
    CLINICAL_TRIALS = "clinical_trials"
    COVERAGE = "coverage"
    COMPARATIVE_BRIEFING = "comparative_briefing"


class SourceKind(str, Enum):
    OPENFDA = "openfda"
    CLINICALTRIALS = "clinicaltrials"
    CMS = "cms"
    OTHER = "other"


class Citation(BaseModel):
    source: SourceKind
    title: str
    url: str
    excerpt: str = ""
    retrieved_at: str | None = None


class EvidenceClaim(BaseModel):
    claim: str
    supported: bool
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    review_flag: bool = False
    review_reason: str | None = None


class ToolCallRecord(BaseModel):
    tool: str
    args: dict[str, Any]
    ok: bool
    latency_ms: float
    error: str | None = None
    result_preview: str = ""


class HumanReviewFlag(BaseModel):
    severity: Literal["info", "warn", "block"]
    reason: str
    claim: str | None = None


class BriefingReport(BaseModel):
    task_id: str
    workflow: WorkflowKind
    query: str
    summary: str
    claims: list[EvidenceClaim]
    citations: list[Citation]
    human_review_flags: list[HumanReviewFlag]
    tool_trace: list[ToolCallRecord]
    mode: Literal["deterministic", "claude"] = "deterministic"
    disclaimer: str = (
        "Informational prototype only. Not medical advice, not promotional "
        "content, and not an autonomous clinical or commercial recommendation. "
        "Unsupported or potentially off-label claims are flagged for human review."
    )


class AgentRequest(BaseModel):
    query: str
    workflow: WorkflowKind = WorkflowKind.COMPARATIVE_BRIEFING
    drugs: list[str] = Field(default_factory=list)
    require_human_review: bool = True


class EvalScore(BaseModel):
    task_id: str
    passed: bool
    citation_supported_rate: float
    tool_success_rate: float
    review_flags_correct: bool
    notes: str = ""
