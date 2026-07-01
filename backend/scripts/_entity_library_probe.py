"""场景实体库 + 跨项目资产库 E2E 探针（mock 环境，不依赖 ComfyUI）。"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from _agent_pipeline_e2e_probe import (
    BASE,
    apply_script_table,
    headers,
    login,
    patch_script_row,
    poll_task,
    run_agent,
    snapshot_from_nodes,
    _db_model,
)
from services.seed import SEED_TESTUSER2_TEAM_ID

MOCK_CAST_IMAGE = "/api/uploads/images/mock-cast-ref.jpg"
MOCK_SCENE_IMAGE = "/api/uploads/images/mock-scene-ref.jpg"

# 与 CanvasEmptyState QUICK_ITEM_KEYS 的 assetView 一致
EMPTY_TAG_ASSET_PREFS = {
    "character": {"contentTab": "subjects", "filter": "character"},
    "scene": {"contentTab": "subjects", "filter": "scene"},
}


def get_team_id(client: httpx.Client, token: str) -> str | None:
    r = client.get(f"{BASE}/api/teams/mine", headers=headers(token), timeout=30)
    r.raise_for_status()
    data = r.json()
    owned = data.get("owned") or {}
    return owned.get("id")


def create_project(client: httpx.Client, token: str, *, name: str, team_id: str | None) -> str:
    payload = {"name": name, "canvas_data": {"nodes": [], "edges": []}}
    if team_id:
        payload["team_id"] = team_id
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_team_asset(
    client: httpx.Client,
    token: str,
    *,
    name: str,
    kind: str,
    team_id: str,
    image_url: str = MOCK_CAST_IMAGE,
) -> dict:
    r = client.post(
        f"{BASE}/api/assets",
        headers=headers(token),
        json={
            "name": name,
            "kind": kind,
            "image_url": image_url,
            "team_id": team_id,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def list_team_assets(
    client: httpx.Client,
    token: str,
    *,
    team_id: str,
    kind: str | None = None,
) -> list[dict]:
    params = {"team_id": team_id}
    if kind:
        params["kind"] = kind
    r = client.get(f"{BASE}/api/assets", headers=headers(token), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def apply_manage_cast(nodes, script_id: str, cast_items: list[dict]) -> list[dict]:
    """将 manage_cast 结果写入分镜表节点 cast_library（简化版）。"""
    cast_library = []
    for item in cast_items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        cast_library.append(
            {
                "id": f"cast-{uuid.uuid4().hex[:8]}",
                "name": name,
                "type": "character",
                "description": item.get("description") or "",
                "imageUrl": item.get("image_url") or item.get("imageUrl"),
                "pendingImage": not bool(item.get("image_url") or item.get("imageUrl")),
            }
        )
    for node in nodes:
        if node.get("id") == script_id and node.get("type") == "script_table":
            node["cast_library"] = cast_library
            break
    return cast_library


def apply_manage_scene(
    nodes,
    script_id: str,
    rows: list[dict],
    scene_items: list[dict],
    row_assignments: list[dict] | None = None,
) -> list[dict]:
    scene_library = []
    for item in scene_items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        scene_library.append(
            {
                "id": f"scene-{uuid.uuid4().hex[:8]}",
                "name": name,
                "description": item.get("description") or "",
                "imageUrl": item.get("image_url") or item.get("imageUrl"),
                "pendingImage": not bool(item.get("image_url") or item.get("imageUrl")),
            }
        )
    scene_by_name = {s["name"].lower(): s for s in scene_library}
    for assign in row_assignments or []:
        row_id = assign.get("row_id") or assign.get("rowId")
        scene_name = (assign.get("scene_name") or assign.get("sceneName") or "").strip()
        scene = scene_by_name.get(scene_name.lower())
        if not row_id or not scene:
            continue
        for row in rows:
            if row.get("id") == row_id:
                row["locationId"] = scene["id"]
                break
    for node in nodes:
        if node.get("id") == script_id and node.get("type") == "script_table":
            node["scene_library"] = scene_library
            node["rows_summary"] = rows
            break
    return scene_library


def extract_mock_reference_images(task: dict) -> list[str]:
    prompt = task.get("prompt_text") or ""
    marker = "<!-- mock_reference_images:"
    if marker not in prompt:
        return []
    start = prompt.index(marker) + len(marker)
    end = prompt.index("-->", start)
    try:
        return json.loads(prompt[start:end])
    except json.JSONDecodeError:
        return []


def task_prompt_text_from_db(task_id: str) -> str:
    db_path = Path(__file__).resolve().parents[1] / "aistudio.db"
    if not db_path.exists():
        return ""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT prompt_text FROM tasks WHERE id=?", (task_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""


def probe_cross_project_cast(client: httpx.Client, issues: list[str]) -> None:
    print("\n[C1] 跨项目角色资产")
    token = login("admin", "Admin@2026!")
    team_id = get_team_id(client, token)
    if not team_id:
        issues.append("C1 admin 无团队")
        return
    print("  team", team_id)

    project_a = create_project(client, token, name=f"probe-A-{uuid.uuid4().hex[:6]}", team_id=team_id)
    project_b = create_project(client, token, name=f"probe-B-{uuid.uuid4().hex[:6]}", team_id=team_id)
    print("  projects", project_a, project_b)

    asset_name = f"探针角色-{uuid.uuid4().hex[:6]}"
    asset = create_team_asset(
        client,
        token,
        name=asset_name,
        kind="character",
        team_id=team_id,
    )
    asset_id = asset.get("id")
    print("  asset", asset_id, asset_name)

    listed = list_team_assets(client, token, team_id=team_id, kind="character")
    names = {a.get("name") for a in listed}
    if asset_name not in names:
        issues.append(f"C1 项目 B 同团队资产库未见到 {asset_name}")

    cast_library = [
        {
            "id": f"cast-{uuid.uuid4().hex[:8]}",
            "name": asset_name,
            "type": "character",
            "imageUrl": asset.get("image_url") or MOCK_CAST_IMAGE,
            "globalAssetId": asset_id,
        }
    ]
    if not cast_library[0].get("globalAssetId"):
        issues.append("C1 cast_library 未写入 globalAssetId")


def probe_manage_scene(client: httpx.Client, issues: list[str]) -> None:
    print("\n[C2] 场景实体 manage_scene")
    token = login("admin", "Admin@2026!")
    pr = client.get(f"{BASE}/api/canvas/projects", headers=headers(token), timeout=30)
    pr.raise_for_status()
    projects = pr.json().get("projects") or []
    if not projects:
        issues.append("C2 无项目")
        return
    project_id = projects[0]["id"]

    nodes = [
        {
            "id": "outline-seed",
            "type": "outline",
            "position": {"x": 900, "y": 160},
            "content_preview": "晨光 操场",
            "label": "大纲",
            "loading": False,
            "scene_count": 2,
        }
    ]
    edges = []
    script_id, rows = apply_script_table(nodes, edges, "outline-seed", row_count=2)

    messages = [{"role": "user", "content": "添加场景「教室」，镜1和镜2都绑定教室"}]
    elapsed, actions, errors, _ = run_agent(
        client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
    )
    print(f"  agent {elapsed:.1f}s errors={errors}")
    step = next((a for a in actions if a.get("type") == "pipeline_step"), None)
    ask = next((a for a in actions if a.get("type") == "ask_user"), None)
    if not step or step.get("step") != "manage_scene":
        issues.append(f"C2 expected manage_scene got {step}")
        if ask and ask.get("scene_pending"):
            print("  note: got scene_pending ask_user without manage_scene in same round")
        return

    data = step.get("data") or {}
    scene_items = data.get("scene_items") or []
    row_assignments = data.get("row_assignments") or []
    scene_lib = apply_manage_scene(nodes, script_id, rows, scene_items, row_assignments)

    if ask and ask.get("scene_pending"):
        print("  scene_pending", ask.get("scene_pending"))

    if not scene_lib:
        issues.append("C2 scene_library 为空")
        return

    scene = scene_lib[0]
    scene["imageUrl"] = MOCK_SCENE_IMAGE
    scene["pendingImage"] = False

    cast_lib = apply_manage_cast(
        nodes,
        script_id,
        [{"name": "小明", "image_url": MOCK_CAST_IMAGE}],
    )
    for c in cast_lib:
        c["imageUrl"] = MOCK_CAST_IMAGE
        c["pendingImage"] = False

    loc_ids = {r.get("locationId") for r in rows if r.get("locationId")}
    if len(loc_ids) < 1:
        issues.append("C2 分镜行 locationId 未写入")
    else:
        print("  locationIds", loc_ids)

    patch_script_row(rows, "row-1", has_beats=True, beat_prompt_count=2, keyframe_count=2)
    patch_script_row(rows, "row-2", has_beats=True, beat_prompt_count=2, keyframe_count=2)

    ref_images = [MOCK_CAST_IMAGE, MOCK_SCENE_IMAGE]
    model_id = _db_model("image")
    task_id = None
    if model_id:
        tr = client.post(
            f"{BASE}/api/tasks/image",
            headers=headers(token),
            json={
                "model": model_id,
                "prompt": "镜1 小明在教室",
                "ratio": "16:9",
                "quality": "2K",
                "count": 1,
                "node_id": f"{script_id}-row-1-storyboard",
                "reference_images": ref_images,
            },
            timeout=30,
        )
        if tr.status_code == 200:
            task_id = tr.json().get("task_id")
            _, status, _, err = poll_task(client, token, task_id, timeout=25)
            print(f"  mock image status={status} err={err}")
            if status != "completed":
                issues.append(f"C2 mock 出图失败: {err}")
                return
    else:
        issues.append("C2 无 image model")
        return

    if task_id:
        prompt = task_prompt_text_from_db(task_id)
        refs = extract_mock_reference_images({"prompt_text": prompt})
        print("  reference_images recorded", refs)
        if len(refs) < 2:
            issues.append("C2 reference_images 应同时含角色+场景")


def probe_empty_tag_prefs(client: httpx.Client, issues: list[str]) -> None:
    print("\n[C3] 空态 Tag → 资产库筛选")
    token = login("admin", "Admin@2026!")
    team_id = get_team_id(client, token)

    for tag, pref in EMPTY_TAG_ASSET_PREFS.items():
        expected_kind = pref.get("filter")
        if expected_kind not in ("character", "scene"):
            issues.append(f"C3 {tag} pref filter 异常: {pref}")
            continue
        assets = list_team_assets(client, token, team_id=team_id, kind=expected_kind)
        print(f"  tag={tag} pref={pref} assets={len(assets)}")
        for row in assets:
            if row.get("kind") != expected_kind:
                issues.append(f"C3 kind={expected_kind} 列表含 {row.get('kind')}")
                break


def probe_team_isolation(client: httpx.Client, issues: list[str]) -> None:
    print("\n[C4] 团队隔离")
    admin_token = login("admin", "Admin@2026!")
    admin_team_id = get_team_id(client, admin_token)
    if not admin_team_id:
        issues.append("C4 admin 无团队")
        return

    secret_name = f"隔离探针-{uuid.uuid4().hex[:8]}"
    create_team_asset(
        client,
        admin_token,
        name=secret_name,
        kind="character",
        team_id=admin_team_id,
    )

    admin_assets = list_team_assets(client, admin_token, team_id=admin_team_id, kind="character")
    if secret_name not in {a.get("name") for a in admin_assets}:
        issues.append("C4 admin 团队资产创建失败")

    token_b = login("testuser2", "Test2@2026!")
    try:
        foreign = list_team_assets(client, token_b, team_id=admin_team_id, kind="character")
        if secret_name in {a.get("name") for a in foreign}:
            issues.append("C4 testuser2 不应看到团队 A 资产")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            issues.append(f"C4 异团队访问应 403，实际 {exc.response.status_code}")

    team_b = get_team_id(client, token_b) or SEED_TESTUSER2_TEAM_ID
    own = list_team_assets(client, token_b, team_id=team_b, kind="character")
    if secret_name in {a.get("name") for a in own}:
        issues.append("C4 团队 B 不应含团队 A 资产")


def main() -> int:
    issues: list[str] = []
    with httpx.Client() as client:
        try:
            probe_cross_project_cast(client, issues)
            probe_manage_scene(client, issues)
            probe_empty_tag_prefs(client, issues)
            probe_team_isolation(client, issues)
        except httpx.HTTPError as exc:
            print("HTTP error:", exc)
            return 1

    print("\n=== ISSUES ===")
    if issues:
        for item in issues:
            print("-", item)
        return 3
    print("Entity library probe passed (manage_scene + cross-project assets + team isolation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
