"""根据画布 @ 引用解析生成上下文（参考图、文本补充）。"""

from __future__ import annotations

import logging
import re
from typing import Any

# 画布 @ 提及标记（与前端 promptMentions.js 序列化格式一致）
MENTION_TOKEN_RE = re.compile(r"@([^\s@]+)\s*")

from sqlalchemy.orm import Session

from models import User
from models.user_asset import UserAsset
from schemas.tasks import CanvasMention

logger = logging.getLogger(__name__)


def _load_canvas_nodes(
    db: Session,
    user: User,
    project_id: str | None = None,
    team_id: str | None = None,
) -> list[dict[str, Any]]:
    """从 CanvasProject 加载节点（不再使用已废弃的 CanvasState）。"""
    try:
        from services.canvas_access import get_accessible_project
        from services.canvas_style_ref import load_canvas_data

        project = None
        if project_id:
            try:
                project = get_accessible_project(db, user, project_id)
            except Exception:
                logger.warning(
                    "mention_context: project %s not accessible for user %s",
                    project_id,
                    getattr(user, "id", None),
                )
                return []
            if project is None:
                return []
        else:
            # 未传 project_id：fail-closed，禁止回退到用户其它项目
            return []
        if not project:
            return []
        data = load_canvas_data(project)
        nodes = data.get("nodes")
        return nodes if isinstance(nodes, list) else []
    except Exception:
        logger.warning(
            "mention_context: failed to load canvas project for user %s",
            getattr(user, "id", None),
            exc_info=True,
        )
        return []


def _node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for node in nodes:
        if node.get("id") == node_id:
            return node
    return None


def _image_url_from_node(node: dict[str, Any], image_index: int | None) -> str | None:
    data = node.get("data") or {}
    results = data.get("results")
    if isinstance(results, list) and results:
        idx = image_index if image_index is not None else 0
        if 0 <= idx < len(results) and results[idx]:
            return str(results[idx])
    for key in ("uploadedImage", "imageUrl", "resultUrl"):
        val = data.get(key)
        if val:
            return str(val)
    return None


def _text_from_node(node: dict[str, Any]) -> str | None:
    data = node.get("data") or {}
    text = data.get("prompt") or data.get("content")
    if text is None:
        return None
    stripped = str(text).strip()
    return stripped or None


def _video_url_from_node(node: dict[str, Any]) -> str | None:
    data = node.get("data") or {}
    url = data.get("videoUrl")
    return str(url).strip() if url else None


def resolve_mentions(
    db: Session,
    user_id: int | User,
    mentions: list[CanvasMention] | None,
    *,
    project_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """解析 mentions，返回 reference_image_urls 与 context_parts。

    user_id 可为 User 实例或 int（兼容旧调用）；推荐传 User。
    """
    result: dict[str, Any] = {
        "reference_image_urls": [],
        "context_parts": [],
    }
    if not mentions:
        return result

    if isinstance(user_id, User):
        user = user_id
        uid = user.id
    else:
        uid = int(user_id)
        user = db.get(User, uid)
        if not user:
            return result

    nodes = _load_canvas_nodes(db, user, project_id=project_id, team_id=team_id)
    seen_urls: set[str] = set()

    for mention in mentions:
        node_type = (mention.type or "").lower()
        label = mention.name or mention.id

        if node_type == "asset":
            row = (
                db.query(UserAsset)
                .filter(UserAsset.id == mention.id, UserAsset.user_id == uid)
                .first()
            )
            if row and row.image_url and row.image_url not in seen_urls:
                seen_urls.add(row.image_url)
                result["reference_image_urls"].append(row.image_url)
                result["context_parts"].append(
                    f"[资产·{row.name}]: 使用全局资产库参考图，保持与设定一致"
                )
            continue

        node = _node_by_id(nodes, mention.id)
        if not node:
            logger.warning(
                "mention_context: node not found id=%s user=%s project_id=%s",
                mention.id,
                uid,
                project_id,
            )
            continue

        node_type = (mention.type or node.get("type") or "").lower()
        label = mention.name or (node.get("data") or {}).get("label") or mention.id

        if node_type in ("image", "image-gen"):
            url = _image_url_from_node(node, mention.image_index)
            if url and url not in seen_urls:
                seen_urls.add(url)
                result["reference_image_urls"].append(url)
            continue

        if node_type in ("video", "video-gen"):
            url = _video_url_from_node(node)
            if url:
                result["context_parts"].append(
                    f"[视频·{label}]: 参考该视频的镜头节奏与氛围"
                )
            continue

        if node_type in ("text", "text-note", "text-response", "outline"):
            text = _text_from_node(node)
            if text:
                result["context_parts"].append(f"[{label}]: {text}")
            continue

        # 其他节点：尽量提取文本上下文
        text = _text_from_node(node)
        if text:
            result["context_parts"].append(f"[{label}]: {text[:500]}")

    return result


def strip_mention_tokens(prompt: str) -> str:
    """移除 prompt 中的 @xxx 提及标记；参考图由 mentions / reference_image 单独传递。"""
    if not prompt:
        return prompt
    cleaned = MENTION_TOKEN_RE.sub("", prompt)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def enrich_prompt(prompt: str, context_parts: list[str] | None) -> str:
    if not context_parts:
        return prompt
    block = "\n".join(context_parts)
    return f"{prompt.strip()}\n\n--- 引用上下文 ---\n{block}"
