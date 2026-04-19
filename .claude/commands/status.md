---
description: Summarize the active year's tax readiness — docs, slots, gaps, questions
---

1. Determine the active year (ask if unclear).
2. Read the year folder contents (`input/` listing, `Profile.md`, `Files.md`, `OpenQuestions.md`).
3. Read the checklist definition in `Farm Ledger/checklist.py` to know which slots are required.
4. Print a terse status report in this format:

```
Year: <YEAR>  (tax year <YEAR-1>)

Documents in input/: <count>
Required slots filled: <filled>/<total>
Missing required: <list of slot labels>

Open questions: <count>
 - Profile gaps: <n>
 - Document questions: <n>

Top 3 next actions:
 1. ...
 2. ...
 3. ...
```

Pick the top 3 next actions yourself based on what's most blocking the CPA handoff (usually: resolve a profile gap, chase a missing required doc, or classify an unsorted file).
