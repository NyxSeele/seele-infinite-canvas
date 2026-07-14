"""分镜 segment/shot 时长归一化到目标成片时长"""

from __future__ import annotations

import re

MIN_SHOT_SEC = 4
MAX_SHOT_SEC = 15


def parse_target_duration_from_text(text: str) -> int | None:
    s = text or ""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|min(?:ute)?s?)", s, re.I)
    if m:
        sec = int(round(float(m.group(1)) * 60))
        if sec > 0:
            return max(15, min(900, sec))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:秒钟|秒|s(?:ec(?:ond)?s?)?)", s, re.I)
    if m:
        sec = int(round(float(m.group(1))))
        if sec >= 10:
            return max(15, min(900, sec))
    return None


def parse_shots_target_from_text(text: str) -> int | None:
    """解析用户显式镜数，如「3个镜头」「共 5 镜」。"""
    s = text or ""
    patterns = (
        r"(\d+)\s*个镜头",
        r"(\d+)\s*个分镜",
        r"(?:共|一共|总共)?\s*(\d+)\s*镜(?:头)?",
        r"(\d+)\s*shots?\b",
    )
    for pat in patterns:
        m = re.search(pat, s, re.I)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 60:
                return n
    return None


def clamp_segments_to_shot_count(
    segments: list, shots_target: int
) -> tuple[list, str | None]:
    """将 segment/shot 总数裁剪到 shots_target（保留前 N 镜）。"""
    if not shots_target or shots_target < 1 or not segments:
        return segments, None

    flat: list[tuple[int, int, dict]] = []
    for si, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        for ji, shot in enumerate(seg.get("shots") or []):
            if isinstance(shot, dict):
                flat.append((si, ji, shot))

    if len(flat) <= shots_target:
        return segments, None

    warning = (
        f"镜头数 {len(flat)} 超过目标 {shots_target} 镜，已保留前 {shots_target} 镜。"
    )
    kept = 0
    new_segments = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        new_shots = []
        for shot in seg.get("shots") or []:
            if kept >= shots_target:
                break
            if isinstance(shot, dict):
                new_shots.append(shot)
                kept += 1
        if new_shots:
            new_seg = dict(seg)
            new_seg["shots"] = new_shots
            new_seg["duration"] = sum(int(s.get("duration") or 0) for s in new_shots)
            new_segments.append(new_seg)
    return new_segments, warning


def normalize_segments_to_target(segments: list, target_sec: int) -> tuple[list, str | None]:
    if not target_sec or target_sec < 1 or not segments:
        return segments, None

    target = max(15, min(900, int(target_sec)))
    flat: list[tuple[int, int, dict]] = []
    for si, seg in enumerate(segments):
        for ji, shot in enumerate(seg.get("shots") or []):
            if isinstance(shot, dict):
                flat.append((si, ji, shot))

    if not flat:
        return segments, None

    max_shots = target // MIN_SHOT_SEC
    warning: str | None = None
    if len(flat) > max_shots:
        warning = (
            f"镜头数 {len(flat)} 超过目标 {target} 秒可容纳约 {max_shots} 镜，"
            f"已保留前 {max_shots} 镜。"
        )
        kept = 0
        new_segments = []
        for seg in segments:
            new_shots = []
            for shot in seg.get("shots") or []:
                if kept >= max_shots:
                    break
                new_shots.append(shot)
                kept += 1
            if new_shots:
                new_seg = dict(seg)
                new_seg["shots"] = new_shots
                new_seg["duration"] = sum(int(s.get("duration") or 0) for s in new_shots)
                new_segments.append(new_seg)
        segments = new_segments
        flat = []
        for si, seg in enumerate(segments):
            for ji, shot in enumerate(seg.get("shots") or []):
                flat.append((si, ji, shot))

    total = sum(int(s[2].get("duration") or MIN_SHOT_SEC) for s in flat)
    if total <= target + 1 and total >= target - 1:
        return segments, warning

    scale = target / max(total, 1)
    for si, ji, shot in flat:
        raw = int(shot.get("duration") or MIN_SHOT_SEC)
        shot["duration"] = max(
            MIN_SHOT_SEC, min(MAX_SHOT_SEC, int(round(raw * scale)))
        )

    total = sum(int(s[2].get("duration") or MIN_SHOT_SEC) for s in flat)
    guard = 0
    while total > target and guard < 500:
        guard += 1
        cand = None
        best_d = -1
        for item in flat:
            d = int(item[2].get("duration") or 0)
            if d > MIN_SHOT_SEC and d > best_d:
                best_d = d
                cand = item[2]
        if not cand:
            break
        cand["duration"] = int(cand.get("duration") or MIN_SHOT_SEC) - 1
        total -= 1

    guard = 0
    while total < target and guard < 500:
        guard += 1
        cand = None
        best_d = 999
        for item in flat:
            d = int(item[2].get("duration") or 0)
            if d < MAX_SHOT_SEC and d < best_d:
                best_d = d
                cand = item[2]
        if not cand:
            break
        cand["duration"] = int(cand.get("duration") or MIN_SHOT_SEC) + 1
        total += 1

    for si, seg in enumerate(segments):
        shots = seg.get("shots") or []
        seg["duration"] = sum(int(s.get("duration") or 0) for s in shots)

    if abs(total - target) > 2 and not warning:
        warning = f"已按目标 {target} 秒调整各镜时长（当前合计约 {total} 秒）。"

    return segments, warning
