"""Checklist of required/optional documents per year type.

Year types:
  current — the year being filed now (full intake flow)
  past    — a year already filed (keep filed return + any correspondence for Q&A)
  future  — a year being planned (projected income, estimated tax payments)

Each item:
  id        stable slug; used as filename prefix when a file is dropped on it
  label     display text
  category  grouping in the UI
  required  True -> red if missing; False -> grey if missing
  match     substrings (lowercase) used to auto-detect existing files in input/
"""

from dataclasses import dataclass, field


@dataclass
class Item:
    id: str
    label: str
    category: str
    required: bool = True
    match: list = field(default_factory=list)
    required_matches: list | None = None  # list[list[str]] — each group must have >=1 file match


# -- Current year: generic checklist covering the most common tax documents.
# Users can customize this in their local copy (rename slots to specific employers
# or brokerages, add/remove items to match their situation).
FILE_TAXES_QUEST = Item(
    "file_taxes", "File Taxes (Federal + State)", "Filing", True,
    # Intentionally strict: only the explicit "filed_return" / "state_return" slot prefixes
    # (used by the past-year onboarding wizard) count. Generic words like "federal", "1040",
    # "state", "it-201" are too easy to match accidentally against pretty-renamed reference
    # docs ("Prior Federal Return") or unrelated statements ("401k Statement").
    match=["filed_return", "state_return"],
    required_matches=[
        ["filed_return", "fed_return"],
        ["state_return", "ny_return"],
    ],
)


CURRENT_YEAR = [
    FILE_TAXES_QUEST,
    # Income — employment
    Item("w2_primary",   "W-2 — primary employer",   "Income", True,  ["w2", "w-2"]),
    Item("w2_secondary", "W-2 — secondary employer", "Income", False, ["w2", "w-2"]),
    # Income — self-employment
    Item("1099_nec",  "1099-NEC — contract / freelance", "Income", False, ["1099-nec", "1099nec"]),
    Item("1099_misc", "1099-MISC — other income",        "Income", False, ["1099-misc", "1099misc"]),
    # Income — investments
    Item("1099_b",   "1099-B — brokerage proceeds (capital gains)", "Income", False, ["1099-b", "1099b"]),
    Item("1099_div", "1099-DIV — dividends",                        "Income", False, ["1099-div", "1099div"]),
    Item("1099_int", "1099-INT — interest income",                  "Income", False, ["1099-int", "1099int"]),
    Item("1099_r",   "1099-R — retirement distributions",           "Income", False, ["1099-r", "1099r"]),
    Item("k1",       "Schedule K-1 — partnership / S-corp",         "Income", False, ["k-1", "k1"]),
    # Health / HSA
    Item("1095",     "1095-A/B/C — health coverage",              "Health / HSA", True,  ["1095"]),
    Item("1099_sa",  "1099-SA — HSA distributions",               "Health / HSA", False, ["1099-sa"]),
    Item("5498_sa",  "5498-SA — HSA contributions (arrives May)", "Health / HSA", False, ["5498-sa", "5498sa"]),
    # Deductions
    Item("1098",        "1098 — mortgage interest",          "Deductions", False, ["1098"]),
    Item("1098_e",      "1098-E — student loan interest",    "Deductions", False, ["1098-e", "1098e"]),
    Item("1098_t",      "1098-T — tuition",                  "Deductions", False, ["1098-t", "1098t"]),
    Item("property_tax","Property tax statements",           "Deductions", False, ["property tax"]),
    Item("charity",     "Charitable contribution receipts",  "Deductions", False, ["donation", "charity"]),
    # Self-employment records
    Item("se_income",    "Self-employment income records",   "Self-employment", False, ["invoice", "income"]),
    Item("se_expenses",  "Self-employment expense records",  "Self-employment", False, ["expense", "receipt"]),
    Item("estimated_tax","Estimated tax payments (1040-ES)", "Self-employment", False, ["estimated", "1040-es"]),
    # Retirement
    Item("ira_contrib", "IRA contribution confirmation", "Retirement", False, ["ira"]),
    Item("5498",        "Form 5498 — IRA contributions",  "Retirement", False, ["5498"]),
    # Prior year + ID
    Item("prior_return","Prior-year return (for carryovers)",    "Prior years & ID", True, ["prior", "return", "1040"]),
    Item("id_license",  "Driver's license / state ID (for e-file)", "Prior years & ID", True, ["license", "id"]),
    # Handoff deliverable
    Item("cpa_package", "CPA package prepared",                  "Handoff", False, ["fydocumentsprepared"]),
]

# Backward-compat alias
CURRENT_TY2025 = CURRENT_YEAR

# -- Past year: a year already filed, kept for reference and Q&A
PAST_YEAR = [
    FILE_TAXES_QUEST,
    # NOTE: legacy `filed_return` quest removed — superseded by `file_taxes` (composite fed+state).
    Item("irs_correspondence", "IRS notices / letters", "Correspondence", False, ["irs", "cp", "notice"]),
    Item("state_correspondence", "NY State / NYC notices", "Correspondence", False, ["nys", "new york", "dtf"]),
    Item("w2_1099_source", "W-2 / 1099 source docs for this year", "Source docs", False, ["w2", "w-2", "1099"]),
    Item("amended_return", "Amended return (1040-X) if any", "Amendments", False, ["1040-x", "amended", "it-201-x"]),
    Item("cpa_package", "CPA package prepared", "Handoff", False, ["fydocumentsprepared"]),
]

# -- Future year: planning / in-progress
FUTURE_YEAR = [
    FILE_TAXES_QUEST,
    Item("q1_estimated", "Q1 estimated tax receipt (Apr)", "Estimated payments", False, ["q1", "april", "1040-es"]),
    Item("q2_estimated", "Q2 estimated tax receipt (Jun)", "Estimated payments", False, ["q2", "june", "1040-es"]),
    Item("q3_estimated", "Q3 estimated tax receipt (Sep)", "Estimated payments", False, ["q3", "september", "1040-es"]),
    Item("q4_estimated", "Q4 estimated tax receipt (Jan)", "Estimated payments", False, ["q4", "january", "1040-es"]),
    Item("projected_income", "Projected income statement / offer letter", "Projections", False, ["offer", "projection", "income"]),
    Item("life_events", "Life-event docs (marriage, home, job change)", "Life events", False, ["marriage", "deed", "offer"]),
]


def checklist_for(year_type: str, year: int) -> list:
    if year_type == "past":
        return PAST_YEAR
    if year_type == "future":
        return FUTURE_YEAR
    return CURRENT_TY2025
