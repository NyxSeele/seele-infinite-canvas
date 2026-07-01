"""类别 4：矛盾与撤销表达。"""

CASES: list[dict] = [
    {
        "id": "cat4_self_correct_name",
        "category": "contradiction_undo",
        "description": "「加一个角色叫小明，不对，叫小红」",
        "known_weakness": "单句内自我修正",
        "canvas_state": "has_script_table",
        "turns": [
            {"role": "user", "content": "加一个角色叫小明，不对，叫小红"},
        ],
        "eval_hint": "期望：manage_cast 仅添加「小红」，或 update 语义；不应同时添加小明和小红",
    },
    {
        "id": "cat4_undo_last_action",
        "category": "contradiction_undo",
        "description": "「撤销刚才那个操作」",
        "known_weakness": "协议无显式撤销 action",
        "canvas_state": "just_created_cast",
        "turns": [
            {"role": "user", "content": "添加角色小李"},
            {"role": "assistant", "content": "已添加角色小李到设定库。"},
            {"role": "user", "content": "撤销刚才那个操作"},
        ],
        "eval_hint": "期望：done 说明无法自动撤销并建议手动删除/或给出可行替代；不应假装已撤销或误触发 pipeline_step",
    },
    {
        "id": "cat4_flip_flop_delete",
        "category": "contradiction_undo",
        "description": "「删掉，不对我又想要了」",
        "known_weakness": "连续反悔",
        "canvas_state": "has_script_table",
        "turns": [
            {"role": "user", "content": "把教室场景删掉，不对我又想要了"},
        ],
        "eval_hint": "期望：以最终意图为准保留教室场景，或 ask_user 确认当前到底要删还是留",
    },
]
