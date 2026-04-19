---
description: Add a new document/requirement quest to the active year's checklist
argument-hint: "<label> | <category> | <token1,token2,...> | [required|optional]"
---

Add a new quest to the active year's checklist.

Args format (pipe-separated): `$ARGUMENTS`
- Label: human-readable text (e.g., "1099-K — Etsy")
- Category: one of Income, Deductions, Health / HSA, Self-employment, Retirement, Prior years & ID, Handoff, Other
- Tokens: comma-separated lowercase substrings that will match filenames when the user drops a matching doc (e.g., `1099-k,etsy`)
- Optional 4th arg: `required` or `optional` (default: optional)

Procedure:
1. Determine the active year (ask if unclear from context).
2. Read `<YEAR>/_quests.json`. Use `/list-quests` mentally — is there an existing quest this overlaps with? If yes, prefer to **update** (PATCH) that quest instead of adding a new one.
3. Generate a stable id from the label: lowercase, non-alphanumerics → `_`, collapse repeats.
4. Append a new entry to the array:
   ```json
   {
     "id": "<slug>",
     "label": "<label>",
     "category": "<category>",
     "required": <bool>,
     "match": ["<tok1>", "<tok2>"],
     "status": "active",
     "added_by": "<your wizard name>",
     "added_at": "<YYYY-MM-DD>"
   }
   ```
5. Write the file back. The UI will refresh within ~1s (SSE).
6. Confirm to the user what you added, in one line.

**Do not duplicate**: if an `id` already exists, append a numeric suffix. **Do not spam**: one quest per distinct real-world document or requirement.
