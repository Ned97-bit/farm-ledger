"""Local Flask app for the Taxes workspace. Bind to 127.0.0.1 only."""

from __future__ import annotations

import atexit
import io
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import uuid
import zipfile
from datetime import date
from pathlib import Path

import markdown as md
from flask import Flask, abort, jsonify, request, send_file, render_template

from checklist import checklist_for as _checklist_for
import cpa_package
import quests as quests_store
from pii_redactor import redact as _redact_pii, redact_file_to_sidecar as _redact_to_sidecar


def checklist_for(year: int) -> list:
    """Return the current live quest list for a year, filtered to active items.
    Reads from <year>/_quests.json so it stays in sync with any personalization made
    by the Wizard's Tower sessions. Falls back to the template list if the year folder
    doesn't exist yet (e.g. during year creation)."""
    yd = (DATA_ROOT / str(year)).resolve()
    if not yd.exists():
        yt = default_type_for(year)
        return _checklist_for(yt, year)
    yt = effective_year_type(yd, year)
    raw = quests_store.load(year, yd, yt)
    return [_QuestShim(d) for d in raw if d.get("status", "active") == "active"]

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # git root (Taxes/)
DATA_ROOT = Path(
    os.getenv("FARM_LEDGER_DATA_ROOT")
    or Path(__file__).resolve().parent / "YearData"
).resolve()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


# -------- helpers --------

def available_years() -> list[int]:
    return sorted(
        int(p.name) for p in DATA_ROOT.iterdir()
        if p.is_dir() and re.fullmatch(r"\d{4}", p.name)
    )


def current_filing_year() -> int:
    """Dynamic: which year's April filing deadline is nearest/upcoming.
    Before May 1 → this calendar year (we're in filing season).
    On/after May 1 → next calendar year (planning toward next April)."""
    t = date.today()
    return t.year if t.month <= 4 else t.year + 1


# Back-compat: any remaining reference reads the dynamic value.
CURRENT_FILING_YEAR = current_filing_year()

MDDOCS_DIR = DATA_ROOT / "MDDocs"
GLOBAL_PROFILE_PATH = MDDOCS_DIR / "Profile.md"
CLAUDE_MD_PATH = PROJECT_ROOT / "CLAUDE.md"
SHIPPED_CLAUDE_MD = Path(__file__).resolve().parent / "CLAUDE.md.template"


def ensure_claude_md() -> None:
    """Restore CLAUDE.md at repo root from the shipped template if missing."""
    if CLAUDE_MD_PATH.exists() or not SHIPPED_CLAUDE_MD.exists():
        return
    CLAUDE_MD_PATH.write_text(SHIPPED_CLAUDE_MD.read_text())

GLOBAL_PROFILE_TEMPLATE = """# Global Tax Profile

> Stable, cross-year identity and history. Facts here persist between tax years. Per-year specifics (this year's income, this year's open questions) live in `<YEAR>/Profile.md`. Update this file whenever a durable fact changes (move, new employer, marriage, dependent added, etc.) — not when year-specific numbers change.

## Identity
- Name: TBD
- Citizenship: TBD
- Filing status (current pattern): TBD
- Dependents: TBD

## Residency history
- TBD

## Employment history
- TBD

## Financial accounts
- Brokerages: TBD
- HYSA / HSA: TBD
- Retirement: TBD

## Recurring obligations / notes
- TBD

## Filed-year history
- _Each year's outcome will be recorded here after filing — AGI, refund/owed, notable events._

## Carryforwards active
- _None tracked yet._
"""


def ensure_global_profile() -> None:
    MDDOCS_DIR.mkdir(exist_ok=True)
    if not GLOBAL_PROFILE_PATH.exists():
        GLOBAL_PROFILE_PATH.write_text(GLOBAL_PROFILE_TEMPLATE)

# -- Profile.md templates per year type
PROFILE_CURRENT = """# Tax Profile — Filing Year {year}

> Snapshot of the user's tax situation for this filing year. Update as facts are confirmed; mark unknowns with `TBD`.

## Personal
- Name: TBD
- Filing status: TBD
- Residency: TBD
- Dependents: TBD

## Summary

- TBD

## Income
- TBD

## Adjustments / Deductions / Credits
- TBD

## Filing
- TBD

## Notes / Open Questions
- TBD
"""

PROFILE_PAST = """# Tax Profile — Filing Year {year} (already filed)

> Reference snapshot of what was filed for this year. Keep filed figures so future years can reference carryforwards, AGI, and comparisons.

## Personal
- Filing status at the time: TBD
- Residency that year: TBD

## Summary

- TBD

## Filed Figures
- AGI: TBD
- Total tax: TBD
- Federal refund/owed: TBD
- NY State + NYC refund/owed: TBD
- Signed & filed on: TBD

## Carryforwards (into future years)
- Capital-loss carryforward: TBD
- Any NOL / credits carried: TBD

## Notes / Open Questions
- TBD
"""

PROFILE_FUTURE = """# Tax Profile — Filing Year {year} (planning)

> Planning snapshot for a future tax year. Use to track projected income, planned retirement contributions, quarterly estimates, and known life events that will affect the return.

## Summary

- TBD

## Projected Income
- Primary employment: TBD
- Side income / 1099: TBD
- Investment income: TBD

## Planned Retirement / Benefits
- 401(k) target: TBD
- HSA target: TBD
- IRA plans: TBD

## Estimated Tax Payments
- Q1 (Apr): TBD
- Q2 (Jun): TBD
- Q3 (Sep): TBD
- Q4 (Jan): TBD

## Life Events
- TBD (marriage, home purchase, job change, move, baby, etc.)

## Notes / Open Questions
- TBD
"""

FILES_TEMPLATE = """# Documents — Filing Year {year}

> Inventory of every document in `input/`. Each entry captures **what the document is** and **why it matters for this year's return**. Updated automatically when files are dropped into the Shipping Bin; may be edited by hand or through the Claude Code session.

_No documents yet. Drop one in the Shipping Bin to start._
"""

QUESTIONS_CURRENT = """# Open Questions — Filing Year {year}

> Outstanding items blocking or clouding this year's return. Updated automatically on each Shipping Bin drop; edit by hand or via `/resolve-question`.

## Profile gaps

_None yet._

## Document questions

_None yet._
"""

QUESTIONS_PAST = """# Open Questions — Filing Year {year} (already filed)

> Things to check or remember about this already-filed year. Examples: any notices received? any amended return? any basis / carryforward details needed for future years?

## Profile gaps

_None yet._

## Document questions

_None yet._
"""

QUESTIONS_FUTURE = """# Open Questions — Filing Year {year} (planning)

> Planning uncertainties and decisions to revisit. Examples: will side income continue? will you max HSA? any ISO exercises planned?

## Profile gaps

_None yet._

## Document questions

_None yet._
"""

PROFILE_BY_TYPE = {"current": PROFILE_CURRENT, "past": PROFILE_PAST, "future": PROFILE_FUTURE}
QUESTIONS_BY_TYPE = {"current": QUESTIONS_CURRENT, "past": QUESTIONS_PAST, "future": QUESTIONS_FUTURE}


def default_type_for(year: int) -> str:
    """Calendar-only classification (used for NEW year creation seeding)."""
    cy = current_filing_year()
    if year < cy:
        return "past"
    if year > cy:
        return "future"
    return "current"


def computed_year_type(year: int) -> str:
    """Runtime classification: derives from filing state + calendar.

    Transitions are automatic:
      - Filed returns present (both fed + state)  → past
      - Calendar-past, no filed returns           → past (late filer fallback)
      - Calendar-current                          → current
      - Calendar-future                           → future
    """
    try:
        if _has_filed_return(year):
            return "past"
    except Exception:
        pass
    return default_type_for(year)


def effective_year_type(yd: Path, year: int) -> str:
    """Resolve the year's type for runtime use.
    Priority: user override in _meta.json → computed from filing state + calendar.
    The stored `year_type` value becomes a creation-time record (informational)."""
    mp = meta_path(yd)
    if mp.is_file():
        try:
            meta = json.loads(mp.read_text())
            ov = meta.get("override_type")
            if ov in ("past", "current", "future"):
                return ov
        except json.JSONDecodeError:
            pass
    return computed_year_type(year)


def meta_path(yd: Path) -> Path:
    return yd / "_meta.json"


def read_meta(yd: Path, year: int) -> dict:
    mp = meta_path(yd)
    if mp.is_file():
        try:
            return json.loads(mp.read_text())
        except json.JSONDecodeError:
            pass
    # Backward compat: infer type from year number.
    return {"year_type": default_type_for(year)}


def write_meta(yd: Path, meta: dict) -> None:
    meta_path(yd).write_text(json.dumps(meta, indent=2))


def year_dir(year: int) -> Path:
    p = (DATA_ROOT / str(year)).resolve()
    if not p.is_dir() or p.parent != DATA_ROOT:
        abort(400, "invalid year")
    ensure_year_files(p, year)
    return p


def ensure_year_files(yd: Path, year: int, year_type: str | None = None) -> None:
    """Create Profile.md / Files.md / OpenQuestions.md / _meta.json and input/ if missing."""
    (yd / "input").mkdir(exist_ok=True)
    yt = year_type or read_meta(yd, year).get("year_type") or default_type_for(year)
    if not meta_path(yd).exists():
        write_meta(yd, {"year_type": yt, "created_at": date.today().isoformat()})
    for name, tpl in [
        ("Profile.md", PROFILE_BY_TYPE.get(yt, PROFILE_CURRENT)),
        ("Files.md", FILES_TEMPLATE),
        ("OpenQuestions.md", QUESTIONS_BY_TYPE.get(yt, QUESTIONS_CURRENT)),
    ]:
        f = yd / name
        if not f.exists():
            f.write_text(tpl.format(year=year))


def input_dir(year: int) -> Path:
    d = year_dir(year) / "input"
    d.mkdir(exist_ok=True)
    return d


def safe_input_path(year: int, rel: str) -> Path:
    """Resolve rel inside <year>/input/; reject traversal."""
    base = input_dir(year).resolve()
    target = (base / rel).resolve()
    if base not in target.parents and target != base:
        abort(400, "path traversal")
    return target


def _normalize(s: str) -> str:
    """Lowercase + collapse all non-alphanumerics to '-'. Makes `1099_b`, `1099 B`,
    and `1099-b` all compare equal."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def match_slot(filename: str, items) -> str | None:
    low_raw = filename.lower()
    low_norm = _normalize(filename)
    # Composite quests (with required_matches) are populated only by the post-pass in
    # api_checklist — exclude them here so they don't steal files from single-match quests.
    single_items = [it for it in items if not getattr(it, "required_matches", None)]
    # prefer explicit id prefix (files we saved ourselves are id__name.ext)
    if "__" in filename:
        prefix = filename.split("__", 1)[0]
        prefix_norm = _normalize(prefix)
        for it in single_items:
            if _normalize(it.id) == prefix_norm:
                return it.id
    # fallback: pick the quest whose LONGEST matching token wins (most specific beats generic)
    best_id = None
    best_len = 0
    for it in single_items:
        for tok in it.match:
            if not tok:
                continue
            if tok in low_raw or _normalize(tok) in low_norm:
                if len(tok) > best_len:
                    best_len = len(tok)
                    best_id = it.id
    return best_id


# -------- routes --------

@app.route("/")
def index():
    ensure_claude_md()
    ensure_global_profile()
    ensure_recommendations()
    return render_template("index.html")


@app.route("/api/recommendations")
def api_recommendations():
    ensure_recommendations()
    return jsonify({"html": render_md(RECOMMENDATIONS_MD_PATH)})


@app.route("/api/global")
def api_global():
    ensure_global_profile()
    return jsonify({"profile_html": render_md(GLOBAL_PROFILE_PATH)})


@app.route("/api/global", methods=["POST"])
def api_global_init():
    """First-run init: seeds Global Profile.md with provided identity fields."""
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    status = (body.get("filing_status") or "").strip()
    residency = (body.get("residency") or "").strip()
    deps = (body.get("dependents") or "").strip()
    citizenship = (body.get("citizenship") or "U.S. citizen").strip()
    txt = GLOBAL_PROFILE_TEMPLATE
    repl = {
        "- Name: TBD": f"- Name: {name or 'TBD'}",
        "- Citizenship: TBD": f"- Citizenship: {citizenship}",
        "- Filing status (current pattern): TBD": f"- Filing status (current pattern): {status or 'TBD'}",
        "- Dependents: TBD": f"- Dependents: {deps or 'None'}",
    }
    for k, v in repl.items():
        txt = txt.replace(k, v)
    if residency:
        txt = txt.replace("## Residency history\n- TBD", f"## Residency history\n- {residency}")
    GLOBAL_PROFILE_PATH.write_text(txt)
    return jsonify({"ok": True})


@app.route("/api/years")
def api_years():
    out = []
    for y in available_years():
        yd = DATA_ROOT / str(y)
        out.append({"year": y, "year_type": effective_year_type(yd, y)})
    return jsonify(out)


@app.route("/api/year-suggestion")
def api_year_suggestion():
    taken = set(available_years())
    y = CURRENT_FILING_YEAR
    while y in taken:
        y += 1
    return jsonify({"current_filing_year": CURRENT_FILING_YEAR, "next_suggested": y})


@app.route("/api/year", methods=["POST"])
def api_create_year():
    body = request.get_json(force=True) or {}
    try:
        year = int(body.get("year"))
    except (TypeError, ValueError):
        abort(400, "year must be an integer")
    if not (2000 <= year <= 2099):
        abort(400, "year out of range")
    year_type = body.get("year_type") or default_type_for(year)
    if year_type not in ("past", "current", "future"):
        abort(400, "invalid year_type")
    yd = DATA_ROOT / str(year)
    if yd.exists():
        abort(409, "year already exists")
    yd.mkdir()
    ensure_year_files(yd, year, year_type=year_type)
    return jsonify({"year": year, "year_type": year_type})


@app.route("/api/year", methods=["DELETE"])
def api_delete_year():
    try:
        year = int(request.args.get("y", ""))
    except ValueError:
        abort(400, "bad year")
    yd = (DATA_ROOT / str(year)).resolve()
    if yd.parent != DATA_ROOT or not yd.is_dir():
        abort(404)
    # Safety: refuse if input/ contains any non-hidden file
    inp = yd / "input"
    if inp.is_dir():
        has_docs = any(p.is_file() and not p.name.startswith(".") for p in inp.rglob("*"))
        if has_docs:
            abort(409, "year has documents in input/ — remove them before deleting")
    shutil.rmtree(yd)
    return jsonify({"deleted": year})


class _QuestShim:
    """Duck-typed substitute for a checklist.Item so match_slot can consume it."""
    __slots__ = ("id", "label", "category", "required", "match", "required_matches")

    def __init__(self, d: dict):
        self.id = d["id"]
        self.label = d["label"]
        self.category = d.get("category", "Other")
        self.required = bool(d.get("required", False))
        self.match = list(d.get("match", []))
        rm = d.get("required_matches")
        self.required_matches = [list(g) for g in rm] if rm else None


@app.route("/api/checklist")
def api_checklist():
    year = int(request.args["year"])
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    raw = quests_store.load(year, yd, yt)
    active = [_QuestShim(d) for d in raw if d.get("status", "active") == "active"]
    inp = input_dir(year)
    files = [p for p in inp.rglob("*") if p.is_file() and not p.name.startswith(".")]
    matched: dict[str, list[str]] = {it.id: [] for it in active}
    unsorted: list[str] = []
    for f in files:
        rel = str(f.relative_to(inp))
        slot = match_slot(f.name, active)
        if slot:
            matched[slot].append(rel)
        else:
            unsorted.append(rel)
    # cpa_package PDF lives at year root, not input/
    pkg = _cpa_package_path(year)
    if pkg and any(it.id == "cpa_package" for it in active):
        matched.setdefault("cpa_package", []).append(f"../{pkg.name}")
    # Composite completion: `required_matches` quests need ALL groups satisfied
    all_file_names = [f.name for f in files]
    for it in active:
        groups = getattr(it, "required_matches", None)
        if not groups:
            continue
        group_hits = []
        for group in groups:
            hits = set()
            for fname in all_file_names:
                low_raw = fname.lower()
                low_norm = _normalize(fname)
                if any(
                    (tok in low_raw) or (_normalize(tok) in low_norm)
                    for tok in group if tok
                ):
                    hits.add(fname)
            group_hits.append(hits)
        if all(group_hits):
            merged = set()
            for g in group_hits:
                merged.update(g)
            matched[it.id] = sorted(merged)
        else:
            matched[it.id] = []  # stays red/grey based on required flag
    return jsonify({
        "items": [
            {
                "id": it.id, "label": it.label, "category": it.category,
                "required": it.required, "files": matched[it.id],
            } for it in active
        ],
        "unsorted": unsorted,
    })


@app.route("/api/quests")
def api_quests_get():
    year = int(request.args["year"])
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    return jsonify(quests_store.load(year, yd, yt))


@app.route("/api/quests", methods=["POST"])
def api_quests_add():
    year = int(request.args["year"])
    body = request.get_json(force=True) or {}
    if not body.get("label"):
        abort(400, "label required")
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    added_by = body.pop("added_by", "api")
    quest = quests_store.add(yd, yt, year, body, added_by=added_by)
    return jsonify(quest), 201


@app.route("/api/quests/<q_id>", methods=["PATCH"])
def api_quests_patch(q_id):
    year = int(request.args["year"])
    body = request.get_json(force=True) or {}
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    updated = quests_store.update(yd, yt, year, q_id, body)
    if not updated:
        abort(404, "quest not found")
    return jsonify(updated)


@app.route("/api/quests/<q_id>", methods=["DELETE"])
def api_quests_delete(q_id):
    year = int(request.args["year"])
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    if not quests_store.soft_remove(yd, yt, year, q_id):
        abort(404, "quest not found")
    return jsonify({"ok": True, "id": q_id, "status": "removed"})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    year = int(request.args["year"])
    slot = request.args.get("slot") or ""
    file = request.files.get("file")
    if not file or not file.filename:
        abort(400, "no file")
    safe_name = Path(file.filename).name  # strip any path
    if slot:
        items = {it.id for it in checklist_for(year)}
        if slot not in items:
            abort(400, "unknown slot")
        target = input_dir(year) / f"{slot}__{safe_name}"
    else:
        (input_dir(year) / "unsorted").mkdir(exist_ok=True)
        target = input_dir(year) / "unsorted" / safe_name
    # avoid overwrite: append (n)
    i = 1
    while target.exists():
        target = target.with_name(f"{target.stem} ({i}){target.suffix}")
        i += 1
    file.save(target)
    return jsonify({"saved": str(target.relative_to(input_dir(year)))})


@app.route("/api/file")
def api_file():
    year = int(request.args["year"])
    rel = request.args["path"]
    # Paths starting with "../" escape input/ to the year folder (e.g., the CPA package PDF).
    # Resolve against the year dir instead, and constrain to the year folder.
    if rel.startswith("../"):
        yd = year_dir(year).resolve()
        target = (yd / rel[3:]).resolve()
        if yd not in target.parents and target != yd:
            abort(400, "path traversal")
        if not target.is_file():
            abort(404)
        return send_file(target)
    p = safe_input_path(year, rel)
    if not p.is_file():
        abort(404)
    return send_file(p)


@app.route("/api/delete", methods=["POST"])
def api_delete():
    year = int(request.args["year"])
    rel = request.args["path"]
    p = safe_input_path(year, rel)
    if not p.is_file():
        abort(404)
    p.unlink()
    return jsonify({"deleted": rel})


def render_md(path: Path) -> str:
    return md.markdown(path.read_text(), extensions=["extra"]) if path.is_file() else ""


def parse_questions(path: Path) -> list:
    """Return question bullets from OpenQuestions.md (any `- [ ]` or plain `-` line in sections)."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        s = line.strip()
        m = re.match(r"^-\s*(?:\[\s?\]\s*)?(.+)", s)
        if m:
            body = m.group(1).strip()
            if body and not body.startswith("_"):
                out.append(body)
    return out


@app.route("/api/summary")
def api_summary():
    year = int(request.args["year"])
    yd = year_dir(year)
    profile_html = render_md(yd / "Profile.md")
    files_html = render_md(yd / "Files.md")
    open_questions = parse_questions(yd / "OpenQuestions.md")

    # Use the SAME logic as /api/checklist (global longest-token-wins + composite
    # required_matches + `cpa_package` at year root), so Journal and Preflight agree.
    # Exclude bellwether quests that aren't gaps (file_taxes = end goal, cpa_package = produced by Ship action).
    bellwether = {"file_taxes", "cpa_package"}
    with app.test_request_context(f"/api/checklist?year={year}"):
        checklist_resp = api_checklist()
    checklist_data = checklist_resp.get_json()
    missing = [
        it["label"] for it in checklist_data["items"]
        if it["required"] and not it["files"] and it["id"] not in bellwether
    ]
    return jsonify({
        "profile_html": profile_html,
        "files_html": files_html,
        "missing_required": missing,
        "open_questions": open_questions,
    })


@app.route("/api/events")
def api_events():
    """Server-Sent Events: emits 'refresh' whenever Profile.md/Files.md/OpenQuestions.md
    or input/ changes for the given year."""
    import time
    year = int(request.args["year"])
    yd = year_dir(year)
    watched = [GLOBAL_PROFILE_PATH, ANALYTICS_MD_PATH, RECOMMENDATIONS_MD_PATH, yd / "_quests.json", yd / "_figures.json", yd / "Profile.md", yd / "Files.md", yd / "OpenQuestions.md"]
    inp = input_dir(year)

    def snapshot():
        sig = []
        for p in watched:
            sig.append(p.stat().st_mtime_ns if p.exists() else 0)
        for p in sorted(inp.rglob("*")):
            if p.is_file():
                sig.append((p.name, p.stat().st_mtime_ns))
        return tuple(sig)

    def gen():
        last = snapshot()
        yield "event: ready\ndata: {}\n\n"
        while True:
            time.sleep(1.0)
            try:
                cur = snapshot()
            except FileNotFoundError:
                continue
            if cur != last:
                last = cur
                yield "event: refresh\ndata: {}\n\n"
            else:
                yield ": keepalive\n\n"

    return app.response_class(gen(), mimetype="text/event-stream")


@app.route("/api/export")
def api_export():
    year = int(request.args["year"])
    yd = year_dir(year)
    inp = input_dir(year)
    items = checklist_for(year)

    # generate cpa_summary.md
    files_by_slot: dict[str, list[str]] = {it.id: [] for it in items}
    unsorted = []
    for f in inp.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(inp))
        slot = match_slot(f.name, items)
        (files_by_slot.setdefault(slot, []) if slot else unsorted).append(rel)

    lines = [f"# CPA Package — Filing Year {year}", ""]
    profile = yd / "Profile.md"
    if profile.is_file():
        lines += ["## Profile", "", profile.read_text(), ""]
    lines += ["## Checklist status", ""]
    for it in items:
        mark = "[x]" if files_by_slot.get(it.id) else ("[ ]" if it.required else "[-]")
        files = ", ".join(files_by_slot.get(it.id, [])) or "_missing_"
        lines.append(f"- {mark} **{it.label}** — {files}")
    if unsorted:
        lines += ["", "## Unsorted files", ""] + [f"- {f}" for f in unsorted]

    summary_text = "\n".join(lines)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cpa_summary.md", summary_text)
        if profile.is_file():
            z.write(profile, "Profile.md")
        for f in inp.rglob("*"):
            if f.is_file():
                z.write(f, f"input/{f.relative_to(inp)}")
    buf.seek(0)
    fname = f"cpa_package_{year}_{date.today().isoformat()}.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=fname)


PROFILE_SECTIONS = ["Personal", "Income", "Adjustments / Deductions / Credits", "Filing", "Notes / Open Questions"]


def run_claude_intake(path: Path, year: int, items) -> dict:
    """Ask Claude CLI to classify a dropped tax document. Returns {} if unavailable.
    PII guard: markdown context is redacted before inclusion; the dropped file
    is read by Claude via its `.redacted.txt` sidecar (generated on demand)."""
    claude = shutil.which("claude")
    if not claude:
        return {}
    slot_catalog = "\n".join(f"  - {it.id}: {it.label}" for it in items)
    profile_md = _redact_pii((year_dir(year) / "Profile.md").read_text())
    questions_md = _redact_pii((year_dir(year) / "OpenQuestions.md").read_text())
    read_path = _redact_to_sidecar(path) or path
    prompt = f"""You are a tax document classifier for filing year {year} (tax year {year - 1}).
Read the file at: {read_path}

Current Profile.md:
---
{profile_md}
---

Current OpenQuestions.md:
---
{questions_md}
---

Available checklist slot IDs:
{slot_catalog}

Return ONLY a JSON object with this exact schema:
{{
  "doc_type": "short label, e.g. W-2, 1099-NEC, 1099-INT",
  "slot_id": "best match from the list, or empty string if none fit",
  "tax_year": <int, calendar year this doc reports on>,
  "issuer": "payer / employer / institution name",
  "key_figures": {{"label": value, ...}},
  "profile_updates": [
    {{"section": "Income|Adjustments / Deductions / Credits|Filing|Notes / Open Questions", "bullet": "short text"}}
  ],
  "files_md_entry": "one-line or short paragraph markdown describing this document and its tax relevance (will be appended to Files.md)",
  "new_open_questions": ["question raised by this document, e.g. unclear cost basis"],
  "resolved_questions": ["substring of an existing OpenQuestions.md bullet that this document now answers"],
  "quest_updates": {{
    "rename": [{{"id": "<existing slot_id>", "new_label": "e.g. W-2 — Acme Corp", "new_match": ["w2","acme"]}}],
    "add":    [{{"label": "e.g. 1099-K — Etsy", "category": "Income", "required": false, "match": ["1099-k","etsy"]}}],
    "remove": [{{"id": "<id to soft-remove>"}}]
  }},
  "proposed_filename": "e.g. W-2 — Acme Corp (2025).pdf — preserve extension; format '<DocType> — <Issuer> (<TaxYear>).ext'; omit missing segments rather than inventing; ASCII-only except em-dash; no slashes/colons/quotes; under 100 chars",
  "confidence": 0.0-1.0,
  "notes": "anything unusual or a question for the CPA"
}}

Use `quest_updates.rename` to personalize generic quest labels when this document reveals a specific issuer (e.g., a Fidelity 1099-B should rename "1099-B — brokerage proceeds" to "1099-B — Fidelity"). Use `add` if this document implies a new recurring doc type not yet in the quest list. Use `remove` sparingly — only when the document proves a quest is irrelevant. Leave the sub-arrays empty if no changes apply.

Be concise. Only output the JSON, no prose.
"""
    try:
        r = subprocess.run(
            [claude, "-p", "--output-format", "json", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print(f"[intake] claude exited {r.returncode}; stderr: {(r.stderr or '').strip()[:800]}", flush=True)
            return {}
        outer = r.stdout.strip()
        try:
            wrapper = json.loads(outer)
            text = wrapper.get("result") if isinstance(wrapper, dict) else outer
        except json.JSONDecodeError:
            text = outer
        m = re.search(r"\{.*\}", text or "", re.S)
        if not m:
            print(f"[intake] claude output had no JSON object; first 400 chars: {(text or '')[:400]!r}", flush=True)
            return {}
        return json.loads(m.group(0))
    except subprocess.TimeoutExpired:
        print("[intake] claude call timed out after 120s", flush=True)
        return {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[intake] claude call raised {type(e).__name__}: {e}", flush=True)
        return {}


def _sanitize_filename(raw: str, src_ext: str) -> str:
    """Produce a safe cross-platform filename, preserving the source extension.
    - Strip directory separators
    - Collapse whitespace to single spaces
    - Remove shell-unfriendly chars (keep letters, digits, spaces, `-`, `_`, `(`, `)`, `,`, `.`, `&`, em-dash)
    - Force the extension to the source's extension
    - Cap length at 120 chars including extension
    """
    name = (raw or "").strip()
    name = name.replace("/", " ").replace("\\", " ")
    # Preserve em-dash (U+2014), drop other odd unicode to ASCII-ish
    name = re.sub(r"[^A-Za-z0-9 \-_(),\.&\u2014]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Extension enforcement
    stem = Path(name).stem or "document"
    if len(stem) > 116:
        stem = stem[:116].rstrip()
    return f"{stem}{src_ext}"


def apply_profile_updates(year: int, bullets_text: str, notes_text: str) -> None:
    """Append bullets under matching `## <section>` headers; notes → Open Questions."""
    profile = year_dir(year) / "Profile.md"
    if not profile.is_file():
        return
    text = profile.read_text()

    # Parse bullets: "[Section] text" per line
    new_by_section: dict[str, list[str]] = {}
    for line in (bullets_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"\[([^\]]+)\]\s*(.+)", line)
        if not m:
            continue
        section, body = m.group(1).strip(), m.group(2).strip()
        new_by_section.setdefault(section, []).append(body)

    if notes_text and notes_text.strip():
        new_by_section.setdefault("Notes / Open Questions", []).extend(
            ln.strip() for ln in notes_text.strip().splitlines() if ln.strip()
        )

    if not new_by_section:
        return

    # Insert bullets at end of each named section (just before the next `##` or EOF).
    def insert_in_section(body: str, section: str, bullets: list[str]) -> str:
        pat = re.compile(rf"(^##\s+{re.escape(section)}\s*\n)(.*?)(?=^##\s+|\Z)", re.S | re.M)
        match = pat.search(body)
        added = "\n".join(f"- {b}" for b in bullets) + "\n"
        if not match:
            # append new section at end
            return body.rstrip() + f"\n\n## {section}\n{added}"
        start, end = match.span()
        head, section_body = match.group(1), match.group(2).rstrip("\n")
        return body[:start] + head + section_body + "\n" + added + body[end:]

    out = text
    for sec, bullets in new_by_section.items():
        out = insert_in_section(out, sec, bullets)
    profile.write_text(out)


@app.route("/api/intake", methods=["POST"])
def api_intake():
    year = int(request.args["year"])
    file = request.files.get("file")
    if not file or not file.filename:
        abort(400, "no file")
    safe_name = Path(file.filename).name
    unsorted = input_dir(year) / "unsorted"
    unsorted.mkdir(exist_ok=True)
    target = unsorted / safe_name
    i = 1
    while target.exists():
        target = target.with_name(f"{target.stem} ({i}){target.suffix}")
        i += 1
    file.save(target)

    items = checklist_for(year)
    analysis = run_claude_intake(target, year, items)
    slots = [{"id": it.id, "label": it.label} for it in items]
    return jsonify({
        "status": "ok" if analysis else "no_claude",
        "saved_path": str(target.relative_to(input_dir(year))),
        "analysis": analysis,
        "slots": slots,
    })


def _strip_files_md_block(text: str, filename: str) -> str:
    """Remove any `### \\`<filename>\\`` heading and the block that follows it
    (up to the next `### ` or EOF). No-op if not present."""
    if not filename:
        return text
    pat = re.compile(
        rf"(?ms)^###\s*`?{re.escape(filename)}`?\s*\n.*?(?=^###\s|\Z)"
    )
    return pat.sub("", text)


def append_files_md(year: int, entry: str, final_filename: str,
                    prior_names: list | None = None) -> None:
    """Append a document entry to Files.md (drop the '_No documents yet_' line if present).

    Dedupes: strips any existing block for `final_filename` before appending, plus any
    blocks for `prior_names` (e.g., the raw upload name before a rename, or a previously
    proposed pretty name that never made it to disk)."""
    if not entry or not entry.strip():
        return
    f = year_dir(year) / "Files.md"
    text = f.read_text()
    text = re.sub(r"\n_No documents yet[^\n]*\n", "\n", text)
    # Strip any stale block for this final name or any prior aliases of the same source.
    for name in {final_filename, *(prior_names or [])}:
        text = _strip_files_md_block(text, name)
    block = f"\n### `{final_filename}`\n{entry.strip()}\n"
    f.write_text(text.rstrip() + "\n" + block)


def update_open_questions(year: int, new_questions: list, resolved: list, filename: str) -> None:
    """Append new questions under Document questions; remove resolved ones."""
    f = year_dir(year) / "OpenQuestions.md"
    text = f.read_text()

    # Remove resolved questions (match any bullet containing the substring).
    for needle in resolved or []:
        needle = (needle or "").strip()
        if not needle:
            continue
        text = re.sub(
            rf"^-\s*(?:\[ \]\s*)?[^\n]*{re.escape(needle)}[^\n]*\n",
            "", text, flags=re.M,
        )

    # Append new questions under "## Document questions".
    new_qs = [q.strip() for q in (new_questions or []) if q and q.strip()]
    if new_qs:
        lines = "\n".join(f"- [ ] ({filename}) {q}" for q in new_qs) + "\n"
        # Drop "_None yet._" under Document questions if present.
        text = re.sub(
            r"(## Document questions\s*\n)(\s*_None yet\._\s*\n?)",
            r"\1", text,
        )
        if "## Document questions" in text:
            text = re.sub(
                r"(## Document questions[^\n]*\n)",
                r"\1\n" + lines, text, count=1,
            )
        else:
            text = text.rstrip() + "\n\n## Document questions\n\n" + lines
    f.write_text(text)


@app.route("/api/commit-intake", methods=["POST"])
def api_commit_intake():
    year = int(request.args["year"])
    body = request.get_json(force=True) or {}
    src_rel = body.get("saved_path") or ""
    slot_id = body.get("slot_id") or ""
    src = safe_input_path(year, src_rel)
    if not src.is_file():
        abort(404, "source missing")

    final_name = src.name
    original_name = src.name  # before any rename; used for Files.md dedupe
    force_prefix = bool(body.get("force_prefix"))
    proposed = (body.get("filename") or "").strip()

    # Fix 4: auto-apply the classifier's proposed filename when the UI didn't pass one
    # explicitly, provided confidence is high enough. Skip if force_prefix is set (the
    # user explicitly opted into the legacy slot-prefix path).
    if not proposed and not force_prefix:
        classifier_proposed = (body.get("proposed_filename") or "").strip()
        try:
            confidence = float(body.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if classifier_proposed and confidence >= 0.7:
            proposed = classifier_proposed

    if proposed:
        # Pretty-name path: sanitize + place in input/ directly (no slot prefix).
        clean = _sanitize_filename(proposed, src.suffix)
        dst = input_dir(year) / clean
        i = 2
        while dst.exists():
            dst = dst.with_name(f"{Path(clean).stem} ({i}){Path(clean).suffix}")
            i += 1
        src.rename(dst)
        final_name = dst.name
    elif slot_id:
        # Legacy path: slot-prefixed filename
        if not force_prefix:
            items = {it.id for it in checklist_for(year)}
            if slot_id not in items:
                abort(400, "unknown slot")
        dst = input_dir(year) / f"{slot_id}__{src.name}"
        i = 1
        while dst.exists():
            dst = dst.with_name(f"{dst.stem} ({i}){dst.suffix}")
            i += 1
        src.rename(dst)
        final_name = dst.name

    apply_profile_updates(year, body.get("bullets", ""), body.get("notes", ""))
    # Pass prior names so a re-commit replaces (rather than duplicates) the earlier entry.
    prior_names = []
    if original_name and original_name != final_name:
        prior_names.append(original_name)
    classifier_proposed = (body.get("proposed_filename") or "").strip()
    if classifier_proposed and classifier_proposed != final_name:
        prior_names.append(classifier_proposed)
    append_files_md(year, body.get("files_md_entry", ""), final_name, prior_names=prior_names)
    update_open_questions(
        year,
        body.get("new_open_questions") or [],
        body.get("resolved_questions") or [],
        final_name,
    )
    apply_quest_updates(year, body.get("quest_updates") or {})
    return jsonify({"ok": True})


def apply_quest_updates(year: int, updates: dict) -> None:
    """Apply rename/add/remove quest mutations returned by Claude intake."""
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    for r in updates.get("rename") or []:
        q_id = r.get("id")
        if not q_id:
            continue
        patch = {}
        if r.get("new_label"): patch["label"] = r["new_label"]
        if r.get("new_match"): patch["match"] = list(r["new_match"])
        if patch:
            quests_store.update(yd, yt, year, q_id, patch)
    for a in updates.get("add") or []:
        if a.get("label"):
            quests_store.add(yd, yt, year, a, added_by="intake")
    for rm in updates.get("remove") or []:
        if rm.get("id"):
            quests_store.soft_remove(yd, yt, year, rm["id"])


@app.route("/api/files-md/rebuild", methods=["POST"])
def api_files_md_rebuild():
    """Walk <YEAR>/input/ and regenerate Files.md entries by re-classifying each file with Claude.
    Defensive: processes files one by one, never aborts on a single failure, only overwrites
    Files.md after at least one successful classification (so we don't nuke existing data)."""
    year = int(request.args["year"])
    yd = year_dir(year)
    inp = input_dir(year)
    items = checklist_for(year)
    files = sorted([p for p in inp.rglob("*") if p.is_file() and not p.name.startswith(".")])

    if not files:
        return jsonify({"processed": [], "skipped": [], "errors": [], "total_files": 0,
                        "note": "input/ is empty — nothing to rescan."})

    processed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    entries: list[tuple[str, str, dict]] = []  # (filename, entry, quest_updates)

    for f in files:
        try:
            analysis = run_claude_intake(f, year, items)
        except Exception as e:
            errors.append({"file": f.name, "error": str(e)})
            continue
        if not analysis:
            skipped.append(f.name)  # claude not available or returned empty
            continue
        entry = (analysis.get("files_md_entry") or "").strip()
        if not entry:
            skipped.append(f.name)
            continue
        entries.append((f.name, entry, analysis.get("quest_updates") or {}))

    if not entries:
        return jsonify({
            "processed": processed, "skipped": skipped, "errors": errors,
            "total_files": len(files),
            "note": "No usable entries from Claude — Files.md left unchanged.",
        }), 200

    # Only now do we overwrite Files.md with the fresh template + accumulated entries.
    # Rescan intentionally does NOT apply quest_updates — per-file context is too narrow
    # and leads to over-broad match tokens (e.g., "2025" matching everything). Quest
    # personalization belongs in the Profile wizard session where full context is available.
    (yd / "Files.md").write_text(FILES_TEMPLATE.format(year=year))
    for name, entry, _qu in entries:
        append_files_md(year, entry, name)
        processed.append(name)

    return jsonify({
        "processed": processed, "skipped": skipped, "errors": errors,
        "total_files": len(files),
    })


@app.route("/api/discard-intake", methods=["POST"])
def api_discard_intake():
    year = int(request.args["year"])
    rel = request.args.get("path", "")
    p = safe_input_path(year, rel)
    if p.is_file():
        p.unlink()
    return jsonify({"ok": True})


# -------- CPA package --------

def _root_user_name() -> str:
    """Parse `- Name: X` from MDDocs/Profile.md. Fallback to 'Owner'."""
    if not GLOBAL_PROFILE_PATH.is_file():
        return "Owner"
    for line in GLOBAL_PROFILE_PATH.read_text().splitlines():
        m = re.match(r"\s*-\s*Name:\s*(.+?)\s*$", line)
        if m and m.group(1).strip() and m.group(1).strip().upper() != "TBD":
            return m.group(1).strip()
    return "Owner"


def _files_md_descriptions(year: int) -> dict:
    """Parse `### <filename>` blocks from Files.md -> {filename: description_text}."""
    f = year_dir(year) / "Files.md"
    if not f.is_file():
        return {}
    text = f.read_text()
    out = {}
    for m in re.finditer(r"^###\s*`?([^`\n]+?)`?\s*\n(.*?)(?=^###\s|\Z)", text, re.M | re.S):
        name = m.group(1).strip()
        body = m.group(2).strip()
        out[name] = body.split("\n")[0][:240]
    return out


def _cpa_package_path(year: int) -> Path | None:
    yd = year_dir(year)
    for p in yd.glob(f"{year}FYDocumentsPrepared_*.pdf"):
        return p
    return None


@app.route("/api/cpa-package/candidates")
def api_cpa_candidates():
    year = int(request.args["year"])
    inp = input_dir(year)
    descs = _files_md_descriptions(year)
    out = []
    unsorted_count = 0
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = p.relative_to(inp)
        # Skip files stranded in input/unsorted/ — they haven't been classified,
        # so they're not ready for the CPA package. Counted separately so the UI can warn.
        if rel.parts and rel.parts[0] == "unsorted":
            unsorted_count += 1
            continue
        out.append({
            "filename": p.name,
            "rel_path": str(rel),
            "description": descs.get(p.name, ""),
            "size_bytes": p.stat().st_size,
        })
    return jsonify({
        "candidates": out,
        "author": _root_user_name(),
        "existing_package": _cpa_package_path(year).name if _cpa_package_path(year) else None,
        "unsorted_count": unsorted_count,
    })


@app.route("/api/cpa-package/status")
def api_cpa_status():
    year = int(request.args["year"])
    pkg = _cpa_package_path(year)
    return jsonify({
        "exists": pkg is not None,
        "filename": pkg.name if pkg else None,
    })


@app.route("/api/cpa-package", methods=["POST"])
def api_cpa_package_create():
    year = int(request.args["year"])
    body = request.get_json(force=True) or {}
    selected = body.get("selected", [])
    if not selected:
        abort(400, "no documents selected")

    inp = input_dir(year)
    paths = []
    for rel in selected:
        p = safe_input_path(year, rel)
        if p.is_file():
            paths.append(p)

    author = _root_user_name()
    safe_author = re.sub(r"[^A-Za-z0-9]", "", author) or "Owner"
    out_name = f"{year}FYDocumentsPrepared_{safe_author}.pdf"
    out_path = year_dir(year) / out_name

    cpa_package.set_descriptions(_files_md_descriptions(year))
    filer = _cpa_filer_facts()
    flags = _cpa_flags(year)
    # Run the Ship-to-CPA briefing prompt for polished clarifications + flags.
    briefing = _run_cpa_briefing(year, [p.name for p in paths])
    result = cpa_package.build_package(year, paths, author, out_path,
                                       filer=filer, flags=flags, briefing=briefing)
    result["filename"] = out_name
    result["briefing_used"] = briefing is not None
    return jsonify(result)


def _run_cpa_briefing(year: int, filenames: list[str]) -> dict | None:
    """Run Claude headlessly to produce structured clarifications + flags + document ordering
    for the CPA package. Returns None on failure. Output schema:
      {
        "clarifications": [ {"filename": "...", "summary": "...", "bullets": ["...", ...]}, ...],
        "flags":          [ {"title": "...", "detail": "..."}, ... ],
        "ordering":       [ {"filename": "...", "section": "..."}, ... ]
      }
    """
    claude = shutil.which("claude")
    if not claude:
        return None
    # PII guard: ensure every file Claude will read has a redacted sidecar.
    _generate_redacted_sidecars_for_year(year)
    files_list = "\n".join(f"  - {f}" for f in filenames)
    prompt = (
        f"You are preparing a tax document handoff package for filing year {year} for a licensed "
        f"CPA. Read these files in order:\n"
        f"  1. {DATA_ROOT}/MDDocs/Profile.md — stable identity\n"
        f"  2. {DATA_ROOT}/{year}/Profile.md — this year's situation\n"
        f"  3. {DATA_ROOT}/{year}/Files.md — one entry per document\n"
        f"  4. {DATA_ROOT}/{year}/OpenQuestions.md — user-curated questions and notes\n"
        f"  5. {DATA_ROOT}/{year}/_figures.json — structured figures if present\n\n"
        f"Documents included in this package (use this exact set, in this order):\n{files_list}\n\n"
        f"Produce ONLY a JSON object with this schema (no prose, no commentary):\n"
        f"{{\n"
        f'  "clarifications": [\n'
        f'    {{\n'
        f'      "filename": "<exact filename from the list above>",\n'
        f'      "summary": "<one short sentence explaining what this doc is; plain language>",\n'
        f'      "bullets": ["<key fact 1>", "<key fact 2>", ...]\n'
        f'    }}, ...\n'
        f'  ],\n'
        f'  "flags": [\n'
        f'    {{\n'
        f'      "title": "<short, bold-worthy lead-in (≤12 words)>",\n'
        f'      "detail": "<1-3 sentences of context/action the CPA needs>"\n'
        f'    }}, ...\n'
        f'  ],\n'
        f'  "ordering": [\n'
        f'    {{ "filename": "<exact filename>", "section": "<section name>" }}, ...\n'
        f'  ]\n'
        f"}}\n\n"
        f"Rules for writing:\n"
        f"  - Audience: experienced CPA. Skip obvious-to-CPA explanations.\n"
        f"  - Clarifications: 2-5 crisp bullets per document. Each bullet 8-18 words. Include "
        f"    specific numbers (with dollar signs and commas) where relevant. No markdown "
        f"    formatting characters (`**`, `*`, backticks) — output plain text only.\n"
        f"  - Flags: pull from {year}/OpenQuestions.md Document-questions section AND from your "
        f"    own read of the docs. Only include things that materially affect the return. "
        f"    Title is a clear action ('Cross-broker wash-sale review needed'), detail is what "
        f"    the CPA should actually do. Max ~8 flags. No markdown characters in output.\n"
        f"  - Do NOT include figures the CPA will compute (estimated tax, AGI, refund). Stick to "
        f"    what's observable in the documents.\n"
        f"  - Every filename in 'clarifications' and 'ordering' must match exactly one from the list above.\n"
        f"  - Keep output ASCII (em-dash U+2014 is fine).\n\n"
        f"Rules for ordering (how the CPA will read the package):\n"
        f"  - Produce an 'ordering' array containing EVERY included filename exactly once.\n"
        f"  - Order the array top-to-bottom as the CPA should review. Files within the same "
        f"    section should be adjacent.\n"
        f"  - Each entry has `section` set to one of these exact strings:\n"
        f"      Income             — W-2s, 1099-NEC, 1099-MISC\n"
        f"      Investments        — brokerage 1099s (B/DIV/INT/R), K-1s, cost-basis letters, rollover 1099-Rs, 401(k) statements\n"
        f"      Benefits           — 1095, HSA (1099-SA, 5498-SA), HSA receipts\n"
        f"      Deductions         — 1098/1098-E/1098-T, mortgage, property tax, charity\n"
        f"      Self-employment    — side-job invoices, expense logs, estimated-tax receipts\n"
        f"      Prior year         — prior filed returns kept for reference\n"
        f"      ID                 — license / state ID\n"
        f"      Other              — use sparingly; only if truly uncategorizable\n"
        f"  - Within a section, put primary forms before supporting receipts/statements; "
        f"    most material amounts first when relevant.\n"
        f"  - A rollover 1099-R or 401(k) statement is Investments, not Benefits.\n"
        f"  - A cost-basis letter goes adjacent to the broker's 1099 for that security.\n"
    )
    try:
        r = subprocess.run(
            [claude, "-p", "--permission-mode", "acceptEdits", prompt],
            cwd=str(DATA_ROOT), capture_output=True, text=True, timeout=240,
        )
        if r.returncode != 0:
            return None
        out = (r.stdout or "").strip()
        try:
            wrapper = json.loads(out)
            text = wrapper.get("result") if isinstance(wrapper, dict) else out
        except json.JSONDecodeError:
            text = out
        m = re.search(r"\{.*\}", text or "", re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        if "clarifications" not in data or "flags" not in data:
            return None
        return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _cpa_filer_facts() -> dict:
    """Parse root Profile.md into the small set of facts the CPA briefing shows.
    Facts only — no computed numbers."""
    if not GLOBAL_PROFILE_PATH.is_file():
        return {}
    text = GLOBAL_PROFILE_PATH.read_text()

    def grab(label: str) -> str:
        m = re.search(rf"^\s*-\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text, re.M)
        return m.group(1).strip() if m else ""

    # Extract multi-line sections by heading
    def section(heading: str) -> list[str]:
        pat = re.compile(rf"^##\s+{re.escape(heading)}\s*\n(.+?)(?=^##\s|\Z)", re.M | re.S)
        m = pat.search(text)
        if not m:
            return []
        bullets = []
        for line in m.group(1).splitlines():
            ln = line.strip()
            if ln.startswith("- "):
                val = ln[2:].strip()
                if val and val.upper() != "TBD" and not val.startswith("_"):
                    bullets.append(val)
        return bullets

    residency_lines = section("Residency history")
    employment_lines = section("Employment history")
    accounts_lines = section("Financial accounts")

    def first_matching(lines: list[str], *needles: str) -> str:
        for ln in lines:
            low = ln.lower()
            if any(n in low for n in needles):
                return ln
        return ""

    return {
        "filing_status": grab("Filing status (current pattern)"),
        "residency": residency_lines[0] if residency_lines else grab("Residency"),
        "dependents": grab("Dependents"),
        "employer": first_matching(employment_lines, "w-2", "w2", "primary") or (employment_lines[0] if employment_lines else ""),
        "side_income": first_matching(employment_lines, "side", "1099", "contract", "freelance"),
        "brokerages": first_matching(accounts_lines, "brokerage"),
        "benefits": first_matching(accounts_lines, "hysa", "hsa", "bank", "savings"),
        "retirement": first_matching(accounts_lines, "retirement", "401", "ira"),
    }


def _cpa_flags(year: int) -> list[str]:
    """Pull CPA-tagged items from <YEAR>/OpenQuestions.md.
    We include EVERY bullet under the `## Document questions` section, plus any
    bullet anywhere else prefixed with `[CPA]` or containing 'for CPA' / 'for your CPA'."""
    f = year_dir(year) / "OpenQuestions.md"
    if not f.is_file():
        return []
    text = f.read_text()
    out: list[str] = []

    # Section: Document questions — everything under it is implicitly "for CPA"
    m = re.search(r"^##\s*Document questions\s*\n(.+?)(?=^##\s|\Z)", text, re.M | re.S)
    if m:
        for line in m.group(1).splitlines():
            ln = line.strip()
            m2 = re.match(r"^-\s*(?:\[\s?\]\s*)?(.+)", ln)
            if m2:
                body = m2.group(1).strip()
                if body and not body.startswith("_"):
                    out.append(body)

    # Anywhere: [CPA] or 'for CPA'/'for your CPA' tagged bullets
    for line in text.splitlines():
        ln = line.strip()
        m2 = re.match(r"^-\s*(?:\[\s?\]\s*)?(.+)", ln)
        if not m2:
            continue
        body = m2.group(1).strip()
        if not body or body.startswith("_"):
            continue
        if re.search(r"\[CPA\]|for (?:your )?CPA\b", body, re.I):
            # Strip the [CPA] tag if present; already implied by being on the flags page
            clean = re.sub(r"\[CPA\]\s*", "", body).strip()
            if clean not in out:
                out.append(clean)
    return out


@app.route("/api/abs-path")
def api_abs_path():
    """Resolve a year + relative input-path to its absolute path (guarded to within DATA_ROOT).
    Paths starting with '../' refer to the year-folder root (e.g., CPA package PDF)."""
    year = int(request.args["year"])
    rel = request.args.get("rel", "")
    if rel.startswith("../"):
        yd = year_dir(year).resolve()
        target = (yd / rel[3:]).resolve()
        if yd not in target.parents and target != yd:
            abort(400, "path traversal")
        return jsonify({"path": str(target)})
    p = safe_input_path(year, rel)
    return jsonify({"path": str(p)})


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """Reveal a file in Finder (macOS)."""
    body = request.get_json(force=True) or {}
    p = Path(body.get("path", "")).resolve()
    if not p.exists() or DATA_ROOT not in p.parents:
        abort(400, "invalid path")
    subprocess.Popen(["open", "-R", str(p)])
    return jsonify({"ok": True})


# -------- Analytics --------

def _has_filed_return(year: int) -> bool:
    """Does this year's input/ contain a filed-return document?"""
    yd = (DATA_ROOT / str(year))
    if not yd.is_dir():
        return False
    inp = yd / "input"
    if not inp.is_dir():
        return False
    for f in inp.rglob("*"):
        if f.is_file() and (f.name.startswith("filed_return__") or f.name.startswith("prior_return__")):
            return True
    return False


def _load_figures(yd: Path) -> dict | None:
    p = yd / "_figures.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def _year_stats(year: int) -> dict:
    yd = year_dir(year)
    yt = effective_year_type(yd, year)
    items = checklist_for(year)
    inp = input_dir(year)
    files = [p.name for p in inp.rglob("*") if p.is_file() and not p.name.startswith(".")]
    required = [it for it in items if it.required]

    def _is_filled(it) -> bool:
        # Composite quests (required_matches) require ≥1 file per group — mirror api_checklist.
        groups = getattr(it, "required_matches", None)
        if groups:
            for group in groups:
                if not any(
                    (tok in f.lower()) or (_normalize(tok) in _normalize(f))
                    for f in files for tok in group if tok
                ):
                    return False
            return True
        return any(match_slot(f, [it]) == it.id for f in files)

    filled_required = [it for it in required if _is_filled(it)]
    filed = _has_filed_return(year)
    figures = _load_figures(yd)
    if yt == "past":
        status = "filed" if filed else "planning"
    elif yt == "future":
        status = "planning"
    else:
        status = "filed" if filed else ("estimated" if filled_required else "planning")
    # Override with figures source_type if explicitly set
    if figures and figures.get("source_type"):
        status = figures["source_type"]
    return {
        "year": year,
        "year_type": yt,
        "required_filled": len(filled_required),
        "required_total": len(required),
        "docs_total": len(files),
        "has_filed_return": filed,
        "status": status,
        "figures": figures,
    }


ANALYTICS_MD_PATH = MDDOCS_DIR / "Analytics.md"
RECOMMENDATIONS_MD_PATH = MDDOCS_DIR / "Recommendations.md"

RECOMMENDATIONS_TEMPLATE = """# Tax Recommendations

> ⚠ Auto-maintained by the Ancient One. Safe to read; edits are overwritten.
> User-only content — excluded from CPA handoff.
> Last reviewed: _never_

## Active strategies
Recurring rules you follow (or should). Strategic, multi-year.

- _none yet — consult the Ancient One to seed this section_

## Current focus
Year-specific opportunities tied to this year's figures. Time-bound.

- _none yet_

## Prior-year archive
Past opportunities, marked [Acted], [Skipped], or [Expired]. Context for future decisions.

- _none yet_

## Watch list
Situations to monitor — not yet actionable.

- _none yet_
"""


def ensure_recommendations() -> None:
    MDDOCS_DIR.mkdir(exist_ok=True)
    if not RECOMMENDATIONS_MD_PATH.exists():
        RECOMMENDATIONS_MD_PATH.write_text(RECOMMENDATIONS_TEMPLATE)


def _fmt_money(v) -> str:
    if v is None: return "—"
    if isinstance(v, (int, float)):
        n = int(v)
        return ("-$" if n < 0 else "$") + f"{abs(n):,}"
    return str(v)


def write_analytics_md(payload: dict) -> None:
    k = payload["kpis"]
    filed = sum(1 for y in payload["years"] if y["status"] == "filed_return" or y["status"] == "filed")
    est   = sum(1 for y in payload["years"] if y["status"] == "estimated")
    plan  = sum(1 for y in payload["years"] if y["status"] == "planning")
    lines = [
        "# Analytics",
        "",
        f"> ⚠ Auto-generated from `<YEAR>/` folders. Last updated: "
        f"{date.today().isoformat()}. Edits will be overwritten.",
        "",
        "## Portfolio KPIs",
        f"- Years tracked: {k['total_years']}",
        f"- Filed: {filed} · Estimated: {est} · Planning: {plan}",
        f"- Documents ingested (total): {k['total_docs']}",
        f"- Lifetime AGI: {_fmt_money(k.get('lifetime_agi'))}",
        f"- Lifetime tax paid: {_fmt_money(k.get('lifetime_tax_paid'))}",
        "",
        "## By year",
        "",
    ]
    status_icon = {
        "filed_return": "✓ Filed", "filed": "✓ Filed",
        "estimated": "~ Estimated", "planning": "… Planning",
    }
    for y in payload["years"]:
        fig = y.get("figures") or {}
        agi = _extract_fig(fig, "income", "agi")
        tax_liab = fig.get("tax_liability") or {}
        tax_paid = fig.get("tax_paid") or {}
        liab_total = sum(v for v in tax_liab.values() if isinstance(v, (int, float))) if tax_liab else None
        paid_total = sum(v for v in tax_paid.values() if isinstance(v, (int, float))) if tax_paid else None
        lines += [
            f"### {y['year']} — {y['year_type']} · {status_icon.get(y['status'], y['status'])}",
            f"- Docs: {y['docs_total']} · Required filled: {y['required_filled']}/{y['required_total']}",
            f"- AGI: {_fmt_money(agi)}",
            f"- Tax liability (total): {_fmt_money(liab_total)}",
            f"- Tax paid (total): {_fmt_money(paid_total)}",
            f"- Investments net: {_fmt_money(_extract_fig(fig, 'investments', 'net_gain_loss'))}",
            f"- Carryforward out: {_fmt_money(_extract_fig(fig, 'investments', 'carryforward_out'))}",
            "",
        ]
    lines.append("_" + payload["note"] + "_")
    MDDOCS_DIR.mkdir(exist_ok=True)
    ANALYTICS_MD_PATH.write_text("\n".join(lines))


def _extract_fig(fig: dict | None, *keys: str):
    """Safe nested getter. Returns None if any segment missing."""
    cur = fig or {}
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


@app.route("/api/analytics")
def api_analytics():
    years = available_years()
    per_year = [_year_stats(y) for y in years]

    # Cross-year aggregates drawn from _figures.json
    lifetime_tax_paid = 0
    lifetime_agi = 0
    years_with_agi = 0
    years_with_tax = 0
    for y in per_year:
        agi = _extract_fig(y["figures"], "income", "agi")
        if isinstance(agi, (int, float)):
            lifetime_agi += int(agi)
            years_with_agi += 1
        tax_paid = y["figures"] and y["figures"].get("tax_paid") or {}
        total_paid = sum(
            v for v in (tax_paid or {}).values() if isinstance(v, (int, float))
        )
        if total_paid:
            lifetime_tax_paid += int(total_paid)
            years_with_tax += 1

    payload = {
        "years": per_year,
        "kpis": {
            "total_years": len(per_year),
            "total_docs": sum(y["docs_total"] for y in per_year),
            "lifetime_agi": lifetime_agi if years_with_agi else None,
            "lifetime_tax_paid": lifetime_tax_paid if years_with_tax else None,
        },
        "note": "Figures are populated by the auto-sync hook from source documents. Filed-return PDFs are treated as ground truth.",
    }
    write_analytics_md(payload)
    return jsonify(payload)


# -------- Profile auto-sync (background hook) --------

_autosync_threads: dict = {}  # year -> threading.Thread


def _autosync_prompt(year: int) -> str:
    tax_year = year - 1
    return (
        f"You are running headlessly to auto-sync profile + figures files for filing year {year} "
        f"(covers tax year {tax_year} — the return filed in April {year} reports on {tax_year} income). "
        f"Documents labeled with '{tax_year}' (e.g. `2024_FEDERAL_RETURN.pdf` in folder `{year}/`) "
        f"are the correct filed return for this filing year — do not treat year-label mismatches as "
        f"disqualifying. Populate figures from the filed return's {tax_year} values into {year}/_figures.json. "
        f"Read, in order, all of: MDDocs/Profile.md, {year}/Profile.md, {year}/Files.md, "
        f"{year}/OpenQuestions.md, {year}/_quests.json, {year}/_meta.json, and every file in {year}/input/. "
        f"Then make these edits directly (no user interaction):\n"
        f"1. Update {year}/Profile.md: refresh the `## Summary` section (5–8 plain-language bullets "
        f"   reflecting current state), fill any `TBD` fields you can confidently answer from the "
        f"   documents, and add/refine bullets under Income, Adjustments, Filing as appropriate.\n"
        f"2. Update MDDocs/Profile.md: if a durable cross-year fact has changed (new employer, "
        f"   new account, new dependent, residency change, retirement account added), reflect it.\n"
        f"3. Open {year}/_figures.json (create if missing). Populate with typed financial numbers "
        f"   you can cite to a specific document. **Only write numbers sourced to a document** — "
        f"   leave `null` otherwise. Schema:\n"
        f"""   {{
     "source_type": "filed_return" | "estimated" | "planning",
     "source_docs": ["<filename>", ...],
     "last_updated": "YYYY-MM-DD",
     "income": {{
       "agi": <int|null>,
       "total_income": <int|null>,
       "split": {{
         "wages_w2":           <int|null>,
         "self_employment":    <int|null>,
         "interest":           <int|null>,
         "dividends":          <int|null>,
         "capital_gains":      <int|null>,
         "retirement_distrib": <int|null>,
         "other":              <int|null>
       }}
     }},
     "adjustments": {{"hsa": <int|null>, "traditional_ira": <int|null>, "student_loan": <int|null>, "se_tax_deduction": <int|null>}},
     "deductions":  {{"method": "standard"|"itemized"|null, "amount": <int|null>}},
     "taxable_income": <int|null>,
     "tax_liability": {{"federal": <int|null>, "ny_state": <int|null>, "nyc": <int|null>, "fica": <int|null>, "se_tax": <int|null>}},
     "tax_paid":      {{"fed_withheld_w2": <int|null>, "state_withheld_w2": <int|null>, "estimated_payments": <int|null>, "other": <int|null>}},
     "refund_or_owed": {{"federal": <int|null>, "state": <int|null>}},
     "investments":  {{"total_proceeds": <int|null>, "total_basis": <int|null>, "net_gain_loss": <int|null>, "wash_sales_flagged": <bool>, "carryforward_in": <int|null>, "carryforward_out": <int|null>}},
     "retirement_contributions": {{"401k": <int|null>, "ira": <int|null>, "hsa": <int|null>, "rollovers": <int|null>}},
     "liabilities":  {{"owed_federal": <int|null>, "owed_state": <int|null>, "underpayment_penalty_est": <int|null>, "estimated_tax_due_next_year": <int|null>}}
   }}\n"""
        f"   Rules: `source_type` = `filed_return` if any input/ file is named `filed_return__*.pdf` "
        f"   or `prior_return__*.pdf` (those figures are ground truth); `estimated` if derived from "
        f"   raw source docs without a filed return; `planning` if _meta.year_type is `future`. "
        f"   `source_docs` lists the filenames you used. Round to whole dollars.\n"
        f"4. **Estimation rules for `source_type: \"estimated\"`** — when no filed return is present, "
        f"   you SHOULD compute AGI and tax estimates from the raw source documents:\n"
        f"   - AGI ≈ sum(wages_w2 + self_employment + interest + dividends + capital_gains + retirement_distrib) "
        f"     − HSA deduction − half of SE tax − student loan interest (up to limit). Use W-2 Box 1, "
        f"     1099-NEC/MISC amounts, 1099-INT/DIV, 1099-B realized gains net, 1099-R taxable portion.\n"
        f"   - Federal tax liability: apply 2025 bracket schedule for the user's filing status (single, "
        f"     MFJ, MFS, HoH). For Single {tax_year}: 10% to $11,925; 12% to $48,475; 22% to $103,350; "
        f"     24% to $197,300; 32% to $250,525; 35% to $626,350; 37% above.\n"
        f"   - NY State: apply NY marginal rates to taxable income (≈4%–10.9% tiered). NYC: additional "
        f"     ≈3.078%–3.876% for NYC residents.\n"
        f"   - Tax paid total: sum W-2 federal+state+local withholding + any estimated payments present.\n"
        f"   - Refund/owed = tax paid − tax liability (sign convention: positive = refund).\n"
        f"   When `source_type` is `filed_return`, NEVER estimate — read the exact filed figures.\n"
        f"5. Do NOT modify Files.md, OpenQuestions.md, or _quests.json.\n"
        f"6. If you can't support a figure with evidence from a document, leave it null. "
        f"   The UI displays null as em-dash.\n"
        f"7. Finish with a single line: `AUTOSYNC DONE: <N> edits` and stop."
    )


def _generate_redacted_sidecars_for_year(year: int) -> int:
    """Create/refresh .redacted.txt sidecars for every user-readable file
    in a year folder and the shared MDDocs. Returns count of sidecars created
    or refreshed. Called before any AI run that will read user documents."""
    count = 0
    yd = year_dir(year)
    targets: list[Path] = []
    for md_name in ("Profile.md", "Files.md", "OpenQuestions.md"):
        p = yd / md_name
        if p.is_file():
            targets.append(p)
    mddocs = DATA_ROOT / "MDDocs"
    if mddocs.is_dir():
        for p in mddocs.glob("*.md"):
            targets.append(p)
    inp = input_dir(year)
    if inp.is_dir():
        for p in inp.rglob("*"):
            if p.is_file() and not p.name.startswith(".") and ".redacted" not in p.name:
                targets.append(p)
    for t in targets:
        try:
            if _redact_to_sidecar(t):
                count += 1
        except Exception as e:
            print(f"[pii] sidecar failed for {t.name}: {type(e).__name__}: {e}", flush=True)
    return count


def _run_autosync(year: int, reason: str) -> None:
    claude = shutil.which("claude")
    if not claude:
        print(f"[autosync] claude CLI missing; skipping sync for {year}")
        return
    n = _generate_redacted_sidecars_for_year(year)
    print(f"[autosync] regenerated {n} redacted sidecars for year={year}", flush=True)
    try:
        subprocess.run(
            [claude, "-p", "--permission-mode", "acceptEdits", _autosync_prompt(year)],
            cwd=str(DATA_ROOT), capture_output=True, text=True, timeout=300,
        )
        print(f"[autosync] year={year} reason={reason} complete")
    except subprocess.TimeoutExpired:
        print(f"[autosync] year={year} timed out after 5 min")
    except Exception as e:
        print(f"[autosync] year={year} failed: {e}")


def _autosync_async(year: int, reason: str = "") -> None:
    """Fire-and-forget background sync. Coalesces: if one is already running for
    this year, skip (it will pick up any new state when it runs)."""
    import threading
    t = _autosync_threads.get(year)
    if t and t.is_alive():
        print(f"[autosync] year={year} already running; skip ({reason})")
        return
    t = threading.Thread(target=_run_autosync, args=(year, reason), daemon=True)
    _autosync_threads[year] = t
    t.start()


@app.route("/api/autosync", methods=["POST"])
def api_autosync():
    """Manual trigger. Runs synchronously so the UI can show a result."""
    year = int(request.args["year"])
    year_dir(year)  # validate
    claude = shutil.which("claude")
    if not claude:
        abort(503, "claude CLI not installed")
    try:
        r = subprocess.run(
            [claude, "-p", "--permission-mode", "acceptEdits", _autosync_prompt(year)],
            cwd=str(DATA_ROOT), capture_output=True, text=True, timeout=300,
        )
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        return jsonify({"ok": True, "summary": tail[0]})
    except subprocess.TimeoutExpired:
        abort(504, "autosync timed out (5 min)")


# -------- Ancient One (premium optimizer) --------

ANCIENT_PORT = 5175
ANCIENT_CWD = Path(__file__).resolve().parent / "personas" / "ancient-one"
_ancient = {"proc": None}


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _stop_ancient() -> None:
    p = _ancient.get("proc")
    if p and p.poll() is None:
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    _ancient["proc"] = None


atexit.register(_stop_ancient)


# -------- Wizard's Tower — multi-tab sessions --------

# Shared xterm.js theme for wizard terminals (classic black + white).
# ttyd serializes every `-t` into a single client-options object.
WIZARD_XTERM_THEME = (
    '{'
    '"background":"#000000",'
    '"foreground":"#ffffff",'
    '"cursor":"#ffffff",'
    '"cursorAccent":"#000000",'
    '"selectionBackground":"rgba(255,255,255,0.3)",'
    '"black":"#000000","red":"#cd3131","green":"#0dbc79","yellow":"#e5e510",'
    '"blue":"#2472c8","magenta":"#bc3fbc","cyan":"#11a8cd","white":"#e5e5e5",'
    '"brightBlack":"#666666","brightRed":"#f14c4c","brightGreen":"#23d18b",'
    '"brightYellow":"#f5f543","brightBlue":"#3b8eea","brightMagenta":"#d670d6",'
    '"brightCyan":"#29b8db","brightWhite":"#ffffff"'
    '}'
)
WIZARD_XTERM_OPTS = [
    "-t", "fontSize=14",
    "-t", "fontFamily=Menlo, Monaco, 'SF Mono', Consolas, monospace",
    "-t", "lineHeight=1.3",
    "-t", "cursorBlink=true",
    "-t", "cursorStyle=block",
    "-t", f"theme={WIZARD_XTERM_THEME}",
]

WIZARD_NAMES = [
    "Gandalf", "Morgana", "Saruman", "Radagast", "Circe",
    "Elminster", "Medea", "Sybil", "Oracle", "Mystic",
    "Ferryman",
]

# Topic → fixed wizard name (falls back to rotation if name taken)
TOPIC_NAMES = {
    "profile": "Gandalf",
    "questions": "Morgana",
    "ship-readiness": "Ferryman",
}
_wizards: dict = {}  # tab_id -> {port, proc, name, topic}
_wizard_next_port = 5176


def _pick_wizard_name(topic: str = "") -> str:
    taken = {w["name"] for w in _wizards.values()}
    preferred = TOPIC_NAMES.get(topic)
    if preferred and preferred not in taken:
        return preferred
    for name in WIZARD_NAMES:
        if name not in taken:
            return name
    return f"Wizard {len(_wizards) + 1}"


def build_wizard_prompt(topic: str, year: int) -> str:
    quest_sync = (
        f"**First, sync the quest list with the profile.** "
        f"Read the MDDocs/Profile.md, {year}/Profile.md, {year}/Files.md, and {year}/_quests.json. "
        f"For every named employer, brokerage, bank, or benefit provider in the profile, ensure "
        f"there's a correspondingly-named quest with specific match tokens (e.g., the quest "
        f"\"W-2 — primary employer\" should be renamed to \"W-2 — <employer-name>\" when known). "
        f"Use /rename-quest for generic→specific renames, /add-quest for missing quests "
        f"(e.g., one per brokerage account), and /remove-quest for quests that don't apply "
        f"(e.g., secondary W-2 if the user has only one). Prefer rename over add+remove."
    )
    # IMPORTANT: every direct-entry topic prompt begins with an identity declaration that
    # overrides CLAUDE.md's "Default session (Merlin)" protocol. Without this override the
    # specialist tabs would misread themselves as Merlin and try to delegate back to themselves.
    specialist_override = (
        "**You are the specialist for this tab, not Merlin.** The user opened this tab directly "
        "from a UI button that spawned a dedicated session for this topic — that is the whole "
        "point. Ignore CLAUDE.md's 'Default session (Merlin)' section; those orchestrator rules "
        "do NOT apply here. Do the work yourself using Read/Edit/Write and the workspace's "
        "slash commands (`/update-profile`, `/resolve-question`, `/status`, etc., as appropriate). "
        "Do NOT invoke `Task` to delegate back to gandalf/morgana subagents — you *are* the "
        "specialist; invoking a subagent from here would be redundant and confusing.\n\n"
    )

    if topic == "profile":
        return (
            f"You are **Gandalf**, the Tax Profile strategy specialist. The user opened this tab "
            f"from the Tax Profile modal and wants to work through their {year} Profile.\n\n"
            f"{specialist_override}"
            f"Help the user walk through their Tax Profile for filing year {year}.\n\n"
            f"**Before asking questions, read MDDocs/Recommendations.md** — the user has a "
            f"playbook maintained by the Ancient One listing their active strategies and watch-list "
            f"items. Your updates to Profile.md should be consistent with their documented strategy. "
            f"You do NOT edit Recommendations.md (Ancient One's turf); you only read it.\n\n"
            f"{quest_sync}\n\n"
            f"Then take them through what's still TBD or unclear, one focused question at a time. "
            f"Update the matching Profile.md as they confirm facts. When a new fact implies a new "
            f"quest (new employer, new account, new benefit), apply it via the quest commands.\n\n"
            f"**Maintain the Summary section**: after each material update to Profile.md, refresh "
            f"the `## Summary` bullets near the top to reflect the current picture (5–8 plain-language "
            f"bullets: filing status, primary income source, side income, major accounts, key "
            f"benefits/contributions, anything unusual). Rewrite the section rather than appending. "
            f"This is what the user sees when they open the Tax Profile modal."
        )
    if topic == "questions":
        return (
            f"You are **Morgana**, the Open Questions reconciliation specialist. The user opened "
            f"this tab from the Open Questions modal and wants to work through their {year} "
            f"OpenQuestions.md list.\n\n"
            f"{specialist_override}"
            f"Help the user resolve the open questions for {year}.\n\n"
            f"{quest_sync}\n\n"
            f"Then walk through {year}/OpenQuestions.md item by item, capture answers, "
            f"remove resolved items, and cascade durable facts into Profile.md (root for "
            f"cross-year facts; {year}/Profile.md for year-specific). If an answer reveals a "
            f"new entity (e.g., \"I also have an E*TRADE account\"), add the matching quest."
        )
    if topic == "ship-readiness":
        return (
            f"You are **Ferryman**, the ship-readiness gatekeeper. The user clicked 'Ship to CPA' "
            f"and wants a final readiness check before handoff for year {year}.\n\n"
            f"{specialist_override}"
            f"Help the user close out the remaining blockers before shipping the {year} package.\n\n"
            f"{quest_sync}\n\n"
            f"Then walk them through readiness:\n"
            f"1. Open {year}/_quests.json and identify every quest with `required: true` "
            f"that has no matching file in {year}/input/. For each: ask whether the document exists, "
            f"whether they can retrieve it, whether the quest itself is actually relevant (and can be "
            f"removed via /remove-quest), or whether to proceed without it. Apply their answers.\n"
            f"2. Then walk through {year}/OpenQuestions.md item by item (same resolve flow as Morgana).\n\n"
            f"Stop when both lists are empty or the user explicitly says \"that's all I can do right now.\" "
            f"Close with a one-line verdict: READY TO SHIP vs. PROCEED WITH GAPS (and name the gaps)."
        )
    return (
        f"You are **Merlin**, the master wizard. The user just opened the default Wizard's Tower "
        f"tab for filing year {year}. Follow the 'Default session (Merlin)' protocol documented in "
        f"the workspace `CLAUDE.md`. Begin by reading `MDDocs/Profile.md`, `{year}/Profile.md`, "
        f"`{year}/OpenQuestions.md`, and `{year}/Files.md`, then greet the user with a short "
        f"status summary and ask what they want to tackle."
    )


def _stop_all_wizards() -> None:
    for w in list(_wizards.values()):
        p = w.get("proc")
        if p and p.poll() is None:
            try:
                p.send_signal(signal.SIGTERM)
                p.wait(timeout=2)
            except Exception:
                try: p.kill()
                except Exception: pass
    _wizards.clear()


atexit.register(_stop_all_wizards)


@app.route("/api/wizard/tab", methods=["POST"])
def api_wizard_tab_create():
    global _wizard_next_port
    body = request.get_json(force=True) or {}
    topic = body.get("topic", "general")
    year = int(body.get("year", CURRENT_FILING_YEAR))
    ttyd = shutil.which("ttyd")
    claude = shutil.which("claude")
    if not (ttyd and claude):
        abort(503, "ttyd or claude CLI not installed")

    port = _wizard_next_port
    _wizard_next_port += 1
    tab_id = uuid.uuid4().hex[:8]
    name = _pick_wizard_name(topic)
    prompt = build_wizard_prompt(topic, year)

    cmd = [
        ttyd, "-p", str(port), "-i", "127.0.0.1", "-W",
        *WIZARD_XTERM_OPTS,
        "bash", "-lc",
        f'cd "{DATA_ROOT}" && exec "{claude}" {shlex.quote(prompt)}',
    ]
    proc = subprocess.Popen(cmd)
    _wizards[tab_id] = {"port": port, "proc": proc, "name": name, "topic": topic, "year": year}

    # Wait for port to be ready (up to ~3s)
    import time
    for _ in range(30):
        if _port_open(port):
            break
        time.sleep(0.1)

    return jsonify({"tab_id": tab_id, "port": port, "name": name, "topic": topic})


@app.route("/api/wizard/tab", methods=["DELETE"])
def api_wizard_tab_delete():
    tab_id = request.args.get("id", "")
    w = _wizards.pop(tab_id, None)
    sync_year = None
    if w:
        p = w.get("proc")
        if p and p.poll() is None:
            try:
                p.send_signal(signal.SIGTERM)
                p.wait(timeout=2)
            except Exception:
                try: p.kill()
                except Exception: pass
        # After a wizard conversation ends, kick off a background profile sync
        # so any facts captured in the chat get reflected in Profile.md + MDDocs/Profile.md.
        sync_year = w.get("year")
    if sync_year:
        _autosync_async(int(sync_year), reason=f"wizard-close ({w.get('name','?')})")
    return jsonify({"ok": True})


@app.route("/api/wizard/tabs")
def api_wizard_tabs():
    # Prune dead processes
    for tab_id in list(_wizards.keys()):
        p = _wizards[tab_id].get("proc")
        if p and p.poll() is not None:
            _wizards.pop(tab_id, None)
    return jsonify([
        {"tab_id": tid, "port": w["port"], "name": w["name"], "topic": w["topic"]}
        for tid, w in _wizards.items()
    ])


@app.route("/api/optimizer/start", methods=["POST"])
def api_optimizer_start():
    year = int(request.args.get("year", CURRENT_FILING_YEAR))
    yd = year_dir(year)
    meta = read_meta(yd, year)
    ttyd = shutil.which("ttyd")
    claude = shutil.which("claude")
    if not (ttyd and claude):
        abort(503, "ttyd or claude CLI not installed")
    if _ancient["proc"] and _ancient["proc"].poll() is None:
        return jsonify({"running": True, "port": ANCIENT_PORT})
    env = {
        **dict(__import__("os").environ),
        "TAXES_ROOT": str(DATA_ROOT),
        "ACTIVE_YEAR": str(year),
        "ACTIVE_YEAR_TYPE": effective_year_type(yd, year),
    }
    ancient_theme = (
        '{'
        '"background":"#0f0a1f",'
        '"foreground":"#f5e6b8",'
        '"cursor":"#d4af37",'
        '"cursorAccent":"#0f0a1f",'
        '"selectionBackground":"rgba(212,175,55,0.3)",'
        '"black":"#1a102a","red":"#c8503a","green":"#7aa870","yellow":"#d4af37",'
        '"blue":"#7a8ad4","magenta":"#b86bd4","cyan":"#6bd4c8","white":"#f5e6b8",'
        '"brightBlack":"#4a3a6b","brightRed":"#e87050","brightGreen":"#94d488",'
        '"brightYellow":"#f5d356","brightBlue":"#9cacf5","brightMagenta":"#d488ec",'
        '"brightCyan":"#8cf5e4","brightWhite":"#fff5d4"'
        '}'
    )
    cmd = [
        ttyd, "-p", str(ANCIENT_PORT), "-i", "127.0.0.1", "-W",
        "-t", "fontSize=14",
        "-t", "fontFamily=Menlo, Monaco, 'SF Mono', Consolas, monospace",
        "-t", "lineHeight=1.3",
        "-t", "cursorBlink=true",
        "-t", "cursorStyle=block",
        "-t", f"theme={ancient_theme}",
        "bash", "-lc", f'cd "{ANCIENT_CWD}" && exec "{claude}"',
    ]
    _ancient["proc"] = subprocess.Popen(cmd, env=env)
    return jsonify({"running": True, "port": ANCIENT_PORT})


@app.route("/api/optimizer/status")
def api_optimizer_status():
    running = bool(_ancient["proc"] and _ancient["proc"].poll() is None)
    ready = running and _port_open(ANCIENT_PORT)
    return jsonify({"running": running, "ready": ready, "port": ANCIENT_PORT})


@app.route("/api/optimizer/stop", methods=["POST"])
def api_optimizer_stop():
    _stop_ancient()
    return jsonify({"running": False})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5173, debug=False)
