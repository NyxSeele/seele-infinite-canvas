#!/usr/bin/env python3
"""G48: R2 团队文件空间权限 / 预签名 / 登记 / add-to-assets 探针."""

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

from core.config import settings  # noqa: E402

BASE = os.environ.get("API_BASE", "http://127.0.0.1:7788").rstrip("/")
ADMIN_USER = os.environ.get("PROBE_ADMIN", "admin")
ADMIN_PASS = os.environ.get("SEED_ADMIN_PASSWORD") or os.environ.get(
    "PROBE_ADMIN_PASSWORD", "Admin@2026!"
)
TEST_USER = os.environ.get("PROBE_USER", "testuser")
TEST_PASS = os.environ.get("SEED_TESTUSER_PASSWORD") or os.environ.get(
    "PROBE_PASSWORD", "Test@2026!"
)

OUT = Path("/root/autodl-tmp/logs/g48_r2_files_probe.json")


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def find_user_id(client: httpx.Client, admin_token: str, username: str) -> int:
    r = client.get(
        f"{BASE}/api/admin/users",
        headers=headers(admin_token),
        params={"q": username, "page_size": 50},
        timeout=30,
    )
    r.raise_for_status()
    for item in r.json().get("items") or []:
        if item.get("username") == username:
            return int(item["id"])
    raise RuntimeError(f"user not found: {username}")


def set_r2_access(
    client: httpx.Client, admin_token: str, user_id: int, enabled: bool
) -> None:
    r = client.patch(
        f"{BASE}/api/admin/users/{user_id}/r2-access",
        headers=headers(admin_token),
        json={"r2_access": enabled},
        timeout=30,
    )
    r.raise_for_status()


def main() -> int:
    results: dict = {"checks": {}, "issues": []}
    issues: list[str] = results["issues"]
    created_file_id: int | None = None

    try:
        with httpx.Client() as client:
            try:
                admin_token = login(client, ADMIN_USER, ADMIN_PASS)
                user_token = login(client, TEST_USER, TEST_PASS)
            except Exception as exc:
                print(f"INFRA login failed: {exc}")
                results["error"] = f"login failed: {exc}"
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                return 1

            user_id = find_user_id(client, admin_token, TEST_USER)

            # Ensure denied baseline
            set_r2_access(client, admin_token, user_id, False)

            # ── 1. 无 r2_access → 403 ────────────────────────────────
            r = client.get(
                f"{BASE}/api/r2/files",
                headers=headers(user_token),
                timeout=30,
            )
            ok_denied = r.status_code == 403
            results["checks"]["no_access_list_403"] = {
                "status": r.status_code,
                "ok": ok_denied,
            }
            if not ok_denied:
                issues.append(f"expected 403 on list without r2_access, got {r.status_code}")

            r2 = client.post(
                f"{BASE}/api/r2/presign-upload",
                headers=headers(user_token),
                json={
                    "filename": "probe.bin",
                    "content_type": "application/octet-stream",
                    "size_bytes": 4,
                },
                timeout=30,
            )
            ok_presign_denied = r2.status_code == 403
            results["checks"]["no_access_presign_403"] = {
                "status": r2.status_code,
                "ok": ok_presign_denied,
            }
            if not ok_presign_denied:
                issues.append(
                    f"expected 403 on presign without r2_access, got {r2.status_code}"
                )

            # Grant access and re-login so JWT/me is fresh (permission is DB-checked each request)
            set_r2_access(client, admin_token, user_id, True)
            user_token = login(client, TEST_USER, TEST_PASS)

            # ── 2. 预签名 URL ────────────────────────────────────────
            fname = f"g48_probe_{uuid.uuid4().hex[:8]}.txt"
            payload = {
                "filename": fname,
                "content_type": "text/plain",
                "size_bytes": 16,
                "description": "g48 probe",
            }
            r = client.post(
                f"{BASE}/api/r2/presign-upload",
                headers=headers(user_token),
                json=payload,
                timeout=30,
            )
            if r.status_code != 200:
                issues.append(f"presign failed: {r.status_code} {r.text[:200]}")
                results["checks"]["presign"] = {"status": r.status_code, "ok": False}
            else:
                data = r.json()
                ok = bool(data.get("upload_url") and data.get("key", "").startswith("team/"))
                results["checks"]["presign"] = {
                    "status": 200,
                    "key": data.get("key"),
                    "has_url": bool(data.get("upload_url")),
                    "ok": ok,
                }
                if not ok:
                    issues.append("presign response missing upload_url or team/ key")
                key = data["key"]

                # Optional: actually PUT a tiny object (best-effort)
                put_ok = False
                try:
                    put = client.put(
                        data["upload_url"],
                        content=b"g48-probe-bytes",
                        headers={"Content-Type": "text/plain"},
                        timeout=60,
                    )
                    put_ok = put.status_code in (200, 201, 204)
                    results["checks"]["direct_put"] = {
                        "status": put.status_code,
                        "ok": put_ok,
                    }
                    if not put_ok:
                        issues.append(f"R2 PUT failed: {put.status_code}")
                except Exception as exc:
                    results["checks"]["direct_put"] = {"ok": False, "error": str(exc)}
                    issues.append(f"R2 PUT error: {exc}")

                # ── 3. 登记 API ──────────────────────────────────────
                reg = client.post(
                    f"{BASE}/api/r2/files",
                    headers=headers(user_token),
                    json={
                        "key": key,
                        "filename": fname,
                        "content_type": "text/plain",
                        "size_bytes": 16,
                        "description": "g48 probe",
                    },
                    timeout=30,
                )
                if reg.status_code != 200:
                    issues.append(f"register failed: {reg.status_code} {reg.text[:200]}")
                    results["checks"]["register"] = {"status": reg.status_code, "ok": False}
                else:
                    created = reg.json()
                    created_file_id = int(created["id"])
                    lst = client.get(
                        f"{BASE}/api/r2/files",
                        headers=headers(user_token),
                        params={"q": fname},
                        timeout=30,
                    )
                    lst.raise_for_status()
                    items = lst.json().get("items") or []
                    found = any(i.get("id") == created_file_id for i in items)
                    results["checks"]["register"] = {
                        "status": 200,
                        "id": created_file_id,
                        "listed": found,
                        "ok": found,
                    }
                    if not found:
                        issues.append("registered file not found in list")

                    # ── 4. add-to-assets ─────────────────────────────
                    add = client.post(
                        f"{BASE}/api/r2/files/{created_file_id}/add-to-assets",
                        headers=headers(user_token),
                        json={"target": "personal"},
                        timeout=30,
                    )
                    public = (settings.r2_public_url or "").strip().rstrip("/")
                    if not public:
                        ok_add = add.status_code == 503
                        results["checks"]["add_to_assets"] = {
                            "status": add.status_code,
                            "ok": ok_add,
                            "mode": "expect_503_no_public_url",
                        }
                        if not ok_add:
                            issues.append(
                                f"expected 503 without R2_PUBLIC_URL, got {add.status_code}"
                            )
                    else:
                        if add.status_code != 200:
                            issues.append(
                                f"add-to-assets failed: {add.status_code} {add.text[:200]}"
                            )
                            results["checks"]["add_to_assets"] = {
                                "status": add.status_code,
                                "ok": False,
                            }
                        else:
                            asset = add.json()
                            url = asset.get("image_url") or ""
                            ok_url = url.startswith(public)
                            results["checks"]["add_to_assets"] = {
                                "status": 200,
                                "image_url": url,
                                "ok": ok_url,
                            }
                            if not ok_url:
                                issues.append(
                                    f"asset image_url should start with {public}, got {url}"
                                )

            # Cleanup via admin delete
            if created_file_id is not None:
                d = client.delete(
                    f"{BASE}/api/r2/files/{created_file_id}",
                    headers=headers(admin_token),
                    timeout=30,
                )
                results["checks"]["cleanup_delete"] = {
                    "status": d.status_code,
                    "ok": d.status_code == 200,
                }
                if d.status_code != 200:
                    issues.append(f"cleanup delete failed: {d.status_code}")

            # Leave testuser without r2_access (safer default)
            set_r2_access(client, admin_token, user_id, False)

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
    print("PASS g48_r2_files_probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
