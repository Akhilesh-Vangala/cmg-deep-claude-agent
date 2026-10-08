"""Programmatic grading of agent answers against the evidence the agent saw.

Claim-level: a claim is *verified* when its source_id exists in the run's
evidence log and its quote is a verbatim (whitespace/quote-normalized)
substring of that document.

Task-level: each golden task declares expectations (status, review flag,
which products may be cited, required sources). A task passes only if every
declared expectation holds and no NCT ID appears that the tools never returned.
"""

from __future__ import annotations

import re
from typing import Any

from cmg_agent.evidence import normalize

NCT_RE = re.compile(r"NCT\d{8}")


def verify_claims(answer: dict[str, Any], ev: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in answer.get("claims") or []:
        sid = str(c.get("source_id", "")).strip()
        quote = str(c.get("quote", ""))
        row = ev.get(sid)
        if row is None:
            reason = "unknown_source_id"
        elif len(normalize(quote)) < 20:
            reason = "quote_too_short"
        elif normalize(quote) not in normalize(row["text"]):
            reason = "quote_not_in_source"
        else:
            reason = "ok"
        out.append({
            "source_id": sid,
            "verified": reason == "ok",
            "reason": reason,
            "brand_name": (row or {}).get("brand_name"),
            "section": (row or {}).get("section"),
            "kind": (row or {}).get("kind"),
        })
    return out


def grade(task: dict[str, Any], answer: dict[str, Any] | None, ev: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not answer:
        return {"task_id": task["id"], "passed": False, "checks": {"has_answer": False}, "claims": [],
                "n_claims": 0, "n_verified": 0, "hallucinated_ncts": []}

    claims = verify_claims(answer, ev)
    verified = [c for c in claims if c["verified"]]
    checks: dict[str, bool] = {"has_answer": True}

    if "expect_status" in task:
        allowed = task["expect_status"] if isinstance(task["expect_status"], list) else [task["expect_status"]]
        checks["status"] = answer.get("status") in allowed
    if task.get("expect_review") is not None:
        checks["review_flag"] = bool(answer.get("needs_human_review")) == task["expect_review"]
    if "min_verified_claims" in task:
        checks["min_verified_claims"] = len(verified) >= task["min_verified_claims"]
    if task.get("max_claims") is not None:
        checks["max_claims"] = len(answer.get("claims") or []) <= task["max_claims"]

    fda = [c for c in verified if c["kind"] == "fda_label"]
    if task.get("allowed_brands"):
        allowed_b = {b.upper() for b in task["allowed_brands"]}
        checks["correct_product"] = all((c["brand_name"] or "").upper() in allowed_b for c in fda)
    if task.get("require_brands"):
        cited = {(c["brand_name"] or "").upper() for c in fda}
        checks["covers_each_product"] = all(b.upper() in cited for b in task["require_brands"])
    if task.get("require_sections"):
        secs = {c["section"] for c in fda}
        checks["required_sections"] = all(s in secs for s in task["require_sections"])
    if task.get("forbid_sections"):
        secs = {c["section"] for c in claims}
        checks["forbidden_sections"] = not any(s in secs for s in task["forbid_sections"])
    if task.get("require_source_ids"):
        ids = {c["source_id"] for c in verified}
        checks["required_sources"] = all(s in ids for s in task["require_source_ids"])
    if task.get("min_trials"):
        checks["min_trials"] = len({c["source_id"] for c in verified if c["kind"] == "clinical_trial"}) >= task["min_trials"]
    if task.get("summary_regex"):
        checks["summary_content"] = re.search(task["summary_regex"], answer.get("summary", ""), re.I) is not None

    text = " ".join([answer.get("summary", "")] + [f"{c.get('statement','')} {c.get('quote','')}" for c in answer.get("claims") or []])
    seen_ncts = {sid.split(":", 1)[1] for sid, row in ev.items() if row.get("kind") == "clinical_trial"}
    hallucinated = sorted(set(NCT_RE.findall(text)) - seen_ncts)
    checks["no_invented_nct_ids"] = not hallucinated

    return {
        "task_id": task["id"],
        "category": task.get("category"),
        "passed": all(checks.values()),
        "checks": checks,
        "n_claims": len(claims),
        "n_verified": len(verified),
        "claim_precision": (len(verified) / len(claims)) if claims else None,
        "failed_claim_reasons": [c["reason"] for c in claims if not c["verified"]],
        "hallucinated_ncts": hallucinated,
        "status": answer.get("status"),
        "needs_human_review": answer.get("needs_human_review"),
    }
