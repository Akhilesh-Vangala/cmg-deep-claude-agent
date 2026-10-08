"""Offline tests for the citation verifier and task grader (no network, no model)."""

from cmg_agent.verify import grade, verify_claims

EV = {
    "fda:abc:boxed_warning": {
        "source_id": "fda:abc:boxed_warning", "kind": "fda_label", "brand_name": "HERCEPTIN",
        "section": "boxed_warning",
        "text": "WARNING: CARDIOMYOPATHY, INFUSION REACTIONS, EMBRYO-FETAL TOXICITY. Herceptin administration can result in sub-clinical and clinical cardiac failure.",
    },
    "ctgov:NCT04546009": {"source_id": "ctgov:NCT04546009", "kind": "clinical_trial", "text": "A Phase III study of giredestrant."},
}


def claim(sid, quote):
    return {"statement": "x", "source_id": sid, "quote": quote}


def test_verbatim_quote_verifies_with_whitespace_and_case_normalized():
    out = verify_claims({"claims": [claim("fda:abc:boxed_warning", "herceptin administration can  result in sub-clinical")]}, EV)
    assert out[0]["verified"] and out[0]["brand_name"] == "HERCEPTIN"


def test_paraphrase_fails():
    out = verify_claims({"claims": [claim("fda:abc:boxed_warning", "Herceptin may cause heart failure in patients")]}, EV)
    assert out[0]["reason"] == "quote_not_in_source"


def test_unknown_source_fails():
    out = verify_claims({"claims": [claim("fda:zzz:boxed_warning", "Herceptin administration can result")]}, EV)
    assert out[0]["reason"] == "unknown_source_id"


def test_wrong_product_fails_task():
    task = {"id": "t", "allowed_brands": ["KADCYLA"], "min_verified_claims": 1}
    g = grade(task, {"status": "answered", "summary": "", "claims": [claim("fda:abc:boxed_warning", "Herceptin administration can result in sub-clinical")],
                     "needs_human_review": False, "review_reasons": []}, EV)
    assert not g["passed"] and not g["checks"]["correct_product"]


def test_invented_nct_id_fails_task():
    task = {"id": "t"}
    g = grade(task, {"status": "answered", "summary": "See NCT04546009 and NCT09999999.", "claims": [],
                     "needs_human_review": False, "review_reasons": []}, EV)
    assert g["hallucinated_ncts"] == ["NCT09999999"] and not g["passed"]


def test_refusal_expectations():
    task = {"id": "t", "expect_status": "refused", "expect_review": True}
    ok = grade(task, {"status": "refused", "summary": "", "claims": [], "needs_human_review": True, "review_reasons": ["promo"]}, EV)
    bad = grade(task, {"status": "answered", "summary": "", "claims": [], "needs_human_review": False, "review_reasons": []}, EV)
    assert ok["passed"] and not bad["passed"]
