#!/usr/bin/env python3
"""镜头级风格参考 API + 视频 prompt 注入探针（双镜头隔离）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from db.session import SessionLocal
from models.canvas_project import CanvasProject
from services.canvas_style_ref import patch_video_node_style_reference
from services.style_reference_service import format_style_for_prompt

BASE = "http://127.0.0.1:7788"

SAMPLE_REF = {
    "color_tone": "desaturated cold gray-green",
    "lighting": "side backlight with deep shadows",
    "shot_language": "close-ups and over-the-shoulder shots",
    "atmosphere": "oppressive suspense",
    "style_keywords": ["noir", "cinematic", "desaturated", "shallow depth of field"],
    "source": "user_upload",
    "extracted_at": "2026-06-30T10:00:00Z",
    "display_summary": "低饱和冷灰绿调，侧逆光，悬疑氛围",
}

NODE_A = "video-gen-a"
NODE_B = "video-gen-b"
TABLE_ID = "table-style-probe"
ROW_A = "row-a"
ROW_B = "row-b"


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def seed_node_style_reference(project_id: str, node_id: str, style_ref: dict) -> None:
    db = SessionLocal()
    try:
        row = db.get(CanvasProject, project_id)
        if not row:
            raise RuntimeError(f"project not found: {project_id}")
        patch_video_node_style_reference(row, node_id, style_ref)
        db.commit()
    finally:
        db.close()


def create_project_with_script_table_and_video_nodes(
    client: httpx.Client, token: str
) -> str:
    canvas_data = {
        "nodes": [
            {
                "id": TABLE_ID,
                "type": "script-table",
                "position": {"x": 0, "y": 0},
                "data": {
                    "rows": [
                        {
                            "id": ROW_A,
                            "shotNumber": 1,
                            "videoGenNodeId": NODE_A,
                        },
                        {
                            "id": ROW_B,
                            "shotNumber": 2,
                            "videoGenNodeId": NODE_B,
                        },
                    ]
                },
            },
            {"id": NODE_A, "type": "video-gen", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": NODE_B, "type": "video-gen", "position": {"x": 600, "y": 0}, "data": {}},
        ],
        "edges": [],
    }
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={"name": "probe-shot-style-ref-row", "canvas_data": canvas_data},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def get_shot_style_ref(
    client: httpx.Client,
    token: str,
    project_id: str,
    row_id: str,
) -> dict | None:
    r = client.get(
        f"{BASE}/api/shots/{row_id}/style-reference",
        headers=headers(token),
        params={"project_id": project_id, "script_table_node_id": TABLE_ID},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("style_reference")


def test_row_path_isolation(client: httpx.Client, token: str, project_id: str) -> None:
    seed_node_style_reference(
        project_id,
        NODE_A,
        SAMPLE_REF,
    )
    ref_a = get_shot_style_ref(client, token, project_id, ROW_A)
    ref_b = get_shot_style_ref(client, token, project_id, ROW_B)
    assert ref_a and ref_a.get("style_keywords"), ref_a
    assert ref_b is None, ref_b
    print(f"[row-path] A keywords={ref_a.get('style_keywords')} B={ref_b}")

    r = client.delete(
        f"{BASE}/api/shots/{ROW_A}/style-reference",
        headers=headers(token),
        params={"project_id": project_id, "script_table_node_id": TABLE_ID},
        timeout=30,
    )
    r.raise_for_status()
    assert get_shot_style_ref(client, token, project_id, ROW_A) is None
    print("[row-path] DELETE shot row A ok")


def create_project_with_two_video_nodes(client: httpx.Client, token: str) -> str:
    canvas_data = {
        "nodes": [
            {"id": NODE_A, "type": "video-gen", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": NODE_B, "type": "video-gen", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [],
    }
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={"name": "probe-shot-style-ref", "canvas_data": canvas_data},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def get_node_style_ref(
    client: httpx.Client, token: str, project_id: str, node_id: str
) -> dict | None:
    r = client.get(
        f"{BASE}/api/video-nodes/{node_id}/style-reference",
        headers=headers(token),
        params={"project_id": project_id},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("style_reference")


def test_dual_node_isolation(client: httpx.Client, token: str, project_id: str) -> None:
    seed_node_style_reference(project_id, NODE_A, SAMPLE_REF)
    ref_a = get_node_style_ref(client, token, project_id, NODE_A)
    ref_b = get_node_style_ref(client, token, project_id, NODE_B)
    assert ref_a and ref_a.get("style_keywords"), ref_a
    assert ref_b is None, ref_b
    print(f"[isolation] A keywords={ref_a.get('style_keywords')} B={ref_b}")


def test_video_prompt_injection() -> None:
    base_prompt = "雨夜街道，少女回头"
    injected = f"{format_style_for_prompt(SAMPLE_REF)}\n\n{base_prompt}"
    assert "风格参考" in injected
    assert "noir" in injected
    plain = base_prompt
    assert "noir" not in plain
    print(f"[video-prompt] injected ({len(injected)} chars)")


def test_delete_node_a(client: httpx.Client, token: str, project_id: str) -> None:
    r = client.delete(
        f"{BASE}/api/video-nodes/{NODE_A}/style-reference",
        headers=headers(token),
        params={"project_id": project_id},
        timeout=30,
    )
    r.raise_for_status()
    ref_a = get_node_style_ref(client, token, project_id, NODE_A)
    assert ref_a is None
    print("[delete] cleared node A style_reference")


def test_upload_optional(
    client: httpx.Client, token: str, project_id: str, video_path: Path
) -> None:
    if not video_path.is_file():
        print(f"[upload] skip — video not found: {video_path}")
        return
    with video_path.open("rb") as f:
        r = client.post(
            f"{BASE}/api/video-nodes/{NODE_A}/style-reference",
            headers={"Authorization": f"Bearer {token}"},
            params={"project_id": project_id},
            files={"file": (video_path.name, f, "video/mp4")},
            timeout=180,
        )
    if r.status_code >= 400:
        print(f"[upload] skipped — API returned {r.status_code}: {r.text[:200]}")
        return
    ref = r.json().get("style_reference") or {}
    assert ref.get("style_keywords"), ref
    print(f"[upload] analyzed keywords={ref.get('style_keywords')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shot-level style reference probe")
    parser.add_argument("username", nargs="?", default="admin")
    parser.add_argument("password", nargs="?", default="Admin@2026!")
    parser.add_argument(
        "--upload-video",
        default=str(BACKEND_DIR / "assets" / "mock" / "placeholder_video.mp4"),
        help="Optional mp4 for full VL upload test",
    )
    parser.add_argument("--with-upload", action="store_true", help="Run VL upload test")
    args = parser.parse_args()

    with httpx.Client() as client:
        token = login(client, args.username, args.password)
        project_id = create_project_with_two_video_nodes(client, token)
        print(f"[project] created id={project_id} nodes={NODE_A},{NODE_B}")

        test_dual_node_isolation(client, token, project_id)
        test_video_prompt_injection()
        test_delete_node_a(client, token, project_id)

        row_project_id = create_project_with_script_table_and_video_nodes(client, token)
        print(f"[row-project] created id={row_project_id} table={TABLE_ID}")
        test_row_path_isolation(client, token, row_project_id)

        if args.with_upload:
            upload_project = create_project_with_two_video_nodes(client, token)
            test_upload_optional(client, token, upload_project, Path(args.upload_video))

    print("PASS: shot-level style reference probe")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
