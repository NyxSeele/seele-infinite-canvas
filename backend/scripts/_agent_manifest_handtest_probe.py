#!/usr/bin/env python3
"""Pipeline Manifest 回归探针：Agent 主链前三步（无浏览器、禁止 text mock）。"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT.parent / "docs" / "AGENT_MANIFEST_PROBE_RESULT.json"

# Backend package root + scripts helpers (NOT baseline's 429→MOCK path).
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from _agent_trace_baseline_probe import (  # noqa: E402
    apply_create_text_note,
    apply_outline_node,
    apply_text_response,
    empty_snapshot,
    get_text_model,
    headers,
    load_admin_password,
    parse_sse,
    snapshot_from_nodes,
)

SOURCE_IDEA = "帮我做一个30秒品牌宣传片，主题是重庆火锅，要有故事感"
MAX_ROUNDS = 12
AGENT_RUN_TIMEOUT = 120.0
SCRIPT_DEADLINE_S = 600.0
TEXT_POLL_TIMEOUT_S = 180.0
TEXT_429_RETRIES = 3
TEXT_429_SLEEP_S = 8.0
EXPECTED_STEPS = ("create_text_note", "start_text_generation", "generate_outline")

# 内测说明：GENERATION_MAX_CONCURRENT 建议保持 2～3；勿为探针改到离谱。
# 探针依赖 release_stale + sync_slots，避免 Redis 槽泄漏导致假 429。


def log(msg: str) -> None:
    print(msg, flush=True)


def wait_for_backend(timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE}/api/health", timeout=5)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def restart_backend_uvicorn() -> bool:
    """Restart local uvicorn on 7788 (no supervisor dependency)."""
    try:
        # Only kill listeners on 7788 uvicorn — avoid thrashing if health is flapping.
        subprocess.run(
            ["pkill", "-f", "uvicorn main:app --host 127.0.0.1 --port 7788"],
            capture_output=True,
            timeout=10,
        )
        time.sleep(3)
        log_f = open("/root/autodl-tmp/logs/backend.out.log", "a")
        subprocess.Popen(
            [
                str(ROOT / ".venv/bin/uvicorn"),
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "7788",
            ],
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return wait_for_backend(60)
    except Exception as exc:
        log(f"uvicorn restart failed: {exc}")
    return False


def ensure_backend() -> tuple[bool, str]:
    if wait_for_backend(5):
        return True, "health ok"
    log("health not 200 — restarting uvicorn")
    if restart_backend_uvicorn():
        return True, "restarted uvicorn, health ok"
    return False, "backend unavailable after uvicorn restart"


def login_with_fallback(client: httpx.Client, password: str) -> tuple[str | None, str]:
    for username in ("seele", "admin"):
        try:
            r = client.post(
                f"{BASE}/api/auth/login",
                json={"username_or_email": username, "password": password},
                timeout=30,
            )
            if r.status_code == 200:
                return r.json()["access_token"], username
            log(f"login {username} failed: HTTP {r.status_code} {r.text[:200]}")
        except httpx.HTTPError as exc:
            log(f"login {username} error: {exc}")
    return None, ""


def prepare_generation_slots(username: str, *, max_age_seconds: int = 60) -> dict:
    """释放僵尸 active/processing 任务并校正 Redis 槽（探针前置）。

    uvicorn 重启会丢掉 asyncio.create_task，DB 中 sp_structure 可能长期 processing。
    """
    from datetime import timedelta

    from db.session import SessionLocal
    from models import Task, User
    from services.generation_guard import (
        ACTIVE_TASK_STATUSES,
        count_active_tasks,
        release_stale_active_tasks,
        sync_slots_from_db,
    )
    from services.generation_slots import release_slot_for_task
    from services.redis_client import get_redis

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            return {"error": f"user {username} not found"}
        before, _ = count_active_tasks(db, user.id)
        # generation_guard.release_stale_active_tasks is async (Comfy probe path).
        stale = asyncio.run(
            release_stale_active_tasks(db, user.id, max_age_seconds=max_age_seconds)
        )
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        zombies = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.status.in_(ACTIVE_TASK_STATUSES),
                Task.created_at < cutoff,
            )
            .all()
        )
        extra = 0
        for task in zombies:
            release_slot_for_task(task)
            task.status = "failed"
            task.error = "probe cleanup: stale active/processing task"
            task.result = None
            extra += 1
        sync_slots_from_db(db, user.id)
        db.commit()
        after, _ = count_active_tasks(db, user.id)
        r = get_redis()
        redis_slots = int(r.get(f"gen:active:user:{user.id}") or 0) if r else None
        return {
            "user_id": user.id,
            "active_before": before,
            "stale_released": stale,
            "zombie_failed": extra,
            "active_after": after,
            "redis_slots_after": redis_slots,
        }
    finally:
        db.close()


def generate_outline_strict(client, token, screenplay_text, source_idea):
    """Real outline API with longer poll; never mock."""
    from _agent_trace_baseline_probe import poll_async_json_task

    t0 = time.time()
    r = client.post(
        f"{BASE}/api/screenplay/structure-from-text",
        headers=headers(token),
        json={
            "text": screenplay_text,
            "target_duration_sec": 30,
            "source_idea": source_idea,
        },
        timeout=180,
    )
    if r.status_code != 200:
        return time.time() - t0, None, r.text[:500]
    body = r.json()
    task_id = body.get("task_id")
    if task_id and "scenes" not in body:
        try:
            body = poll_async_json_task(client, token, task_id, timeout_s=300)
        except Exception as exc:
            return time.time() - t0, None, str(exc)[:500]
    return time.time() - t0, body, None


def start_text_task_strict(
    client: httpx.Client,
    token: str,
    note_id: str,
    prompt: str,
    model_id: str,
) -> tuple[float, str, str, str]:
    """Real /api/tasks/text only. Retry 429 a few times; never MOCK_SCREENPLAY."""
    t0 = time.time()
    response_id = f"text-response-{uuid.uuid4().hex[:8]}"
    last_detail = ""
    for attempt in range(1, TEXT_429_RETRIES + 1):
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
        if r.status_code == 429:
            last_detail = r.text[:300]
            log(f"text task 429 attempt {attempt}/{TEXT_429_RETRIES}: {last_detail}")
            if attempt < TEXT_429_RETRIES:
                time.sleep(TEXT_429_SLEEP_S)
                continue
            return (
                time.time() - t0,
                response_id,
                "failed_429",
                f"429 after {TEXT_429_RETRIES} retries: {last_detail}",
            )
        if r.status_code >= 400:
            return time.time() - t0, response_id, "failed", r.text[:300]
        task_id = r.json().get("task_id")
        deadline = time.time() + TEXT_POLL_TIMEOUT_S
        content = ""
        status = "generating"
        while time.time() < deadline:
            tr = client.get(
                f"{BASE}/api/tasks/{task_id}",
                headers=headers(token),
                timeout=30,
            )
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
                return time.time() - t0, response_id, "completed", str(content)
            if status == "failed":
                return (
                    time.time() - t0,
                    response_id,
                    "failed",
                    td.get("error") or "text failed",
                )
            time.sleep(2)
        return time.time() - t0, response_id, "timeout", "text poll timeout"
    return time.time() - t0, response_id, "failed_429", last_detail


def execute_step_strict(
    client: httpx.Client,
    token: str,
    step: dict,
    *,
    nodes: list,
    edges: list,
    messages: list,
    source_idea: str,
) -> tuple[str | None, str | None, str | None]:
    """Local executor: create_text_note / start_text_generation (strict) / generate_outline."""
    name = step.get("step")
    data = step.get("data") or {}

    if name == "create_text_note":
        apply_create_text_note(nodes, data)
        messages.append({"role": "assistant", "content": "已创建文本输入卡"})
        return None, None, None

    if name == "start_text_generation":
        note_id = data.get("source_id")
        note = next((n for n in nodes if n["id"] == note_id), None)
        if note is None and nodes:
            # Agent 有时不带 source_id；取最近 text_note
            note = next((n for n in reversed(nodes) if n.get("type") == "text_note"), None)
            note_id = (note or {}).get("id")
        prompt = (
            (note or {}).get("full_prompt")
            or (note or {}).get("content_preview")
            or source_idea
        )
        model_id = get_text_model(client, token)
        if not model_id:
            return "no text model registered", None, None
        elapsed, response_id, status, content = start_text_task_strict(
            client, token, note_id, prompt, model_id
        )
        log(f"text task strict {elapsed:.1f}s status={status} len={len(str(content))}")
        if status != "completed" or not str(content).strip():
            return f"text task {status}: {content}", None, None
        apply_text_response(nodes, note_id, response_id, str(content), "completed", edges)
        messages.append({"role": "assistant", "content": "剧本文本已生成"})
        return None, "real_completed", str(content)

    if name == "generate_outline":
        text_nodes = [n for n in nodes if n["type"] == "text_response"]
        screenplay = ""
        if text_nodes:
            node = text_nodes[-1]
            screenplay = (node.get("content") or node.get("content_preview") or "").strip()
        if not screenplay.strip():
            return "no screenplay text", None, None
        # Clear stuck processing leftovers from prior killed uvicorn workers.
        try:
            prepare_generation_slots("seele", max_age_seconds=30)
        except Exception as exc:
            log(f"pre-outline slot cleanup skipped: {exc}")
        last_err = None
        for attempt in range(1, 4):
            if not wait_for_backend(30):
                last_err = "backend down before outline"
                log(f"outline wait backend failed attempt {attempt}")
                # Only restart if health is actually down — never pkill a healthy
                # worker mid-structure task.
                restart_backend_uvicorn()
                continue
            try:
                _elapsed, o_data, o_err = generate_outline_strict(
                    client, token, screenplay, source_idea
                )
            except httpx.HTTPError as exc:
                last_err = str(exc)
                log(f"outline HTTP error attempt {attempt}: {exc}")
                time.sleep(3)
                continue
            if o_err or not o_data:
                last_err = o_err or "outline empty"
                log(f"outline err attempt {attempt}: {last_err}")
                if "timed out" in str(last_err) or "Connection" in str(last_err):
                    prepare_generation_slots("seele", max_age_seconds=10)
                    time.sleep(2)
                    continue
                return last_err, None, None
            resp_id = text_nodes[-1]["id"] if text_nodes else None
            apply_outline_node(nodes, edges, resp_id, o_data)
            messages.append({"role": "assistant", "content": "大纲已生成"})
            return None, None, screenplay
        return last_err or "outline failed", None, None

    return f"unsupported step {name}", None, None


def run_agent(
    client: httpx.Client,
    token: str,
    project_id: str,
    messages: list[dict],
    snapshot: dict,
) -> tuple[float, list[dict], list[dict], str, list[dict]]:
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
        timeout=AGENT_RUN_TIMEOUT,
    )
    elapsed = time.time() - t0
    r.raise_for_status()
    events = parse_sse(r.text)
    actions = [e["action"] for e in events if e.get("event") == "action"]
    errors = [e for e in events if e.get("event") == "error"]
    thinking = next((e.get("content") for e in events if e.get("event") == "thinking"), "")
    return elapsed, actions, errors, thinking, events


def pick_ask_user_reply(ask_user: dict) -> str:
    opts = ask_user.get("options") or []
    if not opts:
        return "继续"
    pick = opts[0]
    title = pick.get("title") or pick.get("label") or "方案一"
    return f"我选择「{title}」"


def relative_order_ok(recorded: list[str], expected: tuple[str, ...]) -> bool:
    pos = 0
    for step in recorded:
        if pos < len(expected) and step == expected[pos]:
            pos += 1
    return pos == len(expected)


def read_env_flag(name: str) -> str | None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return None


def ensure_probe_project(client: httpx.Client, token: str) -> str:
    probe_name = f"manifest-probe-{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={"name": probe_name, "canvas_data": {"nodes": [], "edges": []}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("id") or str(uuid.uuid4())


def main() -> int:
    started = time.time()
    run_at = datetime.now(timezone.utc).isoformat()
    report: dict = {
        "run_at": run_at,
        "base_url": BASE,
        "checks": {},
        "recorded_steps": [],
        "rounds": [],
        "issues": [],
        "warnings": [],
        "env": {
            "AGENT_MOCK_GENERATION": read_env_flag("AGENT_MOCK_GENERATION"),
            "GENERATION_MAX_CONCURRENT": read_env_flag("GENERATION_MAX_CONCURRENT"),
        },
        "text_generation_mode": None,
        "pass": False,
    }

    ok, health_msg = ensure_backend()
    report["checks"]["health"] = {"pass": ok, "detail": health_msg}
    if not ok:
        report["issues"].append(health_msg)
        _finalize(report, started)
        return 1

    password = load_admin_password()
    nodes: list[dict] = []
    edges: list[dict] = []
    messages: list[dict] = [{"role": "user", "content": SOURCE_IDEA}]
    recorded_steps: list[str] = []

    with httpx.Client(timeout=300.0) as client:
        token, username = login_with_fallback(client, password)
        report["login_user"] = username
        if not token:
            report["issues"].append("login failed for seele and admin")
            _finalize(report, started)
            return 1

        slot_info = prepare_generation_slots(username)
        report["slots"] = slot_info
        log(f"slots cleanup: {slot_info}")

        pr = client.get(
            f"{BASE}/api/agent/pipeline/velora_canvas",
            headers=headers(token),
            timeout=30,
        )
        manifest_ok = pr.status_code == 200
        stage_names: list[str] = []
        if manifest_ok:
            stages = pr.json().get("stages") or []
            stage_names = [s.get("name") for s in stages]
            manifest_ok = len(stage_names) == 9 and all(
                name in stage_names for name in EXPECTED_STEPS + ("manage_cast", "manage_scene")
            )
        report["checks"]["manifest_api"] = {
            "pass": manifest_ok,
            "status": pr.status_code,
            "stage_count": len(stage_names),
            "stage_names": stage_names,
        }
        if not manifest_ok:
            report["issues"].append(
                f"GET /api/agent/pipeline/velora_canvas failed or stages!=9: {pr.status_code}"
            )

        project_id = ensure_probe_project(client, token)
        report["project_id"] = project_id
        log(f"project_id={project_id} login={username}")

        need_continue = False
        for round_idx in range(1, MAX_ROUNDS + 1):
            if time.time() - started > SCRIPT_DEADLINE_S:
                report["issues"].append("script deadline exceeded")
                break

            if need_continue:
                messages.append({"role": "user", "content": "继续"})
                need_continue = False

            snapshot = snapshot_from_nodes(nodes, edges)
            try:
                elapsed, actions, errors, thinking, _events = run_agent(
                    client, token, project_id, messages, snapshot
                )
            except Exception as exc:
                report["issues"].append(f"round {round_idx} agent/run failed: {exc}")
                break

            round_info = {
                "round": round_idx,
                "elapsed_s": round(elapsed, 2),
                "action_types": [a.get("type") for a in actions],
                "errors": errors,
                "thinking_preview": (thinking or "")[:120],
            }

            ask_user = next((a for a in actions if a.get("type") == "ask_user"), None)
            pipeline_step = next((a for a in actions if a.get("type") == "pipeline_step"), None)

            if ask_user and not pipeline_step:
                pick_msg = pick_ask_user_reply(ask_user)
                round_info["auto_pick"] = pick_msg
                messages.append(
                    {
                        "role": "assistant",
                        "content": ask_user.get("question") or "请选择创意方向",
                    }
                )
                messages.append({"role": "user", "content": pick_msg})
                report["rounds"].append(round_info)
                continue

            if pipeline_step:
                step_name = pipeline_step.get("step") or ""
                round_info["pipeline_step"] = step_name
                if step_name and (not recorded_steps or recorded_steps[-1] != step_name):
                    recorded_steps.append(step_name)

                err, text_mode, _sp = execute_step_strict(
                    client,
                    token,
                    pipeline_step,
                    nodes=nodes,
                    edges=edges,
                    messages=messages,
                    source_idea=SOURCE_IDEA,
                )
                round_info["execute_error"] = err
                if text_mode:
                    report["text_generation_mode"] = text_mode
                if err:
                    report["issues"].append(f"round {round_idx} execute {step_name}: {err}")
                    report["rounds"].append(round_info)
                    if step_name == "start_text_generation" and "429" in str(err):
                        break
                    if step_name in EXPECTED_STEPS:
                        break
                else:
                    need_continue = True
            elif any(a.get("type") == "done" for a in actions):
                need_continue = True

            report["rounds"].append(round_info)

            if relative_order_ok(recorded_steps, EXPECTED_STEPS):
                if any(n.get("type") == "outline" for n in nodes):
                    break

        report["recorded_steps"] = recorded_steps
        order_ok = relative_order_ok(recorded_steps, EXPECTED_STEPS)
        outline_in_snapshot = any(n.get("type") == "outline" for n in nodes)
        report["checks"]["pipeline_steps"] = {
            "pass": order_ok,
            "recorded": recorded_steps,
            "expected_relative": list(EXPECTED_STEPS),
        }
        report["checks"]["outline_in_snapshot"] = {
            "pass": outline_in_snapshot,
            "outline_count": sum(1 for n in nodes if n.get("type") == "outline"),
        }

        mode = report.get("text_generation_mode") or ""
        text_real = isinstance(mode, str) and mode.startswith("real")
        report["checks"]["text_real"] = {"pass": text_real, "mode": mode}
        if not text_real:
            report["issues"].append(
                f"text_generation_mode must be real_* (got {mode!r}); mock forbidden"
            )

        if not order_ok:
            report["issues"].append(
                f"step order mismatch: got {recorded_steps}, expected relative {EXPECTED_STEPS}"
            )
        if not outline_in_snapshot:
            report["issues"].append("no outline node in snapshot after probe")

    report["pass"] = (
        report["checks"].get("manifest_api", {}).get("pass")
        and report["checks"].get("pipeline_steps", {}).get("pass")
        and report["checks"].get("outline_in_snapshot", {}).get("pass")
        and report["checks"].get("text_real", {}).get("pass")
        and not report["issues"]
    )

    _finalize(report, started)
    return 0 if report["pass"] else 2


def _finalize(report: dict, started: float) -> None:
    report["duration_s"] = round(time.time() - started, 2)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    verdict = "PASS" if report.get("pass") else "FAIL"
    log(f"MANIFEST_HANDTEST={verdict}")
    log(f"report -> {OUT_PATH}")
    log(f"recorded_steps={report.get('recorded_steps')}")
    log(f"text_generation_mode={report.get('text_generation_mode')}")
    if report.get("issues"):
        log("issues:")
        for issue in report["issues"]:
            log(f"  - {issue}")


if __name__ == "__main__":
    raise SystemExit(main())
