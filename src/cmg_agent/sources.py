"""Live public-data tools: openFDA labels, ClinicalTrials.gov v2, CMS Coverage API.

Plain functions so the same implementations back the MCP server (Claude) and
the open-weight tool loop (Ollama). Every document returned to a model is
written to the evidence store under the ``source_id`` the model must cite.
"""

from __future__ import annotations

import html
import re
from typing import Any

from cmg_agent import evidence
from cmg_agent.http_cache import CachedClient

FDA_URL = "https://api.fda.gov/drug/label.json"
CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"
CMS_NCD_LIST_URL = "https://api.coverage.cms.gov/v1/reports/national-coverage-ncd/"
CMS_NCD_URL = "https://api.coverage.cms.gov/v1/data/ncd/"

LABEL_SECTIONS = (
    "indications_and_usage",
    "boxed_warning",
    "warnings_and_cautions",
    "contraindications",
    "adverse_reactions",
    "dosage_and_administration",
    "use_in_specific_populations",
)
MAX_SECTION_CHARS = 6000

_client: CachedClient | None = None


def _http() -> CachedClient:
    global _client
    if _client is None:
        _client = CachedClient()
    return _client


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


# --- openFDA -----------------------------------------------------------------


def fda_search_labels(drug: str, limit: int = 5) -> dict[str, Any]:
    """Find FDA labels whose brand or generic name matches ``drug``.

    Returns candidate products only (no label text), so the agent has to pick
    the right product before reading sections. Brand names often collide
    (e.g. KEYTRUDA vs KEYTRUDA QLEX), and that choice is part of the task.
    """
    term = drug.strip().replace('"', "")
    params = {
        "search": f'openfda.brand_name:"{term}" OR openfda.generic_name:"{term}"',
        "limit": max(1, min(limit, 10)),
    }
    try:
        data, _ = _http().get_json(FDA_URL, params=params)
    except Exception as exc:  # openFDA answers 404 when nothing matches
        if "404" in str(exc):
            return {"query": drug, "candidates": [], "note": "No FDA label matched this name."}
        raise
    candidates = []
    for item in data.get("results", []):
        ofda = item.get("openfda", {})
        candidates.append(
            {
                "set_id": item.get("set_id"),
                "brand_name": (ofda.get("brand_name") or [""])[0],
                "generic_name": (ofda.get("generic_name") or [""])[0],
                "manufacturer": (ofda.get("manufacturer_name") or [""])[0],
                "route": ofda.get("route") or [],
                "effective_time": item.get("effective_time"),
                "sections_available": [s for s in LABEL_SECTIONS if item.get(s)],
            }
        )
    return {"query": drug, "candidates": candidates}


def fda_get_label_section(set_id: str, section: str, offset: int = 0) -> dict[str, Any]:
    """Return one page of a label section as citable text; long sections are paged via ``offset``."""
    if section not in LABEL_SECTIONS:
        return {"error": f"Unknown section '{section}'. Choose one of: {', '.join(LABEL_SECTIONS)}"}
    data, _ = _http().get_json(FDA_URL, params={"search": f'set_id:"{set_id}"', "limit": 1})
    item = (data.get("results") or [None])[0]
    if not item:
        return {"error": f"No label with set_id {set_id}"}
    ofda = item.get("openfda", {})
    brand = (ofda.get("brand_name") or [""])[0]
    raw = " ".join(item.get(section) or [])
    if not raw:
        return {
            "set_id": set_id,
            "brand_name": brand,
            "section": section,
            "text": "",
            "note": f"This label has no '{section}' section.",
        }
    full = _clean(raw)
    offset = max(0, int(offset))
    text = full[offset : offset + MAX_SECTION_CHARS]
    source_id = f"fda:{set_id}:{section}"
    url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}"
    # Record the whole section so a quote from any page verifies against one source_id.
    evidence.record(source_id, "fda_label", full, brand_name=brand, set_id=set_id, section=section, url=url)
    end = offset + len(text)
    return {
        "source_id": source_id,
        "brand_name": brand,
        "generic_name": (ofda.get("generic_name") or [""])[0],
        "effective_time": item.get("effective_time"),
        "section": section,
        "url": url,
        "text": text,
        "section_chars": len(full),
        "next_offset": end if end < len(full) else None,
    }


# --- ClinicalTrials.gov -----------------------------------------------------


def _study_text(proto: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    conds = proto.get("conditionsModule", {}).get("conditions", [])
    arms = proto.get("armsInterventionsModule", {}).get("interventions", [])
    sponsor = proto.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
    summary = proto.get("descriptionModule", {}).get("briefSummary", "")
    outcomes = proto.get("outcomesModule", {}).get("primaryOutcomes", [])
    fields = {
        "nct_id": ident.get("nctId", ""),
        "title": ident.get("briefTitle", ""),
        "overall_status": status.get("overallStatus", ""),
        "phases": design.get("phases") or [],
        "conditions": conds,
        "interventions": [i.get("name", "") for i in arms],
        "sponsor": sponsor,
        "start_date": status.get("startDateStruct", {}).get("date", ""),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "primary_outcomes": [o.get("measure", "") for o in outcomes],
    }
    text = (
        f"{fields['title']}. Status: {fields['overall_status']}. Phases: {', '.join(fields['phases']) or 'N/A'}. "
        f"Conditions: {', '.join(conds)}. Interventions: {', '.join(fields['interventions'])}. "
        f"Sponsor: {sponsor}. Start date: {fields['start_date']}. Enrollment: {fields['enrollment']}. "
        f"Primary outcomes: {'; '.join(fields['primary_outcomes'])}. Summary: {_clean(summary)}"
    )
    return text, fields


def trials_search(
    intervention: str,
    condition: str = "",
    phase: str = "",
    recruiting_only: bool = False,
    max_results: int = 8,
) -> dict[str, Any]:
    """Search ClinicalTrials.gov by intervention and optional condition/phase/status."""
    params: dict[str, Any] = {"query.intr": intervention, "pageSize": 50, "format": "json", "countTotal": "true"}
    if condition:
        params["query.cond"] = condition
    if recruiting_only:
        params["filter.overallStatus"] = "RECRUITING"
    data, _ = _http().get_json(CTGOV_URL, params=params)
    want_phase = phase.upper().replace(" ", "")
    studies = []
    for study in data.get("studies", []):
        text, fields = _study_text(study.get("protocolSection", {}))
        if want_phase and not any(want_phase in p.replace("_", "") for p in fields["phases"]):
            continue
        source_id = f"ctgov:{fields['nct_id']}"
        url = f"https://clinicaltrials.gov/study/{fields['nct_id']}"
        evidence.record(source_id, "clinical_trial", text, title=fields["title"], url=url)
        studies.append({"source_id": source_id, "url": url, **{k: fields[k] for k in (
            "nct_id", "title", "overall_status", "phases", "conditions", "interventions", "sponsor", "start_date")}})
        if len(studies) >= max(1, min(max_results, 15)):
            break
    return {"intervention": intervention, "condition": condition, "total_matching": data.get("totalCount"), "studies": studies}


def trials_get(nct_id: str) -> dict[str, Any]:
    """Fetch one trial record with summary, enrollment, and primary outcomes."""
    data, _ = _http().get_json(f"{CTGOV_URL}/{nct_id.strip().upper()}", params={"format": "json"})
    text, fields = _study_text(data.get("protocolSection", {}))
    source_id = f"ctgov:{fields['nct_id']}"
    url = f"https://clinicaltrials.gov/study/{fields['nct_id']}"
    evidence.record(source_id, "clinical_trial", text, title=fields["title"], url=url)
    return {"source_id": source_id, "url": url, "text": text, **fields}


# --- CMS Coverage API -------------------------------------------------------


def cms_ncd_search(keywords: str, max_results: int = 8) -> dict[str, Any]:
    """Search Medicare National Coverage Determinations (NCDs) by title keywords."""
    data, _ = _http().get_json(CMS_NCD_LIST_URL)
    words = [w for w in re.findall(r"[a-z0-9]+", keywords.lower()) if len(w) > 2]
    scored = []
    for row in data.get("data", []):
        title = row.get("title", "")
        hits = sum(w in title.lower() for w in words)
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda x: -x[0])
    return {
        "keywords": keywords,
        "results": [
            {
                "ncd_id": r["document_id"],
                "version": r["document_version"],
                "section": r["document_display_id"],
                "title": r["title"],
                "last_updated": r.get("last_updated"),
            }
            for _, r in scored[: max(1, min(max_results, 15))]
        ],
    }


def cms_ncd_get(ncd_id: int, version: int = 1) -> dict[str, Any]:
    """Fetch the indications and limitations text of one NCD as citable text."""
    data, _ = _http().get_json(CMS_NCD_URL, params={"ncdid": ncd_id, "ncdver": version})
    row = (data.get("data") or [None])[0]
    if not row:
        return {"error": f"NCD {ncd_id} v{version} not found"}
    text = _clean(
        f"{row.get('item_service_description', '')} {row.get('indications_limitations', '')}"
    )[:MAX_SECTION_CHARS]
    source_id = f"cms:ncd:{ncd_id}"
    url = f"https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid={ncd_id}&ncdver={version}"
    evidence.record(source_id, "cms_ncd", text, title=row.get("title"), url=url)
    return {
        "source_id": source_id,
        "title": row.get("title"),
        "section": row.get("document_display_id"),
        "effective_date": row.get("effective_date"),
        "url": url,
        "text": text,
    }


TOOLS = {
    "fda_search_labels": fda_search_labels,
    "fda_get_label_section": fda_get_label_section,
    "trials_search": trials_search,
    "trials_get": trials_get,
    "cms_ncd_search": cms_ncd_search,
    "cms_ncd_get": cms_ncd_get,
}
