"""MCP server (stdio) exposing the live healthcare-evidence tools to Claude Code.

Run directly: ``python -m cmg_agent.mcp_server``. The agent runner launches it
per task with ``CMG_EVIDENCE_PATH`` set, so each run gets its own evidence log.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from cmg_agent import sources

server = MCPServer(
    name="cmg",
    instructions=(
        "Live public healthcare evidence: FDA labels (openFDA), ClinicalTrials.gov, "
        "and CMS National Coverage Determinations. Every text-bearing result carries a "
        "source_id; cite it with a verbatim quote."
    ),
)


@server.tool()
def fda_search_labels(drug: str, limit: int = 5) -> dict[str, Any]:
    """Find FDA drug labels by brand or generic name. Returns candidate products
    (set_id, brand, generic, manufacturer, sections available) but no label text.
    Several products can share a name, so pick the one that matches the request."""
    return sources.fda_search_labels(drug, limit)


@server.tool()
def fda_get_label_section(set_id: str, section: str, offset: int = 0) -> dict[str, Any]:
    """Read one section of an FDA label. section is one of: indications_and_usage,
    boxed_warning, warnings_and_cautions, contraindications, adverse_reactions,
    dosage_and_administration, use_in_specific_populations. Long sections come back
    in pages; when next_offset is not null, call again with offset=next_offset to read on."""
    return sources.fda_get_label_section(set_id, section, offset)


@server.tool()
def trials_search(
    intervention: str,
    condition: str = "",
    phase: str = "",
    recruiting_only: bool = False,
    max_results: int = 8,
) -> dict[str, Any]:
    """Search ClinicalTrials.gov by intervention (drug name), with optional condition,
    phase (e.g. 'PHASE3'), and recruiting-only filter."""
    return sources.trials_search(intervention, condition, phase, recruiting_only, max_results)


@server.tool()
def trials_get(nct_id: str) -> dict[str, Any]:
    """Fetch one ClinicalTrials.gov record (summary, enrollment, primary outcomes)."""
    return sources.trials_get(nct_id)


@server.tool()
def cms_ncd_search(keywords: str, max_results: int = 8) -> dict[str, Any]:
    """Search Medicare National Coverage Determinations by title keywords."""
    return sources.cms_ncd_search(keywords, max_results)


@server.tool()
def cms_ncd_get(ncd_id: int, version: int = 1) -> dict[str, Any]:
    """Read the item description and indications/limitations of one NCD."""
    return sources.cms_ncd_get(ncd_id, version)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
