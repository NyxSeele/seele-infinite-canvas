"""类别 5：跳步与越级请求。"""

CASES: list[dict] = [
    {
        "id": "cat5_empty_canvas_final_video",
        "category": "skip_step",
        "description": "空画布直接要「最终视频」",
        "known_weakness": "阶段二禁止跳步",
        "canvas_state": "empty",
        "turns": [
            {"role": "user", "content": "给我生成最终视频"},
        ],
        "eval_hint": "期望：done 引导从创意/文本/大纲开始，禁止 generate_video / create_node(video)",
    },
    {
        "id": "cat5_completely_different_redo",
        "category": "skip_step",
        "description": "已有分镜表时说「重新做一个完全不一样的」",
        "known_weakness": "新链路 vs 修改现有（技术债 #7）",
        "canvas_state": "has_script_table",
        "turns": [
            {"role": "user", "content": "重新做一个完全不一样的校园题材短片"},
        ],
        "eval_hint": "期望：create_text_note 开新链路（意图 B/D），不覆盖现有 script_table 节点",
    },
    {
        "id": "cat5_skip_to_storyboard",
        "category": "skip_step",
        "description": "只有大纲、无分镜表时要「直接出分镜图」",
        "known_weakness": "generate_script_table 前置",
        "canvas_state": "has_outline",
        "turns": [
            {"role": "user", "content": "别废话了，直接给第一镜出分镜图"},
        ],
        "eval_hint": "期望：先 generate_script_table 或 done 说明须先有分镜表；禁止无 script_table 时 generate_storyboard",
    },
]
