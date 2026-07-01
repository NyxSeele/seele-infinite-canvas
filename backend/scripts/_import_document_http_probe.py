#!/usr/bin/env python3
"""文档导入 HTTP 全流程探针：scan → parse → apply。

内置最小 xlsx fixture（openpyxl 生成），不依赖桌面样本文件。
前置：后端 :7788；admin 登录。
退出码：0=PASS, 1=infra, 3=assert fail
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

import httpx
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login


def build_minimal_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "ep1"
    ws.append(["镜号", "景别", "时长/s", "画面描述"])
    ws.append([1, "全景", 8, "探针导入：大熊猫馆晨光"])
    wb.save(path)


def create_empty_project(client: httpx.Client, token: str) -> str:
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={"name": f"probe-import-{uuid.uuid4().hex[:8]}", "canvas_data": {"nodes": [], "edges": []}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def main() -> int:
    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        project_id = create_empty_project(client, token)
        print(f"[project] id={project_id}")

        with tempfile.TemporaryDirectory() as tmp:
            xlsx = Path(tmp) / "probe_import.xlsx"
            build_minimal_xlsx(xlsx)

            with xlsx.open("rb") as f:
                scan = client.post(
                    f"{BASE}/api/import/document/scan",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"project_id": project_id},
                    files={"file": (xlsx.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    timeout=60,
                )
            scan.raise_for_status()
            scan_body = scan.json()
            session_id = scan_body.get("import_session_id")
            sheets = scan_body.get("sheets") or []
            assert session_id, scan_body
            assert sheets, scan_body
            sheet_name = sheets[0].get("sheet_name") or sheets[0].get("name") or "ep1"
            print(f"[scan] session={session_id} sheet={sheet_name}")

            parse = client.post(
                f"{BASE}/api/import/document/parse",
                headers=headers(token),
                json={
                    "project_id": project_id,
                    "import_session_id": session_id,
                    "sheet_names": [sheet_name],
                },
                timeout=120,
            )
            parse.raise_for_status()
            parsed_sheets = parse.json().get("sheets") or []
            assert parsed_sheets, parse.json()
            sheet_payload = parsed_sheets[0]
            rows = sheet_payload.get("rows") or []
            assert len(rows) >= 1, sheet_payload
            content_hash = sheet_payload.get("content_hash") or ""
            print(f"[parse] rows={len(rows)} hash={content_hash[:12]}...")

            apply = client.post(
                f"{BASE}/api/import/document/apply",
                headers=headers(token),
                json={
                    "project_id": project_id,
                    "import_session_id": session_id,
                    "cleanup_session": True,
                    "shot_tables": [
                        {
                            "confirmed": True,
                            "sheet_name": sheet_name,
                            "label": sheet_name,
                            "rows": rows,
                            "segments": sheet_payload.get("segments") or [],
                            "content_hash": content_hash,
                        }
                    ],
                },
                timeout=60,
            )
            apply.raise_for_status()
            apply_body = apply.json()
            created = apply_body.get("created_node_ids") or apply_body.get("created_nodes") or []
            assert created, apply_body
            print(f"[apply] created_node_ids={created}")

        proj = client.get(f"{BASE}/api/canvas/projects/{project_id}", headers=headers(token), timeout=30)
        proj.raise_for_status()
        canvas = proj.json().get("canvas_data") or {}
        nodes = canvas.get("nodes") or []
        tables = [n for n in nodes if n.get("type") == "script-table"]
        assert tables, "no script-table after apply"
        data = tables[0].get("data") or {}
        applied_rows = data.get("rows") or []
        assert len(applied_rows) >= 1, data
        print(f"[verify] script-table rows={len(applied_rows)}")

    print("PASS: import document HTTP probe")
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
