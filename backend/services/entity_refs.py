"""角色 / 场景实体参考：共用匹配与 prompt 文案"""

from __future__ import annotations

import re


def _escape_regexp(s: str) -> str:
    return re.sub(r"[.*+?^${}()|[\]\\]", "\\$&", s)


def match_entity_names_in_text(text: str, entities: list[dict]) -> list[dict]:
    """按名称在文本中匹配实体（与前端 matchCastRefsInPrompt 一致）。"""
    raw = (text or "").strip()
    if not raw or not entities:
        return []
    matched: list[dict] = []
    seen: set[str] = set()
    for item in entities:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        patterns = [
            re.compile(rf"@{_escape_regexp(name)}", re.I),
            re.compile(rf"【{_escape_regexp(name)}】"),
            re.compile(rf"\[{_escape_regexp(name)}\]"),
        ]
        if any(p.search(raw) for p in patterns) or name in raw:
            matched.append(item)
            seen.add(key)
    return matched


def _row_text(row: dict) -> str:
    parts = [
        row.get("prompt") or row.get("description") or "",
        row.get("characters") or "",
        row.get("scene") or "",
        row.get("location") or "",
    ]
    return " ".join(str(p).strip() for p in parts if p)


def resolve_scene_refs_for_row(row: dict, scene_library: list[dict]) -> list[dict]:
    lib = [s for s in (scene_library or []) if (s.get("name") or "").strip()]
    if not lib:
        return []
    out: list[dict] = []
    seen: set[str] = set()

    loc_id = row.get("location_id") or row.get("locationId")
    if loc_id:
        hit = next((s for s in lib if s.get("id") == loc_id), None)
        if hit and hit.get("id") not in seen:
            seen.add(hit["id"])
            out.append(hit)

    for item in match_entity_names_in_text(_row_text(row), lib):
        eid = item.get("id")
        if eid and eid not in seen:
            seen.add(eid)
            out.append(item)
    return out


def entity_lines_for_prompt(
    cast_library: list[dict] | None,
    scene_library: list[dict] | None,
    row: dict | None = None,
) -> str:
    """生成写入 prompt 包的实体设定行。"""
    lines: list[str] = []
    for item in cast_library or []:
        if item.get("type") == "scene":
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        lines.append(f"- 人物「{name}」：保持与设定参考图一致")

    scenes = resolve_scene_refs_for_row(row or {}, scene_library or [])
    if not scenes and scene_library:
        for item in scene_library:
            name = (item.get("name") or "").strip()
            if name:
                lines.append(f"- 场景「{name}」：保持与场景参考图一致")
    else:
        for item in scenes:
            name = (item.get("name") or "").strip()
            if name:
                lines.append(f"- 场景「{name}」：保持与场景参考图一致")

    return "\n".join(lines) if lines else "（未绑定设定库）"
