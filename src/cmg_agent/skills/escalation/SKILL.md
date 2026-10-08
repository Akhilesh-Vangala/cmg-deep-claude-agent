# Skill: Escalation / Human Review

## Purpose
Route uncertain, off-label, promotional, or coverage-sensitive content to humans.

## Escalation triggers
- Potential off-label indication claims
- Missing FDA label or empty warnings
- Coverage determinations (always escalate)
- Conflicting tool results
- Tool failures after retry

## Severity
- `info`: FYI for reviewer
- `warn`: needs confirmation before external use
- `block`: do not present as approved guidance

## Constraint
This agent never issues autonomous medical or promotional recommendations.
