---
description: Pick an open question, capture the answer, remove it, and reflect the answer in Profile.md if relevant
---

1. Determine the active year (ask if unclear).
2. Read `<YEAR>/OpenQuestions.md`. List the open items as a numbered menu (profile gaps first, then document questions).
3. Ask the user which one to resolve. Accept a number, a substring match, or "all that I can answer right now".
4. For each chosen item, ask the user for the answer. Confirm your interpretation back to them.
5. Apply the edits:
   - **Remove** the resolved bullet from `OpenQuestions.md`.
   - If the answer is a durable profile fact, **add a bullet to `Profile.md`** under the matching `##` section.
   - If the answer uncovers a new question, add it to `OpenQuestions.md`.
6. After the batch is done, show a short summary: "Resolved N, added M new, profile updated: yes/no."

Do not delete a question until you have a real answer. If the user doesn't know, leave the question in place and optionally reword it to be more specific.
