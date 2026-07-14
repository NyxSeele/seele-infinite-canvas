import json

from services.qwen import CONFIGURED_LLM_ERROR, invoke_configured_text_llm

IMAGE_SYSTEM_PROMPT = """你是一个专业的提示词翻译助手。
规则：
1. 只做中译英，不扩写、不添加词汇
2. 保持原有词语顺序
3. 不添加任何风格描述词（如 masterpiece、cinematic、best quality 等）
4. 输出只有 JSON，无解释

只返回JSON，不要其他内容：
{"positive": "英文正向提示词", "negative": ""}"""

FLUX_SYSTEM_PROMPT = """你是专业AI图像生成提示词专家，专注于 Flux 模型。
把用户描述转成高质量英文摄影提示词。
必须包含：构图描述、光线类型、拍摄风格
如果包含人物：加入 natural pose, proper anatomy, realistic proportions
只返回JSON：{"positive": "英文正向提示词", "negative": ""}"""

HUNYUAN_VIDEO_SYSTEM_PROMPT = """你是专业AI视频生成提示词专家，专注于 HunyuanVideo 模型。
把用户描述转成适合电影级视频生成的英文提示词。
必须包含：镜头类型、运动描述、光线、画面质量
如果包含人物：加入 anatomically correct body, natural gestures, proper finger count
只返回JSON：{"positive": "英文正向提示词", "negative": "英文负向提示词"}"""

VIDEO_SYSTEM_PROMPT = """你是专业AI视频生成提示词专家。
把用户的中文描述转成适合视频生成的英文提示词。
添加动态词：smooth motion, cinematic, fluid movement
添加画质词：high quality, detailed
如果画面包含人物，必须在 prompt 中加入：
anatomically correct body, natural hand gestures,
proper finger count, realistic human anatomy
只返回JSON，不要其他内容：
{"positive": "英文正向提示词", "negative": "英文负向提示词"}"""

VIDEO_TRANSLATE_PLAIN_SYSTEM = (
    "You are a professional video prompt translation assistant. "
    "Rules: translate Chinese to English only; do not add words; "
    "keep camera/motion description at the beginning of the sentence; "
    "use period to separate clauses; do not merge into one long sentence; "
    "do not add smooth motion, cinematic, or quality tags; "
    "character names, hairstyle, and clothing descriptions must be fully "
    "preserved in the translation, regardless of whether the scene shows "
    "the front, side, or back view. "
    "Output only the English prompt text. No quotes, no JSON, no explanation."
)

TRANSLATE_PLAIN_SYSTEM = (
    "You are a professional prompt translation assistant. "
    "Rules: translate Chinese to English only; do not add words; "
    "preserve original word order; do not add style tags. "
    "Output only the English prompt text. No quotes, no JSON, no explanation."
)


async def translate_to_english(user_input: str, *, mode: str = "image") -> dict:
    """纯文本英译（不依赖 JSON），仅走 Admin 已注册文本模型。"""
    text = (user_input or "").strip()
    if not text:
        return {"positive": user_input, "error": "empty input"}

    system_prompt = VIDEO_TRANSLATE_PLAIN_SYSTEM if mode == "video" else TRANSLATE_PLAIN_SYSTEM

    try:
        translated, _, _model_id = await invoke_configured_text_llm(
            system_prompt,
            text,
            max_tokens=500,
            temperature=0.3,
        )
        translated = translated.strip("\"'")
        if not translated:
            raise ValueError("empty translation")
        return {"positive": translated, "error": None}
    except Exception as exc:
        return {
            "positive": text,
            "error": f"翻译失败: {str(exc)[:120]}",
        }


def _resolve_optimize_system_prompt(mode: str, model_hint: str | None = None) -> str:
    hint = (model_hint or "").strip().lower()
    if mode == "image" and hint.startswith("flux"):
        return FLUX_SYSTEM_PROMPT
    if mode == "video" and hint == "hunyuan":
        return HUNYUAN_VIDEO_SYSTEM_PROMPT
    return IMAGE_SYSTEM_PROMPT if mode == "image" else VIDEO_SYSTEM_PROMPT


async def optimize_prompt(
    user_input: str,
    mode: str = "image",
    *,
    model_hint: str | None = None,
) -> dict:
    """提示词优化，仅走 Admin 已注册文本模型（llm_router 分流）。"""
    text = (user_input or "").strip()
    if not text:
        return {
            "positive": user_input,
            "negative": "worst quality, low quality, blurry",
        }

    system_prompt = _resolve_optimize_system_prompt(mode, model_hint)

    try:
        result_text, _, _model_id = await invoke_configured_text_llm(
            system_prompt,
            text,
            max_tokens=500,
            temperature=0.7,
        )
        result_text = result_text.replace("```json", "").replace("```", "").strip()

        result = json.loads(result_text)
        positive = (result.get("positive") or "").strip()
        negative = (result.get("negative") or "").strip()
        if not positive:
            raise ValueError("empty positive")
        return {
            "positive": positive,
            "negative": negative or "worst quality, low quality, blurry",
        }

    except json.JSONDecodeError:
        return {
            "positive": text,
            "negative": "worst quality, low quality, blurry",
            "error": "解析失败，已使用原始描述",
        }
    except Exception as e:
        err = str(e)
        if CONFIGURED_LLM_ERROR in err:
            error_msg = CONFIGURED_LLM_ERROR
        else:
            error_msg = f"提示词优化暂时不可用: {err[:100]}"
        return {
            "positive": user_input,
            "negative": "worst quality, low quality, blurry",
            "error": error_msg,
        }
