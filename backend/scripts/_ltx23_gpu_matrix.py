#!/usr/bin/env python3
"""LTX-2.3 I2AV GPU 质量矩阵：真实 API 出片验收。"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from _prompt_debug_phase2 import (  # noqa: E402
    BASE,
    poll_task,
    summarize,
    upload_image_file,
)

OUT = Path("/root/autodl-tmp/logs/ltx23_gpu_matrix.json")
DEFAULT_REF = BACKEND_ROOT / "scripts" / "g30_probe_face.jpg"
AUDIO_CANDIDATES = [
    Path(
        "/root/autodl-tmp/tmp/pytest-of-root/pytest-12/"
        "test_mix_sfx_into_video_invoke0/sfx.wav"
    ),
    Path("/root/autodl-tmp/ComfyUI/input/sfx.wav"),
]
POLL_TIMEOUT = 2400
CASE_RETRY = 2
CASE_GAP_SEC = 3
HEALTH_RETRIES = 5
HEALTH_WAIT_SEC = 8

CASES = [
    # ── 镜头运动 ──
    {
        "id": "CAM01",
        "prompt": "镜头缓缓推进，人物转头看向远方，霓虹灯光在脸颊上流动",
        "note": "推轨+转头",
        "angle": "dolly_in",
    },
    {
        "id": "CAM02",
        "prompt": "camera slowly pulls back revealing a rainy alley behind the subject",
        "note": "拉镜+环境揭示",
        "angle": "dolly_out",
    },
    {
        "id": "CAM03",
        "prompt": "横摇镜头跟随人物从左走到右，背景店铺灯光掠过",
        "note": "横摇跟随",
        "angle": "pan",
    },
    {
        "id": "CAM04",
        "prompt": "slow orbit around the subject, shallow depth of field, cinematic lighting",
        "note": "环绕",
        "angle": "orbit",
    },
    {
        "id": "CAM05",
        "prompt": "固定机位，人物微微点头，发丝随风轻动，背景虚化",
        "note": "固定机位微动",
        "angle": "static",
    },
    {
        "id": "CAM06",
        "prompt": "轻微手持晃动，纪实风格，人物自然呼吸起伏",
        "note": "手持纪实",
        "angle": "handheld",
    },
    # ── 场景/氛围 ──
    {
        "id": "SCN01",
        "prompt": "雨夜霓虹街道，车辆驶过溅起水花，人物自然行走",
        "note": "霓虹雨夜（反馈类）",
        "angle": "neon_rain",
    },
    {
        "id": "SCN02",
        "prompt": "清晨公园慢跑的人影，阳光穿过树叶形成光斑",
        "note": "户外晨光",
        "angle": "park_morning",
    },
    {
        "id": "SCN03",
        "prompt": "close-up of coffee pouring into a ceramic cup, steam rising, warm indoor light",
        "note": "室内静物",
        "angle": "indoor",
    },
    {
        "id": "SCN04",
        "prompt": "暴风雪中的小屋窗前，人物呵气成雾，壁炉暖光映在脸上",
        "note": "雪景冷暖对比",
        "angle": "snow",
    },
    {
        "id": "SCN05",
        "prompt": "海边日落，人物迎风站立，裙摆与头发被风吹起",
        "note": "海边大风",
        "angle": "beach",
    },
    {
        "id": "SCN06",
        "prompt": "舞台追光灯下，人物抬手致意，烟雾缓缓飘过",
        "note": "舞台戏剧",
        "angle": "stage",
    },
    # ── 人物动作/表演 ──
    {
        "id": "ACT01",
        "prompt": "人物从站立到转身离开，步伐稳定，衣摆随动作自然摆动",
        "note": "转身离场",
        "angle": "turn_walk",
    },
    {
        "id": "ACT02",
        "prompt": "subject raises hand to wave hello, friendly expression, smooth motion",
        "note": "挥手打招呼",
        "angle": "wave",
    },
    {
        "id": "ACT03",
        "prompt": "人物快步穿过走廊，镜头侧面跟拍，光影在墙面掠过",
        "note": "侧面跟拍快走",
        "angle": "side_track",
    },
    {
        "id": "ACT04",
        "prompt": "两人对话感构图（单人出镜），人物嘴唇微动像在说话，表情细腻",
        "note": "对话表演",
        "angle": "dialogue",
    },
    # ── 画幅/时长变体 ──
    {
        "id": "VAR01",
        "prompt": "竖屏短视频风格，人物居中，缓慢推近面部特写",
        "note": "9:16竖屏",
        "angle": "portrait",
        "ratio": "9:16",
    },
    {
        "id": "VAR02",
        "prompt": "wide cinematic establishing shot, subject small in frame, clouds moving",
        "note": "16:9远景",
        "angle": "wide",
        "ratio": "16:9",
        "duration": 10,
    },
    {
        "id": "VAR03",
        "prompt": "竖屏街拍，人物回头一瞥，城市灯光 bokeh 背景",
        "note": "9:16回头",
        "angle": "portrait_glance",
        "ratio": "9:16",
    },
    # ── 音频 I2AV ──
    {
        "id": "AUD01",
        "prompt": "人物轻声哼唱，镜头稳定推进，表情柔和",
        "note": "参考音频哼唱",
        "angle": "audio_hum",
        "audio": True,
        "audio_url": "__AUTO__",
        "required": False,
    },
    {
        "id": "AUD02",
        "prompt": "subject appears to speak emotionally, subtle head movement, synced ambience",
        "note": "参考音频对白感",
        "angle": "audio_speech",
        "audio": True,
        "audio_url": "__AUTO__",
        "required": False,
    },
]

for _c in CASES:
    _c.setdefault("audio", False)
    _c.setdefault("audio_url", None)
    _c.setdefault("required", True)
    _c.setdefault("ratio", "16:9")
    _c.setdefault("duration", 5)
    _c.setdefault("resolution", "720P")


def load_passwords() -> list[str]:
    env_path = BACKEND_ROOT / ".env"
    passwords: list[str] = []
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_ADMIN_PASSWORD="):
            passwords.append(line.split("=", 1)[1].strip())
        if line.startswith("SEED_TESTUSER_PASSWORD="):
            passwords.append(line.split("=", 1)[1].strip())
    if not passwords:
        raise RuntimeError("SEED_ADMIN_PASSWORD not found")
    return passwords


def load_existing_report() -> dict:
    if not OUT.is_file():
        return {}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def case_ids_from(start: str | None) -> list[str]:
    ids = [c["id"] for c in CASES]
    if not start:
        return ids
    if start not in ids:
        raise ValueError(f"unknown case id: {start}")
    return ids[ids.index(start) :]


def build_tables(
    tasks_out: dict[str, dict],
    *,
    resolution: str,
    duration: int,
) -> list[dict]:
    tables = []
    for case in CASES:
        task = tasks_out.get(case["id"], {})
        tables.append(
            {
                "id": case["id"],
                "note": case.get("note"),
                "angle": case.get("angle"),
                "ratio": case.get("ratio", "16:9"),
                "duration": case.get("duration", duration),
                "required": case.get("required", True),
                "status": task.get("status"),
                "verdict": task.get("verdict", evaluate_case(case, task)),
                "error": summarize(task.get("error"), 200),
                "result": summarize(task.get("result"), 120),
                "wall_seconds": task.get("wall_seconds"),
                "task_id": task.get("task_id"),
                "attempts": task.get("attempts"),
            }
        )
    return tables


def finalize_payload(
    tasks_out: dict[str, dict],
    *,
    resolution: str,
    width: int | None,
    height: int | None,
    duration: int,
    ref: Path,
    audio_path: Path | None,
    wall_start: float,
    resumed: bool,
    from_case: str | None,
) -> dict:
    tables = build_tables(tasks_out, resolution=resolution, duration=duration)
    required_failures = [
        t["id"]
        for t in tables
        if t["id"] in {c["id"] for c in CASES if c.get("required")}
        and t.get("verdict") == "FAIL"
    ]
    return {
        "label": "ltx23_gpu_matrix",
        "case_count": len(CASES),
        "resolution": resolution,
        "width": width,
        "height": height,
        "duration": duration,
        "reference_image": str(ref),
        "audio_file": str(audio_path) if audio_path else None,
        "resumed": resumed,
        "from_case": from_case,
        "cases": {c["id"]: tasks_out.get(c["id"], {}) for c in CASES},
        "tables": tables,
        "required_failures": required_failures,
        "pass": not required_failures,
        "wall_seconds_total": round(time.time() - wall_start, 1),
    }


def write_report(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def wait_backend_ready(client: httpx.AsyncClient) -> None:
    for attempt in range(1, HEALTH_RETRIES + 1):
        try:
            r = await client.get(f"{BASE}/api/health", timeout=10)
            if r.status_code == 200:
                return
        except Exception:
            pass
        print(
            f"[health] backend not ready ({attempt}/{HEALTH_RETRIES}), "
            f"sleep {HEALTH_WAIT_SEC}s",
            flush=True,
        )
        await asyncio.sleep(HEALTH_WAIT_SEC)
    raise RuntimeError("backend health check failed")


async def login_admin(client: httpx.AsyncClient) -> str:
    usernames = ("seele", "admin", "testuser")
    last_status = 0
    for password in load_passwords():
        for username in usernames:
            r = await client.post(
                f"{BASE}/api/auth/login",
                json={"username_or_email": username, "password": password},
            )
            last_status = r.status_code
            if r.status_code == 200:
                return r.json()["access_token"]
    raise RuntimeError(f"login failed for all candidates (last_status={last_status})")


async def upload_audio_file(
    client: httpx.AsyncClient, token: str, path: Path
) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    with path.open("rb") as f:
        r = await client.post(
            f"{BASE}/api/upload/audio",
            headers=headers,
            files={"file": (path.name, f, "audio/wav")},
            timeout=60,
        )
    r.raise_for_status()
    url = r.json().get("url")
    if not url:
        raise RuntimeError("audio upload missing url")
    return url


def resolve_audio_path() -> Path | None:
    for path in AUDIO_CANDIDATES:
        if path.is_file() and path.stat().st_size > 1000:
            return path
    return None


def evaluate_case(case: dict, task: dict) -> str:
    """PASS | FAIL | SKIP"""
    if task.get("status") == "skipped":
        return "SKIP"
    if case.get("required") is False and task.get("skip_reason"):
        return "SKIP"
    if task.get("status") == "completed" and task.get("result"):
        return "PASS"
    return "FAIL"


def should_skip_case(
    case: dict,
    tasks_out: dict[str, dict],
    *,
    resume: bool,
) -> bool:
    if not resume:
        return False
    prev = tasks_out.get(case["id"], {})
    verdict = prev.get("verdict") or evaluate_case(case, prev)
    return verdict in ("PASS", "SKIP")


async def run_single_case(
    client: httpx.AsyncClient,
    *,
    token: str,
    headers: dict,
    case: dict,
    ref_url: str,
    audio_url: str | None,
    resolution: str,
    width: int | None,
    height: int | None,
    duration: int,
) -> dict:
    cid = case["id"]
    case_audio_url = case.get("audio_url")
    if case_audio_url == "__AUTO__":
        if not audio_url:
            return {
                "status": "skipped",
                "skip_reason": "no audio file available",
                "verdict": "SKIP",
            }
        case_audio_url = audio_url

    body: dict = {
        "model": "ltx23-i2av",
        "prompt": case["prompt"],
        "generation_mode": "freeref",
        "ratio": case.get("ratio", "16:9"),
        "resolution": case.get("resolution", resolution),
        "duration": int(case.get("duration", duration)),
        "audio": bool(case.get("audio")),
        "count": 1,
        "node_id": f"ltx23-matrix-{cid}-{uuid.uuid4().hex[:6]}",
        "trace_id": str(uuid.uuid4()),
        "reference_image": ref_url,
    }
    if width is not None and height is not None:
        body["width"] = int(width)
        body["height"] = int(height)
    if case_audio_url and case_audio_url != "__AUTO__":
        body["audio_url"] = case_audio_url

    last_task: dict = {}
    for attempt in range(1, CASE_RETRY + 1):
        await wait_backend_ready(client)
        t0 = time.time()
        try:
            r = await client.post(
                f"{BASE}/api/tasks/video", headers=headers, json=body
            )
        except httpx.HTTPError as exc:
            last_task = {
                "status": "submit_failed",
                "error": str(exc),
                "attempts": attempt,
                "wall_seconds": round(time.time() - t0, 1),
                "verdict": "FAIL",
            }
            if attempt < CASE_RETRY:
                await asyncio.sleep(HEALTH_WAIT_SEC)
                continue
            return last_task

        if r.status_code >= 400:
            last_task = {
                "status": "submit_failed",
                "error": r.text[:800],
                "http_status": r.status_code,
                "attempts": attempt,
                "wall_seconds": round(time.time() - t0, 1),
                "verdict": "FAIL",
            }
            if attempt < CASE_RETRY and r.status_code >= 500:
                await asyncio.sleep(HEALTH_WAIT_SEC)
                continue
            return last_task

        task_id = r.json().get("task_id")
        try:
            task = await poll_task(client, token, task_id)
        except TimeoutError as exc:
            task = {
                "status": "failed",
                "error": str(exc),
                "task_id": task_id,
            }
        except httpx.HTTPError as exc:
            task = {
                "status": "failed",
                "error": str(exc),
                "task_id": task_id,
            }

        task["wall_seconds"] = round(time.time() - t0, 1)
        task["attempts"] = attempt
        task["verdict"] = evaluate_case(case, task)
        last_task = task
        if task["verdict"] in ("PASS", "SKIP"):
            return task
        if attempt < CASE_RETRY:
            print(
                f"[retry] {cid} attempt {attempt} -> {task.get('status')}, "
                f"retrying...",
                flush=True,
            )
            await asyncio.sleep(HEALTH_WAIT_SEC)
    return last_task


async def run_matrix(
    *,
    resolution: str = "720P",
    width: int | None = None,
    height: int | None = None,
    duration: int = 5,
    ref_path: Path | None = None,
    resume: bool = False,
    from_case: str | None = None,
) -> dict:
    import _prompt_debug_phase2 as p2

    p2.POLL_TIMEOUT = POLL_TIMEOUT
    ref = ref_path or DEFAULT_REF
    if not ref.is_file():
        raise FileNotFoundError(f"reference image missing: {ref}")

    existing = load_existing_report() if resume else {}
    tasks_out: dict[str, dict] = dict(existing.get("cases") or {})
    wall_start = time.time()
    if resume and existing.get("wall_seconds_total"):
        wall_start -= float(existing["wall_seconds_total"])

    audio_path = resolve_audio_path()
    run_ids = case_ids_from(from_case)

    async with httpx.AsyncClient(timeout=120.0) as client:
        await wait_backend_ready(client)
        token = await login_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        ref_url = await upload_image_file(client, token, ref, filename=ref.name)
        audio_url: str | None = None
        if audio_path:
            try:
                audio_url = await upload_audio_file(client, token, audio_path)
            except Exception as exc:
                audio_url = None
                print(f"[warn] audio upload failed: {exc}", flush=True)

        for case in CASES:
            cid = case["id"]
            if cid not in run_ids:
                continue
            if should_skip_case(case, tasks_out, resume=resume):
                print(f"=== {cid} SKIP (resume) ===", flush=True)
                continue

            print(f"=== {cid} {case.get('note')} ===", flush=True)
            task = await run_single_case(
                client,
                token=token,
                headers=headers,
                case=case,
                ref_url=ref_url,
                audio_url=audio_url,
                resolution=resolution,
                width=width,
                height=height,
                duration=duration,
            )
            tasks_out[cid] = task

            payload = finalize_payload(
                tasks_out,
                resolution=resolution,
                width=width,
                height=height,
                duration=duration,
                ref=ref,
                audio_path=audio_path,
                wall_start=wall_start,
                resumed=resume,
                from_case=from_case,
            )
            write_report(payload)
            await asyncio.sleep(CASE_GAP_SEC)

    payload = finalize_payload(
        tasks_out,
        resolution=resolution,
        width=width,
        height=height,
        duration=duration,
        ref=ref,
        audio_path=audio_path,
        wall_start=wall_start,
        resumed=resume,
        from_case=from_case,
    )
    write_report(payload)
    print(
        json.dumps(
            {"pass": payload["pass"], "tables": payload["tables"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", default="720P")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--ref", type=Path, default=DEFAULT_REF)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="跳过已 PASS/SKIP 的 case，并增量写入报告",
    )
    parser.add_argument(
        "--from-case",
        default=None,
        help="从指定 case id 开始跑（可与 --resume 联用）",
    )
    args = parser.parse_args()
    try:
        payload = asyncio.run(
            run_matrix(
                resolution=args.resolution,
                width=args.width,
                height=args.height,
                duration=args.duration,
                ref_path=args.ref,
                resume=args.resume,
                from_case=args.from_case,
            )
        )
        return 0 if payload.get("pass") else 1
    except Exception as exc:
        payload = {
            "label": "ltx23_gpu_matrix",
            "pass": False,
            "crash": True,
            "error": str(exc),
        }
        write_report(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
