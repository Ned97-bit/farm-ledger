---
description: Rename a file inside <YEAR>/input/ and cascade the new name across every reference (Files.md, OpenQuestions.md, _figures.json, etc.)
argument-hint: "<old filename> | <new filename>"
---

Rename a file in the active year's `input/` and update every place that references it.

Args (pipe-separated): `$ARGUMENTS`
- Old filename — the current name in `<YEAR>/input/`
- New filename — the desired human-readable name

If the user only gave you the old name (no new), propose a clean name in the format `<DocType> — <Issuer> (<TaxYear>).<ext>` based on `Files.md` description + the doc's contents, and confirm with the user before renaming.

Procedure (do all of these in one atomic operation; if any step fails, stop and report):

1. **Determine the active year** (ask if unclear from context).
2. **Validate the rename**:
   - Old file must exist at `<YEAR>/input/<old>`.
   - New name must not collide with an existing file. If it does, append ` (2)`, ` (3)` until unique.
   - New name must be ASCII-only except em-dash, no slashes/colons/quotes, under 100 chars, and preserve the original extension.
3. **Rename on disk**: `mv "<YEAR>/input/<old>" "<YEAR>/input/<new>"`
4. **`<YEAR>/Files.md`**: replace the `### \`<old>\`` heading with `### \`<new>\``. Replace any in-body occurrences of `<old>` with `<new>`.
5. **`<YEAR>/OpenQuestions.md`**: replace `(<old>)` with `(<new>)` everywhere — these tag bullets under `## Document questions`.
6. **`<YEAR>/_figures.json`**: load the JSON; if `<old>` is in `source_docs`, replace with `<new>`; write back (preserve formatting).
7. **`<YEAR>/_quests.json`**: scan every `match` array for entries equal to `<old>` (rare); replace if found.
8. **`MDDocs/Recommendations.md`**: scan for any `<old>` reference; replace if found.
9. **Skip** `MDDocs/Analytics.md` — it's auto-regenerated.
10. Confirm to the user in one line: `"Renamed <old> → <new>. Updated: Files.md, OpenQuestions.md, _figures.json (and N more if applicable)."`

If the rename was a mistake, the user can revert by running `/rename-file` again with the args swapped.
