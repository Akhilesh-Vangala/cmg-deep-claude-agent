# Skill: Source Verification

## Purpose
Verify that each factual claim in the briefing is grounded in a retrieved citation.

## Procedure
1. For every claim, require at least one citation object with source, title, URL, excerpt.
2. Mark `supported=false` when no excerpt overlaps the claim language.
3. Prefer primary public sources: openFDA, ClinicalTrials.gov, CMS.
4. Reject promotional or unsupported superiority language.

## Output
- `supported` boolean per claim
- `confidence` in [0, 1]
- `review_flag` when grounding is weak
