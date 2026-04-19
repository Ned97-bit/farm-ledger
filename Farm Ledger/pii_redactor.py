"""PII redaction applied before content reaches any AI assistant.

Spec (per Farm Ledger product decisions):
  - SSN           → fully redacted ("[REDACTED]")
  - Date of Birth → year preserved ("**/**/YYYY")
  - Account nums  → last 4 digits preserved ("*****4674"); conservative
                    (keyword-required: "Account", "Acct", "A/N")
  - Street addr   → street line + apt/suite/PO-box stripped; city/state/ZIP kept
  - Name          → NOT redacted (user decision; names are not considered
                    sensitive in this product since the app runs locally)

Originals on disk are never modified. `redact()` returns a transformed string;
`redact_file_to_sidecar()` writes a `.redacted.txt` next to the source file.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------- SSN ----------
_SSN_DASHED = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
_SSN_LABELED = re.compile(
    r'((?:SSN|Social[-\s]?Security(?:[-\s]?Number)?|Taxpayer[-\s]?(?:ID|Identification[-\s]?Number?))'
    r'\s*[:#]?\s*)(\d{3}-?\d{2}-?\d{4}|\d{9})',
    re.IGNORECASE,
)

# ---------- Date of Birth ----------
# Only redact dates that appear next to a DOB keyword. Bare dates are left
# alone (too many false positives on tax-period dates, filing deadlines, etc.).
_DOB_KEYWORDED = re.compile(
    r'((?:DOB|D\.O\.B\.|Date[-\s]?of[-\s]?Birth|Birth[-\s]?date|Birth[-\s]?Day|Born(?:\s+on)?)'
    r'\s*[:#]?\s*)'
    r'(?:'
    r'(\d{1,2}[/-]\d{1,2}[/-](\d{4}))'                    # groups 2-3: MM/DD/YYYY → year = 3
    r'|(\d{4})[/-]\d{1,2}[/-]\d{1,2}'                     # group 4: YYYY-MM-DD
    r'|([A-Za-z]+\s+\d{1,2},?\s+(\d{4}))'                 # groups 5-6: Month DD, YYYY → year = 6
    r')',
    re.IGNORECASE,
)

# ---------- Account numbers ----------
# Conservative: only redact when preceded by an account-related keyword.
_ACCOUNT_LABELED = re.compile(
    r'((?:Account(?:[-\s]?Number|[-\s]?No\.?|[-\s]?#)?|Acct\.?(?:[-\s]?No\.?|[-\s]?#|[-\s]?Number)?|A\/N)'
    r'\s*[:#]?\s*)'
    r'([A-Za-z0-9][A-Za-z0-9-]{4,})',
    re.IGNORECASE,
)

# ---------- Street address ----------
_STREET_SUFFIXES = (
    r'Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|'
    r'Court|Ct|Place|Pl|Way|Highway|Hwy|Parkway|Pkwy|Circle|Cir|'
    r'Terrace|Ter|Trail|Tr|Square|Sq|Plaza|Pkwy'
)
# Street number + 1-5 name tokens + street-type suffix, optional period, optional unit.
_STREET_LINE = re.compile(
    rf'\b\d{{1,6}}\s+(?:[A-Za-z0-9\'\.]+\s+){{1,5}}(?:{_STREET_SUFFIXES})\b\.?'
    rf'(?:\s*,?\s*(?:Apt|Apartment|Unit|Suite|Ste|Rm|Room|#)\s*[\w-]+)?',
    re.IGNORECASE,
)
_PO_BOX = re.compile(
    r'\b(?:P\.?\s?O\.?|Post(?:al)?)\s+(?:Box|Office\s+Box)\s+[\w-]+',
    re.IGNORECASE,
)
# Standalone apt/unit line (e.g. "Apt 4B" on its own line, typical for
# multi-line address blocks where the street was already matched).
_APT_ONLY_LINE = re.compile(
    r'^\s*(?:Apt\.?|Apartment|Unit|Suite|Ste\.?|Rm\.?|Room|#)\s*[\w-]+\s*$',
    re.IGNORECASE | re.MULTILINE,
)

SSN_REDACTION = '[REDACTED]'
STREET_REDACTION = '[STREET REDACTED]'
PO_BOX_REDACTION = '[PO BOX REDACTED]'
APT_REDACTION = '[APT REDACTED]'


def _redact_account_match(m: re.Match) -> str:
    prefix, number = m.group(1), m.group(2)
    digits = re.sub(r'\D', '', number)
    # Conservative floor: need at least 5 digits for a plausible account number.
    if len(digits) < 5:
        return m.group(0)
    return prefix + '*' * (len(digits) - 4) + digits[-4:]


def _redact_ssn_labeled(m: re.Match) -> str:
    return m.group(1) + SSN_REDACTION


def _redact_dob_keyworded(m: re.Match) -> str:
    prefix = m.group(1)
    year = m.group(3) or m.group(4) or m.group(6) or 'YYYY'
    return prefix + '**/**/' + year


def redact(text: str) -> str:
    """Apply every PII rule. Safe to call on any string; empty/None → empty string."""
    if not text:
        return text or ''
    # Order matters: SSN before account numbers (SSN has a 9-digit signature that
    # could otherwise get caught by a generic account regex); DOB next; then
    # account numbers; then addresses last so multi-line address redaction
    # doesn't interfere with label matching above it.
    text = _SSN_LABELED.sub(_redact_ssn_labeled, text)
    text = _SSN_DASHED.sub(SSN_REDACTION, text)
    text = _DOB_KEYWORDED.sub(_redact_dob_keyworded, text)
    text = _ACCOUNT_LABELED.sub(_redact_account_match, text)
    text = _STREET_LINE.sub(STREET_REDACTION, text)
    text = _PO_BOX.sub(PO_BOX_REDACTION, text)
    text = _APT_ONLY_LINE.sub(APT_REDACTION, text)
    return text


def redact_file_to_sidecar(path: Path, force: bool = False) -> Path | None:
    """Create a `<stem>.redacted.txt` sidecar next to `path`.

    Returns the sidecar path on success, or None for unsupported file types.
    If the sidecar already exists and is newer than the source, returns it
    unmodified unless `force=True`.
    """
    if not path.is_file():
        return None
    ext = path.suffix.lower()
    sidecar = path.with_name(path.stem + '.redacted.txt')
    if sidecar.exists() and not force:
        try:
            if sidecar.stat().st_mtime >= path.stat().st_mtime:
                return sidecar
        except OSError:
            pass

    text: str
    if ext == '.pdf':
        try:
            from pypdf import PdfReader  # already a dep (requirements.txt)
            reader = PdfReader(str(path))
            text = '\n\n'.join((p.extract_text() or '') for p in reader.pages)
        except Exception as e:
            sidecar.write_text(
                f"[PII guard: could not extract text from {path.name} — "
                f"{type(e).__name__}: {e}]"
            )
            return sidecar
    elif ext in ('.md', '.txt', '.json', '.csv', '.tsv'):
        try:
            text = path.read_text(errors='replace')
        except OSError:
            return None
    else:
        return None

    sidecar.write_text(redact(text))
    return sidecar


# ---------- Self-tests ----------
if __name__ == '__main__':
    tests = [
        # SSN
        ('My SSN is 123-45-6789 on file.', 'My SSN is [REDACTED] on file.'),
        ('SSN: 123456789', 'SSN: [REDACTED]'),
        ('Social Security Number: 123-45-6789', 'Social Security Number: [REDACTED]'),
        # DOB — year preserved
        ('DOB: 03/15/1990', 'DOB: **/**/1990'),
        ('Date of Birth: 1990-03-15', 'Date of Birth: **/**/1990'),
        ('Born on March 15, 1990', 'Born on **/**/1990'),
        # Account numbers — last 4 kept
        ('Account Number: 9876541234674', 'Account Number: *********4674'),
        ('Acct #: Z24-1578-4674', 'Acct #: ******4674'),  # 10 digits total → last 4 kept
        ('Acct #: 12345678', 'Acct #: ****5678'),
        # Account: too-short digits → NOT redacted
        ('Account: 1234', 'Account: 1234'),
        # Street — redacted; city/state/ZIP kept
        ('123 Main Street\nAlbany, NY 12345', '[STREET REDACTED]\nAlbany, NY 12345'),
        ('456 Oak Ave, Apt 4B, Buffalo, NY 14203',
         '[STREET REDACTED], Buffalo, NY 14203'),
        ('P.O. Box 12345, Seattle, WA 98101', '[PO BOX REDACTED], Seattle, WA 98101'),
        # Name — NOT redacted
        ('Taxpayer name: Jane Sample', 'Taxpayer name: Jane Sample'),
        # Dollar amount near "Account" keyword — NOT redacted (no 5+ digit run in match)
        ('Account balance: $1,234.56', 'Account balance: $1,234.56'),
        # Edge: empty / None
        ('', ''),
    ]
    failures = []
    for src, expected in tests:
        got = redact(src)
        if got != expected:
            failures.append((src, expected, got))
    if failures:
        print(f"FAILED {len(failures)}/{len(tests)}:")
        for src, expected, got in failures:
            print(f"  in : {src!r}")
            print(f"  exp: {expected!r}")
            print(f"  got: {got!r}")
            print()
        raise SystemExit(1)
    print(f"OK — {len(tests)} cases passed")
