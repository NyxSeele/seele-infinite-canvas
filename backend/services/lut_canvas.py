"""分镜表节点 LUT 配置读写与批量应用。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from models.canvas_project import CanvasProject
from services.canvas_style_ref import (
    _node_data,
    find_node,
    load_canvas_data,
    save_canvas_data,
)
from services.lut_registry import list_builtin_presets, preset_display_name, resolve_builtin_lut_path
from services.video_lut_service import resolve_lut_file_path


def get_script_table_lut_config(
    canvas_data: dict,
    script_table_node_id: str,
) -> dict[str, Any]:
    table = find_node(canvas_data, script_table_node_id)
    if not table or table.get("type") != "script-table":
        raise HTTPException(status_code=404, detail="分镜表节点不存在")
    data = _node_data(table)
    preset = data.get("lutPreset")
    custom_url = data.get("lutCustomUrl")
    custom_name = data.get("lutCustomName")
    active_name = custom_name or preset_display_name(preset if not custom_url else "custom")
    if not custom_url and preset and preset != "none":
        if not resolve_builtin_lut_path(preset):
            preset = "none"
    return {
        "lut_preset": preset,
        "lut_custom_url": custom_url,
        "lut_custom_name": custom_name,
        "active_name": active_name,
        "builtin_presets": list_builtin_presets(),
    }


def patch_script_table_lut(
    project: CanvasProject,
    script_table_node_id: str,
    *,
    lut_preset: str | None = None,
    lut_custom_url: str | None = None,
    lut_custom_name: str | None = None,
    clear_custom: bool = False,
) -> dict[str, Any]:
    canvas_data = load_canvas_data(project)
    table = find_node(canvas_data, script_table_node_id)
    if not table or table.get("type") != "script-table":
        raise HTTPException(status_code=404, detail="分镜表节点不存在")
    data = dict(_node_data(table))

    if clear_custom:
        data.pop("lutCustomUrl", None)
        data.pop("lutCustomName", None)

    if lut_custom_url is not None:
        path = resolve_lut_file_path(lut_preset=None, lut_custom_url=lut_custom_url)
        if path is None:
            raise HTTPException(status_code=400, detail="自定义 LUT 文件无效")
        data["lutCustomUrl"] = lut_custom_url
        if lut_custom_name:
            data["lutCustomName"] = lut_custom_name
        data.pop("lutPreset", None)
    elif lut_preset is not None:
        pid = (lut_preset or "").strip() or "none"
        if pid != "none" and resolve_builtin_lut_path(pid) is None:
            raise HTTPException(status_code=400, detail="未知 LUT 预设")
        data["lutPreset"] = pid
        data.pop("lutCustomUrl", None)
        data.pop("lutCustomName", None)

    table["data"] = data
    save_canvas_data(project, canvas_data)
    return get_script_table_lut_config(canvas_data, script_table_node_id)


def iter_video_nodes_with_source(canvas_data: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in canvas_data.get("nodes") or []:
        if not isinstance(node, dict) or node.get("type") != "video-gen":
            continue
        data = _node_data(node)
        video_url = (data.get("videoUrl") or "").strip()
        if not video_url:
            continue
        out.append({"node_id": node.get("id"), "video_url": video_url})
    return out


def resolve_active_lut_from_table(canvas_data: dict, script_table_node_id: str) -> tuple[str | None, str | None]:
    table = find_node(canvas_data, script_table_node_id)
    if not table:
        return None, None
    data = _node_data(table)
    custom = (data.get("lutCustomUrl") or "").strip() or None
    preset = (data.get("lutPreset") or "").strip() or None
    if custom:
        return None, custom
    if preset and preset != "none":
        return preset, None
    return None, None


def lut_is_configured(canvas_data: dict, script_table_node_id: str) -> bool:
    preset, custom = resolve_active_lut_from_table(canvas_data, script_table_node_id)
    if custom:
        return resolve_lut_file_path(lut_preset=None, lut_custom_url=custom) is not None
    if preset:
        return resolve_builtin_lut_path(preset) is not None
    return False
