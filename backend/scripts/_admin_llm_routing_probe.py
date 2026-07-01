#!/usr/bin/env python3
"""Admin LLM 路由探针：GET/PUT llm-routing、set-default-text 静态路由。

前置：后端 :7788；admin 登录。
退出码：0=PASS, 1=infra, 3=assert fail
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login


def main() -> int:
    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        get_r = client.get(
            f"{BASE}/api/admin/models/llm-routing",
            headers=headers(token),
            timeout=30,
        )
        get_r.raise_for_status()
        snap = get_r.json()
        mode = snap.get("mode") or "fixed"
        assert mode in ("fixed", "cheapest", "balanced"), snap
        print(f"[get] mode={mode} models={len(snap.get('models') or [])}")

        put_r = client.put(
            f"{BASE}/api/admin/models/llm-routing",
            headers=headers(token),
            json={"mode": mode},
            timeout=30,
        )
        put_r.raise_for_status()
        put_body = put_r.json()
        assert put_body.get("mode") == mode, put_body
        print(f"[put] mode unchanged={mode}")

        models_r = client.get(
            f"{BASE}/api/admin/models",
            headers=headers(token),
            timeout=30,
        )
        models_r.raise_for_status()
        models = models_r.json().get("models") or models_r.json()
        if isinstance(models, dict):
            models = models.get("models") or []
        text_models = [m for m in models if (m.get("type") or "").lower() in ("text", "api")]
        if text_models:
            model_id = text_models[0]["id"]
            set_r = client.post(
                f"{BASE}/api/admin/models/{model_id}/set-default-text",
                headers=headers(token),
                timeout=30,
            )
            assert set_r.status_code != 422, f"set-default-text routed to {{model_id}}: {set_r.text[:200]}"
            if set_r.status_code < 400:
                print(f"[set-default-text] model={model_id} status={set_r.status_code}")
            else:
                print(f"[set-default-text] skip model={model_id} status={set_r.status_code}")
        else:
            print("[set-default-text] skip — no text models registered")

    print("PASS: admin llm routing probe")
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
