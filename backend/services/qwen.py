"""
剧本 / 分镜：调用千问或已注册文本模型。
"""

import json
import logging
import os
import re

import httpx
from openai import AsyncOpenAI

from core.config import settings
from db.base import SessionLocal
from models import RegisteredModel
from services.api_key_service import get_registered_model_api_key

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

logger = logging.getLogger(__name__)

SINGLE_VERSION_PREFIX = (
    "只输出一个版本。不要提供备选方案、不要说'以下是第一个版本'、"
    "不要输出任何编号版本。直接输出内容本身。\n\n"
)

OUTLINE_MULTI_VERSION_SUFFIX = """
当需要多个版本时，严格只输出 JSON，格式：
{
  "versions": [
    { "title": "版本标题", "scenes": [ ... 与单版本 scenes 相同结构 ... ] }
  ]
}
versions 数组长度必须等于要求的版本数，每个版本的 scenes 须满足 3-6 个场景的规则。"""

OUTLINE_SYSTEM_PROMPT = SINGLE_VERSION_PREFIX + """你是专业编剧。根据用户的故事素材，创作一份详细的剧情大纲。
只输出一个版本，不要备选方案。
严格只输出 JSON，不要 markdown 代码块，不要任何前缀文字。
JSON 格式：
{
"title": "故事标题（你来起，简短有力）",
"scenes": [
{
"id": "scene-1",
"title": "场景标题（如：雨夜路边的等待）",
"characters": "本场景出现的人物",
"mood": "情绪氛围关键词，逗号分隔",
"content": "详细剧情描写，200-400字，语言生动，写人物的动作/心理/环境细节"
}
]
}
要求：

场景数量 3-6 个
每个场景 content 为 200-400 字的叙事散文（人物动作/心理/环境）
禁止在 content 里写 markdown 表格、禁止 | 分镜表、禁止镜头号/秒数列表；分镜表在后续步骤生成
只输出 JSON，其他什么都不要输出"""

SHOTS_SYSTEM_PROMPT = SINGLE_VERSION_PREFIX + """你是专业导演。根据用户提供的剧本，将故事拆分为若干片段（segment），每个片段再细分为多个单个镜头（shot）。

每个镜头的导演级提示词必须包含：景别、运镜方式、光影效果、人物动作/表情、环境氛围。
提示词用流畅的中文描述句写成，不是关键词堆砌，用户要能看懂。

严格只输出一个 JSON 对象，禁止 markdown 代码块（禁止 ```），禁止任何前缀或后缀说明文字，只输出裸 JSON。

JSON 格式必须完全符合：
{
  "segments": [
    {
      "id": "seg-1",
      "title": "片段标题",
      "duration": 30,
      "description": "这段剧情的简述",
      "shots": [
        {
          "id": "shot-1-1",
          "duration": 8,
          "prompt": "导演级提示词，连贯中文描述句",
          "camera": "全景 / 中景 / 特写等",
          "movement": "固定 / 推进 / 拉远 / 横摇等",
          "lighting": "光影描述"
        }
      ]
    }
  ]
}

规则：
- 每个 segment 包含 1 个或多个 shot
- 单个 shot 的 duration 在 4-15 秒之间（整数，不得小于 4）
- 同一 segment 内所有 shot 的 duration 之和必须等于该 segment 的 duration
- id 字段使用 seg-N、shot-N-M 格式
- 全中文（id 除外）

若用户给出 target_video_duration_sec（整片目标秒数）：
- 所有 segment 内 shot 的 duration 之和必须等于该目标（误差不超过 2 秒）
- 单镜 duration 仍须在 4-15 秒；镜头总数建议约 target÷8 镜，避免切得过碎
- 优先保证总时长达标，再保证叙事完整"""


def _extract_balanced_json(text: str, start: int, open_ch: str, close_ch: str) -> str:
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def clean_json_response(text: str) -> str:
    """去掉 markdown 代码块包裹与前缀说明，供 json.loads 前清洗。"""
    text = (text or "").strip()
    if not text:
        return text

    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if blocks:
        text = blocks[-1].strip()

    if text and text[0] not in "{[":
        obj_start = text.find("{")
        arr_start = text.find("[")
        starts = [i for i in (obj_start, arr_start) if i >= 0]
        if starts:
            start = min(starts)
            opener, closer = ("{", "}") if text[start] == "{" else ("[", "]")
            text = _extract_balanced_json(text, start, opener, closer).strip()

    return text


def _resolve_text_model() -> RegisteredModel | None:
    from services.llm_router import resolve_text_model

    return resolve_text_model()


def _log_finish_reason(finish_reason: str | None, *, context: str) -> bool:
    if finish_reason == "length":
        logger.warning(
            "LLM 输出可能被截断 (finish_reason=length) context=%s",
            context,
        )
        return True
    return False


async def _call_llm(
    system_prompt: str, user_prompt: str, *, max_tokens: int = 4000
) -> tuple[str, str | None]:
    row = _resolve_text_model()
    if row:
        try:
            content, finish_reason = await _call_registered_model(
                row.id, system_prompt, user_prompt, max_tokens
            )
            _log_finish_reason(finish_reason, context="registered")
            return content, finish_reason
        except Exception:
            pass
    content, finish_reason = await _call_dashscope(
        system_prompt, user_prompt, max_tokens
    )
    _log_finish_reason(finish_reason, context="dashscope")
    return content, finish_reason


async def _call_registered_model(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> tuple[str, str | None]:
    db = SessionLocal()
    try:
        row = (
            db.query(RegisteredModel)
            .filter(RegisteredModel.id == model_id, RegisteredModel.enabled.is_(True))
            .first()
        )
        api_key = get_registered_model_api_key(row)
        if not row or not api_key or not (row.api_base or "").strip():
            raise ValueError(f"模型 {model_id} 未配置或未启用")

        async with httpx.AsyncClient(trust_env=False, timeout=120.0) as http:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=row.api_base.strip(),
                timeout=120.0,
                http_client=http,
            )
            response = await client.chat.completions.create(
                model=(row.model_string or row.id),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=max_tokens,
                stream=False,
            )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        if usage is not None:
            total = int(getattr(usage, "total_tokens", 0) or 0)
            if total <= 0:
                prompt_t = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_t = int(getattr(usage, "completion_tokens", 0) or 0)
                total = prompt_t + completion_t
            if total > 0:
                from services.llm_router import record_usage

                record_usage(model_id, total)
        return (
            (choice.message.content or "").strip(),
            getattr(choice, "finish_reason", None),
        )
    finally:
        db.close()


async def _call_dashscope(
    system_prompt: str, user_prompt: str, max_tokens: int
) -> tuple[str, str | None]:
    api_key = settings.dashscope_api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("未配置 DASHSCOPE_API_KEY，且无可用的已注册文本模型")

    async with httpx.AsyncClient(trust_env=False, timeout=120.0) as http:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=DASHSCOPE_BASE_URL,
            timeout=120.0,
            http_client=http,
        )
        response = await client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
            stream=False,
        )
    choice = response.choices[0]
    return (
        (choice.message.content or "").strip(),
        getattr(choice, "finish_reason", None),
    )


def _validate_scenes(scenes: list, *, label: str = "scenes") -> list:
    if not isinstance(scenes, list) or len(scenes) == 0:
        raise ValueError(f"{label} 必须为非空数组")
    if len(scenes) < 3 or len(scenes) > 6:
        raise ValueError(f"{label} 场景数量须在 3-6 个之间")
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError(f"{label}[{i}] 必须是对象")
        for key in ("id", "title", "characters", "mood", "content"):
            if key not in scene:
                raise ValueError(f"{label}[{i}] 缺少字段: {key}")
        if not str(scene.get("title") or "").strip():
            raise ValueError(f"{label}[{i}].title 不能为空")
        if not str(scene.get("content") or "").strip():
            raise ValueError(f"{label}[{i}].content 不能为空")
    return scenes


def _parse_outline_json(raw: str, *, count: int = 1) -> dict:
    text = clean_json_response(raw)
    if not text:
        raise ValueError("模型返回为空")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. Raw response: %s", raw)
        raise ValueError(f"JSON 解析失败: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("根节点必须是 JSON 对象")

    if count > 1 or isinstance(data.get("versions"), list):
        versions_raw = data.get("versions")
        if not isinstance(versions_raw, list) or len(versions_raw) == 0:
            raise ValueError("versions 必须为非空数组")
        if count > 1 and len(versions_raw) != count:
            raise ValueError(f"需要 {count} 个版本，实际返回 {len(versions_raw)} 个")

        versions = []
        for vi, item in enumerate(versions_raw):
            if not isinstance(item, dict):
                raise ValueError(f"versions[{vi}] 必须是对象")
            title = (item.get("title") or f"版本 {vi + 1}").strip()
            scenes = _validate_scenes(
                item.get("scenes"),
                label=f"versions[{vi}].scenes",
            )
            versions.append({"title": title, "scenes": scenes})

        first = versions[0]
        return {
            "title": first["title"],
            "scenes": first["scenes"],
            "versions": versions,
        }

    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("缺少 title 字段")
    scenes = _validate_scenes(data.get("scenes"))
    return {"title": title, "scenes": scenes, "versions": [{"title": title, "scenes": scenes}]}


MIN_SHOT_DURATION = 4
MAX_SHOT_DURATION = 15


def _trim_dangling_markdown(content: str) -> tuple[str, bool]:
    """截断回复时去掉未写完的 markdown 表格行."""
    if not content:
        return content, False
    lines = content.splitlines()
    changed = False
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            changed = True
            continue
        if last.startswith("|") and (last.count("|") < 3 or last.endswith("|")):
            lines.pop()
            changed = True
            continue
        if re.match(r"^\|[-:\s|]+\|$", last):
            lines.pop()
            changed = True
            continue
        if last.startswith("###") and len(last) < 24:
            lines.pop()
            changed = True
            continue
        break
    text = "\n".join(lines).rstrip()
    if changed and text:
        note = "（本节可能因生成长度限制未完整输出，可点击「重新生成大纲」补全。）"
        if note not in text:
            text = f"{text}\n\n{note}"
    return text, changed


def _sanitize_shots_data(data: dict) -> dict:
    """修正 LLM 返回的非法镜头时长."""
    segments = data.get("segments") or []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        shots = seg.get("shots") or []
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            raw = int(shot.get("duration") or 0)
            if raw < MIN_SHOT_DURATION:
                shot["duration"] = MIN_SHOT_DURATION
            elif raw > MAX_SHOT_DURATION:
                shot["duration"] = MAX_SHOT_DURATION
            elif raw <= 0:
                shot["duration"] = MIN_SHOT_DURATION
        shot_sum = sum(
            int(s.get("duration") or MIN_SHOT_DURATION)
            for s in shots
            if isinstance(s, dict)
        )
        if shot_sum > 0:
            seg["duration"] = shot_sum
    return data


def _parse_shots_json(raw: str) -> dict:
    text = clean_json_response(raw)
    if not text:
        raise ValueError("模型返回为空")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. Raw response: %s", raw)
        raise ValueError(f"JSON 解析失败: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("根节点必须是 JSON 对象")
    segments = data.get("segments")
    if not isinstance(segments, list) or len(segments) == 0:
        raise ValueError("segments 必须为非空数组")

    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValueError(f"segments[{i}] 必须是对象")
        for key in ("id", "title", "duration", "description", "shots"):
            if key not in seg:
                raise ValueError(f"segments[{i}] 缺少字段: {key}")
        shots = seg.get("shots")
        if not isinstance(shots, list) or len(shots) == 0:
            raise ValueError(f"segments[{i}].shots 必须为非空数组")
        seg_duration = int(seg.get("duration") or 0)
        shot_sum = 0
        for j, shot in enumerate(shots):
            if not isinstance(shot, dict):
                raise ValueError(f"segments[{i}].shots[{j}] 必须是对象")
            for key in ("id", "duration", "prompt", "camera", "movement", "lighting"):
                if key not in shot:
                    raise ValueError(f"segments[{i}].shots[{j}] 缺少字段: {key}")
            dur = int(shot.get("duration") or 0)
            if dur < MIN_SHOT_DURATION or dur > MAX_SHOT_DURATION:
                logger.warning(
                    "shots duration out of range segments[%s].shots[%s]=%s, will sanitize",
                    i,
                    j,
                    dur,
                )
            shot_sum += max(MIN_SHOT_DURATION, min(MAX_SHOT_DURATION, dur or MIN_SHOT_DURATION))
        if seg_duration > 0 and shot_sum != seg_duration:
            logger.warning(
                "segment %s duration mismatch sum=%s declared=%s, use sum",
                i,
                shot_sum,
                seg_duration,
            )

    return _sanitize_shots_data(data)


async def generate_outline(idea: str, *, count: int = 1) -> dict:
    text = (idea or "").strip()
    if not text:
        raise ValueError("请提供创意内容")

    from services.segment_duration import parse_target_duration_from_text

    target_sec = parse_target_duration_from_text(text)

    count = max(1, min(4, int(count or 1)))
    system_prompt = OUTLINE_SYSTEM_PROMPT
    user_prompt = text
    if target_sec:
        user_prompt = (
            f"【目标成片时长约 {target_sec} 秒】场景数量与情节密度须匹配该时长，"
            f"大纲只写叙事场景，不要写分镜表或秒级镜头列表。\n\n{text}"
        )
    if count > 1:
        system_prompt = (
            system_prompt.replace(SINGLE_VERSION_PREFIX, "")
            + f"\n请生成 {count} 个不同风格的剧本大纲版本。"
            + OUTLINE_MULTI_VERSION_SUFFIX
        )
        user_prompt = f"请生成 {count} 个版本的剧本大纲。\n\n{user_prompt}"

    max_tokens = 8000 if (target_sec and target_sec <= 120) or count > 1 else 6000
    raw, finish_reason = await _call_llm(
        system_prompt, user_prompt, max_tokens=max_tokens
    )
    if not raw:
        raise ValueError("模型未返回剧本内容")
    parsed = _parse_outline_json(raw, count=count)
    truncated = finish_reason == "length"
    if truncated:
        logger.warning("generate_outline: 输出可能被截断 (finish_reason=length)")
        for key in ("scenes",):
            scenes = parsed.get(key) or []
            if scenes:
                last = scenes[-1]
                if isinstance(last, dict) and last.get("content"):
                    trimmed, _ = _trim_dangling_markdown(str(last["content"]))
                    last["content"] = trimmed
        if parsed.get("versions"):
            for ver in parsed["versions"]:
                vscenes = ver.get("scenes") or []
                if vscenes and isinstance(vscenes[-1], dict):
                    c = vscenes[-1].get("content")
                    if c:
                        vscenes[-1]["content"], _ = _trim_dangling_markdown(str(c))
    return {**parsed, "truncated": truncated}


def _outline_payload_for_shots(outline: str) -> tuple[str, int | None]:
    import json

    from services.segment_duration import parse_target_duration_from_text

    text = (outline or "").strip()
    target: int | None = None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            raw_target = data.get("target_video_duration_sec") or data.get(
                "target_duration_sec"
            )
            if raw_target is not None:
                target = int(raw_target)
            idea = data.get("source_idea") or data.get("idea") or ""
            if target is None and idea:
                target = parse_target_duration_from_text(str(idea))
            if target is None:
                target = parse_target_duration_from_text(text)
            return json.dumps(data, ensure_ascii=False, indent=2), target
    except json.JSONDecodeError:
        pass
    target = parse_target_duration_from_text(text)
    return text, target


async def generate_shots(outline: str, *, target_duration_sec: int | None = None) -> dict:
    text = (outline or "").strip()
    if not text:
        raise ValueError("请提供剧本大纲")

    llm_input, parsed_target = _outline_payload_for_shots(text)
    target = target_duration_sec if target_duration_sec is not None else parsed_target
    if target is not None:
        llm_input = (
            f"【硬性约束】整片目标总时长 = {int(target)} 秒。"
            f"所有镜头的 duration 之和必须等于 {int(target)} 秒（误差≤2）。"
            f"单镜 4-15 秒，镜头数建议 {max(2, int(target) // 8)} 镜左右，勿过度切镜。\n\n"
            + llm_input
        )

    raw, finish_reason = await _call_llm(
        SHOTS_SYSTEM_PROMPT, llm_input, max_tokens=8000
    )
    if not raw:
        raise ValueError("模型未返回内容")
    parsed = _parse_shots_json(raw)
    duration_warning = None
    if target is not None:
        from services.segment_duration import normalize_segments_to_target

        segments, duration_warning = normalize_segments_to_target(
            parsed.get("segments") or [], int(target)
        )
        parsed["segments"] = segments
        parsed["target_video_duration_sec"] = int(target)

    truncated = finish_reason == "length"
    if truncated:
        logger.warning("generate_shots: 输出可能被截断 (finish_reason=length)")
    out = {**parsed, "truncated": truncated}
    if duration_warning:
        out["duration_warning"] = duration_warning
    return out
