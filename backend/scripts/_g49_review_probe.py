#!/usr/bin/env python3
"""G49: 视频审阅 — JWT 发布 / 公开列表 / 匿名评价 / 统计探针."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE = os.environ.get("API_BASE", "http://127.0.0.1:7788").rstrip("/")
ADMIN_USER = os.environ.get("PROBE_ADMIN", "admin")
ADMIN_PASS = os.environ.get("SEED_ADMIN_PASSWORD") or os.environ.get(
    "PROBE_ADMIN_PASSWORD", "Admin@2026!"
)

OUT = Path("/root/autodl-tmp/logs/g49_review_probe.json")


def headers(token: str | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    results: dict = {"checks": {}, "issues": []}
    issues: list[str] = results["issues"]
    video_id: int | None = None

    try:
        with httpx.Client() as client:
            try:
                token = login(client, ADMIN_USER, ADMIN_PASS)
            except Exception as exc:
                results["error"] = f"login failed: {exc}"
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(results, ensure_ascii=False, indent=2))
                return 1

            # ── 1. 无 JWT 发布 → 401 ────────────────────────────────
            r = client.post(
                f"{BASE}/api/review/videos",
                headers=headers(None),
                json={
                    "title": "noauth",
                    "video_url": "https://example.com/v.mp4",
                },
                timeout=30,
            )
            ok1 = r.status_code in (401, 403)
            results["checks"]["publish_requires_jwt"] = {
                "status": r.status_code,
                "ok": ok1,
            }
            if not ok1:
                issues.append(f"expected 401/403 without JWT, got {r.status_code}")

            # ── 2. JWT 发布 → 公开列表无 JWT 可见 ───────────────────
            title = f"g49_review_{uuid.uuid4().hex[:8]}"
            pub = client.post(
                f"{BASE}/api/review/videos",
                headers=headers(token),
                json={
                    "title": title,
                    "description": "g49 probe",
                    "video_url": "https://pub-35b6c5f7046a47fabe9698a7e9566c2a.r2.dev/team/2026/07/ef701e4c1fb645f4928ee0685b000cfb_manual_probe_8d98d690.png",
                    "thumbnail_url": None,
                },
                timeout=30,
            )
            if pub.status_code != 200:
                issues.append(f"publish failed: {pub.status_code} {pub.text[:200]}")
                results["checks"]["publish"] = {"status": pub.status_code, "ok": False}
            else:
                video_id = int(pub.json()["id"])
                results["checks"]["publish"] = {"status": 200, "id": video_id, "ok": True}

                lst = client.get(
                    f"{BASE}/api/review/public/videos",
                    headers=headers(None),
                    timeout=30,
                )
                if lst.status_code != 200:
                    issues.append(f"public list failed: {lst.status_code}")
                    results["checks"]["public_list_no_jwt"] = {
                        "status": lst.status_code,
                        "ok": False,
                    }
                else:
                    found = any(i.get("id") == video_id for i in lst.json())
                    results["checks"]["public_list_no_jwt"] = {
                        "status": 200,
                        "found": found,
                        "ok": found,
                    }
                    if not found:
                        issues.append("published video not in public list")

                # ── 3. 无 JWT 提交评价 ───────────────────────────────
                c1 = client.post(
                    f"{BASE}/api/review/public/videos/{video_id}/comment",
                    headers=headers(None),
                    json={
                        "reviewer_name": "probe_alice",
                        "rating": 4,
                        "liked": True,
                        "comment": "looks good",
                    },
                    timeout=30,
                )
                ok3 = c1.status_code == 200
                results["checks"]["comment_no_jwt"] = {
                    "status": c1.status_code,
                    "ok": ok3,
                }
                if not ok3:
                    issues.append(f"comment failed: {c1.status_code} {c1.text[:200]}")

                # ── 4. 再评一条，校验统计 ───────────────────────────
                c2 = client.post(
                    f"{BASE}/api/review/public/videos/{video_id}/comment",
                    headers=headers(None),
                    json={
                        "reviewer_name": "probe_bob",
                        "rating": 2,
                        "liked": False,
                        "comment": "meh",
                    },
                    timeout=30,
                )
                if c2.status_code != 200:
                    issues.append(f"second comment failed: {c2.status_code}")
                    results["checks"]["stats"] = {"ok": False}
                else:
                    detail = client.get(
                        f"{BASE}/api/review/public/videos/{video_id}",
                        headers=headers(None),
                        timeout=30,
                    )
                    detail.raise_for_status()
                    d = detail.json()
                    avg = d.get("avg_rating")
                    likes = d.get("like_count")
                    dislikes = d.get("dislike_count")
                    count = d.get("comment_count")
                    # (4+2)/2 = 3.0
                    avg_ok = avg is not None and abs(float(avg) - 3.0) < 0.01
                    stats_ok = (
                        avg_ok
                        and likes == 1
                        and dislikes == 1
                        and count == 2
                        and len(d.get("comments") or []) == 2
                    )
                    results["checks"]["stats"] = {
                        "avg_rating": avg,
                        "like_count": likes,
                        "dislike_count": dislikes,
                        "comment_count": count,
                        "ok": stats_ok,
                    }
                    if not stats_ok:
                        issues.append(
                            f"stats mismatch: avg={avg} likes={likes} "
                            f"dislikes={dislikes} count={count}"
                        )

            if video_id is not None:
                dlt = client.delete(
                    f"{BASE}/api/review/videos/{video_id}",
                    headers=headers(token),
                    timeout=30,
                )
                results["checks"]["cleanup_unpublish"] = {
                    "status": dlt.status_code,
                    "ok": dlt.status_code == 200,
                }
                if dlt.status_code != 200:
                    issues.append(f"cleanup failed: {dlt.status_code}")

    except Exception as exc:
        issues.append(f"unexpected: {exc}")
        results["error"] = str(exc)

    results["pass"] = len(issues) == 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if issues:
        print("FAIL:", "; ".join(issues))
        return 3
    print("PASS g49_review_probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
