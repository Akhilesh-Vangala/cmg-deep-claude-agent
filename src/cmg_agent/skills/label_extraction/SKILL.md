# Skill: Label Extraction

## Purpose
Extract labeled indications and major warnings from FDA/openFDA drug-label tool results.

## When to use
- Comparative oncology treatment questions
- Any workflow requiring labeled indications or boxed warnings

## Procedure
1. Call `fda_search_label` for each drug name.
2. Call `fda_get_warnings` for each drug name.
3. Keep only claims that are directly supported by returned label text.
4. Cite the openFDA URL/excerpt for every indication or warning claim.
5. If label text is missing or ambiguous, set `review_flag=true`.

## Constraints
- Do not invent unlabeled or off-label uses.
- Prefer brand and generic names from the tool output.
- Informational only; escalate unsupported claims for human review.
