#!/usr/bin/env python3
"""路线 B：分镜表 3 镜批量出图 → 批量转视频 GPU 验收探针。"""
from __future__ import annotations

import ast
import json
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
LOG_PATH = Path("/root/autodl-tmp/logs/backend.out.log")
OUT_PATH = Path("/root/autodl-tmp/logs/route_b_batch_results.json")
POLL_INTERVAL = 5
POLL_TIMEOUT = 1800

THEME_CONTEXT = "雨夜胡同，电影感叙事。主角林晓：长直黑发，白色风衣。"
CHARACTER_REFS = [{"name": "林晓", "appearance": "长直黑发，白色风衣"}]
QUALITY_PRESET = "cinematic"
IMAGE_MODEL = "flux-dev"
VIDEO_MODEL = "wan-i2v"
REFERENCE_FACE_URL: str | None = None

SHOTS = [
    {
        "id": "001",
        "shot_number": 1,
        "description": "雨夜胡同，女人站在路灯下",
    },
    {
        "id": "002",
        "shot_number": 2,
        "description": "女人缓缓转身，侧脸对镜",
    },
    {
        "id": "003",
        "shot_number": 3,
        "description": "女人走入雨中，背影渐远",
    },
]


def load_admin_password() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_ADMIN_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_ADMIN_PASSWORD not found")


def summarize(text: str | None, n: int = 200) -> str:
    if not text:
        return ""
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def parse_traces_from_log(trace_ids: dict[str, str], log_start_offset: int = 0) -> dict[str, dict]:
    if not LOG_PATH.is_file():
        return {cid: {} for cid in trace_ids}
    # 按 trace_id 精确匹配，读全量日志避免 log_start 漏掉首镜 L0
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    out: dict[str, dict] = {tid: {} for tid in trace_ids.values()}
    id_by_short = {tid: cid for cid, tid in trace_ids.items()}

    for line in text.splitlines():
        if "[AIStudio:trace]" not in line:
            continue
        for tid, case_id in id_by_short.items():
            if tid not in line:
                continue
            if "L0 COMPILED" in line:
                out[tid]["l0_compiled_line"] = line
            if "L0 BUILT" in line:
                out[tid]["l0_line"] = line
            if "L1 SUBMIT" in line:
                out[tid]["l1_line"] = line
            if "L3 TRANSLATED" in line:
                out[tid]["l3_line"] = line
            if "L4 WORKFLOW" in line:
                brace = line.find("{", line.find("L4 WORKFLOW"))
                if brace > 0:
                    try:
                        out[tid]["l4"] = ast.literal_eval(line[brace:])
                    except (SyntaxError, ValueError):
                        out[tid]["l4_raw"] = line[brace:]
                out[tid]["l4_line"] = line

    return {cid: out[tid] for cid, tid in trace_ids.items()}


def abs_media_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("/"):
        return f"{BASE}{url}"
    return url


def login(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "admin", "password": load_admin_password()},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def poll_task(client: httpx.Client, token: str, task_id: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        print(f"  poll {task_id[:8]}… status={status} progress={data.get('progress', 0)}%", flush=True)
        if status in ("completed", "failed"):
            data["_elapsed_s"] = round(time.time() - start, 1)
            return data
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {task_id} timed out")


def task_result_url(data: dict) -> str | None:
    return data.get("result_url") or data.get("image_url") or data.get("video_url") or data.get("result")


def upload_reference_face(client: httpx.Client, token: str, local_path: str) -> str:
    """上传本地正脸参考图，返回带 ticket 的 /api/uploads URL。"""
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(f"reference face not found: {local_path}")
    headers = {"Authorization": f"Bearer {token}"}
    with path.open("rb") as fh:
        files = {"file": (path.name, fh, "image/jpeg")}
        r = client.post(f"{BASE}/api/upload/image", headers=headers, files=files, timeout=60)
    r.raise_for_status()
    return r.json()["url"]


def resolve_image_reference(
    *,
    built: dict,
    prev_image_url: str | None,
    reference_face_url: str | None,
) -> tuple[str | None, float | None]:
    """flux-pulid 用固定正脸；flux-dev 沿用上一镜链式 reference。"""
    if IMAGE_MODEL == "flux-pulid":
        if reference_face_url:
            return reference_face_url, None
        return None, None
    if built.get("use_visual_reference") and prev_image_url:
        return abs_media_url(prev_image_url), built.get("img2img_denoise") or 0.7
    return None, None


def build_shot(
    client: httpx.Client,
    token: str,
    *,
    shot: dict,
    prior_shots: list[dict],
    has_prev_image: bool,
    trace_id: str,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    compile_body = {
        "scene_desc": shot["description"],
        "character_refs": CHARACTER_REFS,
        "style_preset": QUALITY_PRESET,
        "model_target": "flux",
        "trace_id": trace_id,
    }
    cr = client.post(
        f"{BASE}/api/prompt/compile", headers=headers, json=compile_body, timeout=60
    )
    cr.raise_for_status()
    compiled = cr.json()
    description = (compiled.get("positive_prompt") or shot["description"]).strip()

    body = {
        "description": description,
        "model_id": IMAGE_MODEL,
        "global_style": "",
        "quality_preset_id": QUALITY_PRESET,
        "theme_context": THEME_CONTEXT,
        "prior_shots": prior_shots,
        "shot_number": shot["shot_number"],
        "visual_continuity": True,
        "continuity_mode": True,
        "has_previous_shot_image": has_prev_image,
        "has_manual_reference": False,
        "trace_id": trace_id,
        "character_refs_count": len(CHARACTER_REFS),
    }
    r = client.post(f"{BASE}/api/prompt/build-shot", headers=headers, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def submit_image(
    client: httpx.Client,
    token: str,
    *,
    prompt: str,
    display_prompt: str,
    trace_id: str,
    reference_image: str | None,
    denoise: float | None,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "display_prompt": display_prompt,
        "quality_preset_id": QUALITY_PRESET,
        "ratio": "16:9",
        "quality": "2K",
        "count": 1,
        "node_id": f"route-b-img-{uuid.uuid4().hex[:8]}",
        "trace_id": trace_id,
    }
    if reference_image:
        body["reference_image"] = reference_image
        body["reference_images"] = [reference_image]
        if denoise is not None:
            body["denoise"] = denoise
    r = client.post(f"{BASE}/api/tasks/image", headers=headers, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def submit_video(
    client: httpx.Client,
    token: str,
    *,
    prompt: str,
    trace_id: str,
    ref_url: str,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "quality_preset_id": QUALITY_PRESET,
        "generation_mode": "keyframe",
        "ratio": "16:9",
        "resolution": "720P",
        "duration": 3,
        "audio": False,
        "count": 1,
        "node_id": f"route-b-vid-{uuid.uuid4().hex[:8]}",
        "trace_id": trace_id,
        "first_frame": ref_url,
        "last_frame": ref_url,
    }
    r = client.post(f"{BASE}/api/tasks/video", headers=headers, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def check_l4_appearance(positive: str) -> bool:
    low = positive.lower()
    has_name = "lin xiao" in low or "林晓" in positive
    has_hair = "black hair" in low or "黑发" in positive
    has_coat = "trench" in low or "coat" in low or "风衣" in positive
    return has_name and has_hair and has_coat


def check_l0(positive: str, shot_id: str) -> dict[str, bool]:
    checks = {
        "has_theme": "雨夜" in positive or "胡同" in positive,
        "has_character": "黑发" in positive or "风衣" in positive or "林晓" in positive,
        "has_cinematic": "cinematic" in positive.lower() or "电影" in positive,
        "has_continuity": True,
    }
    if shot_id in ("002", "003"):
        checks["has_continuity"] = "承接上一镜头" in positive
    return checks


def main() -> int:
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    results: dict = {
        "image_shots": [],
        "video_shots": [],
        "pytest_note": "run separately",
    }
    image_trace_ids: dict[str, str] = {}
    video_trace_ids: dict[str, str] = {}

    with httpx.Client(timeout=120.0) as client:
        token = login(client)
        prior_for_build: list[dict] = []
        prev_image_url: str | None = None

        print("\n=== Route B Step 3: batch images (3 shots) ===", flush=True)
        for shot in SHOTS:
            trace_id = str(uuid.uuid4())
            image_trace_ids[shot["id"]] = trace_id
            built = build_shot(
                client,
                token,
                shot=shot,
                prior_shots=prior_for_build,
                has_prev_image=bool(prev_image_url),
                trace_id=trace_id,
            )
            positive = (built.get("prompt") or "").strip()
            display = (built.get("display_prompt") or shot["description"]).strip()
            l0_checks = check_l0(positive, shot["id"])
            print(f"\n--- Shot {shot['id']} L0 ---", flush=True)
            print(f"  positive: {summarize(positive, 300)}", flush=True)
            print(f"  checks: {l0_checks}", flush=True)

            denoise = None
            ref = None
            ref, denoise = resolve_image_reference(
                built=built,
                prev_image_url=prev_image_url,
                reference_face_url=REFERENCE_FACE_URL,
            )

            submitted = submit_image(
                client,
                token,
                prompt=positive,
                display_prompt=display,
                trace_id=trace_id,
                reference_image=ref,
                denoise=denoise,
            )
            task_id = submitted["task_id"]
            finished = poll_task(client, token, task_id)
            result_url = task_result_url(finished)
            shot_result = {
                "shot_id": shot["id"],
                "trace_id": trace_id,
                "task_id": task_id,
                "status": finished.get("status"),
                "elapsed_s": finished.get("_elapsed_s"),
                "l0_positive": positive,
                "l0_checks": l0_checks,
                "used_prev_ref": bool(ref),
                "result_url": result_url,
            }
            results["image_shots"].append(shot_result)
            if finished.get("status") != "completed" or not result_url:
                print(f"FAIL image shot {shot['id']}: {finished}", flush=True)
                break
            prev_image_url = result_url if result_url.startswith("/") else result_url
            prior_for_build.append(
                {"shot_number": shot["shot_number"], "description": shot["description"]}
            )

        print("\n=== Route B Step 4: batch videos (3 shots) ===", flush=True)
        for img in results["image_shots"]:
            if img.get("status") != "completed":
                continue
            shot_id = img["shot_id"]
            trace_id = img["trace_id"]
            video_trace_ids[shot_id] = trace_id
            ref_url = abs_media_url(img["result_url"]) or img["result_url"]
            prompt = img["l0_positive"]
            submitted = submit_video(
                client,
                token,
                prompt=prompt,
                trace_id=trace_id,
                ref_url=ref_url,
            )
            task_id = submitted["task_id"]
            finished = poll_task(client, token, task_id)
            video_result = {
                "shot_id": shot_id,
                "trace_id": trace_id,
                "task_id": task_id,
                "status": finished.get("status"),
                "elapsed_s": finished.get("_elapsed_s"),
                "prompt_used": summarize(prompt, 300),
                "ref_url": ref_url,
                "result_url": task_result_url(finished),
            }
            results["video_shots"].append(video_result)
            if finished.get("status") != "completed":
                print(f"FAIL video shot {shot_id}: {finished}", flush=True)

    image_traces = parse_traces_from_log(image_trace_ids, log_start)
    video_traces = parse_traces_from_log(video_trace_ids, log_start)
    results["image_traces"] = image_traces
    results["video_traces"] = video_traces

    for shot in results["image_shots"]:
        sid = shot["shot_id"]
        l4 = (image_traces.get(sid) or {}).get("l4") or {}
        pos = (l4.get("positive_prompt") or "") if isinstance(l4, dict) else ""
        shot["l4_positive_snippet"] = summarize(pos, 200)
        shot["l4_has_cinematic"] = "cinematic" in pos.lower()

    for shot in results["video_shots"]:
        sid = shot["shot_id"]
        l4 = (video_traces.get(sid) or {}).get("l4") or {}
        traces = video_traces.get(sid) or {}
        shot["l0_compiled_line"] = traces.get("l0_compiled_line")
        shot["l0_built_line"] = traces.get("l0_line")
        if isinstance(l4, dict):
            pos = l4.get("positive_prompt") or ""
            shot["l4_positive_snippet"] = summarize(pos, 200)
            shot["l4_has_cinematic"] = "cinematic" in pos.lower()
            shot["l4_ref"] = l4.get("reference_filename") or l4.get("start_reference_filename")
            shot["l4_has_continuity"] = "承接" in pos or "承接" in shot.get("prompt_used", "")
            shot["l4_has_appearance"] = check_l4_appearance(pos)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", flush=True)

    img_ok = all(s.get("status") == "completed" for s in results["image_shots"])
    vid_ok = all(s.get("status") == "completed" for s in results["video_shots"])
    l0_ok = all(all(s.get("l0_checks", {}).values()) for s in results["image_shots"])
    compile_trace_ok = all(
        (image_traces.get(s["shot_id"]) or {}).get("l0_compiled_line")
        for s in results["image_shots"]
    )
    vid_003 = next((s for s in results["video_shots"] if s.get("shot_id") == "003"), None)
    vid_003_appearance_ok = bool(vid_003 and vid_003.get("l4_has_appearance"))
    if vid_003:
        print(
            f"\nShot 003 video L4 appearance: {vid_003.get('l4_has_appearance')} "
            f"snippet={vid_003.get('l4_positive_snippet', '')[:120]}",
            flush=True,
        )
    print(f"compile_trace_ok={compile_trace_ok}", flush=True)
    return (
        0
        if img_ok
        and vid_ok
        and l0_ok
        and compile_trace_ok
        and vid_003_appearance_ok
        and len(results["image_shots"]) == 3
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
