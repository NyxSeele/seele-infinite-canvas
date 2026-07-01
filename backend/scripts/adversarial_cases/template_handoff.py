"""类别 6：起步模板与创意卡衔接。"""

CASES: list[dict] = [
    {
        "id": "cat6_template_then_free_text",
        "category": "template_handoff",
        "description": "广告短片模板出卡后，不选卡片直接描述别的需求",
        "known_weakness": "意图 D ask_user 与用户自由输入衔接",
        "canvas_state": "empty",
        "turns": [
            {"role": "user", "content": "帮我做一个30秒广告短片"},
            {
                "role": "assistant",
                "content": "我准备了三个创意方向，请选择：山城烟火 / 未来之城 / 人文纪实",
            },
            {
                "role": "user",
                "content": "其实我想做的是宠物食品广告，主角是一只柯基，不要城市题材",
            },
        ],
        "eval_hint": "期望：按新需求重新 ask_user 或 create_text_note（宠物/柯基），不应卡在「请先选择上方方案」",
    },
    {
        "id": "cat6_ignore_creative_options",
        "category": "template_handoff",
        "description": "创意卡展示后直接说「继续生成节拍」",
        "known_weakness": "未选方案就推进阶段二",
        "canvas_state": "has_text_note",
        "turns": [
            {"role": "user", "content": "我想拍一段重庆火锅宣传片"},
            {
                "role": "assistant",
                "content": "请选择创意方向：麻辣江湖 / 市井烟火 / 品牌故事",
            },
            {"role": "user", "content": "继续，先生成节拍"},
        ],
        "eval_hint": "期望：提醒先选定方案（ask_user 或 done），或识别用户跳过选题的意图后 create_text_note；禁止无分镜表时 split_shot_beats",
    },
    {
        "id": "cat6_partial_option_match",
        "category": "template_handoff",
        "description": "用户输入与卡片标题部分匹配但不完全一致",
        "known_weakness": "「我选择」意图识别",
        "canvas_state": "empty",
        "turns": [
            {"role": "user", "content": "帮我想几个短剧分镜方向"},
            {
                "role": "assistant",
                "content": "方案：都市逆袭 / 古风情缘 / 悬疑碎片",
            },
            {"role": "user", "content": "就古风吧，偏言情一点"},
        ],
        "eval_hint": "期望：识别为选定「古风情缘」并 create_text_note 开链路，或 ask_user 确认是否指该方案",
    },
]
