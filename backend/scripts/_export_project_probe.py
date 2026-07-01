#!/usr/bin/env python3
"""完整项目导出 HTTP 全流程探针。

前置：后端 :7788；admin 登录；mock 模式即可（分镜表可无真实媒体）。
退出码：0=PASS, 1=infra, 3=assert fail
"""
from __future__ import annotations

import io
import sys
import time
import uuid
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login

TABLE_ID = "st-export-probe"
ROW_ID = "row-export-1"


def create_export_project(client: httpx.Client, token: str) -> str:
    canvas_data = {
        "nodes": [
            {
                "id": TABLE_ID,
                "type": "script-table",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": "导出探针分镜表",
                    "rows": [
                        {
                            "id": ROW_ID,
                            "shotNumber": 1,
                            "duration": 8,
                            "description": "探针导出测试镜头：晨光中的大熊猫馆",
                            "prompt": "探针导出测试镜头：晨光中的大熊猫馆",
                        }
                    ],
                    "segments": [],
                },
            }
        ],
        "edges": [],
    }
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={"name": f"probe-export-{uuid.uuid4().hex[:8]}", "canvas_data": canvas_data},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def poll_export(client: httpx.Client, token: str, export_id: str, *, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"{BASE}/api/exports/{export_id}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(0.5)
    raise TimeoutError(f"export {export_id} not terminal within {timeout}s, last={last}")


def main() -> int:
    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        project_id = create_export_project(client, token)
        print(f"[project] id={project_id} table={TABLE_ID}")

        r = client.post(
            f"{BASE}/api/exports",
            headers=headers(token),
            json={"project_id": project_id, "script_table_node_id": TABLE_ID},
            timeout=30,
        )
        r.raise_for_status()
        export_id = r.json()["id"]
        print(f"[export] job id={export_id}")

        job = poll_export(client, token, export_id)
        assert job.get("status") == "completed", job
        assert job.get("file_path"), job

        dl = client.get(
            f"{BASE}/api/exports/{export_id}/download",
            headers=headers(token),
            timeout=60,
        )
        dl.raise_for_status()
        content = dl.content
        assert len(content) > 100, f"zip too small: {len(content)} bytes"

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            docx = [n for n in names if n.lower().endswith(".docx")]
            assert docx, f"no docx in zip: {names[:20]}"
            print(f"[download] zip_bytes={len(content)} docx={docx[0]}")

    print("PASS: export project probe")
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
