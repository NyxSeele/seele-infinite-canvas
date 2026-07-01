"""阶段二 mock 出图/视频链路探针（跳过阶段一 LLM，专注状态机 + mock API）。"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

# 复用主探针工具
from _agent_pipeline_e2e_probe import (
    BASE,
    apply_script_table,
    expect_pipeline_step,
    headers,
    login,
    patch_script_row,
    run_agent,
    run_canvas_image,
    run_canvas_video,
    snapshot_from_nodes,
    split_shot_beats_api,
)

MOCK_SCREENPLAY = "镜1 晨光初醒\n镜2 竹香早餐"


def main() -> int:
    issues: list[str] = []
    with httpx.Client() as client:
        token = login("admin", "Admin@2026!")
        pr = client.get(f"{BASE}/api/canvas/projects", headers=headers(token), timeout=30)
        pr.raise_for_status()
        projects = pr.json().get("projects") or []
        if not projects:
            print("NO_PROJECT")
            return 1
        project_id = projects[0]["id"]
        print("project", project_id)

        nodes = [
            {
                "id": "text-response-seed",
                "type": "text_response",
                "position": {"x": 520, "y": 160},
                "content_preview": MOCK_SCREENPLAY[:150],
                "label": "文本回复",
                "status": "completed",
            },
            {
                "id": "outline-seed",
                "type": "outline",
                "position": {"x": 900, "y": 160},
                "content_preview": "晨光初醒 竹香早餐",
                "label": "大纲",
                "loading": False,
                "scene_count": 2,
            },
        ]
        edges = [{"source": "text-response-seed", "target": "outline-seed"}]
        script_id, script_rows = apply_script_table(nodes, edges, "outline-seed", row_count=2)
        patch_script_row(script_rows, "row-1", has_beats=True, beat_prompt_count=3, keyframe_count=3)
        patch_script_row(script_rows, "row-2", has_beats=True, beat_prompt_count=3, keyframe_count=3)

        messages = [
            {"role": "assistant", "content": "分镜表已就绪，2 镜"},
            {"role": "user", "content": "生成分镜图"},
        ]

        # R6 — 镜1 出图
        e6, actions6, err6, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R6] agent {e6:.1f}s errors={err6}")
        issue6 = expect_pipeline_step(actions6, "generate_storyboard", "R6")
        if issue6:
            issues.append(issue6)
        else:
            step6 = next(a for a in actions6 if a.get("type") == "pipeline_step")
            row_id = (step6.get("data") or {}).get("row_id") or "row-1"
            elapsed, status, result, err = run_canvas_image(
                client,
                token,
                node_id=f"{script_id}-{row_id}-storyboard",
                prompt="镜1 渝爱醒来",
                reference_images=["/api/uploads/images/mock-cast-ref.jpg"],
            )
            print(f"  mock image {elapsed:.1f}s status={status} err={err}")
            if status != "completed":
                issues.append(f"R6 mock image failed: {err}")
            else:
                patch_script_row(script_rows, row_id, storyboard_ready=True)

        # R7 — 镜1 视频
        messages.extend([
            {"role": "assistant", "content": "分镜图已生成"},
            {"role": "user", "content": "生成视频"},
        ])
        e7, actions7, err7, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R7] agent {e7:.1f}s errors={err7}")
        issue7 = expect_pipeline_step(actions7, "generate_video", "R7")
        if issue7:
            issues.append(issue7)
        else:
            step7 = next(a for a in actions7 if a.get("type") == "pipeline_step")
            row_id = (step7.get("data") or {}).get("row_id") or "row-1"
            elapsed, status, result, err = run_canvas_video(
                client,
                token,
                node_id=f"{script_id}-{row_id}-video",
                prompt="镜1 渝爱醒来视频",
            )
            print(f"  mock video {elapsed:.1f}s status={status} err={err}")
            if status != "completed":
                issues.append(f"R7 mock video failed: {err}")
            else:
                patch_script_row(script_rows, row_id, has_video=True, video_generating=False)

        # R8 — 镜2 出图（一镜一步）
        messages.extend([
            {"role": "assistant", "content": "镜1 视频已完成"},
            {"role": "user", "content": "继续"},
        ])
        e8, actions8, err8, _ = run_agent(
            client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
        )
        print(f"\n[R8] agent {e8:.1f}s errors={err8}")
        step8 = next((a for a in actions8 if a.get("type") == "pipeline_step"), None)
        step_name = step8.get("step") if step8 else None
        print("  step8", step_name)
        if step_name == "generate_storyboard":
            row_id = (step8.get("data") or {}).get("row_id") or "row-2"
            elapsed, status, result, err = run_canvas_image(
                client,
                token,
                node_id=f"{script_id}-{row_id}-storyboard",
                prompt="镜2 渝爱吃竹子",
            )
            print(f"  mock image R8 {elapsed:.1f}s status={status} err={err}")
            if status != "completed":
                issues.append(f"R8 mock image failed: {err}")
            else:
                patch_script_row(script_rows, row_id, storyboard_ready=True)
            messages.extend([
                {"role": "assistant", "content": "镜2 分镜图已生成"},
                {"role": "user", "content": "生成视频"},
            ])
            e8c, actions8c, err8c, _ = run_agent(
                client, token, project_id, messages, snapshot_from_nodes(nodes, edges), "manual"
            )
            print(f"\n[R8c] agent {e8c:.1f}s errors={err8c}")
            issue8c = expect_pipeline_step(actions8c, "generate_video", "R8c")
            if issue8c:
                issues.append(issue8c)
            else:
                step8c = next(a for a in actions8c if a.get("type") == "pipeline_step")
                row_id = (step8c.get("data") or {}).get("row_id") or "row-2"
                elapsed, status, result, err = run_canvas_video(
                    client,
                    token,
                    node_id=f"{script_id}-{row_id}-video",
                    prompt="镜2 渝爱吃竹子视频",
                )
                print(f"  mock video R8c {elapsed:.1f}s status={status} err={err}")
                if status != "completed":
                    issues.append(f"R8c mock video failed: {err}")
                else:
                    patch_script_row(script_rows, row_id, has_video=True, video_generating=False)
        elif step_name == "generate_video":
            row_id = (step8.get("data") or {}).get("row_id") or "row-2"
            elapsed, status, result, err = run_canvas_video(
                client, token, node_id=f"{script_id}-{row_id}-video", prompt="镜2 视频"
            )
            if status != "completed":
                issues.append(f"R8 mock video failed: {err}")
        else:
            issues.append(f"R8 unexpected step: {step8}")

    print("\n=== STAGE2 MOCK ===")
    if issues:
        for item in issues:
            print("-", item)
        return 1
    print("PASS: 2镜 节拍→出图→视频 全链路 completed（mock，无 ComfyUI）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
