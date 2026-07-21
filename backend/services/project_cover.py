"""从画布 JSON 提取最新封面媒体。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

_IMAGE_KEYS = ("generatedImage", "uploadedImage", "imageUrl")
_VIDEO_KEYS = ("videoUrl",)
_VIDEO_RE = re.compile(r"\.(mp4|webm|mov)(\?|$)", re.IGNORECASE)


def _media_type_from_url(url: str) -> str:
    return "video" if _VIDEO_RE.search(url) else "image"


def _parse_ts(val) -> float | None:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str) and val.strip():
        raw = val.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            pass
    return None


def extract_cover_from_data(data_str: str) -> tuple[str | None, str | None]:
    """返回 (url, media_type)，按节点内最新媒体排序。"""
    best: tuple[float, str, str] | None = None
    try:
        data = json.loads(data_str or "{}")
        nodes = data.get("nodes") or []
        for idx, node in enumerate(nodes):
            payload = node.get("data") or {}
            base_ts = (
                _parse_ts(payload.get("updatedAt"))
                or _parse_ts(payload.get("createdAt"))
                or float(idx)
            )
            candidates: list[tuple[float, str, str]] = []

            for key in _VIDEO_KEYS:
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    candidates.append((base_ts, val.strip(), "video"))

            for key in _IMAGE_KEYS:
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    candidates.append((base_ts, val.strip(), "image"))

            results = payload.get("results")
            if isinstance(results, list):
                for ri, item in enumerate(results):
                    if isinstance(item, str) and item.strip():
                        url = item.strip()
                        candidates.append(
                            (base_ts + ri * 0.001, url, _media_type_from_url(url))
                        )

            for sort_key, url, media_type in candidates:
                if best is None or sort_key >= best[0]:
                    best = (sort_key, url, media_type)
    except Exception:
        return None, None

    if best:
        return best[1], best[2]
    return None, None


def apply_cover_from_data(row) -> None:
    url, media_type = extract_cover_from_data(row.data)
    row.cover_url = url
    row.cover_media_type = media_type
