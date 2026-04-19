---
description: Walk the user through updating Profile.md for the active tax year
---

Update the active year's `Profile.md` through conversation.

1. If the year isn't obvious from context (user's last message, a file path), ask which year.
2. Read `<YEAR>/Profile.md`. Show the user a concise summary of what's already captured and which fields are `TBD` or missing.
3. Ask targeted questions to fill the gaps — one area at a time (Personal → Income → Deductions → Filing). Don't dump all questions at once.
4. For each confirmed fact, **write it immediately to `Profile.md`** under the correct `##` section. Keep bullets short.
5. If the user shares a fact that also resolves an existing item in `OpenQuestions.md`, delete that question.
6. If the user shares a fact that raises a new uncertainty, add it to `OpenQuestions.md` under `## Profile gaps`.
7. When the user says they're done (or the checklist is fully addressed), summarize what changed in this session.

Do not invent facts. If the user is unsure, write `TBD` and add a question to `OpenQuestions.md` instead of guessing.
