---
description: Rename an existing quest (label and/or match tokens) in-place — prefer this over remove+add
argument-hint: "<id> | <new label> | <new token1,token2,...>"
---

Rename an existing quest to be more specific. Use this when you learn a real-world name for a generic quest (e.g., "W-2 — primary employer" → "W-2 — Acme Corp").

Args (pipe-separated): `$ARGUMENTS`

Procedure:
1. Determine the active year.
2. Read `<YEAR>/_quests.json`. Find the quest with matching id.
3. Update `label` and `match` fields in place. Keep the same `id` to preserve history and file-match continuity. If the new label obviously implies a different id, leave id as-is anyway — the id is an internal anchor.
4. Write the JSON back.
5. Confirm to the user in one line: `"Renamed w2_primary → W-2 — Acme Corp."`

**Prefer this over `/remove-quest` + `/add-quest`**: renaming preserves provenance and any files already matched to the old id stay matched (because the old id is still the slot prefix used in filenames).
