# CMG Deep Claude Agent

Reusable Claude-powered **healthcare intelligence** agent for CMG-style workflows: drug labels, clinical trials, and coverage pointers — with **MCP tools**, **Agent Skills**, **citations**, and **human-review gates**.

> Informational prototype only. Not medical advice. Not promotional content. Unsupported or potentially off-label claims are flagged for human review.

Suggested GitHub: `cmg-deep-claude-agent`

## Why this exists

Aligned to Genentech / CMG GenAI Applications internship themes:

- Claude Code / agent runtime patterns
- Model Context Protocol (MCP) tool access
- Reusable Agent Skills (`SKILL.md`)
- Multi-step business workflows with evaluation traces
- Human-in-the-loop escalation

The manager selects the exact internal use case. This repo is a **deliberately aligned public proposal**, not a Genentech internal system.

## Example request

> Compare the labeled indications and major warnings of two oncology treatments, identify relevant clinical trials, summarize the supporting evidence, and prepare a cited briefing for medical-affairs review.

```text
User (Medical / Commercial / Government Affairs)
        │
        ▼
Claude-style agent runtime (planning + tool selection + skills)
        │
        ├── FDA MCP  → openFDA labels / warnings
        ├── Trials MCP → ClinicalTrials.gov
        └── CMS MCP → coverage policy pointers
        │
        ▼
Structured evidence report + citations + human-review flags
```

## Exact stack

| Component | Implementation |
| --- | --- |
| Agent runtime | Python orchestrator (Claude-ready); Claude Agent SDK optional |
| Tools | MCP-style FDA / Trials / CMS servers |
| Skills | `SKILL.md` packs (label extraction, evidence synthesis, source verification, escalation) |
| Data | openFDA, ClinicalTrials.gov API, CMS coverage pointers |
| Outputs | Pydantic / JSON Schema (`BriefingReport`) |
| Service | FastAPI |
| Reliability | schema validation, retries (HTTP), human review flags |
| Evaluation | golden tasks, groundedness checks, execution traces |

## Quick start

```bash
cd cmg-deep-claude-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Offline golden eval (CI-friendly)
cmg-eval --offline

# One briefing
cmg-agent --offline --pretty \
  --drugs Keytruda Opdivo \
  -q "Compare labeled indications and major warnings of Keytruda and Opdivo, identify relevant clinical trials, and prepare a cited briefing for medical-affairs review."

# API
uvicorn cmg_agent.api.app:app --reload
```

## Reusable across workflows

Same runtime, different skill/tool emphasis — no orchestrator rewrite:

| Workflow | Skills | Tools |
| --- | --- | --- |
| `drug_label` | label extraction, source verification, escalation | FDA MCP |
| `clinical_trials` | evidence synthesis, source verification, escalation | Trials MCP |
| `coverage` | source verification, escalation | CMS MCP |
| `comparative_briefing` | all skills | FDA + Trials + CMS |

```bash
curl localhost:8000/workflows/drug_label
curl localhost:8000/workflows/clinical_trials
```

## Evaluation

Golden suite: `evals/golden/tasks.json` (8 tasks).

Measured dimensions:

- task completion (pass/fail gates)
- citation-supported claim rate
- tool success rate
- human-review flag correctness (including unsupported superiority)

Traces land in `traces/*.json`.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What “impressive” means here

1. Same agent config adapts label → trials workflows without rewriting the runtime.
2. README + architecture + sample workflows + execution traces.
3. Measured eval vs simpler/no-guardrail behavior (superiority refusal task).

## License / data

Public APIs and offline fixtures only. Respect openFDA, ClinicalTrials.gov, and CMS terms. No PHI. No autonomous clinical decisions.
