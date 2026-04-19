---
description: Conversational onboarding for a newly created year (past / current / future)
argument-hint: <year>
---

The year `$ARGUMENTS` has been scaffolded by the UI wizard. Read `<YEAR>/_meta.json` to determine its `year_type`, then run the **matching** onboarding flow:

## If year_type = past

Goal: capture what was filed so it's useful for future reference.

1. Ask the user to drop the filed 1040 (and IT-201) into the Shipping Bin if not already done. Wait if needed.
2. Once present in `<YEAR>/input/`, read the return and extract:
   - Filing status at the time
   - AGI, taxable income, total tax
   - Federal refund/owed; NY State + NYC refund/owed
   - Any capital-loss carryforward going into the next year
   - Any credits or NOL carryforwards
3. Write those values into `<YEAR>/Profile.md` under the existing sections.
4. Ask: any IRS or NY notices received? any amended return filed? If yes, add to OpenQuestions and suggest they drop those docs too.
5. Rebuild the document catalog so `Files.md` reflects exactly what's on disk (no stale or duplicate entries from mid-onboarding re-ingests):
   `curl -sS -X POST "http://127.0.0.1:5173/api/files-md/rebuild?year=$ARGUMENTS"`
   If the endpoint isn't reachable, skip — the UI will regenerate on the next Shipping Bin action.
6. Stop. Past-year onboarding is light by design.

## If year_type = current

Goal: match the UI's new-year seed form but conversationally.

1. Confirm filing status, residency (full-year NYC?), dependents.
2. Walk through income sources: primary employment, side income (1099 expected?), brokerages, HYSA, crypto, rental, K-1.
3. Walk through deductions/benefits: 401(k), HSA (coverage type), IRA, student loans, mortgage/property tax, charity.
4. Write everything into `<YEAR>/Profile.md` immediately as facts are confirmed. Add uncertain items to `OpenQuestions.md → Profile gaps`.
5. Suggest which documents to drop next (map each confirmed income source to a checklist slot).

## If year_type = future

Goal: capture forward-looking facts.

1. Projected primary income (W-2 + equity). Any changes expected vs. last year?
2. Will side income continue? Rough 1099 target?
3. Planned 401(k) / HSA / IRA contributions.
4. Life events coming (marriage, home purchase, job change, move, ISO exercises, baby, etc.)?
5. Planned quarterly estimated payments (dates + amounts if known).
6. Write into `<YEAR>/Profile.md` under *Projected Income / Planned Retirement / Estimated Payments / Life Events*.

In all three modes: keep bullets short, write facts as soon as confirmed, and don't invent. `TBD` is always an acceptable value.
