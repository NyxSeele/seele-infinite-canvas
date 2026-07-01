"""临时脚本：探测本地 DB 用户/项目并跑 Agent 链路前几步。"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "aistudio.db"
BASE = "http://127.0.0.1:7788"


def load_users_projects():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, username, email FROM users LIMIT 5")
    users = cur.fetchall()
    projects = []
    for table in ("canvas_projects", "projects", "canvas_project"):
        try:
            cur.execute(f"SELECT id, name, owner_id FROM {table} LIMIT 5")
            projects = cur.fetchall()
            if projects:
                print(f"projects from {table}:", projects[:3])
                break
        except sqlite3.OperationalError:
            pass
    conn.close()
    return users, projects


def login(username: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["access_token"]


def parse_sse(text: str):
    events = []
    for part in text.split("\n\n"):
        for line in part.split("\n"):
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events


def run_agent(token: str, project_id: str, messages, execution_mode="manual"):
  payload = {
      "project_id": project_id,
      "canvas_snapshot": {"nodes": [], "edges": [], "selected_node_ids": [], "total_node_count": 0},
      "messages": messages,
      "execution_mode": execution_mode,
  }
  with httpx.Client(timeout=120) as client:
      with client.stream(
          "POST",
          f"{BASE}/api/agent/run",
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
          json=payload,
      ) as resp:
          resp.raise_for_status()
          buf = ""
          for chunk in resp.iter_text():
              buf += chunk
          return parse_sse(buf)


def main():
    users, projects = load_users_projects()
    print("users:", users)
    if not users:
        print("NO_USERS")
        return 1

    # 尝试常见本地密码；失败则只报告用户列表
    creds = [
        ("admin", "admin123"),
        ("admin", "admin"),
        ("test", "test123"),
        ("demo", "demo123"),
    ]
    if len(sys.argv) >= 3:
        creds = [(sys.argv[1], sys.argv[2])]

    token = None
    for u, p in creds:
        for uid, username, email in users:
            for name in {username, email}:
                if not name:
                    continue
                try:
                    token = login(name, p)
                    print("logged in as", name)
                    break
                except Exception:
                    pass
            if token:
                break
        if token:
            break

    if not token:
        print("LOGIN_FAILED - pass username password as args")
        return 2

    project_id = None
    if projects:
        project_id = projects[0][0]
    else:
        # list projects via API
        r = httpx.get(
            f"{BASE}/api/canvas/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code == 200:
            items = r.json()
            if isinstance(items, list) and items:
                project_id = items[0].get("id") or items[0].get("project_id")
            elif isinstance(items, dict):
                arr = items.get("projects") or items.get("items") or []
                if arr:
                    project_id = arr[0].get("id")
        print("api projects status", r.status_code, r.text[:300])

    if not project_id:
        print("NO_PROJECT")
        return 3

    print("project_id", project_id)

    prompt = "我想做一段重庆动物园渝爱的宣传片"
    t0 = time.time()
    events = run_agent(token, project_id, [{"role": "user", "content": prompt}], "manual")
    dt = time.time() - t0
    print(f"step1 elapsed {dt:.1f}s events={len(events)}")
    for e in events:
        if e.get("event") == "action":
            print("  action:", json.dumps(e.get("action"), ensure_ascii=False)[:500])
        elif e.get("event") in ("error", "thinking"):
            print(" ", e.get("event"), str(e.get("content") or e.get("message"))[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
