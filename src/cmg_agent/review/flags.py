from __future__ import annotations

from cmg_agent.schemas import EvidenceClaim, HumanReviewFlag


OFFLABEL_HINTS = (
    "off-label",
    "unapproved",
    "not approved",
    "superior to",
    "better than",
    "guaranteed",
)


def flag_claims(claims: list[EvidenceClaim]) -> list[HumanReviewFlag]:
    flags: list[HumanReviewFlag] = []
    for claim in claims:
        text = claim.claim.lower()
        if any(h in text for h in OFFLABEL_HINTS):
            flags.append(
                HumanReviewFlag(
                    severity="block",
                    reason="Potential off-label or promotional claim language.",
                    claim=claim.claim,
                )
            )
            claim.review_flag = True
            claim.review_reason = "Potential off-label/promotional language"
        if not claim.supported or not claim.citations:
            flags.append(
                HumanReviewFlag(
                    severity="warn",
                    reason="Claim lacks grounded citation support.",
                    claim=claim.claim,
                )
            )
            claim.review_flag = True
            claim.review_reason = claim.review_reason or "Missing grounded citation"
        if claim.confidence < 0.55:
            flags.append(
                HumanReviewFlag(
                    severity="info",
                    reason="Low confidence claim; confirm with source documents.",
                    claim=claim.claim,
                )
            )
    return flags


def always_escalate_coverage(topic: str) -> HumanReviewFlag:
    return HumanReviewFlag(
        severity="warn",
        reason=(
            f"Coverage topic '{topic}' requires human medical-affairs / reimbursement review. "
            "Prototype returns CMS pointers only."
        ),
        claim=None,
    )
