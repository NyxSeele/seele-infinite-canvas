import json

from services.prompt_builder import LTX2_DEFAULT_NEGATIVE
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

QWEN_IMAGE_SYSTEM_PROMPT = """你是专业AI图像生成提示词专家，专注于 Qwen-Image 模型。
把用户描述转成高质量英文摄影提示词。
必须包含：构图描述、光线类型、拍摄风格
如果包含人物：加入 natural pose, proper anatomy, realistic proportions
若用户提供了参考图或描述中暗示参考构图：强调保留参考图的构图和主体，在此基础上提升画质和光线，不要随意改变主体特征
只返回JSON：{"positive": "英文正向提示词", "negative": ""}"""

QWEN_IMAGE_EDIT_SYSTEM_PROMPT = """你是专业AI图像编辑提示词专家，专注于 Qwen-Image 编辑模型。
用户提供参考图和编辑指令，你的任务是把编辑指令转成英文提示词，同时确保参考图的主体（人物、物体、核心构图）被保留。
规则：
- 必须以 "keep the subject unchanged" 或类似约束开头
- 只描述需要改变的部分，不要重新描述整张图
- 禁止生成纯场景描述（如"a rainy street"），必须保留主体存在感
- 若是服装/外观编辑：描述新外观，加 "same person, same pose, same background"
- 若是氛围/光线/背景编辑：加 "subject remains in frame, same composition"
只返回JSON：{"positive": "英文编辑提示词", "negative": ""}"""


WAN_VIDEO_SYSTEM_PROMPT = """你是专业 AI 视频提示词专家，专注于 Wan 2.2。
把用户中文描述转成适合 Wan 的英文提示词。
规则：
1. 运镜/镜头运动放在句首；用句号分句，不要并成超长单句
2. 禁止堆砌 cinematic、smooth motion、masterpiece、best quality、8k 等空泛词
3. 保留具体主体、动作与场景；人物加入 anatomically correct body, natural hand gestures, proper finger count
4. 负向聚焦：肢体崩坏、抖动、静帧、水印
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

LTX2_VIDEO_SYSTEM_PROMPT = """你是专业 AI 视频提示词专家，专注于 LTX-2 文生/图生视频。
用户输入可能是长剧本、分镜、技术规格书或混杂元说明；你必须压缩成**单镜头可执行**的英文提示词。

强制规则：
1. 只保留「可见画面」：人物外貌/服装、单一主动作、场景空间、镜头与光线；删除元评论、测试目标、产品反馈、给开发团队的说明、禁止清单的文学修辞
2. 人物辨识优先：姓名/年龄/发型/体型/服装/表情必须保留为具体英文描述；禁止泛化为 generic Asian man
3. 物理与连续性：动作符合生物力学；道具不得凭空出现/消失；禁止穿模、肢体扭曲、夸张特效灰尘爆炸（除非用户明确要求）
4. 场景锁定：若用户要求传统武馆/岭南庭院等，禁止 neon signs、LED、现代城市、科幻发光体
5. 声音：若提到音频，每个镜头最多 1–2 个核心声源，禁止嘈杂多层音轨描述
6. 时长叙事：只描述当前可在给定秒数内完成的一个连续动作，不要写多幕剧情跳跃
7. 正向宜短：英文约 60–160 词；负向列出易翻车项

只返回JSON：
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


async def translate_to_english(
    user_input: str,
    *,
    mode: str = "image",
    max_tokens: int | None = None,
) -> dict:
    """纯文本英译（不依赖 JSON），仅走 Admin 已注册文本模型。"""
    text = (user_input or "").strip()
    if not text:
        return {"positive": user_input, "error": "empty input"}

    system_prompt = VIDEO_TRANSLATE_PLAIN_SYSTEM if mode == "video" else TRANSLATE_PLAIN_SYSTEM
    # 默认拉满实用输出上限（API 无真正无限）；短文会提前 stop，不会白烧满额
    tokens = int(max_tokens) if max_tokens is not None else 16384
    # 单模型超时随输出上限放宽，便于故障转移到下一候选
    per_model_timeout = min(90.0, max(25.0, 15.0 + tokens / 400.0))

    try:
        translated, _, _model_id = await invoke_configured_text_llm(
            system_prompt,
            text,
            max_tokens=tokens,
            temperature=0.3,
            per_model_timeout=per_model_timeout,
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


_QWEN_IMAGE_EDIT_HINT_MARKERS = ("edit", "restore", "material")


def _is_ltx2_model_hint(model_hint: str | None) -> bool:
    hint = (model_hint or "").strip().lower()
    return hint.startswith("ltx2") or hint in {"ltx-2", "ltx2"}


def _is_wan_model_hint(model_hint: str | None) -> bool:
    hint = (model_hint or "").strip().lower()
    return hint.startswith("wan")


def _resolve_optimize_system_prompt(mode: str, model_hint: str | None = None) -> str:
    hint = (model_hint or "").strip().lower()
    if mode == "image" and hint.startswith("flux"):
        return FLUX_SYSTEM_PROMPT
    if mode == "image" and hint.startswith("qwen-image"):
        if any(marker in hint for marker in _QWEN_IMAGE_EDIT_HINT_MARKERS):
            return QWEN_IMAGE_EDIT_SYSTEM_PROMPT
        return QWEN_IMAGE_SYSTEM_PROMPT
    if mode == "video" and _is_ltx2_model_hint(hint):
        return LTX2_VIDEO_SYSTEM_PROMPT
    if mode == "video" and _is_wan_model_hint(hint):
        return WAN_VIDEO_SYSTEM_PROMPT
    return IMAGE_SYSTEM_PROMPT if mode == "image" else VIDEO_SYSTEM_PROMPT


def _optimize_max_tokens(text: str, *, model_hint: str | None = None) -> int:
    """长剧本 / LTX2 压缩：输出上限与翻译对齐（API 实用天花板）。"""
    _ = text, model_hint
    return 16384


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
    default_negative = (
        LTX2_DEFAULT_NEGATIVE
        if mode == "video" and _is_ltx2_model_hint(model_hint)
        else "worst quality, low quality, blurry"
    )

    try:
        result_text, _, _model_id = await invoke_configured_text_llm(
            system_prompt,
            text,
            max_tokens=_optimize_max_tokens(text, model_hint=model_hint),
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
            "negative": negative or default_negative,
        }

    except json.JSONDecodeError:
        return {
            "positive": text,
            "negative": default_negative,
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
            "negative": default_negative,
            "error": error_msg,
        }
