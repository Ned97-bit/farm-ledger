---
description: Soft-remove a quest from the active year (sets status to removed)
argument-hint: "<id or substring of label>"
---

Soft-remove a quest the user no longer needs.

Args: `$ARGUMENTS` — either a quest id (e.g., `w2_secondary`) or a substring of its label (e.g., `secondary W-2`).

Procedure:
1. Determine the active year.
2. Read `<YEAR>/_quests.json`. Find the matching quest (by id exact match first, then case-insensitive label substring).
3. If multiple match, list them and ask the user which one.
4. Set `status` to `"removed"` on the matching entry. **Do not delete the entry from the array** — soft delete preserves history.
5. Write the file back.
6. Confirm to the user which quest was removed, including its label.

Removed quests don't show in the UI but are recoverable by editing the JSON or PATCHing status back to `"active"`.
