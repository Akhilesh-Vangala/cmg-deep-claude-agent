---
name: fda-label-lookup
description: Procedure for answering questions about an FDA drug label (indications, boxed warning, warnings, contraindications, adverse reactions, dosing). Use whenever a request names a drug product.
---

# FDA label lookup

1. Call `fda_search_labels` with the exact product name the user wrote. If nothing comes back and the user gave a brand name, try the generic name once.
2. **Pick the right product.** Several labels can share a name (for example KEYTRUDA and KEYTRUDA QLEX, or Lunsumio and Lunsumio Velo).
   - Prefer the candidate whose `brand_name` matches the user's wording exactly, ignoring case.
   - If the user's wording fits more than one product equally well, answer for the exact match and mention the other product in `review_reasons` so a reviewer can confirm.
   - Never mix sections from different set_ids into one product's answer.
3. Check `sections_available` before asking for a section. If a label has no `boxed_warning`, say the label has no boxed warning. Do not borrow text from `warnings_and_cautions` and call it a boxed warning.
4. Read only the sections the question needs with `fda_get_label_section`.
5. **Not found** means `fda_search_labels` returned no candidates for both the brand and generic names. Then set `status` to `not_found`, make no claims about the product, and do not answer from memory.
