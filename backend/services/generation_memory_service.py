"""项目级生成记忆：角色参考、模型偏好、反馈路由粗标签。"""

from __future__ import annotations

import json
from typing import Any

from models.canvas_project import CanvasProject

DEFAULT_GENERATION_MEMORY: dict[str, Any] = {
    "protagonist_face_url": None,
    "preferred_video_model": "wan-2.6",
    "preferred_image_model": "qwen-image",
    "lut_preset_id": None,
    "last_ratio": "16:9",
    "last_quality": "720P",
    "routing_hints": {},
}


def _empty_memory() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_GENERATION_MEMORY))


def parse_generation_memory(raw: str | None) -> dict[str, Any]:
    base = _empty_memory()
    if not raw:
        return base
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return base
    if not isinstance(data, dict):
        return base
    for key in base:
        if key in data:
            base[key] = data[key]
    if not isinstance(base.get("routing_hints"), dict):
        base["routing_hints"] = {}
    return base


def serialize_generation_memory(data: dict[str, Any]) -> str:
    merged = _empty_memory()
    for key in merged:
        if key in data:
            merged[key] = data[key]
    if not isinstance(merged.get("routing_hints"), dict):
        merged["routing_hints"] = {}
    return json.dumps(merged, ensure_ascii=False)


def get_project_generation_memory(project: CanvasProject) -> dict[str, Any]:
    return parse_generation_memory(getattr(project, "generation_memory", None))


def update_project_generation_memory(
    project: CanvasProject,
    patch: dict[str, Any],
) -> dict[str, Any]:
    current = get_project_generation_memory(project)
    for key, value in patch.items():
        if key == "routing_hints" and isinstance(value, dict):
            hints = dict(current.get("routing_hints") or {})
            hints.update(value)
            current["routing_hints"] = hints
        elif key in current:
            current[key] = value
    project.generation_memory = serialize_generation_memory(current)
    return current


def record_shot_generation(
    project: CanvasProject,
    *,
    model_id: str | None,
    ratio: str | None,
    quality: str | None,
    protagonist_face_url: str | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if model_id:
        if (model_id or "").startswith("wan") or model_id == "ltx2-fp4":
            patch["preferred_video_model"] = model_id
        elif model_id in ("qwen-image", "flux-pulid", "hidream"):
            patch["preferred_image_model"] = model_id
    if ratio:
        patch["last_ratio"] = ratio
    if quality:
        patch["last_quality"] = quality
    if protagonist_face_url:
        patch["protagonist_face_url"] = protagonist_face_url
    if not patch:
        return get_project_generation_memory(project)
    return update_project_generation_memory(project, patch)


def record_feedback_routing_hint(
    project: CanvasProject,
    *,
    model_id: str,
    rating: int,
) -> dict[str, Any]:
    """满意 +1 / 不满意 -1，按 model_id 累加粗标签。

    若当前偏好模型连续差评（routing_hints ≤ -3），自动切到 wan-i2v，
    引导用户用参考图保人物辨识（基于 LTX2 反馈调优）。
    """
    mid = (model_id or "").strip() or "unknown"
    current = get_project_generation_memory(project)
    hints = dict(current.get("routing_hints") or {})
    delta = 1 if rating == 1 else -1
    hints[mid] = int(hints.get(mid, 0)) + delta
    patch: dict[str, Any] = {"routing_hints": hints}
    preferred = (current.get("preferred_video_model") or "").strip()
    if rating != 1 and preferred == mid and hints[mid] <= -3:
        patch["preferred_video_model"] = "wan-i2v"
    return update_project_generation_memory(project, patch)


def apply_image_defaults_from_memory(
    memory: dict[str, Any],
    *,
    model_id: str | None,
    reference_image: str | None,
    reference_images: list[str] | None,
) -> tuple[str | None, list[str], str | None]:
    """若请求未带参考图，注入项目主角正脸；返回 (ref, refs, model_override)。"""
    refs = list(reference_images or [])
    ref = reference_image
    model_override = None
    face = (memory.get("protagonist_face_url") or "").strip()
    if face:
        if not ref and not refs:
            ref = face
            refs = [face]
        elif ref and ref not in refs:
            refs.insert(0, ref)
        elif not ref and refs:
            ref = refs[0]
    preferred = (memory.get("preferred_image_model") or "").strip()
    if not model_id and preferred:
        model_override = preferred
    elif model_id in ("qwen-image", "hidream") and face and preferred == "flux-pulid":
        model_override = "flux-pulid"
    return ref, refs, model_override
