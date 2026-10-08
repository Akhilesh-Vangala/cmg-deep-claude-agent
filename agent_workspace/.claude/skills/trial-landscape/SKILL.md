---
name: trial-landscape
description: Procedure for clinical-trial questions (which trials exist, phases, recruiting status, sponsors) using ClinicalTrials.gov.
---

# Trial landscape

1. Call `trials_search` with the drug (generic name works best) as `intervention`. Add `condition`, `phase` (e.g. `PHASE3`) or `recruiting_only` only when the user asked for them.
2. Report trials only from the results. Cite each with its `source_id` (`ctgov:NCT...`) and a quote from that trial's text (title, status, or phase line).
3. Use `trials_get` when you need the summary, enrollment, or primary outcome of a specific trial.
4. Trial listings are not evidence of efficacy. Never turn "a trial exists" into "the drug works for X".
5. If the search returns nothing, say so; do not substitute trials of other drugs.
