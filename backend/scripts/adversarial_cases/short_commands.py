"""类别 1：短指令在不同上下文下的解析。"""

CASES: list[dict] = [
    {
        "id": "cat1_continue_in_ask_user",
        "category": "short_commands",
        "description": "分镜表卡在 ask_user（待配图）时说「继续」",
        "known_weakness": "技术债 #11：短指令须走 LLM 推断上下文",
        "canvas_state": "ask_user_blocked",
        "turns": [
            {"role": "user", "content": "添加角色叫小明"},
            {
                "role": "assistant",
                "content": "已在角色库添加小明，待配图。是否现在配图？",
            },
            {"role": "user", "content": "继续"},
        ],
        "eval_hint": "期望：续接被打断的 pipeline（如 split_shot_beats / 配图流程），而非重新开始整条链路",
    },
    {
        "id": "cat1_continue_after_storyboard",
        "category": "short_commands",
        "description": "镜1 分镜图已完成时说「继续」",
        "known_weakness": "技术债 #11：「下一步」需从 rows_summary 推断",
        "canvas_state": "has_script_table_progress",
        "turns": [
            {"role": "user", "content": "继续"},
        ],
        "eval_hint": "期望：推进镜1 视频或镜2 节拍/出图，而非重复 generate_storyboard 镜1",
    },
    {
        "id": "cat1_another_one_after_cast",
        "category": "short_commands",
        "description": "刚创建角色后说「再来一个」",
        "known_weakness": "歧义：再建角色 vs 建场景",
        "canvas_state": "just_created_cast",
        "turns": [
            {"role": "user", "content": "添加角色小红"},
            {"role": "assistant", "content": "已在角色库添加小红。"},
            {"role": "user", "content": "再来一个"},
        ],
        "eval_hint": "期望：默认再添加一个角色（manage_cast），或 ask_user 澄清是角色还是场景，不应误触发 manage_scene",
    },
]
