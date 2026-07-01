#!/usr/bin/env python3
"""团队生成历史探针：GET /api/tasks/records?team_id=。

前置：后端 :7788 + mock；admin 在团队上下文提交 completed 图任务。
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
from _mock_generation_acceptance import poll_task


def get_admin_team_id(client: httpx.Client, token: str) -> str:
    r = client.get(f"{BASE}/api/teams/mine", headers=headers(token), timeout=30)
    r.raise_for_status()
    owned = (r.json().get("owned") or {})
    team_id = owned.get("id")
    assert team_id, r.json()
    return team_id


def main() -> int:
    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        team_id = get_admin_team_id(client, token)

        r = client.post(
            f"{BASE}/api/tasks/image",
            headers=headers(token),
            json={
                "model": "stable-diffusion",
                "prompt": "task records probe image",
                "ratio": "1:1",
                "quality": "2K",
                "count": 1,
                "node_id": f"probe-records-{uuid.uuid4().hex[:8]}",
                "team_id": team_id,
            },
            timeout=30,
        )
        r.raise_for_status()
        task_id = r.json()["task_id"]
        result = poll_task(client, token, task_id, timeout=20)
        assert result["status"] == "completed", result
        print(f"[image] completed task_id={task_id}")

        rec = client.get(
            f"{BASE}/api/tasks/records",
            headers=headers(token),
            params={"team_id": team_id, "limit": 50},
            timeout=30,
        )
        rec.raise_for_status()
        records = rec.json().get("records") or []
        hit = [row for row in records if row.get("id") == task_id]
        assert hit, f"task {task_id} not in team records ({len(records)} rows)"
        row = hit[0]
        assert row.get("status") == "completed", row
        assert row.get("result"), row
        assert row.get("team_id") == team_id, row
        print(f"[records] found task result={str(row.get('result'))[:60]}...")

    print("PASS: task records probe")
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
