"""类别 2：manage_cast / manage_scene 边界混淆。"""

CASES: list[dict] = [
    {
        "id": "cat2_room_style_consistency",
        "category": "cast_scene_boundary",
        "description": "「这个房间的风格也要保持一致」",
        "known_weakness": "技术债 #21：场景 vs 角色一致性措辞相似",
        "canvas_state": "has_script_table",
        "turns": [
            {"role": "user", "content": "这个房间的风格也要保持一致"},
        ],
        "eval_hint": "期望：manage_scene（场景实体），不是 manage_cast",
    },
    {
        "id": "cat2_character_and_scene_both",
        "category": "cast_scene_boundary",
        "description": "「小明站在教室里，两个都要记住」",
        "known_weakness": "技术债 #21：单轮能否输出两个 pipeline_step",
        "canvas_state": "has_script_table",
        "turns": [
            {"role": "user", "content": "小明站在教室里，两个都要记住"},
        ],
        "eval_hint": "期望：manage_cast（小明）+ manage_scene（教室），或一轮 manage_cast 后 done 建议补场景；禁止只用 manage_cast 处理教室",
    },
    {
        "id": "cat2_vague_save_to_library",
        "category": "cast_scene_boundary",
        "description": "「这个也存到库里」（模糊指代）",
        "known_weakness": "技术债 #21：指代消解",
        "canvas_state": "has_script_table_with_scene_ref",
        "turns": [
            {"role": "user", "content": "刚才那张教室参考图不错"},
            {"role": "assistant", "content": "好的，已记录教室场景描述。"},
            {"role": "user", "content": "这个也存到库里"},
        ],
        "eval_hint": "期望：manage_scene 或 ask_user 澄清「这个」指场景图；不应默认 manage_cast",
    },
]
