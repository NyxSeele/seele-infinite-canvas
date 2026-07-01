"""类别 3：多链路场景下的指代消解。"""

CASES: list[dict] = [
    {
        "id": "cat3_regenerate_this_shot_video",
        "category": "multi_chain_reference",
        "description": "两条分镜链路时说「把这一镜的视频重新生成」",
        "known_weakness": "技术债 #7：buildActiveChain / 多主题追踪",
        "canvas_state": "two_script_tables",
        "turns": [
            {"role": "user", "content": "把这一镜的视频重新生成"},
        ],
        "eval_hint": "期望：ask_user 澄清哪条链路/哪一镜，或基于选中节点推断；不应随机选一条链路",
    },
    {
        "id": "cat3_cross_chain_character_reuse",
        "category": "multi_chain_reference",
        "description": "切换话题后说「刚才那个角色用这里」",
        "known_weakness": "技术债 #7：跨链路 cast_library 引用",
        "canvas_state": "two_script_tables",
        "turns": [
            {"role": "user", "content": "我想做一条新的校园短片"},
            {"role": "assistant", "content": "好的，已为你开新链路。"},
            {"role": "user", "content": "刚才那个角色用这里"},
        ],
        "eval_hint": "期望：识别指向上一条链路的角色（如小明），在当前链路 manage_cast 引用或 ask_user 澄清；不应忽略「刚才」",
    },
    {
        "id": "cat3_which_script_table",
        "category": "multi_chain_reference",
        "description": "「给分镜表加一个人物」画布上有两张分镜表",
        "known_weakness": "技术债 #7：script_table_id 歧义",
        "canvas_state": "two_script_tables",
        "turns": [
            {"role": "user", "content": "给分镜表加一个人物叫阿强"},
        ],
        "eval_hint": "期望：manage_cast 带明确 script_table_id，或 ask_user 问哪条链路",
    },
]
