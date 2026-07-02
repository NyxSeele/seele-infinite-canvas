"""镜头级风格参考：读写 canvas_data 中的 video-gen 节点 / 分镜行。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from models.canvas_project import CanvasProject


def load_canvas_data(project: CanvasProject) -> dict[str, Any]:
    try:
        data = json.loads(project.data or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    if not isinstance(data["nodes"], list):
        data["nodes"] = []
    return data


def save_canvas_data(project: CanvasProject, canvas_data: dict[str, Any]) -> None:
    project.data = json.dumps(canvas_data, ensure_ascii=False)
    project.updated_at = datetime.now(timezone.utc)
    project.version = int(project.version or 1) + 1


def _node_data(node: dict) -> dict:
    data = node.get("data")
    return data if isinstance(data, dict) else {}


def find_node(canvas_data: dict, node_id: str) -> dict | None:
    for node in canvas_data.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return None


def find_script_row(
    canvas_data: dict, script_table_node_id: str, row_id: str
) -> tuple[dict, dict] | None:
    table = find_node(canvas_data, script_table_node_id)
    if not table or table.get("type") != "script-table":
        return None
    data = _node_data(table)
    for row in data.get("rows") or []:
        if isinstance(row, dict) and row.get("id") == row_id:
            return table, row
    return None


def resolve_video_node_for_shot(
    canvas_data: dict, script_table_node_id: str, row_id: str
) -> str:
    found = find_script_row(canvas_data, script_table_node_id, row_id)
    if not found:
        raise HTTPException(status_code=404, detail="分镜行不存在")
    _, row = found
    node_id = (row.get("videoGenNodeId") or "").strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="该镜头尚未关联视频生成节点")
    node = find_node(canvas_data, node_id)
    if not node or node.get("type") != "video-gen":
        raise HTTPException(status_code=404, detail="视频生成节点不存在")
    return node_id


def get_video_node_style_reference(canvas_data: dict, node_id: str) -> dict | None:
    node = find_node(canvas_data, node_id)
    if not node or node.get("type") != "video-gen":
        raise HTTPException(status_code=404, detail="视频生成节点不存在")
    ref = _node_data(node).get("styleReference")
    return ref if isinstance(ref, dict) else None


def get_script_table_content_style(
    canvas_data: dict,
    script_table_node_id: str | None = None,
) -> str:
    """读取项目级内容风格；默认写实电影。"""

    def _read(table: dict) -> str:
        cs = _node_data(table).get("contentStyle")
        return "generic" if cs == "generic" else "photorealistic_cinema"

    if script_table_node_id:
        node = find_node(canvas_data, script_table_node_id)
        if node and node.get("type") == "script-table":
            return _read(node)
    for node in canvas_data.get("nodes") or []:
        if isinstance(node, dict) and node.get("type") == "script-table":
            return _read(node)
    return "photorealistic_cinema"


def _sync_row_style_reference(
    canvas_data: dict,
    *,
    script_table_node_id: str | None,
    row_id: str | None,
    style_ref: dict | None,
) -> None:
    if not script_table_node_id or not row_id:
        return
    found = find_script_row(canvas_data, script_table_node_id, row_id)
    if not found:
        return
    table, row = found
    data = _node_data(table)
    rows = data.get("rows") or []
    new_rows = []
    for r in rows:
        if isinstance(r, dict) and r.get("id") == row_id:
            updated = {**r}
            if style_ref is None:
                updated.pop("styleReference", None)
            else:
                updated["styleReference"] = style_ref
            new_rows.append(updated)
        else:
            new_rows.append(r)
    data["rows"] = new_rows
    table["data"] = data


def patch_video_node_style_reference(
    project: CanvasProject,
    node_id: str,
    style_ref: dict,
    *,
    script_table_node_id: str | None = None,
    row_id: str | None = None,
) -> dict:
    canvas_data = load_canvas_data(project)
    node = find_node(canvas_data, node_id)
    if not node or node.get("type") != "video-gen":
        raise HTTPException(status_code=404, detail="视频生成节点不存在")
    data = _node_data(node)
    data["styleReference"] = style_ref
    node["data"] = data
    _sync_row_style_reference(
        canvas_data,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
        style_ref=style_ref,
    )
    save_canvas_data(project, canvas_data)
    return style_ref


def clear_video_node_style_reference(
    project: CanvasProject,
    node_id: str,
    *,
    script_table_node_id: str | None = None,
    row_id: str | None = None,
) -> None:
    canvas_data = load_canvas_data(project)
    node = find_node(canvas_data, node_id)
    if not node or node.get("type") != "video-gen":
        raise HTTPException(status_code=404, detail="视频生成节点不存在")
    data = _node_data(node)
    data.pop("styleReference", None)
    node["data"] = data
    _sync_row_style_reference(
        canvas_data,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
        style_ref=None,
    )
    save_canvas_data(project, canvas_data)
