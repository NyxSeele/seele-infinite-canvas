#!/usr/bin/env python3
"""G46 A5：真实 LLM 节拍拆分探针（POST /api/prompt/split-shot-beats, use_llm=true）。

验收：source 必须为 llm（rule 回退视为失败）；结构字段完整；日志含 A5 BEATS_*。
不改产品代码；与 GPU_DEBT Seedance G46 无关，仅本探针文件名。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path("/root/autodl-tmp/logs/backend.out.log")
OUT_PATH = Path("/root/autodl-tmp/logs/g46_a5_beats_probe.json")

# 固定标准分镜（雨夜重庆 · duration=8 → 期望 3 节拍）
STANDARD_PAYLOAD = {
    "row": {
        "shot_number": 1,
        "duration": 8,
        "prompt": (
            "全景固定机位缓慢横移，冷调蓝灰主光笼罩潮湿重庆老街；"
            "女人身着米色风衣手持深灰长柄伞独自伫立街角，雨丝逆光"
        ),
        "atmosphere_note": "雨夜孤独",
        "camera": "全景",
        "movement": "缓慢横移",
        "keyframes": [],
    },
    "cast_library": [{"name": "女人", "type": "character"}],
    "use_llm": True,
}


def load_admin_password() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("SEED_ADMIN_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_ADMIN_PASSWORD not found")


def login(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "admin", "password": load_admin_password()},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def validate_beats(data: dict, *, duration: float = 8.0) -> list[str]:
    issues: list[str] = []
    source = data.get("source")
    if source != "llm":
        issues.append(f"source={source!r} expected 'llm' (rule fallback = FAIL)")
    beats = data.get("beats") or []
    if not (2 <= len(beats) <= 4):
        issues.append(f"beats_count={len(beats)} not in 2..4")
    if duration <= 9 and len(beats) != 3:
        issues.append(f"duration={duration} expected 3 beats, got {len(beats)}")
    if not beats:
        return issues
    first_start = beats[0].get("time_start")
    if first_start is None or abs(float(first_start) - 0.0) > 0.05:
        issues.append(f"first time_start={first_start} expected 0")
    last_end = beats[-1].get("time_end")
    if last_end is None or abs(float(last_end) - float(duration)) > 0.05:
        issues.append(f"last time_end={last_end} expected {duration}")
    for i, b in enumerate(beats):
        for key in ("label", "prompt", "prompt_en"):
            if not str(b.get(key) or "").strip():
                issues.append(f"beats[{i}].{key} empty")
        if i > 0:
            prev_end = beats[i - 1].get("time_end")
            cur_start = b.get("time_start")
            if prev_end is None or cur_start is None:
                issues.append(f"beats[{i}] missing time fields")
            elif abs(float(prev_end) - float(cur_start)) > 0.05:
                issues.append(f"beats[{i}] gap: prev_end={prev_end} start={cur_start}")
    return issues


def check_a5_traces(log_delta: str) -> list[str]:
    issues: list[str] = []
    if "A5 BEATS_INPUT" not in log_delta:
        issues.append("missing A5 BEATS_INPUT in log delta")
    if "A5 BEATS_OUTPUT" not in log_delta:
        issues.append("missing A5 BEATS_OUTPUT in log delta")
    return issues


def main() -> int:
    print("=== G46 A5 BEATS LLM PROBE ===", flush=True)
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    issues: list[str] = []
    result: dict = {
        "probe": "g46_a5_beats",
        "payload": STANDARD_PAYLOAD,
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            token = login(client)
            t0 = time.time()
            r = client.post(
                f"{BASE}/api/prompt/split-shot-beats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=STANDARD_PAYLOAD,
            )
            elapsed = time.time() - t0
            result["http_status"] = r.status_code
            result["elapsed_s"] = round(elapsed, 2)
            print(f"HTTP {r.status_code} {elapsed:.1f}s", flush=True)
            if r.status_code != 200:
                issues.append(f"HTTP {r.status_code}: {r.text[:400]}")
                result["body_preview"] = r.text[:500]
            else:
                data = r.json()
                result["source"] = data.get("source")
                result["duration"] = data.get("duration")
                result["beats_count"] = len(data.get("beats") or [])
                result["beats_preview"] = [
                    {
                        "label": b.get("label"),
                        "time_start": b.get("time_start"),
                        "time_end": b.get("time_end"),
                        "prompt": (b.get("prompt") or "")[:120],
                    }
                    for b in (data.get("beats") or [])
                ]
                print(
                    f"source={data.get('source')} beats={result['beats_count']}",
                    flush=True,
                )
                issues.extend(validate_beats(data, duration=float(data.get("duration") or 8)))
    except Exception as exc:
        issues.append(f"request failed: {exc}")
        print(f"ERROR: {exc}", flush=True)

    time.sleep(0.3)
    log_delta = ""
    if LOG_PATH.is_file():
        log_delta = LOG_PATH.read_bytes()[log_start:].decode(errors="ignore")
    result["a5_input_in_log"] = "A5 BEATS_INPUT" in log_delta
    result["a5_output_in_log"] = "A5 BEATS_OUTPUT" in log_delta
    issues.extend(check_a5_traces(log_delta))
    print(
        f"log A5 INPUT={result['a5_input_in_log']} OUTPUT={result['a5_output_in_log']}",
        flush=True,
    )

    result["issues"] = issues
    result["ok"] = len(issues) == 0
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}", flush=True)

    if result["ok"]:
        print("PASS", flush=True)
        return 0
    print("FAIL", flush=True)
    for i in issues:
        print(f"  - {i}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
