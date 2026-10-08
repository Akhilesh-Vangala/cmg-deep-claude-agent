from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from cmg_agent import __version__
from cmg_agent.agent import CMGDeepClaudeAgent
from cmg_agent.schemas import AgentRequest, WorkflowKind
from cmg_agent.skills.loader import skill_catalog

app = FastAPI(
    title="CMG Deep Claude Agent",
    description="Reusable healthcare intelligence agent with MCP tools, skills, and human review.",
    version=__version__,
)
agent = CMGDeepClaudeAgent(offline=False)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/tools")
def tools() -> dict:
    return {"tools": agent.list_tools()}


@app.get("/skills")
def skills() -> dict:
    return {"skills": skill_catalog()}


@app.get("/workflows/{workflow}")
def workflow_config(workflow: WorkflowKind) -> dict:
    return agent.adapt_workflow(workflow)


@app.post("/v1/briefing")
def briefing(req: AgentRequest):
    report = agent.run(req)
    return JSONResponse(report.model_dump())
