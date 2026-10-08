---
name: cited-evidence
description: Rules for writing claims with verifiable citations. Use before writing the final answer for any request.
---

# Cited evidence

Every claim is checked by a program after you answer. A claim passes only if its `quote` appears **word for word** in the document named by `source_id`.

- `source_id` must be copied exactly from a tool result (for example `fda:<set_id>:boxed_warning`, `ctgov:NCT01234567`, `cms:ncd:372`).
- `quote` must be copied exactly from that tool result's text: 1 to 3 consecutive sentences, at most 300 characters. Do not paraphrase, merge sentences, fix typos, or add ellipses inside a quote.
- `statement` is your plain-English claim. It must say nothing that the quote does not support.
- Write one claim per fact. Prefer 3 to 8 strong claims over many weak ones.
- Never mention an NCT ID, product, or number that did not come from a tool result in this session.
- If the tools did not return evidence for part of the question, say so in `summary` and add a review reason instead of filling the gap from memory.
