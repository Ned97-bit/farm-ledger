"""Builds a single CPA-ready PDF:
  Cover → Filer context → Clarifications → Flags → Grouped TOC → [Section dividers + raw docs]
Raw document PDFs are merged byte-identically; images are wrapped in single-page PDFs.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem,
)
from reportlab.lib import colors

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp", ".tiff"}


# -------- Canonical ordering --------
# Maps slot-id prefixes (from filename prefix before `__`) to a section + sort priority.
# Files whose prefix matches a key below are placed in that section in the listed order.
# Anything unmatched falls into "Other" at the end.
SECTION_ORDER = ["Income", "Investments", "Benefits", "Deductions", "Self-employment", "Prior year", "ID", "Other"]

SLOT_CATEGORIES: list[tuple[str, str]] = [
    # (needle, section) — matched via canonical (alphanumeric-only) substring.
    # Order within the list doubles as priority within section (first entry = earliest).
    # ---- Income — employment ----
    ("w2",            "Income"),
    ("w-2",           "Income"),
    ("1099nec",       "Income"),
    ("1099-nec",      "Income"),
    ("1099misc",      "Income"),
    ("1099-misc",     "Income"),
    # ---- Investments — form codes ----
    ("1099b",         "Investments"),
    ("1099-b",        "Investments"),
    ("1099div",       "Investments"),
    ("1099-div",      "Investments"),
    ("1099int",       "Investments"),
    ("1099-int",      "Investments"),
    ("1099r",         "Investments"),
    ("1099-r",        "Investments"),
    ("k1",            "Investments"),
    ("k-1",           "Investments"),
    ("pltr",          "Investments"),
    ("costbasis",     "Investments"),
    ("cost-basis",    "Investments"),
    ("consolidated",  "Investments"),
    ("composite",     "Investments"),
    # ---- Investments — common brokerage / retirement providers ----
    ("fidelity",      "Investments"),
    ("schwab",        "Investments"),
    ("robinhood",     "Investments"),
    ("empower",       "Investments"),
    ("vanguard",      "Investments"),
    ("etrade",        "Investments"),
    ("e*trade",       "Investments"),
    ("ameritrade",    "Investments"),
    ("morganstanley", "Investments"),
    ("betterment",    "Investments"),
    ("wealthfront",   "Investments"),
    ("coinbase",      "Investments"),
    ("kraken",        "Investments"),
    # ---- Benefits ----
    ("1095",          "Benefits"),
    ("1099sa",        "Benefits"),
    ("1099-sa",       "Benefits"),
    ("5498sa",        "Benefits"),
    ("5498-sa",       "Benefits"),
    ("5498",          "Benefits"),
    ("hsa",           "Benefits"),
    ("ira",           "Benefits"),
    ("roth",          "Benefits"),
    ("navia",         "Benefits"),
    ("umb",           "Benefits"),
    # ---- Deductions ----
    ("1098e",         "Deductions"),
    ("1098-e",        "Deductions"),
    ("1098t",         "Deductions"),
    ("1098-t",        "Deductions"),
    ("1098",          "Deductions"),
    ("property",      "Deductions"),
    ("charity",       "Deductions"),
    ("donation",      "Deductions"),
    # ---- Self-employment ----
    ("seincome",      "Self-employment"),
    ("seexpenses",    "Self-employment"),
    ("invoice",       "Self-employment"),
    ("expense",       "Self-employment"),
    ("estimated",     "Self-employment"),
    # ---- Prior year ----
    ("priorreturn",   "Prior year"),
    ("prior-return",  "Prior year"),
    ("priorfederal",  "Prior year"),
    ("priorstate",    "Prior year"),
    ("filedreturn",   "Prior year"),
    ("filed-return",  "Prior year"),
    ("staterreturn",  "Prior year"),
    ("state-return",  "Prior year"),
    # ---- ID ----
    ("idlicense",     "ID"),
    ("license",       "ID"),
]


def _canon(s: str) -> str:
    """Strip to lowercase alphanumerics only, so 'W-2' and 'w2' compare equal."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _categorize(filename: str) -> tuple[str, int]:
    """Returns (section, priority_within_section). Canonical substring match against needles."""
    canon = _canon(filename)
    for i, (needle, section) in enumerate(SLOT_CATEGORIES):
        if _canon(needle) in canon:
            return section, i
    return "Other", 999


# -------- reportlab styles --------

def _base_styles():
    styles = getSampleStyleSheet()
    return {
        "h1":     ParagraphStyle("h1", parent=styles["Heading1"], fontSize=22, spaceAfter=12, textColor=colors.HexColor("#3d2817")),
        "h2":     ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#6b4e2e")),
        "body":   ParagraphStyle("body", parent=styles["Normal"], fontSize=11, leading=15, textColor=colors.HexColor("#2a1f14")),
        "label":  ParagraphStyle("label", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#6b4e2e")),
        "caption":ParagraphStyle("cap",  parent=styles["Normal"], fontSize=9, textColor=colors.grey),
        "center": ParagraphStyle("ctr",  parent=styles["Normal"], fontSize=14, alignment=TA_CENTER, textColor=colors.HexColor("#3d2817")),
    }


# -------- Generated pages --------

def _cover_pdf(author: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    w, h = LETTER
    c.setFillColor(colors.HexColor("#3d2817"))
    c.setFont("Helvetica", 18)
    c.drawCentredString(w / 2, h / 2 + 0.2 * inch,
                        f"Prepared by {author} on {date.today().strftime('%B %d, %Y')}")
    c.showPage()
    c.save()
    return buf.getvalue()


def _filer_context_pdf(filer: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
                            leftMargin=0.9*inch, rightMargin=0.9*inch,
                            topMargin=0.9*inch, bottomMargin=0.9*inch)
    S = _base_styles()
    story = [Paragraph("Filer Context", S["h1"])]
    # Render each (label, value) pair; skip empty/TBD
    pairs = [
        ("Filing status",    filer.get("filing_status")),
        ("Residency",        filer.get("residency")),
        ("Dependents",       filer.get("dependents")),
        ("Primary employer", filer.get("employer")),
        ("Side income",      filer.get("side_income")),
        ("Brokerages",       filer.get("brokerages")),
        ("Benefits accounts",filer.get("benefits")),
        ("Retirement",       filer.get("retirement")),
    ]
    tbl_rows = []
    for label, val in pairs:
        if val and str(val).strip().upper() != "TBD":
            tbl_rows.append([Paragraph(f"<b>{label}</b>", S["label"]),
                             Paragraph(str(val), S["body"])])
    if not tbl_rows:
        story.append(Paragraph("<i>No filer context available.</i>", S["body"]))
    else:
        t = Table(tbl_rows, colWidths=[1.7*inch, 4.5*inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#d4b97a")),
        ]))
        story.append(t)
    doc.build(story)
    return buf.getvalue()


# ---- markdown-inline → reportlab HTML (fallback, used when briefing is unavailable) ----

def _md_to_rl(text: str) -> str:
    """Convert basic markdown-inline to reportlab's Paragraph-friendly inline HTML.
       **bold** → <b>bold</b>,  *em* / _em_ → <i>em</i>,  `code` → <font face="Courier">code</font>
       Escapes existing <, > first."""
    if not text:
        return ""
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\w)`([^`\n]+?)`(?!\w)", r'<font face="Courier">\1</font>', t)
    t = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", t)
    return t


def _strip_filename_prefix(desc: str, filename: str) -> str:
    """If the description starts with a restatement of the filename (e.g. `**filename**`
    or `` `filename` ``), drop that chunk so we don't repeat the heading."""
    if not desc:
        return ""
    t = desc.lstrip()
    patterns = [
        rf"^\*\*`?{re.escape(filename)}`?\*\*\s*[—-]*\s*",
        rf"^`{re.escape(filename)}`\s*[—-]*\s*",
        rf"^{re.escape(filename)}\s*[—-]+\s*",
    ]
    for p in patterns:
        new = re.sub(p, "", t, count=1)
        if new != t:
            return new
    return t


def _clarifications_pdf(entries: list[dict]) -> bytes:
    """entries: [{filename, summary?, bullets?, raw_description?}, ...] in merged order.

    If `summary` + `bullets` are present (briefing-driven), render as:
       <b>filename</b>
       <summary line>
       • bullet 1
       • bullet 2

    Otherwise (fallback to Files.md prose), render as markdown-parsed paragraph.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
                            leftMargin=0.9*inch, rightMargin=0.9*inch,
                            topMargin=0.9*inch, bottomMargin=0.9*inch)
    S = _base_styles()
    story = [Paragraph("Clarifications", S["h1"]),
             Paragraph("Notes on each document included in this package, in the order they appear.", S["caption"]),
             Spacer(1, 10)]
    filename_style = ParagraphStyle("fname", parent=S["body"],
                                     fontName="Helvetica-Bold", fontSize=11,
                                     textColor=colors.HexColor("#3d2817"),
                                     spaceBefore=8, spaceAfter=2)
    summary_style = ParagraphStyle("summ", parent=S["body"],
                                    textColor=colors.HexColor("#3d2817"),
                                    spaceAfter=4)
    for e in entries:
        fname = e.get("filename", "")
        story.append(Paragraph(_md_to_rl(fname), filename_style))
        if e.get("summary") or e.get("bullets"):
            summary = e.get("summary") or ""
            if summary:
                story.append(Paragraph(_md_to_rl(summary), summary_style))
            bullets = e.get("bullets") or []
            if bullets:
                items = [ListItem(Paragraph(_md_to_rl(b), S["body"]), leftIndent=10) for b in bullets]
                story.append(ListFlowable(items, bulletType="bullet", start="•",
                                           leftIndent=14, bulletFontSize=9, spaceAfter=6))
        else:
            # Fallback — raw Files.md description with markdown parsed
            raw = _strip_filename_prefix(e.get("raw_description", "") or "", fname)
            if raw:
                story.append(Paragraph(_md_to_rl(raw), S["body"]))
            else:
                story.append(Paragraph("<i>No description provided.</i>", S["body"]))
    doc.build(story)
    return buf.getvalue()


def _flags_pdf(flags: list[dict] | list[str]) -> bytes:
    """flags: either a list of strings (legacy) or list of {title, detail} dicts (briefing)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
                            leftMargin=0.9*inch, rightMargin=0.9*inch,
                            topMargin=0.9*inch, bottomMargin=0.9*inch)
    S = _base_styles()
    story = [Paragraph("Flags for your review", S["h1"]),
             Paragraph("Items flagged while preparing this package. Please advise.", S["caption"]),
             Spacer(1, 10)]
    if not flags:
        story.append(Paragraph("<i>No flagged items for this filing.</i>", S["body"]))
        doc.build(story)
        return buf.getvalue()

    title_style = ParagraphStyle("ftitle", parent=S["body"],
                                  fontName="Helvetica-Bold", fontSize=11,
                                  textColor=colors.HexColor("#3d2817"),
                                  spaceBefore=8, spaceAfter=2)
    detail_style = ParagraphStyle("fdet", parent=S["body"],
                                   textColor=colors.HexColor("#3d2817"),
                                   spaceAfter=4)
    for idx, f in enumerate(flags, start=1):
        if isinstance(f, dict):
            title = f.get("title", "").strip() or f"Flag {idx}"
            detail = f.get("detail", "").strip()
        else:
            # Legacy string: split on first ":" or "—" for a title/body if possible
            s = str(f).strip()
            m = re.match(r"^(.{4,80}?)[:—](.+)$", s, re.S)
            if m:
                title, detail = m.group(1).strip(), m.group(2).strip()
            else:
                title, detail = s[:80], s[80:].strip() if len(s) > 80 else ""
        story.append(Paragraph(f"{idx}. {_md_to_rl(title)}", title_style))
        if detail:
            story.append(Paragraph(_md_to_rl(detail), detail_style))
    doc.build(story)
    return buf.getvalue()


def _toc_pdf(grouped: list[tuple[str, list[tuple[str, int, int]]]]) -> bytes:
    """grouped: [(section, [(filename, start_page, end_page), ...]), ...]"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.9*inch, bottomMargin=0.9*inch)
    S = _base_styles()
    story = [Paragraph("Table of Contents", ParagraphStyle("toc_title", parent=S["h1"], alignment=TA_CENTER))]
    rows = [["Section / Document", "Pages"]]
    section_rows: list[int] = []  # indices for styling
    for section, items in grouped:
        rows.append([Paragraph(f"<b>{section}</b>", S["label"]), ""])
        section_rows.append(len(rows) - 1)
        for fname, sp, ep in items:
            page_range = str(sp) if sp == ep else f"{sp}–{ep}"
            rows.append([Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{fname}", S["body"]), page_range])
    t = Table(rows, colWidths=[5.5*inch, 1.0*inch], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8b6f47")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d4b97a")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]
    for r in section_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#e8d4a0")))
    t.setStyle(TableStyle(style))
    story.append(t)
    doc.build(story)
    return buf.getvalue()


def _section_divider_pdf(section: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    w, h = LETTER
    c.setFillColor(colors.HexColor("#f4e4bc"))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#3d2817"))
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(w / 2, h / 2 + 0.1 * inch, section.upper())
    # Thin wood-tone underline
    c.setStrokeColor(colors.HexColor("#8b6f47"))
    c.setLineWidth(2)
    c.line(w / 2 - 2 * inch, h / 2 - 0.2 * inch, w / 2 + 2 * inch, h / 2 - 0.2 * inch)
    c.showPage()
    c.save()
    return buf.getvalue()


# -------- Raw-doc rendering --------

def _image_to_pdf_bytes(path: Path) -> bytes:
    with Image.open(path) as im:
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="PDF")
        return buf.getvalue()


def _page_count(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


# -------- Assembly --------

def build_package(year: int,
                  selected_files: list[Path],
                  author: str,
                  output_path: Path,
                  filer: dict | None = None,
                  flags: list[str] | None = None,
                  briefing: dict | None = None) -> dict:
    """Assemble the professional CPA package.
    If `briefing` is provided (output of the Ship-to-CPA Claude call), it takes precedence
    over raw Files.md prose + user-curated OpenQuestions flags for the generated pages.
    """
    filer = filer or {}
    flags = flags or []
    briefing = briefing or {}

    # 1. Categorize + sort selected files
    # If Claude's briefing returned an `ordering` array, honor that exactly (it's authoritative
    # for both section assignment and within-section order). Fall back to heuristic categorization
    # for files not present in the ordering (or when no briefing is available).
    briefing_order = briefing.get("ordering") or []
    order_map = {}   # filename -> (position_in_briefing, section_from_briefing)
    for pos, row in enumerate(briefing_order):
        fn = (row or {}).get("filename")
        sec = (row or {}).get("section") or "Other"
        if fn:
            order_map[fn] = (pos, sec if sec in SECTION_ORDER else "Other")

    items = []
    for f in selected_files:
        if f.name in order_map:
            pos, section = order_map[f.name]
            # Preserve Claude's exact list order: use position directly as priority.
            items.append((section, pos, f))
        else:
            section, priority = _categorize(f.name)
            # Push heuristic-categorized items to the end of their section (after briefing-ordered).
            items.append((section, 10000 + priority, f))

    items.sort(key=lambda it: (SECTION_ORDER.index(it[0]) if it[0] in SECTION_ORDER else 999,
                                it[1], it[2].name.lower()))

    # 2. Render each doc to PDF bytes
    rendered: list[tuple[str, Path, bytes]] = []  # (section, path, bytes)
    skipped: list[str] = []
    for section, _prio, f in items:
        ext = f.suffix.lower()
        try:
            if ext == ".pdf":
                data = f.read_bytes()
                _page_count(data)
                rendered.append((section, f, data))
            elif ext in IMAGE_EXTS:
                rendered.append((section, f, _image_to_pdf_bytes(f)))
            else:
                skipped.append(f.name)
        except Exception as e:
            skipped.append(f"{f.name} ({e})")

    # 3. Group by section preserving order
    grouped_docs: list[tuple[str, list[tuple[Path, bytes]]]] = []
    for section, f, data in rendered:
        if not grouped_docs or grouped_docs[-1][0] != section:
            grouped_docs.append((section, []))
        grouped_docs[-1][1].append((f, data))

    # 4. Generate cover/context/clarifications/flags (fixed, known page counts)
    cover   = _cover_pdf(author)
    context = _filer_context_pdf(filer)

    # Build clarification entries — prefer briefing (structured) if present, else fallback
    included_names = [it[2].name for it in items]
    briefing_clar = {c.get("filename"): c for c in (briefing.get("clarifications") or [])}
    clar_entries = []
    for name in included_names:
        b = briefing_clar.get(name)
        if b and (b.get("summary") or b.get("bullets")):
            clar_entries.append({
                "filename": name,
                "summary": b.get("summary", ""),
                "bullets": b.get("bullets", []) or [],
            })
        else:
            clar_entries.append({
                "filename": name,
                "raw_description": _description_for(name),
            })
    clar = _clarifications_pdf(clar_entries)

    # Flags — prefer briefing structured flags; fallback to the raw user-curated list
    briefing_flags = briefing.get("flags") or []
    flags_to_render = briefing_flags if briefing_flags else flags
    flags_b = _flags_pdf(flags_to_render)

    n_cover   = _page_count(cover)     # 1
    n_context = _page_count(context)
    n_clar    = _page_count(clar)
    n_flags   = _page_count(flags_b)

    # 5. Compute document start/end pages for TOC — includes section dividers.
    # Layout plan:
    #   [cover][context][clarifications][flags][TOC ... variable][section divider][docs][divider][docs]...
    # TOC page count isn't known until we build it, so two-pass.

    def compute_grouped_toc(toc_guess: int) -> list[tuple[str, list[tuple[str, int, int]]]]:
        grouped = []
        # cursor = 1 after cover + context + clar + flags + TOC
        cursor = n_cover + n_context + n_clar + n_flags + toc_guess + 1
        for section, docs in grouped_docs:
            section_entries = []
            cursor += 1  # divider page takes 1
            for f, data in docs:
                pages = _page_count(data)
                sp = cursor
                ep = cursor + pages - 1
                section_entries.append((f.name, sp, ep))
                cursor += pages
            grouped.append((section, section_entries))
        return grouped

    # Two-pass TOC: assume 1, then rebuild if actual pages differ
    toc_guess = 1
    toc_bytes = _toc_pdf(compute_grouped_toc(toc_guess))
    actual_toc_pages = _page_count(toc_bytes)
    if actual_toc_pages != toc_guess:
        toc_bytes = _toc_pdf(compute_grouped_toc(actual_toc_pages))

    # 6. Assemble via pypdf
    writer = PdfWriter()

    def append(pdf_bytes: bytes) -> None:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for p in reader.pages:
            writer.add_page(p)

    append(cover)
    append(context)
    append(clar)
    append(flags_b)
    append(toc_bytes)
    for section, docs in grouped_docs:
        append(_section_divider_pdf(section))
        for _f, data in docs:
            append(data)

    writer.add_metadata({
        "/Author": author,
        "/Title": f"{year}FYDocumentsPrepared",
        "/Creator": "Farm Ledger",
        "/Subject": f"{year} tax year — CPA handoff package",
    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as out:
        writer.write(out)

    return {
        "path": str(output_path),
        "pages": len(writer.pages),
        "included": [f.name for _s, f, _d in rendered],
        "skipped": skipped,
        "sections": [s for s, _ in grouped_docs],
    }


# ---- file description lookup (set by the caller) ----
_description_cache: dict[str, str] = {}


def set_descriptions(descs: dict[str, str]) -> None:
    _description_cache.clear()
    _description_cache.update(descs)


def _description_for(filename: str) -> str:
    return _description_cache.get(filename, "")
