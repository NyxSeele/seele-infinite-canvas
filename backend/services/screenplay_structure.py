"""将 LLM 剧本/分镜文稿结构化为大纲 scenes（供大纲卡片展示）"""

from __future__ import annotations

import json
import logging
import re
import time

from core.logging_setup import studio_print
from services.qwen import _call_llm, _validate_scenes, clean_json_response

logger = logging.getLogger(__name__)

STRUCTURE_FROM_TEXT_SYSTEM = """你是影视剧本编辑。把用户给出的剧本或分镜文稿整理为结构化大纲 JSON。
严格只输出 JSON，不要 markdown 代码块。

格式：
{
  "title": "片名",
  "scenes": [
    {
      "id": "scene-1",
      "title": "段落小标题",
      "time_start": "00:00",
      "time_end": "00:15",
      "characters": "本段人物",
      "mood": "情绪氛围",
      "content": "200-400字叙事：动作/心理/环境，不要用 markdown 表格",
      "camera": "景别，无则空字符串",
      "movement": "运镜",
      "lighting": "光影",
      "composition": "构图",
      "color_grade": "色调",
      "lens": "镜头",
      "performance": "表演",
      "sound_design": "声音/配乐"
    }
  ]
}

规则：
1. 从原文识别时间轴写入 time_start/time_end（如 00:52-01:00）；无则留空
2. 导演字段仅从原文提取，没有则 ""，不要编造
3. scenes 数量 3-12，按叙事段落划分，不要把每个镜头都拆成独立 scene
4. content 为散文叙事，禁止 | 表格
5. 保留原文信息，不要另起炉灶重写故事"""


SCREENPLAY_CHAT_WRAP = """【创作模式：影视剧本 / 分镜前置稿】
你正在为后续「大纲 → 分镜提示词 → 分镜表出图 → 视频」链路写稿。必须遵守：

1. 按时间线划分段落，每段标题行标注时间范围，例如：【00:00-00:15】竹林醒来
2. 每段须包含：人物、氛围、剧情（动作/心理/环境）
3. 每段末尾用独立行写出导演信息（至少写清）：景别：… / 运镜：… / 光影：…
4. 若用户指定成片时长（如 1 分钟），叙事密度须匹配，不要写成 2 分钟以上体量
5. 用清晰中文小标题分段，不要输出 JSON，不要 markdown 表格

用户需求：
"""


def wrap_screenplay_user_prompt(user_prompt: str) -> str:
    return SCREENPLAY_CHAT_WRAP + (user_prompt or "").strip()


def _parse_structure_json(raw: str) -> dict:
    text = clean_json_response(raw)
    if not text:
        raise ValueError("模型返回为空")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("根节点必须是对象")
    title = (data.get("title") or "剧本大纲").strip()
    scenes_raw = data.get("scenes") or []
    scenes = []
    for i, sc in enumerate(scenes_raw):
        if not isinstance(sc, dict):
            continue
        scene = {
            "id": (sc.get("id") or f"scene-{i + 1}").strip(),
            "title": (sc.get("title") or f"段落{i + 1}").strip(),
            "characters": (sc.get("characters") or "").strip(),
            "mood": (sc.get("mood") or "").strip(),
            "content": (sc.get("content") or "").strip(),
            "time_start": (sc.get("time_start") or "").strip(),
            "time_end": (sc.get("time_end") or "").strip(),
            "camera": (sc.get("camera") or "").strip(),
            "movement": (sc.get("movement") or "").strip(),
            "lighting": (sc.get("lighting") or "").strip(),
            "composition": (sc.get("composition") or "").strip(),
            "color_grade": (sc.get("color_grade") or "").strip(),
            "lens": (sc.get("lens") or "").strip(),
            "performance": (sc.get("performance") or "").strip(),
            "sound_design": (sc.get("sound_design") or "").strip(),
        }
        if not scene["content"]:
            continue
        scenes.append(scene)
    if len(scenes) < 1:
        raise ValueError("未能从文稿中解析出有效场景")
    if len(scenes) < 3:
        logger.warning("structure_from_text: only %s scenes", len(scenes))
    return {"title": title, "scenes": scenes}


async def structure_screenplay_from_text(
    text: str,
    *,
    target_duration_sec: int | None = None,
    source_idea: str = "",
) -> dict:
    body = (text or "").strip()
    if not body:
        raise ValueError("文稿为空")

    user_parts = []
    if target_duration_sec:
        user_parts.append(f"【目标成片约 {int(target_duration_sec)} 秒】")
    if source_idea and source_idea.strip() != body[:200]:
        user_parts.append(f"【用户最初需求】{source_idea.strip()}")
    user_parts.append("【待整理文稿】\n" + body)
    user_prompt = "\n\n".join(user_parts)

    studio_print("trace", f"A3 STRUCTURE_INPUT input_len={len(user_prompt)}")
    t0 = time.perf_counter()
    raw, finish_reason = await _call_llm(
        STRUCTURE_FROM_TEXT_SYSTEM, user_prompt, max_tokens=8000
    )
    if not raw:
        raise ValueError("模型未返回内容")
    try:
        parsed = _parse_structure_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("structure JSON failed, retry validate path: %s", exc)
        raise ValueError(f"结构化失败: {exc}") from exc

    scenes = parsed["scenes"]
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    studio_print(
        "trace",
        f"A3 STRUCTURE_OUTPUT scenes_count={len(scenes)} elapsed_ms={elapsed_ms}",
    )
    titles = " | ".join(
        (sc.get("title") or "").strip() for sc in scenes if (sc.get("title") or "").strip()
    )
    if len(titles) > 200:
        titles = titles[:197] + "..."
    if titles:
        studio_print("trace", f"A3 STRUCTURE_SCENE_TITLES {titles}")

    truncated = finish_reason == "length"
    return {
        "title": parsed["title"],
        "scenes": parsed["scenes"],
        "versions": [{"title": parsed["title"], "scenes": parsed["scenes"]}],
        "truncated": truncated,
        "target_video_duration_sec": target_duration_sec,
    }
