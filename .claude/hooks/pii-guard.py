#!/usr/bin/env python3
"""PreToolUse hook: redirect Claude's file reads to PII-redacted sidecars.

Installed via .claude/settings.json. Fires on Read and Bash tool calls.
- Read  → if the target file is under the tax data tree, generate (if needed)
          a `.redacted.txt` sidecar and rewrite `file_path` to the sidecar.
- Bash  → for `cat | head | tail | less | more` on a single file under the
          data tree, rewrite the file path arg to the sidecar.

Fail-open is intentional for files OUTSIDE the data tree (e.g., when Claude
reads its own config). Fail-closed would break Claude Code's own bootstrap.
For files INSIDE the data tree, we fail-closed if we can't redact.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path


BASH_READERS = {"cat", "head", "tail", "less", "more", "bat"}


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def _allow(updated_input: dict | None = None) -> None:
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
    if updated_input:
        out["hookSpecificOutput"]["updatedInput"] = updated_input
    _emit(out)


def _deny(reason: str) -> None:
    _emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


def _data_root() -> Path:
    """Resolve the Farm Ledger data root.

    Priority: FARM_LEDGER_DATA_ROOT env var → CLAUDE_PROJECT_DIR/Farm Ledger/YearData
    → first ancestor containing a MDDocs/ dir. Fallback: None."""
    env = os.environ.get("FARM_LEDGER_DATA_ROOT")
    if env:
        p = Path(env).resolve()
        if p.is_dir():
            return p
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cand = Path(proj) / "Farm Ledger" / "YearData"
        if cand.is_dir():
            return cand.resolve()
    # Walk up from cwd
    cur = Path.cwd().resolve()
    for _ in range(6):
        if (cur / "MDDocs").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path.cwd().resolve()


def _redactor_module():
    """Import pii_redactor from Farm Ledger/. Returns module or None."""
    proj = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    candidates = [
        Path(proj) / "Farm Ledger",
        Path(proj),
    ]
    for c in candidates:
        if (c / "pii_redactor.py").is_file():
            sys.path.insert(0, str(c))
            try:
                import pii_redactor  # type: ignore
                return pii_redactor
            except Exception:
                return None
    return None


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def _sidecar_for(path: Path, redactor) -> Path | None:
    if ".redacted" in path.name:
        return path  # already a sidecar
    try:
        return redactor.redact_file_to_sidecar(path)
    except Exception as e:
        sys.stderr.write(f"[pii-guard] sidecar failed for {path.name}: {type(e).__name__}: {e}\n")
        return None


def handle_read(tool_input: dict, root: Path, redactor) -> None:
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        _allow()
        return
    p = Path(file_path)
    if not p.is_absolute():
        p = (root / file_path).resolve()
    else:
        p = p.resolve()
    if not _under(p, root):
        _allow()
        return
    if not p.is_file():
        _allow()
        return
    # Only rewrite if we can produce a sidecar; fail-closed otherwise.
    if redactor is None:
        _deny("PII guard unavailable (pii_redactor not importable); refusing to read tax file.")
        return
    sidecar = _sidecar_for(p, redactor)
    if not sidecar or not sidecar.is_file():
        _deny(f"PII guard could not sanitize {p.name}; read refused.")
        return
    # Rewrite the Read's file_path to the sidecar. Preserve offset/limit if set.
    updated = {"file_path": str(sidecar)}
    for k in ("offset", "limit"):
        if k in tool_input and tool_input[k] is not None:
            updated[k] = tool_input[k]
    _allow(updated)


def _bash_rewrite_reader(cmd: str, root: Path, redactor) -> str | None:
    """If `cmd` is a simple reader (cat/head/tail/less/more) on a file under
    the data root, return a rewritten command that reads the sidecar instead.
    Return None if the command doesn't match — in which case caller leaves it."""
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    # Pipelines/redirects disqualify the rewrite (keep simple).
    if any(t in ("|", ">", ">>", "<", "<<", "&&", "||", ";") for t in tokens):
        return None
    # Find the reader program (strip common wrappers like `env`).
    base = Path(tokens[0]).name
    if base not in BASH_READERS:
        return None
    # Find the last token that looks like a file path.
    new_tokens = list(tokens)
    for i in range(len(new_tokens) - 1, 0, -1):
        tok = new_tokens[i]
        if tok.startswith("-"):
            continue
        p = Path(tok)
        if not p.is_absolute():
            p = (root / tok).resolve()
        else:
            p = p.resolve()
        if not _under(p, root) or not p.is_file():
            continue
        sidecar = _sidecar_for(p, redactor) if redactor else None
        if not sidecar:
            return None
        new_tokens[i] = str(sidecar)
        return shlex.join(new_tokens)
    return None


def handle_bash(tool_input: dict, root: Path, redactor) -> None:
    cmd = tool_input.get("command") or ""
    if not cmd.strip():
        _allow()
        return
    rewritten = _bash_rewrite_reader(cmd, root, redactor)
    if rewritten and rewritten != cmd:
        _allow({"command": rewritten})
    else:
        _allow()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()
        return
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    root = _data_root()
    redactor = _redactor_module()
    if tool == "Read":
        handle_read(tool_input, root, redactor)
    elif tool == "Bash":
        handle_bash(tool_input, root, redactor)
    else:
        _allow()


if __name__ == "__main__":
    main()
