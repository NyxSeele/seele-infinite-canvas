"""角色 / 场景实体参考：共用匹配与 prompt 文案 + identity 门禁"""

from __future__ import annotations

import re
from typing import Any


class MissingIdentityError(Exception):
    def __init__(
        self,
        *,
        names: list[str] | None = None,
        identity_ids: list[str] | None = None,
        message: str = "",
    ) -> None:
        self.names = names or []
        self.identity_ids = identity_ids or []
        self.message = message or "角色已引用但缺少 identity 或参考图"


def _escape_regexp(s: str) -> str:
    return re.sub(r"[.*+?^${}()|[\]\\]", "\\$&", s)


def _norm_url(url: str | None) -> str:
    return (url or "").strip()


def pick_ref_urls(entry: dict | None, *, max_urls: int = 3) -> list[str]:
    if not entry:
        return []
    slots = (
        "threeViewUrl",
        "three_view_url",
        "faceUrl",
        "face_url",
        "costumeUrl",
        "costume_url",
        "imageUrl",
        "image_url",
    )
    seen: set[str] = set()
    out: list[str] = []
    for key in slots:
        url = _norm_url(entry.get(key))
        if url and url not in seen:
            seen.add(url)
            out.append(url)
        if len(out) >= max_urls:
            break
    return out


def slug_identity_id(name: str, variant: str = "default") -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff-]", "", (name or "").strip().lower().replace(" ", "_"))
    return f"{base or 'char'}_{variant}"


def normalize_cast_entry(item: dict | None) -> dict | None:
    if not item:
        return None
    name = (item.get("name") or "").strip()
    if not name:
        return None
    face = _norm_url(item.get("faceUrl") or item.get("face_url") or item.get("imageUrl") or item.get("image_url"))
    three = _norm_url(item.get("threeViewUrl") or item.get("three_view_url"))
    costume = _norm_url(item.get("costumeUrl") or item.get("costume_url"))
    image = face or three or costume or _norm_url(item.get("imageUrl") or item.get("image_url"))
    identity_id = (item.get("identityId") or item.get("identity_id") or "").strip() or slug_identity_id(name)
    return {
        **item,
        "name": name,
        "type": "scene" if item.get("type") == "scene" else "character",
        "identityId": identity_id,
        "faceUrl": face or None,
        "threeViewUrl": three or None,
        "costumeUrl": costume or None,
        "imageUrl": image or None,
    }


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


def _character_cast_library(cast_library: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for raw in cast_library or []:
        entry = normalize_cast_entry(raw)
        if entry and entry.get("type") != "scene":
            out.append(entry)
    return out


def resolve_cast_refs_for_row(row: dict, cast_library: list[dict] | None) -> list[dict]:
    """对齐前端 resolveCastRefsForRow：identityIds > mentions > 文本匹配。"""
    lib = _character_cast_library(cast_library)
    if not lib:
        return []

    seen: set[str] = set()
    out: list[dict] = []

    def push(item: dict) -> None:
        key = (item.get("identityId") or item.get("id") or "").strip()
        if not key or key in seen:
            return
        seen.add(key)
        out.append(item)

    row_identity_ids = row.get("identityIds") or row.get("identity_ids") or []
    for iid in row_identity_ids:
        id_str = str(iid or "").strip()
        if not id_str:
            continue
        hit = next(
            (c for c in lib if c.get("identityId") == id_str or c.get("id") == id_str),
            None,
        )
        if hit:
            push(hit)

    for mention in row.get("promptMentions") or row.get("prompt_mentions") or []:
        mid = mention.get("id")
        mname = (mention.get("name") or "").strip()
        hit = next(
            (c for c in lib if (mid and c.get("id") == mid) or (mname and c.get("name") == mname)),
            None,
        )
        if hit:
            push(hit)

    for item in match_entity_names_in_text(_row_text(row), lib):
        push(item)

    return out


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


def validate_row_identity(row: dict | None, cast_library: list[dict] | None) -> None:
    """行已引用角色但缺 identity 或参考图时抛出 MissingIdentityError；无引用则放行。"""
    row = row or {}
    refs = resolve_cast_refs_for_row(row, cast_library)
    if not refs:
        return

    missing_names: list[str] = []
    missing_ids: list[str] = []
    for entry in refs:
        name = (entry.get("name") or "").strip()
        identity_id = (entry.get("identityId") or entry.get("identity_id") or "").strip()
        if not identity_id:
            if name:
                missing_names.append(name)
            continue
        if not pick_ref_urls(entry):
            missing_names.append(name or identity_id)
            missing_ids.append(identity_id)

    if missing_names or missing_ids:
        names = sorted(set(missing_names))
        ids = sorted(set(missing_ids))
        raise MissingIdentityError(
            names=names,
            identity_ids=ids,
            message=f"角色 {', '.join(names)} 缺少 identity 或参考图，请先完善角色资产",
        )


def identity_lock_lines(resolved: list[dict]) -> str:
    lines: list[str] = []
    for entry in resolved:
        if entry.get("type") == "scene":
            continue
        name = (entry.get("name") or "").strip()
        identity_id = (entry.get("identityId") or entry.get("identity_id") or "").strip()
        if not name:
            continue
        if identity_id:
            lines.append(
                f"- 角色「{name}」（identity: {identity_id}）：跨镜头保持同一身份，五官/服装与参考图一致"
            )
        else:
            lines.append(f"- 角色「{name}」：保持与设定参考图一致的视觉特征")
    return "\n".join(lines)


def entity_lines_for_prompt(
    cast_library: list[dict] | None,
    scene_library: list[dict] | None,
    row: dict | None = None,
) -> str:
    """生成写入 prompt 包的实体设定行。"""
    row = row or {}
    char_refs = resolve_cast_refs_for_row(row, cast_library)
    lines: list[str] = []
    if char_refs:
        lines.append(identity_lock_lines(char_refs))
    else:
        for item in cast_library or []:
            if item.get("type") == "scene":
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            identity_id = (item.get("identityId") or item.get("identity_id") or "").strip()
            id_note = f"（identity: {identity_id}）" if identity_id else ""
            lines.append(f"- 人物「{name}」{id_note}：保持与设定参考图一致")

    scenes = resolve_scene_refs_for_row(row, scene_library or [])
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

    merged = "\n".join(line for line in lines if line)
    return merged if merged else "（未绑定设定库）"


def build_entity_ref_audit(resolved: list[dict]) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    for entry in resolved:
        if entry.get("type") == "scene":
            continue
        audit.append(
            {
                "identityId": entry.get("identityId") or entry.get("identity_id"),
                "name": entry.get("name"),
                "urls": pick_ref_urls(entry),
            }
        )
    return audit
