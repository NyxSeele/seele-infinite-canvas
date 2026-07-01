"""LLM 语义大镜划分：细分镜行 → 大镜头 groups。"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.qwen import _call_llm, clean_json_response
from services.shot_grouping import _micro_duration, suggest_groups

logger = logging.getLogger(__name__)

MAX_MACRO_DURATION = 15.0
MAX_MICRO_SHOTS_FOR_LLM = 80
_DURATION_TOLERANCE = 0.5

_GROUP_SYSTEM = """你是分镜导演助手。用户从 Excel 导入细分镜表，每行是一个短镜头（常 2–5 秒）。
请按叙事、场次与可生成视频的节奏，将相邻细分镜合并为「大镜头」分组。

只输出 JSON，不要 markdown：
{
  "groups": [[0, 1, 2], [3, 4]],
  "summary": "一句话说明划分思路"
}

硬性规则：
1. groups 是二维数组，内层为 0-based 行索引，必须覆盖 0..n-1 全部索引，不丢不重
2. 每组必须是连续索引（如 [2,3,4]），保持表格原始顺序
3. 每组细分镜 duration 之和 ≤ 15 秒（允许单镜 2 秒独立成组）
4. 同一场次 segment、同一动作/对白优先合并；明显转场/切场处切开
5. 只输出分组，不修改镜号与文案"""


def _compact_micro_shots(
    micro_rows: list[dict[str, Any]],
    segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    seg_titles = {s.get("id"): s.get("title") for s in (segments or []) if s.get("id")}
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(micro_rows):
        seg_id = row.get("segmentId") or row.get("segment_id") or ""
        item: dict[str, Any] = {
            "index": idx,
            "shotNumber": row.get("shotNumber"),
            "duration": _micro_duration(row),
            "prompt": (row.get("prompt") or row.get("description") or "")[:200],
        }
        if seg_id:
            item["segmentId"] = seg_id
            if seg_titles.get(seg_id):
                item["segmentTitle"] = seg_titles[seg_id]
        for key in ("camera", "movement", "soundDesign"):
            val = row.get(key)
            if val and str(val).strip():
                item[key] = str(val).strip()[:80]
        out.append(item)
    return out


def validate_groups(
    groups: list[list[int]] | None,
    n: int,
    micro_rows: list[dict[str, Any]] | None = None,
) -> list[list[int]] | None:
    """校验分组合法性；不通过返回 None。"""
    if not groups or n <= 0:
        return None

    flat: list[int] = []
    for g in groups:
        if not g or not isinstance(g, list):
            return None
        for i in g:
            if not isinstance(i, int) or i < 0 or i >= n:
                return None
            flat.append(i)

    if len(flat) != n or sorted(flat) != list(range(n)):
        return None

    rows = micro_rows or []
    for g in groups:
        if g != sorted(g):
            return None
        if g[0] > 0 and g[0] - 1 in flat:
            prev_group = None
            for gg in groups:
                if g[0] - 1 in gg:
                    prev_group = gg
                    break
            if prev_group and g[0] != prev_group[-1] + 1:
                return None

    expected = 0
    for g in groups:
        if g[0] != expected:
            return None
        expected = g[-1] + 1

    if rows:
        for g in groups:
            total = sum(_micro_duration(rows[i]) for i in g if 0 <= i < len(rows))
            if total > MAX_MACRO_DURATION + _DURATION_TOLERANCE:
                return None

    return [list(g) for g in groups]


async def suggest_groups_llm(
    micro_rows: list[dict[str, Any]],
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    LLM 语义划分；失败或校验不通过时回退规则 suggest_groups。
    返回 { groups, source, summary }。
    """
    n = len(micro_rows)
    if n == 0:
        return {"groups": [], "source": "rule", "summary": ""}

    if n > MAX_MICRO_SHOTS_FOR_LLM:
        logger.info("shot_grouping_llm: %d rows exceeds %d, rule fallback", n, MAX_MICRO_SHOTS_FOR_LLM)
        groups = suggest_groups(micro_rows, target_duration=10.0)
        return {
            "groups": groups,
            "source": "rule_fallback",
            "summary": f"镜头数超过 {MAX_MICRO_SHOTS_FOR_LLM}，已使用规则划分",
        }

    payload = {
        "micro_shot_count": n,
        "max_macro_duration_sec": MAX_MACRO_DURATION,
        "micro_shots": _compact_micro_shots(micro_rows, segments),
    }

    try:
        raw, _ = await _call_llm(
            _GROUP_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
            max_tokens=4000,
        )
        text = clean_json_response(raw)
        data = json.loads(text)
    except Exception as exc:
        logger.warning("shot_grouping_llm LLM failed: %s", exc)
        groups = suggest_groups(micro_rows, target_duration=10.0)
        return {
            "groups": groups,
            "source": "rule_fallback",
            "summary": "",
            "error": str(exc),
        }

    raw_groups = data.get("groups")
    summary = str(data.get("summary") or "").strip()
    validated = validate_groups(raw_groups, n, micro_rows)

    if validated:
        return {"groups": validated, "source": "llm", "summary": summary}

    logger.warning("shot_grouping_llm invalid groups from LLM: %s", raw_groups)
    groups = suggest_groups(micro_rows, target_duration=10.0)
    return {
        "groups": groups,
        "source": "rule_fallback",
        "summary": summary or "LLM 分组无效，已使用规则划分",
    }
