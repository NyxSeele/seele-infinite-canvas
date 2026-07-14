#!/usr/bin/env python3
"""Agent trace 基线：雨夜重庆 3 镜 → 创意卡片 → 大纲 → 分镜表，收集 A1–A4 trace。"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path("/root/autodl-tmp/logs/backend.out.log")
OUT_PATH = Path("/root/autodl-tmp/logs/agent_trace_baseline.json")

SCENARIO = "雨夜重庆，一个女人独自等待，3个镜头"

MOCK_SCREENPLAY = """【00:00-00:08】雨夜站台
女人独自站在重庆轻轨站外的雨棚下，霓虹在积水里碎成光斑。她攥着手机，屏幕反复亮起又熄灭。
景别：中景。运镜：缓慢推近。光影：冷色路灯与暖色霓虹对比。

【00:08-00:16】等待
雨势渐大，女人把风衣领口拉高，望向空荡的阶梯。远处车灯划过湿漉漉的街面。
景别：全景转中景。运镜：横摇。光影：高反差，雨丝逆光。

【00:16-00:24】离去
她深吸一口气，转身走入雨幕，背影在红色尾灯中渐远。
景别：远景。运镜：固定后缓慢拉远。光影：剪影，城市雾感。
"""


def load_admin_password() -> str:
    env_path = ROOT / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_ADMIN_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_ADMIN_PASSWORD not found")


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def login(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "admin", "password": load_admin_password()},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def run_agent(client, token, project_id, messages, snapshot) -> tuple[float, list, list, str, list]:
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/agent/run",
        headers=headers(token),
        json={
            "project_id": project_id,
            "canvas_snapshot": snapshot,
            "messages": messages,
            "execution_mode": "manual",
        },
        timeout=180,
    )
    elapsed = time.time() - t0
    r.raise_for_status()
    events = parse_sse(r.text)
    actions = [e["action"] for e in events if e.get("event") == "action"]
    errors = [e for e in events if e.get("event") == "error"]
    thinking = next((e.get("content") for e in events if e.get("event") == "thinking"), "")
    return elapsed, actions, errors, thinking, events


def empty_snapshot() -> dict:
    return {
        "nodes": [],
        "edges": [],
        "selected_node_ids": [],
        "total_node_count": 0,
        "snapshot_truncated": False,
        "omitted_node_count": 0,
    }


def snapshot_from_nodes(nodes, edges=None) -> dict:
    edges = edges or []
    return {
        "nodes": nodes,
        "edges": edges,
        "selected_node_ids": [],
        "total_node_count": len(nodes),
        "snapshot_truncated": False,
        "omitted_node_count": 0,
    }


def apply_create_text_note(nodes, data) -> str:
    nid = f"text-note-{uuid.uuid4().hex[:8]}"
    intent = (data.get("intent") or "screenplay").lower()
    text_mode = "chat" if intent == "chat" else "screenplay"
    nodes.append(
        {
            "id": nid,
            "type": "text_note",
            "position": {"x": 120, "y": 160},
            "content_preview": (data.get("prompt") or "")[:150],
            "full_prompt": (data.get("prompt") or "").strip(),
            "label": data.get("label") or "文本",
            "text_mode": text_mode,
            "intent": text_mode,
        }
    )
    return nid


def get_text_model(client: httpx.Client, token: str) -> str | None:
    db_path = ROOT / "aistudio.db"
    if db_path.exists():
        import sqlite3

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM registered_models WHERE category='text' AND enabled=1 "
            "ORDER BY is_default_text DESC, id"
        )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        if rows:
            return rows[0]
    return None


def start_text_task(client, token, note_id, prompt, model_id):
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/tasks/text",
        headers=headers(token),
        json={
            "model": model_id,
            "prompt": prompt,
            "count": 1,
            "node_id": note_id,
            "screenplay_mode": True,
        },
        timeout=120,
    )
    if r.status_code in (429, 500, 502, 503):
        # 限流/瞬时错误：回退 mock，保证 A3/A4 链路可继续校准
        print(f"text task HTTP {r.status_code}; fallback MOCK_SCREENPLAY", flush=True)
        return time.time() - t0, f"text-response-{uuid.uuid4().hex[:8]}", "completed", MOCK_SCREENPLAY
    r.raise_for_status()
    task_id = r.json().get("task_id")
    response_id = f"text-response-{uuid.uuid4().hex[:8]}"
    deadline = time.time() + 300
    content = ""
    status = "generating"
    while time.time() < deadline:
        tr = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        if tr.status_code != 200:
            break
        td = tr.json()
        status = td.get("status") or status
        if status == "completed":
            result = td.get("result")
            if isinstance(result, dict):
                content = result.get("text") or result.get("content") or ""
            elif isinstance(result, str):
                content = result
            else:
                content = td.get("text") or ""
            if isinstance(content, list):
                content = content[0] if content else ""
            break
        if status == "failed":
            return time.time() - t0, response_id, "failed", td.get("error") or "text failed"
        time.sleep(2)
    return time.time() - t0, response_id, status, content


def apply_text_response(nodes, note_id, response_id, content, status, edges):
    full = (content or "") if status == "completed" else ""
    preview = "[生成中]" if status == "generating" else (full[:500] if full else "")
    nodes.append(
        {
            "id": response_id,
            "type": "text_response",
            "position": {"x": 520, "y": 160},
            "content": full,
            "content_preview": preview,
            "label": "文本回复",
            "status": status,
            "text_mode": "screenplay",
            "intent": "screenplay",
        }
    )
    edges.append({"source": note_id, "target": response_id})


def poll_async_json_task(client, token, task_id: str, *, timeout_s: float = 300) -> dict:
    """轮询 screenplay 等异步 JSON 任务，返回 completed 时的 result 对象。"""
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        tr = client.get(
            f"{BASE}/api/tasks/{task_id}",
            headers=headers(token),
            timeout=30,
        )
        tr.raise_for_status()
        last = tr.json()
        status = (last.get("status") or "").lower()
        if status == "completed":
            result = last.get("result")
            if isinstance(result, str) and result.strip().startswith(("{", "[")):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    pass
            if isinstance(result, dict):
                return result
            return {"result": result}
        if status == "failed":
            raise RuntimeError(last.get("error") or f"task {task_id} failed")
        time.sleep(1.0)
    raise TimeoutError(f"async task {task_id} timed out after {timeout_s}s")


def generate_outline(client, token, screenplay_text, source_idea):
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/screenplay/structure-from-text",
        headers=headers(token),
        json={
            "text": screenplay_text,
            "target_duration_sec": 24,
            "source_idea": source_idea,
        },
        timeout=180,
    )
    elapsed = time.time() - t0
    if r.status_code != 200:
        return elapsed, None, r.text[:500]
    body = r.json()
    task_id = body.get("task_id")
    if task_id and "scenes" not in body:
        try:
            body = poll_async_json_task(client, token, task_id, timeout_s=180)
        except Exception as exc:
            return time.time() - t0, None, str(exc)[:500]
    return time.time() - t0, body, None


def apply_outline_node(nodes, edges, response_id, o_data) -> str:
    outline_id = f"outline-{uuid.uuid4().hex[:8]}"
    scenes = o_data.get("scenes") or (o_data.get("versions") or [{}])[0].get("scenes") or []
    preview = " ".join((s.get("title") or s.get("content") or "")[:40] for s in scenes[:3])
    nodes.append(
        {
            "id": outline_id,
            "type": "outline",
            "position": {"x": 900, "y": 160},
            "content_preview": preview[:150] or "大纲",
            "label": o_data.get("title") or "大纲",
            "loading": False,
            "scene_count": len(scenes),
            "scenes": scenes,
            "targetVideoDurationSec": 24,
        }
    )
    if response_id:
        edges.append({"source": response_id, "target": outline_id})
    return outline_id


def generate_shots_api(client, token, outline_node) -> tuple[float, dict | None, str | None]:
    scenes = outline_node.get("scenes") or []
    outline_payload = json.dumps(
        {
            "title": outline_node.get("label") or "雨夜重庆",
            "scenes": scenes,
            "target_video_duration_sec": 24,
        },
        ensure_ascii=False,
        indent=2,
    )
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/screenplay/generate-shots",
        headers=headers(token),
        json={"outline": outline_payload, "target_duration_sec": 24},
        timeout=300,
    )
    elapsed = time.time() - t0
    if r.status_code != 200:
        return elapsed, None, r.text[:500]
    body = r.json()
    task_id = body.get("task_id")
    if task_id and "segments" not in body:
        try:
            body = poll_async_json_task(client, token, task_id, timeout_s=300)
        except Exception as exc:
            return time.time() - t0, None, str(exc)[:500]
    return time.time() - t0, body, None


def parse_trace_lines(log_text: str) -> list[str]:
    lines = []
    for line in log_text.splitlines():
        if "[AIStudio:trace]" not in line:
            continue
        if re.search(r"\bA[1-5]\b", line):
            lines.append(line.strip())
    return lines


def parse_trace_structured(lines: list[str]) -> dict:
    parsed: dict = {"A1": {}, "A2": {}, "A3": {}, "A4": {}, "A5": {}}
    for line in lines:
        if "A1 AGENT_INPUT" in line:
            parsed["A1"]["agent_input_line"] = line
        elif "A1 AGENT_OUTPUT" in line:
            parsed["A1"]["agent_output_line"] = line
            m = re.search(r"tokens=(\d+)", line)
            if m:
                parsed["A1"]["tokens"] = int(m.group(1))
            m2 = re.search(r"tokens_estimated=(True|False)", line)
            if m2:
                parsed["A1"]["tokens_estimated"] = m2.group(1) == "True"
        elif "A1 CREATIVE_CARDS" in line:
            parsed["A1"]["creative_cards_line"] = line
        elif "A2 TEXT_INPUT" in line:
            parsed["A2"].setdefault("text_inputs", []).append(line)
        elif "A2 TEXT_OUTPUT" in line:
            parsed["A2"].setdefault("text_outputs", []).append(line)
        elif "A3 STRUCTURE_INPUT" in line:
            parsed["A3"]["structure_input_line"] = line
        elif "A3 STRUCTURE_OUTPUT" in line:
            parsed["A3"]["structure_output_line"] = line
        elif "A3 STRUCTURE_SCENE_TITLES" in line:
            parsed["A3"]["structure_scene_titles_line"] = line
        elif "A4 SHOTS_INPUT" in line:
            parsed["A4"]["shots_input_line"] = line
        elif "A4 SHOTS_OUTPUT" in line:
            parsed["A4"]["shots_output_line"] = line
        elif "A5 BEATS_" in line:
            parsed["A5"].setdefault("beats_lines", []).append(line)
    return parsed


def execute_pipeline_step(
    client,
    token,
    step: dict,
    *,
    nodes,
    edges,
    messages,
    source_idea: str,
) -> tuple[str | None, dict | None, str | None]:
    """模拟前端 executeAgentPipelineStep，返回 (error, shots_result, screenplay_text)。"""
    name = step.get("step")
    data = step.get("data") or {}

    if name == "create_text_note":
        apply_create_text_note(nodes, data)
        messages.append({"role": "assistant", "content": "已创建文本输入卡"})
        return None, None, None

    if name == "start_text_generation":
        note_id = data.get("source_id")
        note = next((n for n in nodes if n["id"] == note_id), None)
        prompt = (
            (note or {}).get("full_prompt")
            or (note or {}).get("content_preview")
            or source_idea
        )
        model_id = get_text_model(client, token)
        if not model_id:
            response_id = f"text-response-{uuid.uuid4().hex[:8]}"
            content = MOCK_SCREENPLAY
            apply_text_response(nodes, note_id, response_id, content, "completed", edges)
            messages.append({"role": "assistant", "content": "剧本文本已生成（mock）"})
            return None, None, content
        t_elapsed, response_id, status, content = start_text_task(
            client, token, note_id, prompt, model_id
        )
        if status != "completed" or not str(content).strip():
            return f"text task {status}", None, None
        apply_text_response(nodes, note_id, response_id, str(content), "completed", edges)
        messages.append({"role": "assistant", "content": "剧本文本已生成"})
        return None, None, str(content)

    if name == "generate_outline":
        text_nodes = [n for n in nodes if n["type"] == "text_response"]
        screenplay = ""
        if text_nodes:
            node = text_nodes[-1]
            screenplay = (node.get("content") or node.get("content_preview") or "").strip()
        if not screenplay.strip():
            return "no screenplay text", None, None
        o_elapsed, o_data, o_err = generate_outline(client, token, screenplay, source_idea)
        if o_err or not o_data:
            return o_err or "outline empty", None, None
        resp_id = text_nodes[-1]["id"] if text_nodes else None
        apply_outline_node(nodes, edges, resp_id, o_data)
        messages.append({"role": "assistant", "content": "大纲已生成"})
        return None, None, screenplay

    if name == "generate_script_table":
        outline_node = next((n for n in nodes if n["type"] == "outline"), None)
        if not outline_node:
            return "no outline node", None, None
        s_elapsed, shots_result, s_err = generate_shots_api(client, token, outline_node)
        if s_err or not shots_result:
            return s_err or "generate-shots empty", None, None
        sid = f"script-table-{uuid.uuid4().hex[:8]}"
        segments = shots_result.get("segments") or []
        row_count = sum(len(s.get("shots") or []) for s in segments)
        nodes.append(
            {
                "id": sid,
                "type": "script_table",
                "position": {"x": 1200, "y": 160},
                "content_preview": f"分镜表 {row_count} 镜",
                "label": "分镜表",
                "row_count": row_count,
                "loading": False,
                "source_outline_id": outline_node["id"],
            }
        )
        edges.append({"source": outline_node["id"], "target": sid})
        messages.append({"role": "assistant", "content": "分镜表已生成"})
        return None, shots_result, None

    return f"unsupported step {name}", None, None


def main() -> int:
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    run_at = datetime.now(timezone.utc).isoformat()
    agent_rounds: list[dict] = []
    messages: list[dict] = []
    nodes: list[dict] = []
    edges: list[dict] = []
    issues: list[str] = []

    with httpx.Client(timeout=300.0) as client:
        token = login(client)
        pr = client.get(f"{BASE}/api/canvas/projects", headers=headers(token), timeout=30)
        pr.raise_for_status()
        projects = pr.json().get("projects") or []
        if not projects:
            cr = client.post(
                f"{BASE}/api/canvas/projects",
                headers=headers(token),
                json={"name": "Agent Trace Baseline", "canvas_data": {"nodes": [], "edges": []}},
                timeout=30,
            )
            cr.raise_for_status()
            project_id = cr.json().get("id")
        else:
            project_id = projects[0]["id"]
        if not project_id:
            print("NO_PROJECT", flush=True)
            return 1
        print(f"project={project_id}", flush=True)

        # R1 — 创意方向
        messages.append({"role": "user", "content": SCENARIO})
        e1, actions1, err1, think1, ev1 = run_agent(
            client, token, project_id, messages, empty_snapshot()
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

        pick_msg = SCENARIO
        if ask and (ask.get("options") or []):
            opt = (ask.get("options") or [{}])[0]
            title = opt.get("title") or opt.get("label") or "雨夜独白"
            focus = opt.get("focus") or "侧重：城市雨夜的孤独等待"
            pick_msg = f"我选择「{title}」（{focus}）"
            messages.append({"role": "assistant", "content": ask.get("question") or "请选择创意方向"})
            messages.append({"role": "user", "content": pick_msg})
        elif not ask:
            step1 = next((a for a in actions1 if a.get("type") == "pipeline_step"), None)
            if step1:
                err, _, _ = execute_pipeline_step(
                    client,
                    token,
                    step1,
                    nodes=nodes,
                    edges=edges,
                    messages=messages,
                    source_idea=SCENARIO,
                )
                if err:
                    issues.append(f"R1 direct step: {err}")
            else:
                issues.append("R1: no ask_user and no pipeline_step")

        shots_result = None
        screenplay_text = ""
        round_num = 1
        max_rounds = 12

        while round_num < max_rounds and shots_result is None:
            round_num += 1
            if round_num > 2:
                messages.append({"role": "user", "content": "继续"})
            snap = snapshot_from_nodes(nodes, edges) if nodes else empty_snapshot()
            elapsed, actions, errors, thinking, _ = run_agent(
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
            err, shots_result, sp = execute_pipeline_step(
                client,
                token,
                step,
                nodes=nodes,
                edges=edges,
                messages=messages,
                source_idea=SCENARIO,
            )
            if sp:
                screenplay_text = sp
            if err:
                issues.append(f"R{round_num} execute {step.get('step')}: {err}")
                break
            if shots_result is not None:
                agent_rounds[-1]["generate_shots_api"] = {
                    "segments_count": len(shots_result.get("segments") or []),
                }
                break

        if shots_result is None:
            issues.append("pipeline did not reach generate_script_table")

    log_slice = ""
    if LOG_PATH.is_file():
        log_slice = LOG_PATH.read_text(encoding="utf-8", errors="replace")[log_start:]
    trace_lines = parse_trace_lines(log_slice)
    if not trace_lines and LOG_PATH.is_file():
        trace_lines = parse_trace_lines(LOG_PATH.read_text(encoding="utf-8", errors="replace"))

    parsed_traces = parse_trace_structured(trace_lines)
    if shots_result:
        segments = shots_result.get("segments") or []
        all_shots = []
        for seg in segments:
            for shot in seg.get("shots") or []:
                all_shots.append(shot)
        parsed_traces["A4"]["shots_detail"] = all_shots

    out = {
        "scenario": SCENARIO,
        "run_at": run_at,
        "project_id": project_id,
        "agent_rounds": agent_rounds,
        "trace_lines": trace_lines,
        "parsed": parsed_traces,
        "issues": issues,
        "screenplay_preview": (screenplay_text or "")[:800],
        "outline_scenes_count": len(
            next((n.get("scenes") or [] for n in nodes if n.get("type") == "outline"), [])
        ),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", flush=True)
    print(f"trace_lines={len(trace_lines)} issues={issues}", flush=True)
    return 0 if shots_result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
