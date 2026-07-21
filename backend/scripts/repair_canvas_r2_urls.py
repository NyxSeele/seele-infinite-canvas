#!/usr/bin/env python3
"""Repair canvas_projects JSON: bare /canvas/... paths → full R2 public URLs."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.r2 import r2_public_url_for_key  # noqa: E402

DB_PATH = ROOT / "aistudio.db"
CANVAS_PREFIX = "/canvas/"


def fix_string(value: str) -> tuple[str, bool]:
    raw = value.strip()
    if not raw.startswith(CANVAS_PREFIX):
        return value, False
    path_part, _, query = raw.partition("?")
    key = path_part.lstrip("/")
    try:
        full = r2_public_url_for_key(key)
    except Exception:
        return value, False
    fixed = f"{full}?{query}" if query else full
    return fixed, fixed != value


def walk(value):
    changed = False
    if isinstance(value, str):
        fixed, did = fix_string(value)
        return fixed, did
    if isinstance(value, list):
        out = []
        for item in value:
            fixed, did = walk(item)
            out.append(fixed)
            changed = changed or did
        return out, changed
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            fixed, did = walk(v)
            out[k] = fixed
            changed = changed or did
        return out, changed
    return value, False


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, data FROM canvas_projects WHERE data IS NOT NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        try:
            payload = json.loads(row["data"])
        except json.JSONDecodeError:
            continue
        fixed, changed = walk(payload)
        if not changed:
            continue
        conn.execute(
            "UPDATE canvas_projects SET data = ? WHERE id = ?",
            (json.dumps(fixed, ensure_ascii=False), row["id"]),
        )
        updated += 1
        print(f"fixed project {row['id']} ({row['name']})")
    conn.commit()
    conn.close()
    print(f"done: {updated} project(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
