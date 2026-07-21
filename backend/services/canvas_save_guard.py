"""画布保存防护：禁止空画布静默覆盖有内容的服务端数据。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 相对 backend 工作目录；生产部署 cwd 一般为 backend/
_BACKUP_DIR = Path(__file__).resolve().parent.parent / "data" / "canvas_backups"


def canvas_node_count(canvas_data: dict | None) -> int:
    if not isinstance(canvas_data, dict):
        return 0
    nodes = canvas_data.get("nodes")
    return len(nodes) if isinstance(nodes, list) else 0


def parse_canvas_node_count(data_str: str | None) -> int:
    try:
        data = json.loads(data_str or "{}")
    except Exception:
        return 0
    return canvas_node_count(data if isinstance(data, dict) else None)


def is_empty_overwrite(
    existing_data_str: str | None,
    incoming_canvas_data: dict | None,
) -> bool:
    """已有节点 > 0，且入参明确给出空 nodes 列表。"""
    if incoming_canvas_data is None:
        return False
    if "nodes" not in incoming_canvas_data:
        return False
    nodes = incoming_canvas_data.get("nodes")
    if not isinstance(nodes, list):
        return False
    if len(nodes) > 0:
        return False
    return parse_canvas_node_count(existing_data_str) > 0


def write_nonempty_backup(project_id: str, data_str: str | None) -> None:
    """每次成功写入非空画布前，落一份最近快照，便于事故恢复。"""
    if not project_id or parse_canvas_node_count(data_str) <= 0:
        return
    try:
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = _BACKUP_DIR / f"{project_id}.json"
        path.write_text(data_str or "{}", encoding="utf-8")
    except Exception as exc:
        logger.warning("canvas backup failed project=%s: %s", project_id, exc)


def read_backup(project_id: str) -> dict[str, Any] | None:
    path = _BACKUP_DIR / f"{project_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
