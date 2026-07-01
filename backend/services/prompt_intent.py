"""识别用户粘贴/输入内容的创作意图，供生成前二次确认。"""

from __future__ import annotations

import json
import logging
import re

from services.qwen import _call_llm, clean_json_response

logger = logging.getLogger(__name__)

INTENT_LABELS = {
    "screenplay": "完整剧本 / 分镜文稿",
    "shot_prompt": "单镜头画面描述",
    "image_prompt": "图像生成提示词",
    "video_prompt": "视频生成提示词",
    "chat": "普通对话 / 说明文字",
    "unknown": "未明确分类",
}

CLASSIFY_SYSTEM = """你是创作助手。分析用户输入，判断其创作意图，并提炼出最适合交给下游模型的「生成用提示词」。

只输出 JSON，不要 markdown：
{
  "intent": "screenplay|shot_prompt|image_prompt|video_prompt|chat",
  "confidence": 0.0-1.0,
  "summary": "一句话说明用户想做什么",
  "generation_prompt": "若用于单张图/单条视频/单镜出图，写一条精炼的中文提示词；若是完整剧本则留空字符串",
  "suggested_text_mode": "screenplay|chat|null",
  "warnings": ["可选警告，如与当前卡片类型不符"]
}

规则：
- 多场景、对白、时间轴、【00:00】、分场、人物列表 → screenplay，suggested_text_mode=screenplay
- 单画面、景别运镜、一句可出图描述 → shot_prompt 或 image_prompt
- 当前上下文为 image 时，优先 image_prompt；video 时优先 video_prompt
- generation_prompt 只保留视觉可执行信息，去掉「请帮我」「写一段」等元指令
- 超过 800 字且像剧本 → screenplay，confidence 应 >= 0.85
- 仅有一两句对白、无「第X场」/时间轴/分场标题的长段叙述 → 优先 chat，confidence 约 0.55~0.65，不要仅凭字数判 screenplay

边界示例（仅作判断锚点，勿照抄输出）：
示例 A — 弱剧本信号（约 400 字，重复对白，无场次标记）→ intent=chat，confidence=0.6，suggested_text_mode=chat，generation_prompt 保留可出图的一句视觉描述
示例 B — 强剧本信号（含「第一场」「场景：」或【00:00】时间轴）→ intent=screenplay，confidence>=0.85，generation_prompt=""，suggested_text_mode=screenplay"""


def _rule_classify(text: str, context: str, current_text_mode: str | None) -> dict:
    t = (text or "").strip()
    low = t.lower()
    ctx = (context or "text").lower()

    screenplay_signals = [
        len(t) > 600,
        bool(re.search(r"第[一二三四五六七八九十\d]+[场幕镜]", t)),
        bool(re.search(r"【\s*\d{1,2}:\d{2}", t)),
        "分场" in t and "场景" in t,
        t.count("\n\n") >= 4 and len(t) > 400,
    ]
    if any(screenplay_signals):
        intent = "screenplay"
        return {
            "intent": intent,
            "intent_label": INTENT_LABELS[intent],
            "confidence": 0.82,
            "summary": "看起来像完整剧本或分场文稿，建议走「剧本模式 → 大纲 → 分镜表」",
            "generation_prompt": "",
            "suggested_text_mode": "screenplay",
            "warnings": _warnings_for_intent(intent, ctx, current_text_mode),
        }

    if len(t) < 80:
        intent = "video_prompt" if ctx == "video" else "image_prompt"
        if ctx == "text":
            intent = "chat" if current_text_mode != "screenplay" else "screenplay"
        return {
            "intent": intent,
            "intent_label": INTENT_LABELS.get(intent, intent),
            "confidence": 0.7,
            "summary": "短文本，按当前卡片类型直接生成",
            "generation_prompt": t,
            "suggested_text_mode": None,
            "warnings": [],
        }

    intent = "shot_prompt" if ctx == "text" else ("video_prompt" if ctx == "video" else "image_prompt")
    return {
        "intent": intent,
        "intent_label": INTENT_LABELS.get(intent, intent),
        "confidence": 0.55,
        "summary": "内容较长，建议确认后再生成",
        "generation_prompt": t[:1200],
        "suggested_text_mode": "screenplay" if len(t) > 500 else None,
        "warnings": _warnings_for_intent(intent, ctx, current_text_mode),
    }


def _warnings_for_intent(intent: str, context: str, current_text_mode: str | None) -> list[str]:
    warnings: list[str] = []
    if context == "image" and intent == "screenplay":
        warnings.append("当前选中的是图像生成卡，但内容更像完整剧本，建议改用文本卡「剧本模式」。")
    if context == "video" and intent == "screenplay":
        warnings.append("当前选中的是视频生成卡，但内容更像完整剧本，建议先整理到大纲/分镜表。")
    if context == "text" and intent in ("image_prompt", "video_prompt", "shot_prompt"):
        if current_text_mode == "screenplay" and intent != "screenplay":
            warnings.append("文本卡为剧本模式，但内容更像单条出图描述，确认是否只需生成这一条？")
    if context == "text" and intent == "screenplay" and current_text_mode != "screenplay":
        warnings.append("检测到完整剧本文风，建议切换到「剧本」模式后再生成。")
    return warnings


async def classify_user_intent(
    text: str,
    *,
    context: str = "text",
    current_text_mode: str | None = None,
) -> dict:
    body = (text or "").strip()
    if not body:
        raise ValueError("内容为空")

    ctx = (context or "text").lower()
    if ctx not in ("text", "image", "video"):
        ctx = "text"

    if len(body) < 50:
        return _rule_classify(body, ctx, current_text_mode)

    user_prompt = (
        f"【当前画布上下文】{ctx}\n"
        f"【文本卡模式】{current_text_mode or '未知'}\n\n"
        f"【用户输入】\n{body[:12000]}"
    )
    try:
        raw, _ = await _call_llm(CLASSIFY_SYSTEM, user_prompt, max_tokens=1500)
        parsed = json.loads(clean_json_response(raw))
        if not isinstance(parsed, dict):
            raise ValueError("invalid json")
        intent = (parsed.get("intent") or "unknown").strip()
        if intent not in INTENT_LABELS:
            intent = "unknown"
        gen = (parsed.get("generation_prompt") or "").strip()
        if intent == "screenplay":
            gen = ""
        elif not gen:
            gen = body[:1200]
        return {
            "intent": intent,
            "confidence": float(parsed.get("confidence") or 0.75),
            "summary": (parsed.get("summary") or "").strip() or INTENT_LABELS.get(intent, ""),
            "generation_prompt": gen,
            "suggested_text_mode": parsed.get("suggested_text_mode"),
            "warnings": list(parsed.get("warnings") or [])
            or _warnings_for_intent(intent, ctx, current_text_mode),
            "intent_label": INTENT_LABELS.get(intent, intent),
        }
    except Exception as exc:
        logger.warning("classify_user_intent LLM fallback: %s", exc)
        fallback = _rule_classify(body, ctx, current_text_mode)
        fallback["intent_label"] = INTENT_LABELS.get(fallback["intent"], fallback["intent"])
        return fallback
