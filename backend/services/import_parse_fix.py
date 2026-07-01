"""导入解析 LLM 校正（仅自检失败时兜底）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from services.qwen import _call_llm, clean_json_response

logger = logging.getLogger(__name__)

_FIX_SYSTEM = """你是分镜表数据校正助手。用户 Excel 规则解析后自检失败，请根据 issues 修正 rows JSON。
只输出 JSON，不要 markdown：
{
  "fixed": true,
  "rows": [ { "shotNumber": 1, "duration": 2, "prompt": "...", ... } ],
  "fix_summary": "一句话说明修正了什么"
}

规则：
- 保留原有 prompt/导演字段内容，只修正镜号连续性、明显错位
- 若无法可靠修正，fixed=false，reason 说明原因
- rows 数量应与输入相近，不要凭空增删镜头"""


def _rule_fix_rows(rows: list[dict[str, Any]], issues: list[dict]) -> tuple[list[dict], str] | None:
    codes = {i.get("code") for i in issues}
    if not rows:
        return None
    fixed = [dict(r) for r in rows]
    changed = 0

    if "gap_shot_numbers" in codes or "duplicate_shot_numbers" in codes:
        for i, row in enumerate(fixed):
            expected = i + 1
            if row.get("shotNumber") != expected:
                row["shotNumber"] = expected
                changed += 1
        if changed:
            return fixed, f"规则修正镜号为 1..{len(fixed)}（{changed} 处）"

    return None


async def try_fix_parsed_rows(
    parsed: dict[str, Any],
    *,
    use_llm: bool = True,
) -> dict[str, Any]:
    self_check = parsed.get("self_check") or {}
    if self_check.get("ok"):
        return {"fixed": False, "reason": "self_check_passed", "rows": parsed.get("rows") or []}

    rows = parsed.get("rows") or []
    issues = self_check.get("issues") or []

    rule_result = _rule_fix_rows(rows, issues)
    if rule_result:
        new_rows, summary = rule_result
        from services.excel_shot_parser import attach_self_check

        trial = {**parsed, "rows": new_rows}
        attach_self_check(trial)
        if trial.get("self_check", {}).get("ok"):
            return {
                "fixed": True,
                "source": "rule",
                "rows": new_rows,
                "fix_summary": summary,
                "self_check": trial["self_check"],
            }

    if not use_llm or len(rows) == 0:
        return {"fixed": False, "reason": "rule_fix_insufficient", "rows": rows}

    sample = rows[:40]
    user_payload = {
        "sheet_name": parsed.get("sheet_name"),
        "issues": issues,
        "rows_sample": sample,
        "row_count": len(rows),
    }
    try:
        raw, _ = await _call_llm(
            _FIX_SYSTEM,
            json.dumps(user_payload, ensure_ascii=False),
            max_tokens=4000,
        )
        text = clean_json_response(raw)
        data = json.loads(text)
    except Exception as exc:
        logger.warning("import_parse_fix LLM failed: %s", exc)
        return {"fixed": False, "reason": str(exc), "rows": rows}

    if not data.get("fixed"):
        return {
            "fixed": False,
            "reason": data.get("reason") or "llm_declined",
            "rows": rows,
        }

    new_rows = data.get("rows")
    if not isinstance(new_rows, list) or len(new_rows) < 1:
        return {"fixed": False, "reason": "invalid_llm_rows", "rows": rows}

    from services.excel_shot_parser import attach_self_check

    trial = {**parsed, "rows": new_rows}
    attach_self_check(trial)
    return {
        "fixed": True,
        "source": "llm",
        "rows": new_rows,
        "fix_summary": data.get("fix_summary") or "LLM 已校正",
        "self_check": trial.get("self_check"),
    }
