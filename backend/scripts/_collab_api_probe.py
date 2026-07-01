#!/usr/bin/env python3
"""协作相关 API 探针：评论@通知、迁移团队、编辑锁 HTTP。

前置：后端 :7788；种子账号 admin / testuser2；Redis 可选（锁）。
退出码：0=PASS, 1=infra, 3=assert fail
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login


def get_admin_team_id(client: httpx.Client, token: str) -> str:
    r = client.get(f"{BASE}/api/teams/mine", headers=headers(token), timeout=30)
    r.raise_for_status()
    owned = (r.json().get("owned") or {})
    team_id = owned.get("id")
    assert team_id, r.json()
    return team_id


def me(client: httpx.Client, token: str) -> dict:
    r = client.get(f"{BASE}/api/auth/me", headers=headers(token), timeout=30)
    r.raise_for_status()
    return r.json()


def create_personal_project(client: httpx.Client, token: str) -> str:
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={
            "name": f"probe-collab-{uuid.uuid4().hex[:8]}",
            "canvas_data": {
                "nodes": [{"id": "n1", "type": "text-note", "position": {"x": 0, "y": 0}, "data": {}}],
                "edges": [],
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def test_migrate_to_team(client: httpx.Client, admin_token: str, team_id: str) -> None:
    project_id = create_personal_project(client, admin_token)
    r = client.post(
        f"{BASE}/api/canvas/projects/{project_id}/migrate-to-team",
        headers=headers(admin_token),
        json={"team_id": team_id},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    assert body.get("team_id") == team_id, body
    print(f"[migrate] project={project_id} team_id={body.get('team_id')}")


def test_edit_lock_http(client: httpx.Client, admin_token: str) -> None:
    project_id = create_personal_project(client, admin_token)
    acq = client.post(
        f"{BASE}/api/canvas/projects/{project_id}/session",
        headers=headers(admin_token),
        json={"display_name": "probe-admin"},
        timeout=30,
    )
    acq.raise_for_status()
    session_id = acq.json().get("session_id")
    assert session_id, acq.json()
    hb = client.post(
        f"{BASE}/api/canvas/projects/{project_id}/session/heartbeat",
        headers=headers(admin_token),
        json={"session_id": session_id},
        timeout=30,
    )
    hb.raise_for_status()
    assert hb.json().get("ok") is True
    rel = client.delete(
        f"{BASE}/api/canvas/projects/{project_id}/session",
        headers=headers(admin_token),
        params={"session_id": session_id},
        timeout=30,
    )
    rel.raise_for_status()
    print(f"[lock] acquire/heartbeat/release ok project={project_id}")


def test_comment_mention_notification(
    client: httpx.Client, admin_token: str, testuser2_token: str, testuser2_id: int
) -> None:
    project_id = create_personal_project(client, admin_token)
    post = client.post(
        f"{BASE}/api/canvas/projects/{project_id}/comments",
        headers=headers(admin_token),
        json={
            "node_id": "n1",
            "body": "探针 @提及 testuser2",
            "mentioned_user_ids": [testuser2_id],
        },
        timeout=30,
    )
    post.raise_for_status()
    thread = post.json().get("thread") or {}
    assert thread.get("messages"), thread
    print(f"[comment] thread_id={thread.get('id')}")

    notes = client.get(
        f"{BASE}/api/notifications",
        headers=headers(testuser2_token),
        timeout=30,
    )
    notes.raise_for_status()
    items = notes.json().get("notifications") or notes.json().get("items") or []
    if isinstance(notes.json(), list):
        items = notes.json()
    matched = [
        n
        for n in items
        if n.get("type") == "comment_mention"
        and (n.get("payload") or {}).get("project_id") == project_id
    ]
    assert matched, f"no comment_mention for project {project_id} in {len(items)} notifications"
    print(f"[notify] testuser2 mention count={len(matched)}")


def main() -> int:
    with httpx.Client() as client:
        try:
            admin_token = login("admin", "Admin@2026!")
            testuser2_token = login("testuser2", "Test2@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        testuser2 = me(client, testuser2_token)
        testuser2_id = int(testuser2["id"])
        print(f"[users] testuser2 id={testuser2_id}")

        team_id = get_admin_team_id(client, admin_token)
        print(f"[team] id={team_id}")

        test_migrate_to_team(client, admin_token, team_id)
        test_edit_lock_http(client, admin_token)
        test_comment_mention_notification(client, admin_token, testuser2_token, testuser2_id)

    print("PASS: collab API probe")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
