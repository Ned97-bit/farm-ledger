---
description: Re-analyze a specific document in input/ and update Files.md / Profile.md / OpenQuestions.md
argument-hint: <filename in input/>
---

Review the document `$ARGUMENTS` (interpreted as a path inside `<YEAR>/input/`).

1. Resolve the full path. If the filename is ambiguous across years, ask which year.
2. Read the file. If it's a PDF or image, extract the relevant text/values. If it's already classified (prefix before `__`), note the expected slot.
3. Cross-check against `Files.md`:
   - If an entry for this file exists, compare it to what you see and flag discrepancies.
   - If no entry exists, draft one (what it is, tax relevance, key figures).
4. Propose updates:
   - New or revised entry in `Files.md`.
   - New bullets for `Profile.md` under the right section(s).
   - New items for `OpenQuestions.md` (anything unclear).
   - Existing OpenQuestions this doc resolves (to delete).
5. Show the diff to the user. Apply only after they confirm.

Be explicit about confidence. If cost basis, tax-year assignment, or payer identity is ambiguous, raise a question rather than guessing.
