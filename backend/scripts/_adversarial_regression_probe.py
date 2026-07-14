"""
对抗性 Prompt 回归断言：将 HANDOFF 2026-06-25 修复的 6 条问题用例沉淀为自动校验。

用法（需已启动后端 :7788，且 DASHSCOPE_API_KEY / 文本模型可用）：
  cd backend
  .\\.venv\\Scripts\\python.exe scripts\\_adversarial_regression_probe.py
  .\\.venv\\Scripts\\python.exe scripts\\_adversarial_regression_probe.py --id cat3_cross_chain_character_reuse
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from _adversarial_prompt_probe import (
    build_messages,
    build_nodes_edges,
    get_project_id,
)
from _agent_pipeline_e2e_probe import (
    expect_pipeline_step,
    login,
    run_agent,
    snapshot_from_nodes,
)

# HANDOFF 2026-06-25 修复的 6 条问题用例 → 机器可读断言
REGRESSION_ASSERTIONS: dict[str, dict] = {
    "cat1_continue_in_ask_user": {
        "expect_type": "done",
        "forbid_pipeline_step": True,
        "label": "ask_user 待配图时说「继续」",
    },
    "cat1_continue_after_storyboard": {
        "expect_pipeline_step": "generate_video",
        "label": "镜1 分镜图完成后说「继续」→ 生成镜1视频",
    },
    "cat3_regenerate_this_shot_video": {
        "expect_type": "ask_user",
        "forbid_pipeline_step": True,
        "label": "多链路「重新生成这一镜视频」",
    },
    "cat3_cross_chain_character_reuse": {
        "expect_type": "ask_user",
        "forbid_pipeline_step": True,
        "label": "跨链路「刚才那个角色用这里」",
    },
    "cat3_which_script_table": {
        "expect_type": "ask_user",
        "forbid_pipeline_step": True,
        "label": "两张分镜表「给分镜表加人物」",
    },
    "cat6_ignore_creative_options": {
        "expect_type": "done",
        "forbid_pipeline_step": True,
        "label": "创意卡未选时说「继续，先生成节拍」",
    },
}

REGRESSION_CASE_IDS = list(REGRESSION_ASSERTIONS.keys())


def expect_action_type(actions: list[dict], expected_type: str, label: str) -> str | None:
    """断言 actions 中含指定 type。"""
    match = next((a for a in actions if a.get("type") == expected_type), None)
    if not match:
        types = [a.get("type") for a in actions]
        return f"{label}: expected type={expected_type}, got {types}"
    return None


def expect_no_pipeline_step(actions: list[dict], label: str) -> str | None:
    """断言 actions 中无 pipeline_step。"""
    step = next((a for a in actions if a.get("type") == "pipeline_step"), None)
    if step:
        return f"{label}: expected NO pipeline_step, got step={step.get('step')}"
    return None


def load_regression_cases(case_id: str | None) -> list[dict]:
    from adversarial_cases import ALL_CASES

    cases = [c for c in ALL_CASES if c["id"] in REGRESSION_ASSERTIONS]
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]
        if not cases:
            raise SystemExit(f"未找到回归用例 ID: {case_id!r}")
    return cases


def run_assertions(case_id: str, actions: list[dict], errors: list) -> list[str]:
    issues: list[str] = []
    spec = REGRESSION_ASSERTIONS[case_id]
    label = spec.get("label") or case_id

    if errors:
        issues.append(f"{label}: SSE errors={errors}")

    if not actions and not errors:
        issues.append(f"{label}: no actions returned")

    if spec.get("expect_type"):
        err = expect_action_type(actions, spec["expect_type"], label)
        if err:
            issues.append(err)

    if spec.get("expect_pipeline_step"):
        err = expect_pipeline_step(actions, spec["expect_pipeline_step"], label)
        if err:
            issues.append(err)

    if spec.get("forbid_pipeline_step"):
        err = expect_no_pipeline_step(actions, label)
        if err:
            issues.append(err)

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="对抗性 Prompt 回归断言探针")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="Admin@2026!")
    parser.add_argument("--id", default=None, help="仅跑指定用例 ID")
    parser.add_argument(
        "--mode",
        default="manual",
        choices=("manual", "auto"),
        help="Agent execution_mode",
    )
    args = parser.parse_args()

    cases = load_regression_cases(args.id)
    print(f"对抗性回归探针 — {len(cases)} 条用例")
    print("（需后端 :7788 已启动）\n")

    try:
        token = login(args.username, args.password)
    except httpx.ConnectError:
        print("错误：无法连接 http://127.0.0.1:7788，请先启动后端")
        return 1

    all_issues: list[str] = []
    passed = 0

    with httpx.Client() as client:
        project_id = get_project_id(client, token)
        print(f"project_id={project_id}\n")

        for i, case in enumerate(cases, 1):
            case_id = case["id"]
            print(f"[{i}/{len(cases)}] {case_id} …", flush=True)

            nodes, edges = build_nodes_edges(case["canvas_state"])
            snapshot = snapshot_from_nodes(nodes, edges)
            messages = build_messages(case.get("turns") or [])

            elapsed = 0.0
            try:
                elapsed, actions, errors, _thinking = run_agent(
                    client,
                    token,
                    project_id,
                    messages,
                    snapshot,
                    args.mode,
                )
            except Exception as exc:
                all_issues.append(f"{case_id}: request failed: {exc}")
                print(f"  FAIL: {exc}")
                continue

            issues = run_assertions(case_id, actions, errors)
            if issues:
                all_issues.extend(issues)
                summary = ", ".join(issues)
                print(f"  FAIL ({elapsed:.1f}s): {summary}")
            else:
                passed += 1
                types = [a.get("type") for a in actions]
                step = next(
                    (a.get("step") for a in actions if a.get("type") == "pipeline_step"),
                    None,
                )
                detail = f"step={step}" if step else f"types={types}"
                print(f"  PASS ({elapsed:.1f}s): {detail}")

    print(f"\n结果: {passed}/{len(cases)} 通过")
    if all_issues:
        print("\n失败项:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
