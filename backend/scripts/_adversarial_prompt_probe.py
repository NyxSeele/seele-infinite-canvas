"""
对抗性 Prompt 探测：批量发送 + 完整记录（供人工复核，非断言式单测）。

用法（需已启动后端 :7788，且 DASHSCOPE_API_KEY / 文本模型可用）：
  cd backend
  .\\.venv\\Scripts\\python.exe scripts\\_adversarial_prompt_probe.py
  .\\.venv\\Scripts\\python.exe scripts\\_adversarial_prompt_probe.py --category short_commands
  .\\.venv\\Scripts\\python.exe scripts\\_adversarial_prompt_probe.py --username admin --password Admin@2026!
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from _agent_pipeline_e2e_probe import (
    BASE,
    headers,
    login,
    make_row_summary,
    run_agent,
    snapshot_from_nodes,
)
from adversarial_cases import ALL_CASES, CASES_BY_CATEGORY

RESULTS_ROOT = Path(__file__).resolve().parent / "adversarial_results"

CATEGORY_LABELS = {
    "short_commands": "短指令",
    "cast_scene_boundary": "cast/scene 边界",
    "multi_chain_reference": "多链路指代",
    "contradiction_undo": "矛盾与撤销",
    "skip_step": "跳步越级",
    "template_handoff": "起步模板衔接",
}


def _text_note_node(note_id: str = "text-note-adv-1", *, prompt: str = "重庆宣传片创意") -> dict:
    return {
        "id": note_id,
        "type": "text_note",
        "position": {"x": 120, "y": 160},
        "content_preview": prompt[:150],
        "label": "文本",
        "text_mode": "screenplay",
        "intent": "screenplay",
    }


def _outline_node(outline_id: str, *, source_note_id: str | None = None) -> dict:
    return {
        "id": outline_id,
        "type": "outline",
        "position": {"x": 560, "y": 160},
        "content_preview": "镜1 晨光 镜2 竹香 镜3 嬉戏",
        "label": "大纲",
        "loading": False,
        "scene_count": 3,
        "linked_script_table_id": None,
    }


def _script_table_node(
    script_id: str,
    outline_id: str,
    *,
    rows: list[dict] | None = None,
    cast_library: list[dict] | None = None,
    scene_library: list[dict] | None = None,
    x: float = 1200,
) -> dict:
    row_count = len(rows) if rows is not None else 2
    rows = rows or [make_row_summary(f"row-{i + 1}", i + 1) for i in range(row_count)]
    return {
        "id": script_id,
        "type": "script_table",
        "position": {"x": x, "y": 160},
        "content_preview": f"分镜表 {row_count} 镜",
        "label": "分镜表",
        "row_count": row_count,
        "loading": False,
        "rows_summary": rows,
        "source_outline_id": outline_id,
        "cast_library": cast_library or [],
        "scene_library": scene_library or [],
    }


def build_nodes_edges(canvas_state: str) -> tuple[list[dict], list[dict]]:
    """按预置枚举构造画布 nodes / edges。"""
    nodes: list[dict] = []
    edges: list[dict] = []

    if canvas_state == "empty":
        return nodes, edges

    if canvas_state == "has_text_note":
        nodes.append(_text_note_node())
        return nodes, edges

    if canvas_state == "has_outline":
        note_id = "text-note-adv-1"
        outline_id = "outline-adv-1"
        nodes.extend([_text_note_node(note_id), _outline_node(outline_id)])
        edges.append({"source": note_id, "target": outline_id})
        return nodes, edges

    if canvas_state in (
        "has_script_table",
        "ask_user_blocked",
        "just_created_cast",
        "has_script_table_with_scene_ref",
        "has_script_table_progress",
    ):
        note_id = "text-note-adv-1"
        outline_id = "outline-adv-1"
        script_id = "script-table-adv-1"
        nodes.extend([_text_note_node(note_id), _outline_node(outline_id)])
        edges.extend(
            [
                {"source": note_id, "target": outline_id},
                {"source": outline_id, "target": script_id},
            ]
        )

        rows = [make_row_summary("row-1", 1), make_row_summary("row-2", 2)]
        cast_library: list[dict] = []
        scene_library: list[dict] = []

        if canvas_state == "ask_user_blocked":
            cast_library = [
                {
                    "id": "cast-xiaoming",
                    "name": "小明",
                    "type": "character",
                    "has_image": False,
                    "pending_image": True,
                    "description": "主角少年",
                }
            ]
        elif canvas_state == "just_created_cast":
            cast_library = [
                {
                    "id": "cast-xiaohong",
                    "name": "小红",
                    "type": "character",
                    "has_image": False,
                    "pending_image": True,
                    "description": "刚添加的角色",
                }
            ]
        elif canvas_state == "has_script_table_with_scene_ref":
            scene_library = [
                {
                    "id": "scene-classroom",
                    "name": "教室",
                    "type": "scene",
                    "has_image": False,
                    "pending_image": True,
                    "description": "室内教室，午后阳光",
                }
            ]
            rows[0]["location_id"] = "scene-classroom"
        elif canvas_state == "has_script_table_progress":
            rows[0] = make_row_summary(
                "row-1",
                1,
                has_beats=True,
                storyboard_ready=True,
                has_video=False,
            )

        nodes.append(
            _script_table_node(
                script_id,
                outline_id,
                rows=rows,
                cast_library=cast_library,
                scene_library=scene_library,
            )
        )
        return nodes, edges

    if canvas_state == "two_script_tables":
        for idx in (1, 2):
            note_id = f"text-note-chain-{idx}"
            outline_id = f"outline-chain-{idx}"
            script_id = f"script-table-chain-{idx}"
            nodes.extend(
                [
                    _text_note_node(note_id, prompt=f"链路{idx}主题"),
                    _outline_node(outline_id),
                    _script_table_node(
                        script_id,
                        outline_id,
                        x=1200 + (idx - 1) * 480,
                        cast_library=[
                            {
                                "id": f"cast-chain{idx}",
                                "name": "小明" if idx == 1 else "阿花",
                                "type": "character",
                                "has_image": True,
                            }
                        ],
                    ),
                ]
            )
            edges.extend(
                [
                    {"source": note_id, "target": outline_id},
                    {"source": outline_id, "target": script_id},
                ]
            )
        return nodes, edges

    raise ValueError(f"未知 canvas_state: {canvas_state}")


def build_messages(turns: list[dict]) -> list[dict]:
    return [{"role": t["role"], "content": t["content"]} for t in turns]


def get_project_id(client: httpx.Client, token: str) -> str:
    r = client.get(f"{BASE}/api/canvas/projects", headers=headers(token), timeout=30)
    r.raise_for_status()
    projects = r.json().get("projects") or []
    if not projects:
        raise RuntimeError("无 canvas 项目，请用 admin 账号先创建项目")
    return projects[0]["id"]


def _format_user_inputs(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        role = t.get("role", "user")
        content = (t.get("content") or "").strip()
        if role == "user":
            lines.append(f"- 用户：「{content}」")
        else:
            preview = content[:120] + ("…" if len(content) > 120 else "")
            lines.append(f"- 助手（历史）：{preview}")
    return "\n".join(lines) if lines else "（无）"


def _action_summary(actions: list[dict]) -> str:
    if not actions:
        return "（无 action）"
    parts = []
    for action in actions:
        atype = action.get("type")
        if atype == "pipeline_step":
            parts.append(f"pipeline_step:{action.get('step')}")
        elif atype == "ask_user":
            opts = action.get("options") or []
            titles = [o.get("title") or o.get("id") for o in opts if isinstance(o, dict)]
            parts.append(f"ask_user({', '.join(titles[:3])})")
        elif atype == "done":
            parts.append("done")
        else:
            parts.append(str(atype))
    return " → ".join(parts)


def write_case_markdown(
    out_dir: Path,
    case: dict,
    *,
    elapsed: float,
    actions: list[dict],
    errors: list[dict],
    thinking: str,
    sse_events: list[dict] | None = None,
) -> Path:
    cat = case["category"]
    cat_label = CATEGORY_LABELS.get(cat, cat)
    case_id = case["id"]
    filename = f"{case_id}.md"
    path = out_dir / filename

    errors_text = ""
    if errors:
        errors_text = "\n\n## 错误\n\n```json\n" + json.dumps(errors, ensure_ascii=False, indent=2) + "\n```\n"

    sse_text = ""
    if sse_events is not None:
        sse_text = (
            "\n\n## SSE 事件流（调试）\n\n```json\n"
            + json.dumps(sse_events, ensure_ascii=False, indent=2)
            + "\n```\n"
        )

    thinking_block = (thinking or "（无 thinking 事件）").strip()
    actions_json = json.dumps(actions, ensure_ascii=False, indent=2)

    body = f"""# [{cat}] {cat_label} — {case["description"]}

**ID**: `{case_id}`
**已知脆弱点**: {case.get("known_weakness", "—")}
**期望行为**: {case.get("eval_hint", "—")}
**耗时**: {elapsed:.1f}s
**Action 摘要**: {_action_summary(actions)}

## 输入

**画布状态**: `{case["canvas_state"]}`

{_format_user_inputs(case.get("turns") or [])}

## Agent 思考过程

{thinking_block}

## 返回 Actions

```json
{actions_json}
```
{errors_text}{sse_text}
## 人工复核

- [ ] 合理
- [ ] 有问题：_______________________
- [ ] 不确定

---
"""
    path.write_text(body, encoding="utf-8")
    return path


def write_summary(
    out_dir: Path,
    results: list[dict],
    *,
    username: str,
    categories: list[str] | None,
) -> Path:
    path = out_dir / "summary.md"
    lines = [
        "# 对抗性 Prompt 测试 — 运行汇总",
        "",
        f"- **运行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **账号**: {username}",
        f"- **类别过滤**: {', '.join(categories) if categories else '全部'}",
        f"- **用例数**: {len(results)}",
        "",
        "| ID | 类别 | 描述 | 耗时 | Action 摘要 | 错误 | 记录文件 |",
        "|----|------|------|------|-------------|------|----------|",
    ]
    for row in results:
        err = "是" if row.get("errors") else "否"
        lines.append(
            f"| `{row['id']}` | {row['category']} | {row['description']} "
            f"| {row['elapsed']:.1f}s | {row['action_summary']} | {err} "
            f"| [{row['file']}](./{row['file']}) |"
        )
    lines.extend(
        [
            "",
            "## 下一步（人工）",
            "",
            "1. 打开各用例 `.md`，勾选「合理 / 有问题 / 不确定」",
            "2. 对「有问题」写明理想响应，汇总后改 `agent_service.py` SYSTEM_PROMPT",
            "3. 修复验证后，将案例沉淀为 E2E 探针断言",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_cases(category: str | None) -> list[dict]:
    if not category:
        return list(ALL_CASES)
    if category not in CASES_BY_CATEGORY:
        known = ", ".join(sorted(CASES_BY_CATEGORY))
        raise SystemExit(f"未知类别 {category!r}，可选: {known}")
    return list(CASES_BY_CATEGORY[category])


def main() -> int:
    parser = argparse.ArgumentParser(description="对抗性 Prompt 批量记录探针")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="Admin@2026!")
    parser.add_argument(
        "--category",
        default=None,
        help="仅跑指定类别，如 short_commands",
    )
    parser.add_argument(
        "--id",
        default=None,
        help="仅跑指定用例 ID，如 cat3_cross_chain_character_reuse",
    )
    parser.add_argument(
        "--mode",
        default="manual",
        choices=("manual", "auto"),
        help="Agent execution_mode",
    )
    args = parser.parse_args()

    cases = load_cases(args.category)
    if args.id:
        cases = [c for c in cases if c["id"] == args.id]
        if not cases:
            raise SystemExit(f"未找到用例 ID: {args.id!r}")
    if not cases:
        print("没有用例")
        return 1

    run_id = datetime.now().strftime("RUN_%Y%m%d_%H%M%S")
    out_dir = RESULTS_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"对抗性 Prompt 探针 — {len(cases)} 条用例 → {out_dir}")
    print("（需后端 :7788 已启动）\n")

    try:
        token = login(args.username, args.password)
    except httpx.ConnectError:
        print("错误：无法连接 http://127.0.0.1:7788，请先启动后端（uvicorn main:app --port 7788）")
        return 1
    results: list[dict] = []

    with httpx.Client() as client:
        project_id = get_project_id(client, token)
        print(f"project_id={project_id}\n")

        for i, case in enumerate(cases, 1):
            case_id = case["id"]
            print(f"[{i}/{len(cases)}] {case_id} …", flush=True)
            nodes, edges = build_nodes_edges(case["canvas_state"])
            snapshot = snapshot_from_nodes(nodes, edges)
            messages = build_messages(case.get("turns") or [])

            try:
                elapsed, actions, errors, thinking, events = run_agent(
                    client,
                    token,
                    project_id,
                    messages,
                    snapshot,
                    args.mode,
                    return_events=True,
                )
            except Exception as exc:
                elapsed = 0.0
                actions = []
                errors = [{"event": "error", "content": str(exc)}]
                thinking = ""
                events = []

            md_path = write_case_markdown(
                out_dir,
                case,
                elapsed=elapsed,
                actions=actions,
                errors=errors,
                thinking=thinking,
                sse_events=events,
            )
            action_summary = _action_summary(actions)
            results.append(
                {
                    "id": case_id,
                    "category": case["category"],
                    "description": case["description"],
                    "elapsed": elapsed,
                    "action_summary": action_summary,
                    "errors": errors,
                    "file": md_path.name,
                }
            )
            status = "ERROR" if errors else "OK"
            print(f"  {status} {elapsed:.1f}s {action_summary}")

    summary_path = write_summary(
        out_dir,
        results,
        username=args.username,
        categories=[args.category] if args.category else None,
    )
    print(f"\n汇总: {summary_path}")
    print(f"单条记录目录: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
