"""Agent 剧本链路探测：模拟前端多轮 Agent + 画布状态推进。"""
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
ROOT = Path(__file__).resolve().parents[1]

MOCK_SCREENPLAY = """# 镜1 晨光初醒
渝爱在重庆动物园大熊猫馆醒来，阳光透过竹林。
它伸懒腰、打哈欠，与游客温馨互动。

# 镜2 竹香早餐
渝爱挑选新鲜竹子，咀嚼声清脆，饲养员在远处微笑记录。

# 镜3 午后嬉戏
渝爱在草地上翻滚，镜头环绕，展现活泼一面。
"""


def mock_outline_nodes(nodes, edges, response_id, outline_id=None):
    outline_id = outline_id or f"outline-{uuid.uuid4().hex[:8]}"
    preview = "晨光初醒 竹香早餐 午后嬉戏"
    nodes.append(
        {
            "id": outline_id,
            "type": "outline",
            "position": {"x": 900, "y": 160},
            "content_preview": preview,
            "label": "大纲",
            "loading": False,
            "scene_count": 3,
        }
    )
    if response_id:
        edges.append({"source": response_id, "target": outline_id})
    return outline_id


def login(username: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def parse_sse_stream(resp: httpx.Response) -> list[dict]:
    events = []
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def run_agent(
    client: httpx.Client,
    token: str,
    project_id: str,
    messages,
    snapshot,
    mode="manual",
    *,
    return_events: bool = False,
):
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/agent/run",
        headers=headers(token),
        json={
            "project_id": project_id,
            "canvas_snapshot": snapshot,
            "messages": messages,
            "execution_mode": mode,
        },
        timeout=180,
    )
    elapsed = time.time() - t0
    r.raise_for_status()
    events = parse_sse_stream(r)
    actions = [e["action"] for e in events if e.get("event") == "action"]
    errors = [e for e in events if e.get("event") == "error"]
    thinking = next((e.get("content") for e in events if e.get("event") == "thinking"), "")
    if return_events:
        return elapsed, actions, errors, thinking, events
    return elapsed, actions, errors, thinking


def empty_snapshot():
    return {
        "nodes": [],
        "edges": [],
        "selected_node_ids": [],
        "total_node_count": 0,
        "snapshot_truncated": False,
        "omitted_node_count": 0,
    }


def snapshot_from_nodes(nodes, edges=None):
    edges = edges or []
    return {
        "nodes": nodes,
        "edges": edges,
        "selected_node_ids": [],
        "total_node_count": len(nodes),
        "snapshot_truncated": False,
        "omitted_node_count": 0,
    }


def apply_create_text_note(nodes, data):
    nid = f"text-note-{uuid.uuid4().hex[:8]}"
    intent = (data.get("intent") or "screenplay").lower()
    text_mode = "chat" if intent == "chat" else "screenplay"
    nodes.append(
        {
            "id": nid,
            "type": "text_note",
            "position": {"x": 120, "y": 160},
            "content_preview": (data.get("prompt") or "")[:150],
            "label": data.get("label") or "文本",
            "text_mode": text_mode,
            "intent": text_mode,
        }
    )
    return nid


def get_text_model(client, token):
    # /api/models 可能因可用性探测较慢，优先读 DB
    db_path = ROOT / "aistudio.db"
    if db_path.exists():
        import sqlite3

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM registered_models WHERE category='text' AND enabled=1 ORDER BY id"
        )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        for mid in rows:
            if "deepseek" in mid.lower():
                return mid
        if rows:
            return rows[0]
    r = client.get(f"{BASE}/api/models", headers=headers(token), timeout=120)
    if r.status_code != 200:
        return None
    items = r.json()
    if isinstance(items, dict):
        items = items.get("models") or items.get("items") or []
    for m in items:
        blob = f"{m.get('id','')} {m.get('model_string','')}".lower()
        if m.get("kind") == "text" or "deepseek" in blob or "qwen" in blob:
            return m.get("id") or m.get("model_string")
    return items[0].get("id") if items else None


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
    r.raise_for_status()
    task_id = r.json().get("task_id")
    response_id = f"text-response-{uuid.uuid4().hex[:8]}"
    nodes_wait = []
    deadline = time.time() + 180
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
        time.sleep(1.5)
    elapsed = time.time() - t0
    return elapsed, response_id, status, content


def apply_text_response(nodes, note_id, response_id, content, status):
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
        }
    )


def generate_outline(client, token, screenplay_text, source_idea):
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/screenplay/structure-from-text",
        headers=headers(token),
        json={
            "text": screenplay_text,
            "target_duration_sec": None,
            "source_idea": source_idea,
        },
        timeout=180,
    )
    elapsed = time.time() - t0
    if r.status_code != 200:
        return elapsed, None, r.text[:300]
    data = r.json()
    scenes = data.get("scenes") or (data.get("versions") or [{}])[0].get("scenes") or []
    return elapsed, data, None if scenes else "empty scenes"


def make_row_summary(row_id, shot_number, *, has_beats=False, storyboard_ready=False, has_video=False, video_generating=False):
    return {
        "id": row_id,
        "shot_number": shot_number,
        "plot_preview": f"镜{shot_number} 渝爱日常片段",
        "keyframe_count": 3 if has_beats else 0,
        "beat_prompt_count": 3 if has_beats else 0,
        "has_beats": has_beats,
        "storyboard_ready": storyboard_ready,
        "has_video": has_video,
        "video_generating": video_generating,
        "status": "idle",
    }


def apply_script_table(nodes, edges, outline_id, row_count=2):
    sid = f"script-table-{uuid.uuid4().hex[:8]}"
    rows = [
        make_row_summary(f"row-{i + 1}", i + 1)
        for i in range(row_count)
    ]
    nodes.append(
        {
            "id": sid,
            "type": "script_table",
            "position": {"x": 1200, "y": 160},
            "content_preview": f"分镜表 {row_count} 镜",
            "label": "分镜表",
            "row_count": row_count,
            "loading": False,
            "rows_summary": rows,
            "source_outline_id": outline_id,
        }
    )
    if outline_id:
        edges.append({"source": outline_id, "target": sid})
    return sid, rows


def patch_script_row(rows, row_id, **kwargs):
    for row in rows:
        if row["id"] == row_id:
            row.update(kwargs)
            return row
    return None


def split_shot_beats_api(client, token, shot_number=1):
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/prompt/split-shot-beats",
        headers=headers(token),
        json={
            "row": {
                "shot_number": shot_number,
                "duration": 8,
                "prompt": "渝爱在大熊猫馆与游客温馨互动，阳光透过竹林",
                "keyframes": [],
            },
            "cast_library": [],
            "use_llm": True,
        },
        timeout=120,
    )
    elapsed = time.time() - t0
    if r.status_code != 200:
        return elapsed, None, r.text[:300]
    data = r.json()
    beats = data.get("beats") or []
    return elapsed, data, None if beats else "empty beats"


def expect_pipeline_step(actions, step_name, label):
    step = next((a for a in actions if a.get("type") == "pipeline_step"), None)
    if not step or step.get("step") != step_name:
        return f"{label} expected {step_name} got {step}"
    return None


def _db_model(category: str) -> str | None:
    db_path = ROOT / "aistudio.db"
    if not db_path.exists():
        return None
    import sqlite3

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM registered_models WHERE category=? AND enabled=1 ORDER BY id",
        (category,),
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows[0] if rows else None


def poll_task(client, token, task_id, *, timeout=30):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        tr = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        if tr.status_code != 200:
            break
        last = tr.json()
        status = last.get("status")
        if status in ("completed", "failed"):
            return time.time(), status, last.get("result"), last.get("error")
        time.sleep(0.5)
    return time.time(), last.get("status") or "timeout", last.get("result"), last.get("error")


def run_canvas_image(
    client,
    token,
    *,
    node_id: str,
    prompt: str,
    reference_images: list[str] | None = None,
):
    model_id = _db_model("image")
    if not model_id:
        return 0.0, "failed", None, "no image model registered"
    t0 = time.time()
    payload = {
        "model": model_id,
        "prompt": prompt,
        "ratio": "16:9",
        "quality": "2K",
        "count": 1,
        "node_id": node_id,
    }
    if reference_images:
        payload["reference_images"] = reference_images
    r = client.post(
        f"{BASE}/api/tasks/image",
        headers=headers(token),
        json=payload,
        timeout=30,
    )
    if r.status_code != 200:
        return time.time() - t0, "failed", None, r.text[:300]
    task_id = r.json().get("task_id")
    _, status, result, error = poll_task(client, token, task_id, timeout=20)
    return time.time() - t0, status, result, error


def run_canvas_video(client, token, *, node_id: str, prompt: str):
    model_id = _db_model("video")
    if not model_id:
        return 0.0, "failed", None, "no video model registered"
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/tasks/video",
        headers=headers(token),
        json={
            "model": model_id,
            "prompt": prompt,
            "ratio": "16:9",
            "resolution": "720P",
            "duration": 5,
            "count": 1,
            "node_id": node_id,
        },
        timeout=30,
    )
    if r.status_code != 200:
        return time.time() - t0, "failed", None, r.text[:300]
    task_id = r.json().get("task_id")
    _, status, result, error = poll_task(client, token, task_id, timeout=25)
    return time.time() - t0, status, result, error


def parse_argv():
    args = list(sys.argv[1:])
    mode = "manual"
    skip_text = "--skip-text" in args
    if "--skip-text" in args:
        args = [a for a in args if a != "--skip-text"]
    if "--mode" in args:
        idx = args.index("--mode")
        mode = args[idx + 1] if idx + 1 < len(args) else "manual"
        del args[idx : idx + 2]
    username = args[0] if args else "admin"
    password = args[1] if len(args) > 1 else "Admin@2026!"
    return username, password, mode, skip_text


def main():
    username, password, mode, skip_text = parse_argv()
    print(f"execution_mode={mode} skip_text={skip_text}")
    issues = []
    with httpx.Client() as client:
        token = login(username, password)
        pr = client.get(f"{BASE}/api/canvas/projects", headers=headers(token), timeout=30)
        pr.raise_for_status()
        projects = pr.json().get("projects") or []
        if not projects:
            print("NO_PROJECT")
            return 1
        project_id = projects[0]["id"]
        print("project", project_id)

        messages = []
        nodes = []
        edges = []

        # Round 1 — 新主题可能先出创意卡片（意图 D），再「我选择」落卡
        user_msg = "我想做一段重庆动物园渝爱的宣传片"
        messages.append({"role": "user", "content": user_msg})
        e1, actions1, err1, _ = run_agent(
            client, token, project_id, messages, empty_snapshot(), "manual"
        )
        print(f"\n[R1] agent {e1:.1f}s actions={len(actions1)} errors={err1}")
        step = next((a for a in actions1 if a.get("type") == "pipeline_step"), None)
        ask_user = next((a for a in actions1 if a.get("type") == "ask_user"), None)
        if ask_user and (not step or step.get("step") != "create_text_note"):
            opts = ask_user.get("options") or []
            pick = opts[0] if opts else {}
            pick_title = pick.get("title") or pick.get("label") or "暖萌日常"
            pick_msg = f"我选择：{pick_title}"
            print(f"  R1 ask_user → user picks: {pick_msg}")
            messages.append({"role": "assistant", "content": ask_user.get("question") or "请选择创意方向"})
            messages.append({"role": "user", "content": pick_msg})
            e1b, actions1b, err1b, _ = run_agent(
                client, token, project_id, messages, empty_snapshot(), "manual"
            )
            print(f"  [R1b] agent {e1b:.1f}s actions={len(actions1b)} errors={err1b}")
            step = next((a for a in actions1b if a.get("type") == "pipeline_step"), None)
            if err1b:
                issues.append(f"R1b agent errors: {err1b}")
        if not step or step.get("step") != "create_text_note":
            issues.append(f"R1 expected create_text_note got {step}")
            print("FAIL R1", actions1)
            return 2
        note_id = apply_create_text_note(nodes, step.get("data") or {})
        messages.append({"role": "assistant", "content": "已创建文本输入卡"})
        print("  note_id", note_id)

        response_id = None
        outline_id = None

        # Round 2 - continue
        messages.append({"role": "user", "content": "继续"})
        e2, actions2, err2, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes), mode
        )
        print(f"\n[R2] agent {e2:.1f}s actions={len(actions2)} errors={err2}")
        step2 = next((a for a in actions2 if a.get("type") == "pipeline_step"), None)
        if not step2 or step2.get("step") != "start_text_generation":
            issues.append(f"R2 expected start_text_generation got {step2}")
        else:
            prompt = step.get("data", {}).get("prompt") or user_msg
            response_id = f"text-response-{uuid.uuid4().hex[:8]}"
            if skip_text:
                print("  skip_text: mock text_response")
                mock_content = MOCK_SCREENPLAY
                apply_text_response(nodes, note_id, response_id, mock_content, "completed")
                edges.append({"source": note_id, "target": response_id})
                messages.append({"role": "assistant", "content": "剧本文本已生成（mock）"})
            else:
                model_id = get_text_model(client, token)
                print("  text model", model_id)
                if not model_id:
                    issues.append("no text model registered")
                else:
                    t_elapsed, response_id, status, content = start_text_task(
                        client, token, note_id, prompt, model_id
                    )
                    print(f"  text task {t_elapsed:.1f}s status={status} len={len(str(content))}")
                    if t_elapsed > 60:
                        issues.append(f"text generation took {t_elapsed:.0f}s > 60s frontend timeout")
                    if status != "completed" or not str(content).strip():
                        issues.append(f"text task failed status={status}")
                        print("  text task fallback: mock text_response for downstream intent probes")
                        mock_content = MOCK_SCREENPLAY
                        apply_text_response(nodes, note_id, response_id, mock_content, "completed")
                        edges.append({"source": note_id, "target": response_id})
                        messages.append({"role": "assistant", "content": "剧本文本已生成（mock）"})
                    else:
                        apply_text_response(nodes, note_id, response_id, str(content), "completed")
                        edges.append({"source": note_id, "target": response_id})
                        messages.append({"role": "assistant", "content": "剧本文本已生成"})

        # Round 3 - outline
        messages.append({"role": "user", "content": "继续"})
        e3, actions3, err3, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), mode
        )
        print(f"\n[R3] agent {e3:.1f}s actions={len(actions3)} errors={err3}")
        step3 = next((a for a in actions3 if a.get("type") == "pipeline_step"), None)
        if not step3 or step3.get("step") != "generate_outline":
            issues.append(f"R3 expected generate_outline got {step3}")
        else:
            text_nodes = [n for n in nodes if n["type"] == "text_response"]
            screenplay = MOCK_SCREENPLAY
            if text_nodes and "[生成中]" not in text_nodes[-1].get("content_preview", ""):
                node = text_nodes[-1]
                screenplay = node.get("content") or node.get("content_preview") or MOCK_SCREENPLAY
            o_elapsed, o_data, o_err = generate_outline(client, token, screenplay, user_msg)
            print(f"  outline api {o_elapsed:.1f}s err={o_err}")
            if o_err:
                issues.append(f"outline api: {o_err}")
                print("  outline api fallback: mock outline node")
                resp_nodes = [n for n in nodes if n["type"] == "text_response"]
                rid = resp_nodes[-1]["id"] if resp_nodes else None
                outline_id = mock_outline_nodes(nodes, edges, rid)
                messages.append({"role": "assistant", "content": "大纲已生成（mock）"})
            elif o_data:
                outline_id = f"outline-{uuid.uuid4().hex[:8]}"
                scenes = o_data.get("scenes") or o_data.get("versions", [{}])[0].get("scenes", [])
                preview = " ".join(
                    (s.get("title") or s.get("content") or "")[:40] for s in scenes[:3]
                )
                nodes.append(
                    {
                        "id": outline_id,
                        "type": "outline",
                        "position": {"x": 900, "y": 160},
                        "content_preview": preview[:150] or "大纲",
                        "label": "大纲",
                        "loading": False,
                        "scene_count": len(scenes),
                    }
                )
                if response_id:
                    edges.append({"source": response_id, "target": outline_id})
                messages.append({"role": "assistant", "content": "大纲已生成"})

        # Round 4 - script table intent
        messages.append({"role": "user", "content": "继续"})
        e4, actions4, err4, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), mode
        )
        print(f"\n[R4] agent {e4:.1f}s actions={len(actions4)} errors={err4}")
        step4 = next((a for a in actions4 if a.get("type") == "pipeline_step"), None)
        print("  step4", step4.get("step") if step4 else None)
        if not step4 or step4.get("step") != "generate_script_table":
            issues.append(f"R4 expected generate_script_table got {step4}")

        # Stage 2 — simulate script table with 2 shots (linked to outline)
        if not outline_id:
            outline_nodes = [n for n in nodes if n.get("type") == "outline"]
            outline_id = outline_nodes[-1]["id"] if outline_nodes else None
        script_id, script_rows = apply_script_table(nodes, edges, outline_id, row_count=2)
        print(f"\n  script_table {script_id} rows={len(script_rows)}")

        # R5 — split_shot_beats (镜 1)
        messages.append({"role": "user", "content": "继续"})
        e5, actions5, err5, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R5] agent {e5:.1f}s actions={len(actions5)} errors={err5}")
        issue5 = expect_pipeline_step(actions5, "split_shot_beats", "R5")
        if issue5:
            issues.append(issue5)
        else:
            b_elapsed, b_data, b_err = split_shot_beats_api(client, token, shot_number=1)
            print(f"  split-shot-beats api {b_elapsed:.1f}s beats={len((b_data or {}).get('beats') or [])} err={b_err}")
            if b_err:
                issues.append(f"R5 beats api: {b_err}")
            else:
                patch_script_row(script_rows, "row-1", has_beats=True, beat_prompt_count=3, keyframe_count=3)
                patch_script_row(script_rows, "row-2", has_beats=True, beat_prompt_count=3, keyframe_count=3)

        # R6 — generate_storyboard (镜 1)
        messages.append({"role": "user", "content": "生成分镜图"})
        e6, actions6, err6, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R6] agent {e6:.1f}s actions={len(actions6)} errors={err6}")
        issue6 = expect_pipeline_step(actions6, "generate_storyboard", "R6")
        if issue6:
            issues.append(issue6)
        else:
            step6 = next((a for a in actions6 if a.get("type") == "pipeline_step"), None)
            row_id = (step6.get("data") or {}).get("row_id") or "row-1"
            img_elapsed, img_status, img_result, img_err = run_canvas_image(
                client,
                token,
                node_id=f"{script_id}-{row_id}-storyboard",
                prompt="渝爱在大熊猫馆与游客温馨互动，阳光透过竹林",
                reference_images=["/api/uploads/images/mock-cast-ref.jpg"],
            )
            print(
                f"  mock image {img_elapsed:.1f}s status={img_status} "
                f"result={str(img_result)[:80] if img_result else None} err={img_err}"
            )
            if img_status != "completed" or not img_result:
                issues.append(f"R6 mock image: status={img_status} err={img_err}")
            else:
                patch_script_row(script_rows, row_id, storyboard_ready=True)

        # R7 — generate_video (镜 1)
        messages.append({"role": "user", "content": "生成视频"})
        e7, actions7, err7, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R7] agent {e7:.1f}s actions={len(actions7)} errors={err7}")
        issue7 = expect_pipeline_step(actions7, "generate_video", "R7")
        if issue7:
            issues.append(issue7)
        else:
            step7 = next((a for a in actions7 if a.get("type") == "pipeline_step"), None)
            row_id = (step7.get("data") or {}).get("row_id") or "row-1"
            vid_elapsed, vid_status, vid_result, vid_err = run_canvas_video(
                client,
                token,
                node_id=f"{script_id}-{row_id}-video",
                prompt="渝爱在大熊猫馆与游客温馨互动，镜头缓缓推进",
            )
            print(
                f"  mock video {vid_elapsed:.1f}s status={vid_status} "
                f"result={str(vid_result)[:80] if vid_result else None} err={vid_err}"
            )
            if vid_status != "completed" or not vid_result:
                issues.append(f"R7 mock video: status={vid_status} err={vid_err}")
            else:
                patch_script_row(
                    script_rows,
                    row_id,
                    has_video=True,
                    video_generating=False,
                )

        # R8 — generate_video (镜 2) 或下一镜节拍（若镜2尚未拆节拍）
        messages.append({"role": "user", "content": "继续"})
        e8, actions8, err8, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R8] agent {e8:.1f}s actions={len(actions8)} errors={err8}")
        step8 = next((a for a in actions8 if a.get("type") == "pipeline_step"), None)
        if step8 and step8.get("step") == "generate_video":
            print("  R8 generate_video")
            row_id = (step8.get("data") or {}).get("row_id") or "row-2"
            vid_elapsed, vid_status, vid_result, vid_err = run_canvas_video(
                client,
                token,
                node_id=f"{script_id}-{row_id}-video",
                prompt="渝爱挑选新鲜竹子，咀嚼声清脆",
            )
            print(
                f"  mock video R8 {vid_elapsed:.1f}s status={vid_status} "
                f"result={str(vid_result)[:80] if vid_result else None} err={vid_err}"
            )
            if vid_status != "completed" or not vid_result:
                issues.append(f"R8 mock video: status={vid_status} err={vid_err}")
            else:
                patch_script_row(script_rows, row_id, has_video=True, video_generating=False)
        elif step8 and step8.get("step") == "generate_storyboard":
            row_id = (step8.get("data") or {}).get("row_id") or "row-2"
            print(f"  R8 generate_storyboard row={row_id} (一镜一步，镜2先出图)")
            img_elapsed, img_status, img_result, img_err = run_canvas_image(
                client,
                token,
                node_id=f"{script_id}-{row_id}-storyboard",
                prompt="渝爱挑选新鲜竹子，咀嚼声清脆",
            )
            print(
                f"  mock image R8 {img_elapsed:.1f}s status={img_status} "
                f"result={str(img_result)[:80] if img_result else None} err={img_err}"
            )
            if img_status != "completed" or not img_result:
                issues.append(f"R8 mock image: status={img_status} err={img_err}")
            else:
                patch_script_row(script_rows, row_id, storyboard_ready=True)
            # R8c — 镜2出图完成后应 generate_video
            messages.append({"role": "assistant", "content": "分镜图已生成"})
            messages.append({"role": "user", "content": "生成视频"})
            e8c, actions8c, err8c, _ = run_agent(
                client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
            )
            print(f"\n[R8c] agent {e8c:.1f}s actions={len(actions8c)} errors={err8c}")
            issue8c = expect_pipeline_step(actions8c, "generate_video", "R8c")
            if issue8c:
                issues.append(issue8c)
            else:
                step8c = next((a for a in actions8c if a.get("type") == "pipeline_step"), None)
                row_id = (step8c.get("data") or {}).get("row_id") or row_id
                vid_elapsed, vid_status, vid_result, vid_err = run_canvas_video(
                    client,
                    token,
                    node_id=f"{script_id}-{row_id}-video",
                    prompt="渝爱挑选新鲜竹子，咀嚼声清脆",
                )
                print(
                    f"  mock video R8c {vid_elapsed:.1f}s status={vid_status} "
                    f"result={str(vid_result)[:80] if vid_result else None} err={vid_err}"
                )
                if vid_status != "completed" or not vid_result:
                    issues.append(f"R8c mock video: status={vid_status} err={vid_err}")
                else:
                    patch_script_row(script_rows, row_id, has_video=True, video_generating=False)
        elif step8 and step8.get("step") == "split_shot_beats":
            row_id = (step8.get("data") or {}).get("row_id")
            if row_id and row_id != "row-2":
                issues.append(f"R8 split_shot_beats expected row-2 got {row_id}")
        else:
            issue8 = expect_pipeline_step(actions8, "generate_video", "R8")
            if issue8:
                issues.append(issue8)

        # R8b — 镜1全流程完成后，镜2未拆节拍时应 split_shot_beats（一镜一步语义）
        patch_script_row(script_rows, "row-2", has_beats=False, beat_prompt_count=0, keyframe_count=0)
        messages.append({"role": "user", "content": "继续"})
        e8b, actions8b, err8b, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R8b] agent {e8b:.1f}s actions={len(actions8b)} errors={err8b}")
        issue8b = expect_pipeline_step(actions8b, "split_shot_beats", "R8b")
        if issue8b:
            issues.append(issue8b)
        else:
            step8b = next((a for a in actions8b if a.get("type") == "pipeline_step"), None)
            row_id = (step8b.get("data") or {}).get("row_id") if step8b else None
            if row_id and row_id != "row-2":
                issues.append(f"R8b expected row_id row-2 got {row_id}")

        # RA — 意图 A：分析分镜进度，禁止 pipeline_step
        messages_a = [{"role": "user", "content": "帮我分析分镜进度"}]
        e_a, actions_a, err_a, _ = run_agent(
            client,
            token,
            project_id,
            messages_a,
            snapshot_from_nodes(nodes, edges),
            "manual",
        )
        print(f"\n[RA] agent {e_a:.1f}s actions={len(actions_a)} errors={err_a}")
        pipeline_a = [a for a in actions_a if a.get("type") == "pipeline_step"]
        if pipeline_a:
            issues.append(f"RA intent A should not return pipeline_step got {pipeline_a}")
        elif not any(a.get("type") == "done" for a in actions_a):
            issues.append("RA intent A expected done action")

        # RC — manage_cast 意图（分镜表已存在）
        messages_c = [{"role": "user", "content": "在角色库里添加角色小明和小红"}]
        e_c, actions_c, err_c, _ = run_agent(
            client,
            token,
            project_id,
            messages_c,
            snapshot_from_nodes(nodes, edges),
            "manual",
        )
        print(f"\n[RC] agent {e_c:.1f}s actions={len(actions_c)} errors={err_c}")
        step_c = next((a for a in actions_c if a.get("type") == "pipeline_step"), None)
        if not step_c or step_c.get("step") != "manage_cast":
            issues.append(f"RC expected manage_cast got {step_c}")

        print("\n=== ISSUES ===")
        if issues:
            for i in issues:
                print("-", i)
            return 3
        print("No critical issues in API-level pipeline probe (stage 1 + stage 2 intent + mock generation)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
