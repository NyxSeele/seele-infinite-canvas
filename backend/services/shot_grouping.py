"""大小镜头归并：细分镜 → 大镜头 + 节拍 keyframes。"""

from __future__ import annotations

import time
import uuid
from typing import Any

MAX_SHOT_DURATION = 15
BEAT_LABELS = ["起幅", "推进", "高潮", "落幅"]
DIRECTOR_KEYS = (
    "camera",
    "movement",
    "lighting",
    "composition",
    "colorGrade",
    "lens",
    "performance",
    "soundDesign",
    "soundNote",
    "atmosphereNote",
)


def _micro_duration(row: dict) -> float:
    try:
        d = float(row.get("duration") or 8)
        return max(0.5, min(MAX_SHOT_DURATION, d))
    except (TypeError, ValueError):
        return 8.0


def _segment_key(row: dict) -> str:
    return str(row.get("segmentId") or row.get("segment_id") or "_default")


def suggest_groups(
    micro_rows: list[dict[str, Any]],
    target_duration: float = 10.0,
) -> list[list[int]]:
    """按原始顺序 + 场次边界 + 秒数累加，给出大镜头分组（索引列表）。"""
    if not micro_rows:
        return []
    target = max(2.0, min(MAX_SHOT_DURATION, float(target_duration or 10)))

    groups: list[list[int]] = []
    current: list[int] = []
    acc = 0.0
    current_seg = _segment_key(micro_rows[0])

    for idx, row in enumerate(micro_rows):
        seg = _segment_key(row)
        dur = _micro_duration(row)

        if current and seg != current_seg:
            groups.append(current)
            current = []
            acc = 0.0
            current_seg = seg

        if current and acc + dur > target and acc > 0:
            groups.append(current)
            current = []
            acc = 0.0

        current.append(idx)
        acc += dur
        current_seg = seg

    if current:
        groups.append(current)

    return groups


def _make_row_id() -> str:
    return f"row-import-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _make_kf_id() -> str:
    return f"kf-import-{uuid.uuid4().hex[:10]}"


def _pick_director_fields(micro_rows: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in DIRECTOR_KEYS:
        for m in micro_rows:
            val = m.get(key)
            if val is not None and str(val).strip():
                out[key] = str(val).strip()
                break
    return out


def _beat_label(index: int, total: int) -> str:
    if total <= len(BEAT_LABELS):
        return BEAT_LABELS[index] if index < len(BEAT_LABELS) else f"格{index + 1}"
    return f"格{index + 1}"


def build_macro_rows(
    micro_rows: list[dict[str, Any]],
    groups: list[list[int]],
    segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """每组细分镜 → 1 个大镜头 row，组内每镜 → 1 个 keyframe（对齐 applyBeatsToRow 字段）。"""
    if not groups:
        return []

    seg_map = {s["id"]: s for s in (segments or []) if s.get("id")}
    macro_rows: list[dict[str, Any]] = []
    now = int(time.time() * 1000)

    for gi, indices in enumerate(groups):
        if not indices:
            continue
        micros = [micro_rows[i] for i in indices if 0 <= i < len(micro_rows)]
        if not micros:
            continue

        total_dur = round(sum(_micro_duration(m) for m in micros), 1)
        total_dur = min(MAX_SHOT_DURATION, max(1.0, total_dur))

        prompts = [
            (m.get("prompt") or m.get("description") or "").strip() for m in micros
        ]
        shot_prompt = prompts[0] if prompts else ""
        if len(prompts) > 1:
            extra = "；".join(p for p in prompts[1:3] if p)
            if extra:
                shot_prompt = f"{shot_prompt}（{extra}）" if shot_prompt else extra

        keyframes: list[dict[str, Any]] = []
        t = 0.0
        for ki, m in enumerate(micros):
            md = _micro_duration(m)
            mp = (m.get("prompt") or m.get("description") or "").strip()
            start = round(t, 1)
            end = round(t + md, 1) if ki < len(micros) - 1 else total_dur
            t = end
            keyframes.append(
                {
                    "id": _make_kf_id(),
                    "index": ki,
                    "label": _beat_label(ki, len(micros)),
                    "timeStart": start,
                    "timeEnd": end,
                    "prompt": mp,
                    "description": mp,
                    "promptEn": "",
                    "actionNote": (m.get("soundDesign") or m.get("sound_design") or "")[:200],
                    "promptMentions": [],
                    "referenceImage": None,
                    "resultUrl": None,
                    "status": "idle",
                    "builtPrompt": None,
                    "compiledPromptPackage": None,
                    "negativePrompt": None,
                    "imageGenNodeId": None,
                    "error": None,
                    "importMicroShotNumber": m.get("shotNumber"),
                }
            )

        seg_id = micros[0].get("segmentId") or micros[0].get("segment_id") or ""
        macro = {
            "id": _make_row_id(),
            "shotNumber": gi + 1,
            "duration": total_dur,
            "prompt": shot_prompt,
            "description": shot_prompt,
            "promptMentions": [],
            "segmentId": seg_id,
            "segmentTitle": (seg_map.get(seg_id) or {}).get("title") or "",
            "keyframes": keyframes,
            "beatsSplitAt": now,
            "beatsSplitSource": "import",
            "status": "idle",
            "error": None,
            "resultUrl": None,
            **_pick_director_fields(micros),
        }
        macro_rows.append(macro)

    return macro_rows


def preview_group_stats(
    micro_rows: list[dict[str, Any]],
    groups: list[list[int]],
) -> dict[str, Any]:
    macro_count = len(groups)
    durations = []
    beat_counts = []
    for indices in groups:
        micros = [micro_rows[i] for i in indices if 0 <= i < len(micro_rows)]
        if not micros:
            continue
        durations.append(round(sum(_micro_duration(m) for m in micros), 1))
        beat_counts.append(len(micros))
    return {
        "macro_shot_count": macro_count,
        "micro_shot_count": len(micro_rows),
        "macro_durations": durations,
        "beats_per_macro": beat_counts,
    }
