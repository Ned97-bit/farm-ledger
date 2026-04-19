"""Runtime-editable per-year quest list stored as _quests.json."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from checklist import checklist_for as _template_for


def _quests_path(year_dir_: Path) -> Path:
    return year_dir_ / "_quests.json"


def _item_to_dict(it, added_by: str = "template") -> dict:
    d = asdict(it)
    d["status"] = "active"
    d["added_by"] = added_by
    d["added_at"] = date.today().isoformat()
    return d


def _slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s or "quest"


# Explicit allowlist of template quest IDs that MUST exist in every year's _quests.json.
# Adding to this list triggers auto-injection on next load. Keep it small — existing
# users' personalized quests must not be duplicated. Generic template items (w2_primary,
# 1099_b, etc.) should NOT be here, because users typically rename them
# (e.g. w2-acme, 1099-fidelity) and re-injecting the generics creates duplicates.
REQUIRED_TEMPLATE_IDS = {"file_taxes", "cpa_package"}


def load(year: int, year_dir_: Path, year_type: str) -> list:
    """Return full quest list. Creates the file from template on first call.
    Migrations: only quests whose id is in REQUIRED_TEMPLATE_IDS get auto-injected
    when missing. All other template items are advisory — users may rename/remove freely."""
    p = _quests_path(year_dir_)
    if not p.exists():
        items = [_item_to_dict(it) for it in _template_for(year_type, year)]
        save(year_dir_, items)
        return items
    try:
        data = json.loads(p.read_text())
        if isinstance(data, list):
            existing_ids = {q.get("id") for q in data}
            template_items = list(_template_for(year_type, year))
            injected = False
            for idx, it in enumerate(template_items):
                if it.id in existing_ids:
                    continue
                if it.id not in REQUIRED_TEMPLATE_IDS:
                    continue  # skip — user may have personalized this quest under a different id
                new_item = _item_to_dict(it)
                insert_pos = idx if idx < len(data) else len(data)
                data.insert(insert_pos, new_item)
                existing_ids.add(it.id)
                injected = True
            if injected:
                save(year_dir_, data)
            return data
    except json.JSONDecodeError:
        pass
    # Corrupted file — fall back to template, but do NOT overwrite so a human can fix.
    return [_item_to_dict(it) for it in _template_for(year_type, year)]


def save(year_dir_: Path, items: list) -> None:
    """Atomic write."""
    p = _quests_path(year_dir_)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    tmp.replace(p)


def add(year_dir_: Path, year_type: str, year: int, new: dict, added_by: str = "user") -> dict:
    items = load(year, year_dir_, year_type)
    base_id = new.get("id") or _slugify(new.get("label", "quest"))
    q_id = base_id
    i = 2
    existing_ids = {x["id"] for x in items}
    while q_id in existing_ids:
        q_id = f"{base_id}_{i}"
        i += 1
    quest = {
        "id": q_id,
        "label": new["label"],
        "category": new.get("category", "Other"),
        "required": bool(new.get("required", False)),
        "match": list(new.get("match", [])),
        "status": "active",
        "added_by": added_by,
        "added_at": date.today().isoformat(),
    }
    items.append(quest)
    save(year_dir_, items)
    return quest


def update(year_dir_: Path, year_type: str, year: int, q_id: str, patch: dict) -> dict | None:
    items = load(year, year_dir_, year_type)
    for q in items:
        if q["id"] == q_id:
            for k, v in patch.items():
                if k not in ("id", "added_at"):
                    q[k] = v
            save(year_dir_, items)
            return q
    return None


def soft_remove(year_dir_: Path, year_type: str, year: int, q_id: str) -> bool:
    return update(year_dir_, year_type, year, q_id, {"status": "removed"}) is not None
