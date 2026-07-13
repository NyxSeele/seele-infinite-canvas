#!/usr/bin/env python3
"""路线 C：Agent A1–A4 自动分镜表 → 动态 rows → 路线 B 式批量出图/转视频。"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import _agent_trace_baseline_probe as baseline  # noqa: E402
import _route_b_batch_probe as route_b  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.image_consistency import check_consistency  # noqa: E402

BASE = baseline.BASE
ROOT = baseline.ROOT
LOG_PATH = baseline.LOG_PATH
OUT_PATH = Path("/root/autodl-tmp/logs/route_c_results.json")
SCENARIO = baseline.SCENARIO
SHOTS_TARGET = 3
POLL_TIMEOUT = 1800

# 路线 B 固定文案，用于断言 rows 非硬编码来源
ROUTE_B_HARDCODED_DESCRIPTIONS = {
    s["description"] for s in route_b.SHOTS
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Route C agent + GPU batch probe")
    p.add_argument(
        "--require-ask-user",
        action="store_true",
        help="Fail if R1 skips creative cards (ask_user)",
    )
    p.add_argument(
        "--skip-gpu",
        action="store_true",
        help="Stop after agent/A4 rows phase (no image/video batch)",
    )
    p.add_argument(
        "--model",
        default="flux-dev",
        choices=("flux-dev", "flux-pulid"),
        help="Image model for GPU batch phase",
    )
    p.add_argument(
        "--reference-face",
        default=None,
        help="Local face image path (required for flux-pulid)",
    )
    return p.parse_args()


def cleanup_pending_tasks() -> int:
    db = ROOT / "aistudio.db"
    if not db.is_file():
        return 0
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "UPDATE tasks SET status='failed' WHERE status IN ('pending','running')"
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def segments_to_script_payload(raw_segments: list | None) -> tuple[list, list]:
    """与 frontend segmentsToScriptPayload 等价的 rows 物化。"""
    segments: list[dict] = []
    rows: list[dict] = []
    shot_num = 1
    for si, seg in enumerate(raw_segments or []):
        seg_id = str(seg.get("id") or f"seg-{si + 1}")
        segments.append(
            {
                "id": seg_id,
                "title": (seg.get("title") or "").strip() or f"片段 {si + 1}",
                "description": (seg.get("description") or "").strip(),
                "duration": float(seg.get("duration") or 0),
            }
        )
        for shot in seg.get("shots") or []:
            prompt = (shot.get("prompt") or "").strip()
            row_id = f"{shot_num:03d}"
            rows.append(
                {
                    "id": row_id,
                    "shot_number": shot_num,
                    "segmentId": seg_id,
                    "duration": shot.get("duration") or 8,
                    "prompt": prompt,
                    "description": prompt,
                }
            )
            shot_num += 1
    return segments, rows


def apply_script_table_from_shots(
    nodes: list,
    edges: list,
    outline_node: dict,
    shots_result: dict,
) -> tuple[list, list]:
    segments, rows = segments_to_script_payload(shots_result.get("segments") or [])
    sid = f"script-table-{uuid.uuid4().hex[:8]}"
    nodes.append(
        {
            "id": sid,
            "type": "script_table",
            "position": {"x": 1200, "y": 160},
            "content_preview": f"分镜表 {len(rows)} 镜",
            "label": "分镜表",
            "row_count": len(rows),
            "loading": False,
            "source_outline_id": outline_node["id"],
            "segments": segments,
            "rows": rows,
        }
    )
    edges.append({"source": outline_node["id"], "target": sid})
    return segments, rows


def extract_theme_context(screenplay: str, scenario: str) -> str:
    text = " ".join((screenplay or scenario).split())
    return text[:200] if text else scenario


def extract_character_refs(screenplay: str) -> list[dict]:
    appearance: list[str] = []
    if "风衣" in screenplay:
        appearance.append("风衣")
    if "黑发" in screenplay or "长发" in screenplay:
        appearance.append("黑发")
    if "女人" in screenplay:
        name = "女人"
    elif re.search(r"[\u4e00-\u9fff]{2,4}", screenplay):
        m = re.search(r"([\u4e00-\u9fff]{2,4})(?:独自|站在|望向|转身)", screenplay)
        name = m.group(1) if m else "主角"
    else:
        name = "主角"
    if appearance:
        return [{"name": name, "appearance": "，".join(appearance)}]
    return [{"name": name, "appearance": "电影感人物"}]


def extract_appearance_terms(screenplay: str, character_refs: list[dict]) -> list[str]:
    terms: list[str] = []
    for ref in character_refs:
        if ref.get("name"):
            terms.append(ref["name"])
        for part in (ref.get("appearance") or "").split("，"):
            part = part.strip()
            if part:
                terms.append(part)
    for kw in ("女人", "风衣", "黑发", "雨夜", "重庆"):
        if kw in screenplay and kw not in terms:
            terms.append(kw)
    return terms


def validate_a4_quality(shots_result: dict, rows: list[dict]) -> list[str]:
    issues: list[str] = []
    segments = shots_result.get("segments") or []
    total_shots = sum(len(s.get("shots") or []) for s in segments)
    if total_shots < SHOTS_TARGET:
        issues.append(f"A4 total_shots={total_shots} < {SHOTS_TARGET}")
    if len(rows) != total_shots:
        issues.append(f"rows len={len(rows)} != total_shots={total_shots}")
    for row in rows:
        desc = (row.get("description") or "").strip()
        if len(desc) < 50:
            issues.append(f"shot {row.get('id')} prompt too short ({len(desc)} chars)")
        if desc in ROUTE_B_HARDCODED_DESCRIPTIONS:
            issues.append(f"shot {row.get('id')} matches route_b hardcoded description")
    return issues


def rows_to_gpu_shots(rows: list[dict]) -> list[dict]:
    return [
        {
            "id": row["id"],
            "shot_number": row["shot_number"],
            "description": row["description"],
        }
        for row in rows
    ]


def check_l0_route_c(positive: str, shot_id: str, theme_terms: list[str]) -> dict[str, bool]:
    low = positive.lower()
    checks = {
        "has_theme": any(t in positive for t in theme_terms if t in ("雨夜", "重庆", "胡同", "站台")),
        "has_character": "女人" in positive or "主角" in positive or "woman" in low or any(
            t in positive for t in theme_terms if len(t) <= 4
        ),
        "has_cinematic": (
            "cinematic" in low
            or "电影" in positive
            or "photorealistic" in low
            or "35mm" in low
            or "photography" in low
        ),
        "has_continuity": True,
    }
    if not checks["has_theme"]:
        checks["has_theme"] = any(t in positive for t in theme_terms[:3]) or "chongqing" in low
    if shot_id in ("002", "003"):
        checks["has_continuity"] = "承接上一镜头" in positive
    return checks


def check_l4_appearance_route_c(positive: str, appearance_terms: list[str]) -> bool:
    if not appearance_terms:
        return True
    low = positive.lower()
    hits = 0
    for term in appearance_terms:
        if term in positive:
            hits += 1
            continue
        if term == "女人" and "woman" in low:
            hits += 1
        elif term == "风衣" and ("trench" in low or "coat" in low or "风衣" in positive):
            hits += 1
        elif term == "黑发" and ("black hair" in low or "黑发" in positive):
            hits += 1
        elif term == "雨夜" and ("rain" in low or "雨" in positive):
            hits += 1
        elif term == "重庆" and ("chongqing" in low or "重庆" in positive):
            hits += 1
    return hits >= min(2, len(appearance_terms))


def run_agent_phase(
    client: httpx.Client,
    token: str,
    *,
    require_ask_user: bool,
) -> dict:
    """Agent A1–A4，物化真实 rows。"""
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    agent_rounds: list[dict] = []
    messages: list[dict] = []
    nodes: list[dict] = []
    edges: list[dict] = []
    issues: list[str] = []
    pipeline_steps: list[str] = []
    creative_cards_skipped = False
    shots_result = None
    screenplay_text = ""
    rows: list[dict] = []
    segments: list[dict] = []

    pr = client.get(f"{BASE}/api/canvas/projects", headers=baseline.headers(token), timeout=30)
    pr.raise_for_status()
    projects = pr.json().get("projects") or []
    if not projects:
        cr = client.post(
            f"{BASE}/api/canvas/projects",
            headers=baseline.headers(token),
            json={"name": "Route C Probe", "canvas_data": {"nodes": [], "edges": []}},
            timeout=30,
        )
        cr.raise_for_status()
        project_id = cr.json().get("id")
    else:
        project_id = projects[0]["id"]
    if not project_id:
        return {"ok": False, "issues": ["no project_id"], "log_start": log_start}

    print(f"project={project_id}", flush=True)
    messages.append({"role": "user", "content": SCENARIO})
    e1, actions1, err1, think1, _ = baseline.run_agent(
        client, token, project_id, messages, baseline.empty_snapshot()
    )
    ask = next((a for a in actions1 if a.get("type") == "ask_user"), None)
    agent_rounds.append(
        {
            "round": 1,
            "user": SCENARIO,
            "elapsed_s": round(e1, 1),
            "actions": actions1,
            "errors": err1,
            "thinking": think1,
        }
    )
    print(f"R1 actions={[a.get('type') for a in actions1]} ask={bool(ask)}", flush=True)

    if require_ask_user and not ask:
        issues.append("C1: --require-ask-user but R1 has no ask_user")
    if not ask:
        creative_cards_skipped = True

    pick_msg = SCENARIO
    if ask and (ask.get("options") or []):
        opts = ask.get("options") or []
        if len(opts) < 2 and require_ask_user:
            issues.append(f"C1: options_count={len(opts)} < 2")
        opt = opts[0]
        title = opt.get("title") or opt.get("label") or "雨夜独白"
        focus = opt.get("focus") or "侧重：城市雨夜的孤独等待"
        pick_msg = f"我选择「{title}」（{focus}）"
        messages.append({"role": "assistant", "content": ask.get("question") or "请选择创意方向"})
        messages.append({"role": "user", "content": pick_msg})
    elif not ask:
        step1 = next((a for a in actions1 if a.get("type") == "pipeline_step"), None)
        if step1:
            err, _, _, _ = execute_pipeline_step_route_c(
                client,
                token,
                step1,
                nodes=nodes,
                edges=edges,
                messages=messages,
                source_idea=SCENARIO,
                rows_out=[],
            )
            if err:
                issues.append(f"R1 direct step: {err}")
            elif step1.get("step"):
                pipeline_steps.append(step1["step"])
        else:
            issues.append("R1: no ask_user and no pipeline_step")

    round_num = 1
    max_rounds = 12
    while round_num < max_rounds and shots_result is None:
        round_num += 1
        if round_num > 2:
            messages.append({"role": "user", "content": "继续"})
        snap = baseline.snapshot_from_nodes(nodes, edges) if nodes else baseline.empty_snapshot()
        elapsed, actions, errors, thinking, _ = baseline.run_agent(
            client, token, project_id, messages, snap
        )
        step = next((a for a in actions if a.get("type") == "pipeline_step"), None)
        agent_rounds.append(
            {
                "round": round_num,
                "user": pick_msg if round_num == 2 else "继续",
                "elapsed_s": round(elapsed, 1),
                "actions": actions,
                "errors": errors,
                "thinking": thinking,
                "pipeline_step": step.get("step") if step else None,
            }
        )
        print(
            f"R{round_num} step={step.get('step') if step else None} nodes={len(nodes)}",
            flush=True,
        )
        if errors:
            issues.append(f"R{round_num} agent errors: {errors}")
            break
        if not step:
            issues.append(f"R{round_num}: no pipeline_step")
            break
        step_name = step.get("step")
        err, sr, sp, new_rows = execute_pipeline_step_route_c(
            client,
            token,
            step,
            nodes=nodes,
            edges=edges,
            messages=messages,
            source_idea=SCENARIO,
            rows_out=rows,
        )
        if step_name and step_name not in pipeline_steps:
            pipeline_steps.append(step_name)
        if sp:
            screenplay_text = sp
        if err:
            issues.append(f"R{round_num} execute {step_name}: {err}")
            break
        if sr is not None:
            shots_result = sr
            rows = new_rows
            segments, _ = segments_to_script_payload(sr.get("segments") or [])
            agent_rounds[-1]["generate_shots_api"] = {
                "segments_count": len(segments),
                "total_shots": len(rows),
            }
            break

    if shots_result is None:
        issues.append("pipeline did not reach generate_script_table")

    expected_steps = [
        "create_text_note",
        "start_text_generation",
        "generate_outline",
        "generate_script_table",
    ]
    for step in expected_steps:
        if step not in pipeline_steps:
            issues.append(f"missing pipeline_step: {step}")

    a4_issues = []
    if shots_result and rows:
        a4_issues = validate_a4_quality(shots_result, rows)
        issues.extend(a4_issues)

    log_slice = ""
    if LOG_PATH.is_file():
        log_slice = LOG_PATH.read_text(encoding="utf-8", errors="replace")[log_start:]
    trace_lines = baseline.parse_trace_lines(log_slice)
    if not trace_lines and LOG_PATH.is_file():
        trace_lines = baseline.parse_trace_lines(
            LOG_PATH.read_text(encoding="utf-8", errors="replace")
        )
    parsed_traces = baseline.parse_trace_structured(trace_lines)
    if shots_result:
        all_shots = []
        for seg in shots_result.get("segments") or []:
            for shot in seg.get("shots") or []:
                all_shots.append(shot)
        parsed_traces["A4"]["shots_detail"] = all_shots

    outline_scenes = next(
        (n.get("scenes") or [] for n in nodes if n.get("type") == "outline"),
        [],
    )
    if len(screenplay_text) < 500:
        issues.append(f"A2 screenplay too short: {len(screenplay_text)}")
    if len(outline_scenes) < SHOTS_TARGET:
        issues.append(
            f"A3 scenes_count={len(outline_scenes)} < {SHOTS_TARGET}"
        )

    return {
        "ok": shots_result is not None and not issues,
        "project_id": project_id,
        "agent_rounds": agent_rounds,
        "pipeline_steps": pipeline_steps,
        "creative_cards_skipped": creative_cards_skipped,
        "shots_result": shots_result,
        "rows": rows,
        "segments": segments,
        "screenplay_text": screenplay_text,
        "issues": issues,
        "trace_lines": trace_lines,
        "parsed": parsed_traces,
        "outline_scenes_count": len(outline_scenes),
        "log_start": log_start,
    }


def execute_pipeline_step_route_c(
    client,
    token,
    step: dict,
    *,
    nodes,
    edges,
    messages,
    source_idea: str,
    rows_out: list,
) -> tuple[str | None, dict | None, str | None, list]:
    """扩展 baseline execute_pipeline_step，generate_script_table 写入真实 rows。"""
    name = step.get("step")
    data = step.get("data") or {}

    if name == "create_text_note":
        baseline.apply_create_text_note(nodes, data)
        messages.append({"role": "assistant", "content": "已创建文本输入卡"})
        return None, None, None, rows_out

    if name == "start_text_generation":
        note_id = data.get("source_id")
        note = next((n for n in nodes if n["id"] == note_id), None)
        prompt = (
            (note or {}).get("full_prompt")
            or (note or {}).get("content_preview")
            or source_idea
        )
        model_id = baseline.get_text_model(client, token)
        if not model_id:
            return "no text model enabled", None, None, rows_out
        _, response_id, status, content = baseline.start_text_task(
            client, token, note_id, prompt, model_id
        )
        if status != "completed" or not str(content).strip():
            return f"text task {status}", None, None, rows_out
        baseline.apply_text_response(nodes, note_id, response_id, str(content), "completed", edges)
        messages.append({"role": "assistant", "content": "剧本文本已生成"})
        return None, None, str(content), rows_out

    if name == "generate_outline":
        text_nodes = [n for n in nodes if n["type"] == "text_response"]
        screenplay = ""
        if text_nodes:
            node = text_nodes[-1]
            screenplay = (node.get("content") or node.get("content_preview") or "").strip()
        if not screenplay.strip():
            return "no screenplay text", None, None, rows_out
        _, o_data, o_err = baseline.generate_outline(client, token, screenplay, source_idea)
        if o_err or not o_data:
            return o_err or "outline empty", None, None, rows_out
        resp_id = text_nodes[-1]["id"] if text_nodes else None
        baseline.apply_outline_node(nodes, edges, resp_id, o_data)
        messages.append({"role": "assistant", "content": "大纲已生成"})
        return None, None, screenplay, rows_out

    if name == "generate_script_table":
        outline_node = next((n for n in nodes if n["type"] == "outline"), None)
        if not outline_node:
            return "no outline node", None, None, rows_out
        _, shots_result, s_err = baseline.generate_shots_api(client, token, outline_node)
        if s_err or not shots_result:
            return s_err or "generate-shots empty", None, None, rows_out
        _, new_rows = apply_script_table_from_shots(nodes, edges, outline_node, shots_result)
        messages.append({"role": "assistant", "content": "分镜表已生成"})
        return None, shots_result, None, new_rows

    return f"unsupported step {name}", None, None, rows_out


def run_gpu_batch(
    client: httpx.Client,
    token: str,
    rows: list[dict],
    screenplay: str,
    log_start: int,
) -> dict:
    """路线 B 式批量 GPU，SHOTS 来自 A4 rows。"""
    route_b.POLL_TIMEOUT = POLL_TIMEOUT
    theme_context = extract_theme_context(screenplay, SCENARIO)
    character_refs = extract_character_refs(screenplay)
    appearance_terms = extract_appearance_terms(screenplay, character_refs)
    theme_terms = [t for t in appearance_terms if t in ("雨夜", "重庆", "胡同", "站台", "女人")]

    route_b.THEME_CONTEXT = theme_context
    route_b.CHARACTER_REFS = character_refs

    shots = rows_to_gpu_shots(rows)
    results: dict = {"image_shots": [], "video_shots": [], "theme_context": theme_context}
    image_trace_ids: dict[str, str] = {}
    video_trace_ids: dict[str, str] = {}

    prior_for_build: list[dict] = []
    prev_image_url: str | None = None

    print("\n=== Route C GPU: batch images ===", flush=True)
    for shot in shots:
        trace_id = str(uuid.uuid4())
        image_trace_ids[shot["id"]] = trace_id
        built = route_b.build_shot(
            client,
            token,
            shot=shot,
            prior_shots=prior_for_build,
            has_prev_image=bool(prev_image_url),
            trace_id=trace_id,
        )
        positive = (built.get("prompt") or "").strip()
        display = (built.get("display_prompt") or shot["description"]).strip()
        l0_checks = check_l0_route_c(positive, shot["id"], theme_terms)
        print(f"\n--- Shot {shot['id']} L0 ---", flush=True)
        print(f"  positive: {route_b.summarize(positive, 300)}", flush=True)
        print(f"  checks: {l0_checks}", flush=True)

        denoise = None
        ref = None
        ref, denoise = route_b.resolve_image_reference(
            built=built,
            prev_image_url=prev_image_url,
            reference_face_url=route_b.REFERENCE_FACE_URL,
        )

        submitted = route_b.submit_image(
            client,
            token,
            prompt=positive,
            display_prompt=display,
            trace_id=trace_id,
            reference_image=ref,
            denoise=denoise,
        )
        task_id = submitted["task_id"]
        finished = route_b.poll_task(client, token, task_id)
        result_url = route_b.task_result_url(finished)
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
            "source_description": shot["description"][:120],
        }
        results["image_shots"].append(shot_result)
        if finished.get("status") != "completed" or not result_url:
            print(f"FAIL image shot {shot['id']}: {finished}", flush=True)
            break
        prev_image_url = result_url
        prior_for_build.append(
            {"shot_number": shot["shot_number"], "description": shot["description"]}
        )

    print("\n=== Route C GPU: batch videos ===", flush=True)
    for img in results["image_shots"]:
        if img.get("status") != "completed":
            continue
        shot_id = img["shot_id"]
        trace_id = img["trace_id"]
        video_trace_ids[shot_id] = trace_id
        ref_url = route_b.abs_media_url(img["result_url"]) or img["result_url"]
        prompt = img["l0_positive"]
        submitted = route_b.submit_video(
            client,
            token,
            prompt=prompt,
            trace_id=trace_id,
            ref_url=ref_url,
        )
        task_id = submitted["task_id"]
        finished = route_b.poll_task(client, token, task_id)
        video_result = {
            "shot_id": shot_id,
            "trace_id": trace_id,
            "task_id": task_id,
            "status": finished.get("status"),
            "elapsed_s": finished.get("_elapsed_s"),
            "prompt_used": route_b.summarize(prompt, 300),
            "ref_url": ref_url,
            "result_url": route_b.task_result_url(finished),
        }
        results["video_shots"].append(video_result)
        if finished.get("status") != "completed":
            print(f"FAIL video shot {shot_id}: {finished}", flush=True)

    image_traces = route_b.parse_traces_from_log(image_trace_ids, log_start)
    video_traces = route_b.parse_traces_from_log(video_trace_ids, log_start)
    results["image_traces"] = image_traces
    results["video_traces"] = video_traces
    results["appearance_terms"] = appearance_terms

    for shot in results["image_shots"]:
        sid = shot["shot_id"]
        l4 = (image_traces.get(sid) or {}).get("l4") or {}
        pos = (l4.get("positive_prompt") or "") if isinstance(l4, dict) else ""
        shot["l4_positive_snippet"] = route_b.summarize(pos, 200)

    for shot in results["video_shots"]:
        sid = shot["shot_id"]
        l4 = (video_traces.get(sid) or {}).get("l4") or {}
        traces = video_traces.get(sid) or {}
        shot["l0_compiled_line"] = traces.get("l0_compiled_line")
        shot["l0_built_line"] = traces.get("l0_line")
        if isinstance(l4, dict):
            pos = l4.get("positive_prompt") or ""
            shot["l4_positive_snippet"] = route_b.summarize(pos, 200)
            shot["l4_has_continuity"] = "承接" in pos or "承接" in shot.get("prompt_used", "")
            shot["l4_has_appearance"] = check_l4_appearance_route_c(pos, appearance_terms)

    return results


def evaluate_gpu_results(gpu: dict, rows: list[dict]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    img_ok = all(s.get("status") == "completed" for s in gpu.get("image_shots") or [])
    vid_ok = all(s.get("status") == "completed" for s in gpu.get("video_shots") or [])
    if len(gpu.get("image_shots") or []) != len(rows):
        issues.append("image batch count mismatch")
    if len(gpu.get("video_shots") or []) != len(rows):
        issues.append("video batch count mismatch")
    if not img_ok:
        issues.append("not all images completed")
    if not vid_ok:
        issues.append("not all videos completed")

    l0_ok = True
    for s in gpu.get("image_shots") or []:
        checks = s.get("l0_checks") or {}
        sid = s.get("shot_id")
        if sid == "001":
            if not all(checks.values()):
                l0_ok = False
        elif sid in ("002", "003"):
            if not checks.get("has_continuity") or not checks.get("has_theme"):
                l0_ok = False
        elif not all(checks.values()):
            l0_ok = False
    if not l0_ok:
        issues.append("L0 checks failed for some image shots")

    compile_trace_ok = all(
        (gpu.get("image_traces") or {}).get(s["shot_id"], {}).get("l0_compiled_line")
        for s in gpu.get("image_shots") or []
    )
    if not compile_trace_ok:
        issues.append("missing L0 compile trace lines")

    for sid in ("002", "003"):
        img = next((s for s in gpu.get("image_shots") or [] if s.get("shot_id") == sid), None)
        if img and not img.get("l0_checks", {}).get("has_continuity"):
            issues.append(f"shot {sid} missing continuity in L0")

    last_id = rows[-1]["id"] if rows else "003"
    vid_last = next(
        (s for s in gpu.get("video_shots") or [] if s.get("shot_id") == last_id),
        None,
    )
    if vid_last and not vid_last.get("l4_has_appearance"):
        issues.append(f"shot {last_id} video L4 missing appearance keywords")

    ok = img_ok and vid_ok and l0_ok and compile_trace_ok and not issues
    return ok, issues


def main() -> int:
    args = parse_args()
    run_at = datetime.now(timezone.utc).isoformat()
    cleaned = cleanup_pending_tasks()
    print(f"cleaned pending tasks: {cleaned}", flush=True)

    agent_phase: dict = {}
    gpu_phase: dict | None = None
    all_issues: list[str] = []

    with httpx.Client(timeout=300.0) as client:
        token = baseline.login(client)
        agent_phase = run_agent_phase(client, token, require_ask_user=args.require_ask_user)
        all_issues.extend(agent_phase.get("issues") or [])

        if not args.skip_gpu and agent_phase.get("rows"):
            log_start = agent_phase.get("log_start", 0)
            route_b.IMAGE_MODEL = args.model
            if args.model == "flux-pulid":
                if not args.reference_face:
                    all_issues.append("flux-pulid requires --reference-face")
                else:
                    with httpx.Client(timeout=300.0) as up_client:
                        face_token = baseline.login(up_client)
                        route_b.REFERENCE_FACE_URL = route_b.upload_reference_face(
                            up_client, face_token, args.reference_face
                        )
            else:
                route_b.REFERENCE_FACE_URL = None
            gpu_phase = run_gpu_batch(
                client,
                token,
                agent_phase["rows"],
                agent_phase.get("screenplay_text") or "",
                log_start,
            )
            gpu_ok, gpu_issues = evaluate_gpu_results(gpu_phase, agent_phase["rows"])
            all_issues.extend(gpu_issues)
            agent_phase["gpu_ok"] = gpu_ok
        elif args.skip_gpu:
            print("--skip-gpu: agent phase only", flush=True)

    consistency: dict | None = None
    if gpu_phase and (gpu_phase.get("image_shots") or []):
        image_urls = [
            route_b.abs_media_url(s.get("result_url")) or s.get("result_url")
            for s in gpu_phase["image_shots"]
            if s.get("status") == "completed" and s.get("result_url")
        ]
        if len(image_urls) >= 2:
            with httpx.Client(timeout=300.0) as client:
                token = baseline.login(client)
            consistency = check_consistency(image_urls, token, base_url=BASE)

    out = {
        "scenario": SCENARIO,
        "run_at": run_at,
        "shots_target": SHOTS_TARGET,
        "creative_cards_skipped": agent_phase.get("creative_cards_skipped"),
        "pipeline_steps": agent_phase.get("pipeline_steps"),
        "project_id": agent_phase.get("project_id"),
        "agent_rounds": agent_phase.get("agent_rounds"),
        "rows_count": len(agent_phase.get("rows") or []),
        "rows_preview": [
            {"id": r["id"], "description": r["description"][:100]}
            for r in (agent_phase.get("rows") or [])[:3]
        ],
        "parsed": agent_phase.get("parsed"),
        "trace_lines_count": len(agent_phase.get("trace_lines") or []),
        "outline_scenes_count": agent_phase.get("outline_scenes_count"),
        "screenplay_len": len(agent_phase.get("screenplay_text") or ""),
        "gpu": gpu_phase,
        "consistency_phash": (consistency or {}).get("consistency_phash"),
        "consistency_threshold": (consistency or {}).get("threshold"),
        "image_model": args.model,
        "issues": all_issues,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", flush=True)
    print(f"issues={all_issues}", flush=True)

    agent_ok = (
        agent_phase.get("shots_result") is not None
        and len(agent_phase.get("rows") or []) >= SHOTS_TARGET
        and not any(i.startswith("missing pipeline_step") for i in all_issues)
        and not any(i.startswith("A4") for i in all_issues)
        and (agent_phase.get("outline_scenes_count") or 0) >= SHOTS_TARGET
    )
    gpu_ok = args.skip_gpu or agent_phase.get("gpu_ok", False)
    if args.require_ask_user and agent_phase.get("creative_cards_skipped"):
        agent_ok = False

    return 0 if agent_ok and gpu_ok and not all_issues else 1


if __name__ == "__main__":
    sys.exit(main())
