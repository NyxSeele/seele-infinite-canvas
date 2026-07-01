"""分镜镜：根据剧情与时长 LLM 拆分为连续节拍（含每格画面 prompt）"""

from __future__ import annotations

import json
import re

from services.qwen import _call_llm

MAX_SHOT_DURATION = 15

_SYSTEM = f"""You are a senior storyboard director. Split one shot into timed beats for AI image/video generation.
The user provides: shot number, duration (seconds, max {MAX_SHOT_DURATION}), plot, optional style and cast.

Output JSON only (no markdown):
{{
  "beats": [
    {{
      "label": "起幅",
      "time_start": 0,
      "time_end": 4.5,
      "prompt": "中文画面描述（景别、人物动作、光影、情绪，供用户界面展示）",
      "prompt_en": "English visual description for image/video API. Include shot size, action, lighting, mood, and relevant director notes (lens, performance, color grade). Be specific and cinematic.",
      "action_note": "演出要点（运镜/对白/音效，中文一句话）"
    }}
  ]
}}

Rules:
1. beats count 2–4: duration ≤4s → 2 beats, ≤9s → 3, longer → 4.
2. First beat time_start=0, last beat time_end equals total duration; contiguous, no gaps.
3. prompt must be Chinese, concrete, visual; prompt_en must be English, cinematic, suitable for diffusion/video models.
4. label: short Chinese (起幅、推进、高潮、落幅), not English.
5. Avoid repeating the same visual in consecutive beats; form a clear arc."""


def _beat_count(duration: float) -> int:
    d = max(1.0, min(MAX_SHOT_DURATION, float(duration or 8)))
    if d <= 4:
        return 2
    if d <= 9:
        return 3
    return 4


def _rule_beats(row: dict) -> list[dict]:
    duration = max(1.0, min(MAX_SHOT_DURATION, float(row.get("duration") or 8)))
    shot = (row.get("prompt") or row.get("description") or "").strip()
    count = _beat_count(duration)
    labels = ["起幅", "推进", "高潮", "落幅"][:count]
    label_en_map = {
        "起幅": "Opening frame",
        "推进": "Build-up",
        "高潮": "Climax",
        "落幅": "Closing frame",
    }
    step = duration / count
    beats = []
    shot_en = shot[:80] if shot else "scene continuation"
    for i in range(count):
        start = round(i * step, 1)
        end = duration if i == count - 1 else round((i + 1) * step, 1)
        seg_hint = f"【{labels[i]}·{start}s–{end}s】"
        prompt = f"{seg_hint}{shot}" if shot else f"{seg_hint}（待补充画面）"
        label_en = label_en_map.get(labels[i], labels[i])
        beats.append(
            {
                "label": labels[i],
                "time_start": start,
                "time_end": end,
                "prompt": prompt,
                "prompt_en": f"{label_en}, {start}s-{end}s. {shot_en}",
                "action_note": "",
            }
        )
    return beats


def _parse_llm_beats(raw: str, duration: float) -> list[dict] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    beats = data.get("beats") if isinstance(data, dict) else None
    if not isinstance(beats, list) or len(beats) < 1:
        return None

    duration = max(1.0, min(MAX_SHOT_DURATION, float(duration or 8)))
    out = []
    for i, b in enumerate(beats[:4]):
        if not isinstance(b, dict):
            continue
        label = (b.get("label") or f"格{i + 1}").strip()
        prompt = (b.get("prompt") or b.get("prompt_zh") or "").strip()
        prompt_en = (b.get("prompt_en") or b.get("promptEn") or "").strip()
        if not prompt and not prompt_en:
            continue
        if not prompt:
            prompt = prompt_en
        start = float(b.get("time_start", 0))
        end = float(b.get("time_end", 0))
        out.append(
            {
                "label": label,
                "time_start": start,
                "time_end": end,
                "prompt": prompt,
                "prompt_en": prompt_en,
                "action_note": (b.get("action_note") or b.get("dialogue_action") or "").strip(),
            }
        )
    if not out:
        return None

    out[0]["time_start"] = 0.0
    out[-1]["time_end"] = duration
    for j in range(1, len(out)):
        out[j]["time_start"] = out[j - 1]["time_end"]
    return out


async def split_shot_beats(payload: dict, *, use_llm: bool = True) -> dict:
    row = payload.get("row") or {}
    duration = max(1.0, min(MAX_SHOT_DURATION, float(row.get("duration") or 8)))
    cast = payload.get("cast_library") or []

    rule = _rule_beats({**row, "duration": duration})
    if not use_llm:
        return {"beats": rule, "source": "rule", "duration": duration}

    shot = (row.get("prompt") or row.get("description") or "").strip()
    if not shot:
        return {"beats": rule, "source": "rule", "duration": duration}

    user = {
        "shot_number": row.get("shot_number") or 1,
        "duration_seconds": duration,
        "plot": shot,
        "atmosphere": (row.get("atmosphere_note") or "").strip(),
        "cast_library": [
            {"name": c.get("name"), "type": c.get("type")}
            for c in cast
            if (c.get("name") or "").strip()
        ],
        "director": {
            k: (row.get(k) or "").strip()
            for k in (
                "camera",
                "movement",
                "lighting",
                "composition",
                "color_grade",
                "lens",
                "performance",
                "sound_design",
                "sound_note",
            )
            if (row.get(k) or "").strip()
        },
    }

    try:
        raw, _ = await _call_llm(
            _SYSTEM,
            json.dumps(user, ensure_ascii=False, indent=2),
            max_tokens=2800,
        )
        parsed = _parse_llm_beats(raw, duration)
        if parsed:
            return {"beats": parsed, "source": "llm", "duration": duration}
    except Exception:
        pass

    return {"beats": rule, "source": "rule", "duration": duration}
