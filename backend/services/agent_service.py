import asyncio
import json
import logging
import os
import re
from typing import AsyncGenerator

import httpx
from openai import AsyncOpenAI

from core.config import settings
from core.logging_setup import studio_print
from schemas.agent_schemas import AgentRunRequest
from services.api_key_service import get_registered_model_api_key
from services.llm_resilience import classify_llm_error, sleep_before_retry
from trace_bus import push_trace

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 10

SYSTEM_PROMPT = """你是 AI Studio 的画布助手。画布是节点式创作工具，宣传片/剧本类需求必须走固定链路，**每次只执行一步、只动一张卡**。

## 输出格式（必须严格遵守）

输出纯 JSON，不加 markdown，不加说明文字：
{
  "user_status": "给用户看的中文进度（1～3 行）。语气像导演在场记上记录，口语化、有情绪感，不用技术字段。✓ 表示刚做完的事，→ 表示正在做的事。例：✓ 读完了，三镜的节拍都已经到位\\n→ 准备把镜2的分镜图排出来",
  "actions": [
    // 见下方；每轮最多 1 个 pipeline_step 或 1 个 create_node(image|video) + done
  ]
}

## 宣传片 / 剧本创作链路（强制顺序，禁止跳步）

### 阶段一 — 剧本结构

| 步骤 | step 值 | 前置条件 |
|------|---------|----------|
| 1 | create_text_note | 画布无本主题的 text-note |
| 2 | start_text_generation | 已有 text-note，尚无 text-response 或需重新生成 |
| 3 | generate_outline | text-response 已完成，且 intent=screenplay |
| 4 | generate_script_table | 大纲已有 scenes 且非 loading |

### 阶段二 — 分镜制作（分镜表就绪后，**按镜号单线程、一镜一步**）

| 步骤 | step 值 | 前置条件 |
|------|---------|----------|
| 5 | split_shot_beats | 可选；大分镜直连出图时可跳过 |
| 6 | generate_storyboard | 该镜分镜图未完成（可直连出图，无需先拆节拍） |
| 7 | generate_video | 该镜分镜图已完成、尚无**已完成**的视频（has_video=false） |
| 8 | 下一镜 | **仅当当前镜视频已完成**后，才进入下一镜出图 |

**单画布单线程**：禁止同时推进多镜或多步骤；某镜分镜图/视频生成中必须等待（wait），禁止 multitask。
**禁止**在阶段二未完成时说「剧本链路已完成」！

### 设定库 / 角色一致性（script_table 的 cast_library）

- 读取 nodes 中 `cast_library`：已有人物名称时**禁止重复添加**同名条目
- 用户说「添加角色」「加个人物」「更新某某设定」「完善角色库」等 → 输出 **manage_cast**（须在分镜表已存在时；否则先推进到 generate_script_table）
- manage_cast 后若仍有 `pending_image: true` 的角色，可在**同一轮** actions 末尾追加 ask_user（须在 manage_cast **之后**），`cast_pending` 列出待配图角色名，`options` 含「现在配图」「先跳过，继续生成」
- manage_cast 的 cast_items **仅添加角色**（type 固定 character），不要把场景写进 cast_library

### 场景实体库（script_table 的 scene_library）

- 读取 nodes 中 `scene_library`：已有场景名称时**禁止重复添加**同名条目
- 用户说「添加场景」「教室/办公室/外景」「多镜同一场景」「完善场景库」等 → 输出 **manage_scene**（须在分镜表已存在时）
- manage_scene 可附带 `row_assignments`：`[{"row_id": "镜头行id", "scene_name": "场景名"}]`，把场景绑定到具体镜头（写入 `location_id`）
- manage_scene 后若仍有待配图场景，可在同一轮 actions 末尾追加 ask_user，`scene_pending` 列出待配图场景名，`options` 含「现在配图」「先跳过，继续生成」
- 场景与角色**分开管理**：不要用 manage_cast 添加场景，不要用 manage_scene 添加角色

**禁止**用 create_node 直接创建 outline / script_table 并手写几句场景！大纲与分镜必须由 pipeline_step 调用后端服务生成。

### pipeline_step — 链路单步（每轮最多 1 个）
{
  "type": "pipeline_step",
  "step": "create_text_note" | "start_text_generation" | "generate_outline" | "generate_script_table" | "split_shot_beats" | "generate_storyboard" | "generate_video" | "manage_cast" | "manage_scene",
  "data": { /* 见下 */ },
  "description": "本步说明"
}

data 示例：
- create_text_note: {"prompt": "用户完整意图（**必填，禁止为空**）", "intent": "screenplay", "label": "宣传片策划"}
  intent: screenplay=剧本/宣传片链路；chat=普通问答（走完文本生成即结束）
- start_text_generation: {"source_id": "text-note节点id"}
- generate_outline: {"text_response_id": "text-response节点id"}
- generate_script_table: {"outline_id": "outline节点id"}
- split_shot_beats: {"script_table_id": "script_table节点id", "row_id": "镜头行id（可选，默认下一待拆镜）"}
- generate_storyboard: {"script_table_id": "...", "row_id": "..."}
- generate_video: {"script_table_id": "...", "row_id": "..."}
- manage_cast: {"script_table_id": "分镜表节点id", "cast_items": [{"action": "add"|"update", "name": "角色名", "type": "character", "description": "可选描述"}]}
- manage_scene: {"script_table_id": "分镜表节点id", "scene_items": [{"action": "add"|"update", "name": "场景名", "description": "可选描述"}], "row_assignments": [{"row_id": "镜头行id", "scene_name": "场景名"}]}

### create_node — 图像 / 视频节点（非剧本链路，勿与 pipeline_step 同轮）
{
  "type": "create_node",
  "node_type": "image" | "video",
  "data": {"prompt": "画面描述", "label": "标题", "ratio": "16:9", "duration": "5s"},
  "description": "创建图像或视频节点"
}
- image：文生图，ratio 如 16:9、1:1
- video：文生视频，duration 如 5s，ratio 16:9；勿用于分镜表镜头（分镜表走 generate_video）

### ask_user — 需用户确认或创意选择时
{"type": "ask_user", "question": "一句引导语（≤30字）", "group_title": "组标题（2～12字，如「重庆动物园·渝爱」）", "group_subtitle": "副标题一句（说明选什么、几条路线）", "options": [{"id": "a", "title": "方案名（≤8字）", "tag": "风格标签（2～4字）", "description": "2句话描述画面感和情感氛围", "focus": "侧重：一句话点出核心优劣"}]}
- 角色待配图：`cast_pending` 为角色名数组（如 ["小明","小红"]），配合 `script_table_id`；options 示例：[{"id":"assign","label":"现在配图","value":"assign_cast_images"},{"id":"skip","label":"先跳过，继续生成","value":"skip_cast_images"}]
- 场景待配图：`scene_pending` 为场景名数组（如 ["教室","操场"]），配合 `script_table_id`；options 同上结构，value 可用 assign_scene_images / skip_scene_images
- group_title / group_subtitle 可选；有 options 时建议填写，供前端展示 TapNow 式卡片组标题
- options 可选，2～4 个创意卡片（TapNow 式），用于故事方向/风格路线等**非剧本主链路**讨论
- 有 ask_user 时，done.summary **≤2 句**，只写一句收尾引导语，不重复 options 内容
- 禁止在 options 里写英文 step 名或技术字段
- thoughts_en 等内部英文字段**禁止**出现在 user_status / done.summary / options 中

### done — 必须放在最后
{"type": "done", "summary": "纯中文。禁止 node id、step 名、JSON、英文技术词", "suggestions": ["快捷回复1", "快捷回复2"]}
- 链路执行类（意图B）：summary 描述本步结果；**必须**给 2～3 个 suggestions（用户可一键发送的下一步短语）
- 分析类（意图A）：summary 按结构写完整分析；suggestions 可选
- 创意策划（意图D，有 ask_user.options）：summary ≤2 句；**不要** suggestions（已有卡片）

## 关键约束

1. **每轮 actions 只能有 1 个 mutating 操作**（1 个 pipeline_step 或 1 个 create_node），外加可选 ask_user、done。禁止一次返回多步。
2. 根据「当前画布状态」和「链路进度提示」判断下一步；若文本仍在 generating，用 ask_user 请用户稍后再发「继续」。
3. 普通闲聊 intent=chat：只需 create_text_note + start_text_generation，不要 generate_outline。
4. 图像/视频 create_node 不要与 pipeline_step 同轮混用。
5. id 必须来自画布 nodes 列表，禁止编造。
6. done.summary 与 user_status 均须中文、面向用户，禁止技术术语。
7. 阶段二按镜号单线程：每次只推进**一镜**的一个子步骤（出图 / 出视频）；当前镜视频完成前禁止下一镜。
8. 画布存在多个 `script_table`（多条分镜链路）时，若用户请求含模糊指代（「这一镜」「这个角色」「那个」等），**禁止**直接执行 pipeline_step / manage_cast / manage_scene，**必须先** ask_user 澄清目标链路/镜头/角色。单链路时可默认指向唯一 script_table；多链路时必须澄清。

示例（单链路）：用户「重生成这一镜的视频」→ 可直接对唯一 script_table 的对应镜执行 generate_video。
示例（多链路）：用户「重生成这一镜的视频」→ 必须先 ask_user 澄清是哪条链路、哪一镜，禁止直接 pipeline_step。

## 用户意图分类（优先于链路提示）

先判断用户**本轮**要什么，再决定 actions：

### A. 画布分析 / 问答 / 建议（无画布修改）
用户说：分析、检查、看看、总结、评估、有什么问题、怎么样、帮我读一下、审查……
→ **禁止** pipeline_step / create_node
→ **必须**先阅读「画布摘要」与 nodes 中的 rows_summary / scenes_preview / content_preview
→ user_status 写 1～3 行进度（导演语感，✓ 已读哪些 → → 正在整理结论）
→ done.summary 按以下结构写完整中文分析（禁止敷衍一句话）：
  第1句：画布整体状态（X 镜，Y 镜已拆节拍，Z 镜已出图）
  中间句：逐镜说明剧情要点 + 该镜进度（依据 plot_preview / has_beats / storyboard_ready / has_video / 导演字段）
  最后1句：明确指出缺什么、下一步建议
→ suggestions 可选，2～3 个可点击的后续操作短语
→ **禁止**只回复「是/否」「有/无」或一句话敷衍；**禁止**说「分镜表为空」当 rows_summary 有数据

示例：
{
  "user_status": "✓ 已阅读画布分镜表\n→ 整理分析结论",
  "actions": [{"type": "done", "summary": "当前分镜表共 N 镜：镜1……（具体基于快照内容）"}]
}

### B. 链路执行 / 创作推进
用户说：继续、下一步、生成、创建、采纳……**或用户已选定创意方案（如「我选择…」）** **或用户明确要求另开新链路（重新做、换个主题、新建一条）**
→ 按链路进度提示执行**一个** pipeline_step；开新链路时执行 create_text_note（**新建**节点，禁止复用旧链路 id）
→ **禁止**在用户首次提出全新主题、尚未选定方向时直接 create_text_note（那种情况走意图 D）
→ **ask_user 门禁**：若消息历史中最近一条 assistant 消息包含 ask_user（创意卡片或 cast_pending / scene_pending），且用户本轮**既未**明确选择某个 option、**也未**提出新的明确创作方向（仅说「继续」「下一步」等推进词），**禁止**推进链路，应 done 说明仍在等待用户选择或回答
→ **新明确方向**：若用户本轮给出了新的、明确的创作内容（不是重复推进词），视为放弃旧 ask_user，以新内容为准，按意图 B/D 处理

### C. 普通闲聊
→ 可只 done 回复，或 create_text_note（chat 模式）

### D. 创意策划 / 方向讨论（非剧本强制链路）
用户说：几个方向、故事路线、人物设定、风格选择、帮我想想、哪种更好……
**或**：用户**第一次**描述某个创作主题（如「我想做重庆宣传片」「拍一段关于…的宣传片」），且本轮**尚未**选定方案、也**未**说「继续」「下一步」「生成节拍」等推进词
→ **禁止** pipeline_step / create_text_note（不要直接落卡）
→ 用 ask_user + options（2～4 个含 title/tag/description/focus 的中文卡片），或只 done 给建议
→ 有 ask_user 时 done.summary ≤2 句；不要 suggestions
→ 用户选定某卡片后（「我选择「方案名」」），下一轮再走意图 B 执行 create_text_note 进入剧本链路
→ 若画布上已有**其他主题**的节点，**禁止**读取或推进那些旧节点，本轮只做创意讨论

**链路进度提示仅在 B 类意图时强制遵循**；A/D 类时忽略「推荐下一步阶段」。

## 示例

用户：「我想做一段重庆的宣传片」，画布为空或尚无针对该主题的 text-note

{
  "user_status": "✓ 收到重庆城市宣传片的想法\\n→ 先整理几个创意方向给你选",
  "actions": [
    {
      "type": "ask_user",
      "question": "重庆宣传片想走哪种感觉？",
      "group_title": "重庆动物园·渝爱",
      "group_subtitle": "三条叙事路线，风格各异——你的直觉偏向哪一种？",
      "options": [
        {"id": "a", "title": "山城烟火", "tag": "人文纪实", "description": "从市井街巷、火锅与江景切入，呈现重庆人的日常温度与城市性格。", "focus": "侧重：真实感与城市烟火气"},
        {"id": "b", "title": "魔幻都市", "tag": "视觉奇观", "description": "轻轨穿楼、夜景霓虹、立体交通，用强视觉冲击呈现未来感山城。", "focus": "侧重：画面冲击力"},
        {"id": "c", "title": "新做重庆", "tag": "全新叙事", "description": "不沿用旧素材，从城市气质与时代精神重新构思一条完整叙事线。", "focus": "侧重：创意自由度"}
      ]
    },
    {"type": "done", "summary": "先看上面几个方向，选一个咱们再往下做。"}
  ]
}

用户：「我选择「山城烟火」」

{
  "user_status": "✓ 已锁定山城烟火方向\\n→ 准备创建文本输入卡",
  "actions": [
    {
      "type": "pipeline_step",
      "step": "create_text_note",
      "data": {
        "prompt": "重庆城市宣传片，山城烟火人文纪实风格",
        "intent": "screenplay",
        "label": "山城烟火宣传片"
      },
      "description": "创建文本输入卡"
    },
    {"type": "done", "summary": "已创建文本输入卡，下一步将触发生成剧本文本", "suggestions": ["继续"]}
  ]
}

用户：「我想做一段重庆动物园渝爱的宣传片」，用户已明确选定方案且要求直接开做（非首次提主题）

{
  "user_status": "✓ 已理解宣传片需求\\n→ 准备创建文本输入卡",
  "actions": [
    {
      "type": "pipeline_step",
      "step": "create_text_note",
      "data": {
        "prompt": "重庆动物园渝爱主题宣传片",
        "intent": "screenplay",
        "label": "渝爱宣传片"
      },
      "description": "创建文本输入卡"
    },
    {"type": "done", "summary": "已创建文本输入卡，下一步将触发生成剧本文本", "suggestions": ["继续"]}
  ]
}

用户：「继续」（分镜表已有 rows，镜1 分镜图已完成，链路进度提示推荐 generate_video）

{
  "user_status": "✓ 分镜表已进入阶段二\\n→ 按进度提示为镜1生成视频",
  "actions": [
    {
      "type": "pipeline_step",
      "step": "generate_video",
      "data": {"script_table_id": "（来自画布的 script_table id）", "shot_number": 1},
      "description": "为镜1生成视频"
    },
    {"type": "done", "summary": "正在为镜1生成视频，完成后可继续下一镜。", "suggestions": ["继续"]}
  ]
}

用户：「继续」（上一轮 assistant 输出了 cast_pending ask_user，用户尚未回答）

{
  "user_status": "✓ 角色配图尚未确认\\n→ 等待你选择",
  "actions": [
    {
      "type": "done",
      "summary": "还在等你决定是否为待配图角色出图，请先选择「现在配图」或「先跳过」后再继续。",
      "suggestions": ["现在配图", "先跳过，继续生成"]
    }
  ]
}
"""

# G32: 阶段化短 prompt（pipeline「继续」轮），砍掉创意示例 / 意图 D 长文
SYSTEM_PROMPT_CORE = """你是 AI Studio 的画布助手。画布是节点式创作工具，宣传片/剧本类需求必须走固定链路，**每次只执行一步、只动一张卡**。

## 输出格式（必须严格遵守）

输出纯 JSON，不加 markdown，不加说明文字：
{
  "user_status": "给用户看的中文进度（1～3 行）。语气像导演在场记上记录，口语化、有情绪感，不用技术字段。✓ 表示刚做完的事，→ 表示正在做的事。",
  "actions": []
}

## 关键约束

1. **每轮 actions 只能有 1 个 mutating 操作**（1 个 pipeline_step 或 1 个 create_node），外加可选 ask_user、done。禁止一次返回多步。
2. 根据「当前画布状态」和「链路进度提示」判断下一步；若文本仍在 generating，用 ask_user 请用户稍后再发「继续」。
3. id 必须来自画布 nodes / 节点 id 列表，禁止编造。
4. done.summary 与 user_status 均须中文、面向用户，禁止技术术语与英文 step 名堆砌。
5. 阶段二按镜号单线程：每次只推进**一镜**的一个子步骤；当前镜视频完成前禁止下一镜；生成中必须等待。
6. 画布存在多个 script_table 时，模糊指代须先 ask_user 澄清。

### done — 必须放在最后
{"type": "done", "summary": "纯中文", "suggestions": ["快捷回复1", "快捷回复2"]}
- 链路执行类：summary 描述本步结果；必须给 2～3 个 suggestions
"""

SYSTEM_PROMPT_PIPELINE = """
## 宣传片 / 剧本创作链路（强制顺序，禁止跳步）

### 阶段一 — 剧本结构
| 步骤 | step 值 |
|------|---------|
| 1 | create_text_note |
| 2 | start_text_generation |
| 3 | generate_outline |
| 4 | generate_script_table |

### 阶段二 — 分镜制作（按镜号单线程、一镜一步）
| 步骤 | step 值 |
|------|---------|
| 5 | split_shot_beats（可选） |
| 6 | generate_storyboard |
| 7 | generate_video |

当前镜视频完成前禁止下一镜；分镜图/视频生成中必须 wait，禁止 multitask。
**禁止**用 create_node 手写 outline / script_table。大纲与分镜必须由 pipeline_step 调用后端。

### pipeline_step — 每轮最多 1 个
{
  "type": "pipeline_step",
  "step": "create_text_note" | "start_text_generation" | "generate_outline" | "generate_script_table" | "split_shot_beats" | "generate_storyboard" | "generate_video" | "manage_cast" | "manage_scene",
  "data": {},
  "description": "本步说明"
}

data 要点：
- create_text_note: {"prompt": "必填", "intent": "screenplay", "label": "..."}
- start_text_generation: {"source_id": "text-note id"}
- generate_outline: {"text_response_id": "..."}
- generate_script_table: {"outline_id": "..."}
- split_shot_beats / generate_storyboard / generate_video: {"script_table_id": "...", "row_id": "可选"}

### ask_user（仅当进度提示要求等待或澄清时）
{"type": "ask_user", "question": "…", "options": []}

**必须先读「链路进度提示」的「推荐下一步阶段」并执行对应 pipeline_step**；禁止回退到已完成阶段。
若上一轮 ask_user 尚未回答，禁止推进，用 done 引导用户选择。
"""

_PIPELINE_ADVANCE_STAGES = frozenset({
    "create_text_note",
    "start_text_generation",
    "generate_outline",
    "generate_script_table",
    "split_shot_beats",
    "generate_storyboard",
    "generate_video",
    "wait",
    "wait_outline",
    "wait_script_table",
    "wait_storyboard",
    "wait_video",
    "manage_cast",
    "manage_scene",
})

_PIPELINE_FORCE_STEPS = frozenset({
    "create_text_note",
    "start_text_generation",
    "generate_outline",
    "generate_script_table",
    "split_shot_beats",
    "generate_storyboard",
    "generate_video",
})

_PIPELINE_SLIM_NODE_TYPES = frozenset({
    "text_note",
    "text-note",
    "text_response",
    "text-response",
    "outline",
    "script_table",
    "script-table",
})


def _extract_recommended_stage(pipeline_ctx: str) -> str:
    m = re.search(r"推荐下一步阶段:\s*(\S+)", pipeline_ctx or "")
    return (m.group(1) if m else "").strip()


def _is_pipeline_advance_intent(messages: list) -> bool:
    """意图 B：继续/推进链路（非创意首轮、非纯分析）。"""
    last_user = _last_user_message(messages)
    if not last_user:
        return False
    if last_user.startswith("我选择"):
        return True
    advance = ("继续", "下一步", "采纳", "生成节拍", "拆分节拍", "分镜图", "出图", "出视频")
    if any(k in last_user for k in advance):
        return True
    if last_user in ("继续", "继续。"):
        return True
    analysis = (
        "分析", "检查", "看看", "总结", "评估", "审查", "怎么样",
        "如何", "什么问题", "建议", "读一下", "解读", "帮忙看",
    )
    pipeline_kw = (
        "继续", "下一步", "生成", "创建", "做一段", "宣传片", "剧本", "采纳",
        "节拍", "分镜图", "分镜", "视频",
    )
    if any(k in last_user for k in analysis) and not any(k in last_user for k in pipeline_kw):
        return False
    fresh = _fresh_chain_intent_kind(messages)
    if fresh == "brainstorm":
        return False
    if fresh == "create":
        return True
    if any(k in last_user for k in ("生成", "创建", "节拍", "分镜", "视频", "大纲", "剧本")):
        return True
    return False


def _should_use_pipeline_prompt(messages: list, pipeline_ctx: str) -> bool:
    stage = _extract_recommended_stage(pipeline_ctx)
    if stage == "ask_user":
        return False
    if not _is_pipeline_advance_intent(messages):
        return False
    if stage in _PIPELINE_ADVANCE_STAGES or stage == "pipeline_complete":
        return True
    # 有明确推进词时即使 stage 空也用短 prompt
    last_user = _last_user_message(messages)
    return bool(last_user and last_user.strip() in ("继续", "继续。", "下一步"))


def _select_system_prompt(messages: list, pipeline_ctx: str) -> str:
    if _should_use_pipeline_prompt(messages, pipeline_ctx):
        return SYSTEM_PROMPT_CORE + SYSTEM_PROMPT_PIPELINE
    return SYSTEM_PROMPT


def _slim_snapshot_json(snapshot) -> str:
    data = snapshot.model_dump()
    nodes = [
        n
        for n in (data.get("nodes") or [])
        if (n.get("type") or "") in _PIPELINE_SLIM_NODE_TYPES
    ]
    slim = {
        "nodes": nodes,
        "edges": data.get("edges") or [],
        "snapshot_truncated": data.get("snapshot_truncated"),
    }
    return json.dumps(slim, ensure_ascii=False, indent=2)


def _resolve_agent_model() -> tuple[str, str, str, str | None]:
    """返回 (api_key, base_url, model_string, registered_model_id)。仅 Admin 已注册文本模型。"""
    from services.api_key_service import get_registered_model_api_key
    from services.llm_router import resolve_text_model

    row = resolve_text_model()
    if row:
        api_key = get_registered_model_api_key(row)
        base = (row.api_base or "").strip()
        model = (row.model_string or row.id).strip()
        if api_key and base and model:
            return api_key, base, model, row.id

    return "", "", "", None


def _estimate_tokens(messages: list[dict], completion: str) -> int:
    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    return max(1, prompt_chars // 4 + len(completion or "") // 4)


def _node_text_mode(node: dict | None) -> str:
    if not node:
        return "screenplay"
    mode = (node.get("text_mode") or node.get("intent") or "screenplay").strip().lower()
    return "chat" if mode == "chat" else "screenplay"


def _row_has_beats(row: dict) -> bool:
    return bool(
        row.get("has_beats")
        or row.get("beats_split_at")
        or row.get("beat_card_node_id")
    )


def _production_stage_hint(script_table: dict) -> tuple[str, str]:
    """分镜制作：按镜号单线程推进（出图→视频）；节拍可选；生成中必须 wait。"""
    st_id = script_table.get("id", "")
    rows = list(script_table.get("rows_summary") or [])
    if not rows:
        return (
            "wait_script_table",
            "分镜表尚无镜头行，请等待分镜表生成完成",
        )

    def _shot_key(row: dict) -> int:
        try:
            return int(row.get("shot_number") or 0)
        except (TypeError, ValueError):
            return 0

    rows = sorted(rows, key=_shot_key)

    for row in rows:
        shot = row.get("shot_number", 1)
        rid = row.get("id", "")
        if row.get("image_generating"):
            return (
                "wait_storyboard",
                f"镜 {shot} 分镜图正在生成中，应 ask_user 请用户等待后发送「继续」，"
                f"禁止开启下一镜或其它步骤（单画布单线程）。",
            )
        if row.get("video_generating"):
            return (
                "wait_video",
                f"镜 {shot} 视频正在生成中，应 ask_user 请用户等待后发送「继续」，"
                f"禁止开启下一镜或其它步骤（单画布单线程）。",
            )
        if not row.get("storyboard_ready") and not row.get("direct_image_ready"):
            return (
                "generate_storyboard",
                f'镜 {shot} 待出分镜图（大分镜直连出图，无需先拆分节拍）。'
                f' generate_storyboard，data.script_table_id="{st_id}" row_id="{rid}"',
            )
        if not row.get("has_video"):
            return (
                "generate_video",
                f'镜 {shot} 分镜图已完成，下一步生成视频（完成前禁止推进下一镜）。'
                f' generate_video，data.script_table_id="{st_id}" row_id="{rid}"',
            )

    return (
        "pipeline_complete",
        "全部分镜制作完成（文本→大纲→分镜表→分镜图→视频）",
    )

def _chain_sort_key(node_id: str) -> int:
    nid = (node_id or "").strip()
    if nid.startswith("agent_"):
        parts = nid.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
    return 0


def _build_edge_map(edges: list) -> dict[str, list[str]]:
    edge_map: dict[str, list[str]] = {}
    for e in edges or []:
        src = e.get("source")
        tgt = e.get("target")
        if src and tgt:
            edge_map.setdefault(src, []).append(tgt)
    return edge_map


def _follow_edge_target(
    source_id: str | None,
    edge_map: dict[str, list[str]],
    nodes_by_id: dict[str, dict],
    node_type: str,
) -> dict | None:
    if not source_id:
        return None
    for target_id in edge_map.get(source_id, []):
        node = nodes_by_id.get(target_id)
        if node and node.get("type") == node_type:
            return node
    return None


def _build_active_chain(nodes: list, edges: list) -> dict | None:
    edge_map = _build_edge_map(edges)
    nodes_by_id = {n.get("id"): n for n in nodes if n.get("id")}
    notes = [n for n in nodes if n.get("type") == "text_note"]
    responses = [n for n in nodes if n.get("type") == "text_response"]
    outlines = [n for n in nodes if n.get("type") == "outline"]
    scripts = [n for n in nodes if n.get("type") == "script_table"]

    chains: list[dict] = []
    for note in notes:
        chain: dict = {"note": note}
        resp = _follow_edge_target(note.get("id"), edge_map, nodes_by_id, "text_response")
        if resp:
            chain["response"] = resp
        outline = None
        if resp:
            outline = _follow_edge_target(resp.get("id"), edge_map, nodes_by_id, "outline")
        if not outline:
            outline = _follow_edge_target(note.get("id"), edge_map, nodes_by_id, "outline")
        if outline:
            chain["outline"] = outline
        script = None
        if outline:
            script = _follow_edge_target(outline.get("id"), edge_map, nodes_by_id, "script_table")
            if not script:
                oid = outline.get("id")
                linked_id = outline.get("linked_script_table_id")
                if linked_id:
                    candidate = nodes_by_id.get(linked_id)
                    if candidate and candidate.get("type") == "script_table":
                        script = candidate
                if not script and oid:
                    for s in scripts:
                        if s.get("source_outline_id") == oid:
                            script = s
                            break
        if script:
            chain["script"] = script
        chains.append(chain)

    if not chains:
        return None
    chains.sort(key=lambda c: _chain_sort_key((c.get("note") or {}).get("id", "")), reverse=True)
    return chains[0]


def _infer_stage_from_chain(chain: dict) -> tuple[str, str]:
    note = chain.get("note") or {}
    response = chain.get("response")
    outline = chain.get("outline")
    script = chain.get("script")
    note_id = note.get("id", "")
    pipeline_mode = _node_text_mode(note)

    if not response:
        if script:
            rows = script.get("rows_summary") or []
            if rows:
                stage, hint = _production_stage_hint(script)
                return stage, f"活跃链路（text-note=\"{note_id}\"）{hint}"
            if script.get("loading"):
                return (
                    "wait_script_table",
                    "活跃链路分镜表正在生成中，应 ask_user 请用户等待后发送「继续」",
                )
        return (
            "start_text_generation",
            f"当前活跃链路 text-note=\"{note_id}\"，下一步 start_text_generation，"
            f'data.source_id="{note_id}"',
        )

    resp_id = response.get("id", "")
    preview = (response.get("content_preview") or "").strip()
    status = (response.get("status") or "").strip().lower()
    if preview == "[生成中]" or status == "generating" or not preview:
        return (
            "wait",
            f"活跃链路 text-note=\"{note_id}\" 的文本仍在生成中，应 ask_user 请用户等待后发送「继续」",
        )
    if pipeline_mode == "chat":
        return (
            "pipeline_complete",
            f"活跃链路 text-note=\"{note_id}\" 为 chat 模式，文本已生成，不要 generate_outline",
        )
    if not outline:
        return (
            "generate_outline",
            f'活跃链路下一步 generate_outline，data.text_response_id="{resp_id}"（勿混用其他主题节点 id）',
        )

    outline_id = outline.get("id", "")
    op = (outline.get("content_preview") or "").strip()
    o_loading = outline.get("loading") is True or op == "[生成中]"
    scene_count = outline.get("scene_count") or 0
    if o_loading:
        return (
            "wait_outline",
            f"活跃链路大纲正在生成中，应 ask_user 请用户等待后发送「继续」",
        )
    if scene_count == 0 and not op:
        return (
            "generate_outline",
            f'大纲无内容，重新 generate_outline，text_response_id="{resp_id}"',
        )
    if not script:
        return (
            "generate_script_table",
            f'活跃链路下一步 generate_script_table，data.outline_id="{outline_id}"',
        )

    if script.get("loading"):
        return (
            "wait_script_table",
            "活跃链路分镜表正在生成中，应 ask_user 请用户等待后发送「继续」",
        )
    rows = script.get("rows_summary") or []
    if rows:
        stage, hint = _production_stage_hint(script)
        return stage, f"活跃链路（text-note=\"{note_id}\"）{hint}"
    return (
        "wait_script_table",
        "活跃链路分镜表尚无镜头行，请等待分镜表生成完成",
    )


_PIPELINE_NEW_CHAIN_NOTE = (
    "若用户本轮要开**全新主题**链路（换新主题、重新做一个、另起一条），"
    "应 create_text_note 创建**新** text-note，禁止复用或更新已有链路的节点 id。\n"
)


def _last_user_message(messages: list) -> str:
    for msg in reversed(messages or []):
        if getattr(msg, "role", None) == "user" or (isinstance(msg, dict) and msg.get("role") == "user"):
            return (getattr(msg, "content", None) or msg.get("content") or "").strip()
    return ""


def _previous_assistant_pending_choice(messages: list) -> bool:
    """上一轮 assistant 是否在等待用户选择创意方案或配图确认。"""
    seen_last_user = False
    for msg in reversed(messages or []):
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = (
            getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None) or ""
        ).strip()
        if role == "user":
            if seen_last_user:
                break
            seen_last_user = True
            continue
        if role == "assistant" and seen_last_user:
            markers = (
                "请选择", "创意方向", "选一个", "是否现在配图",
                "待配图", "配图", "方案：", "方案:", "方向", "准备了",
            )
            return any(m in content for m in markers)
    return False


def _is_advance_only_message(text: str) -> bool:
    """用户输入是否仅为推进词组合（无实质新创作内容）。"""
    stripped = text.strip().rstrip("。.!！")
    remainder = stripped
    for phrase in (
        "继续", "下一步", "采纳", "生成节拍", "拆分节拍", "分镜图", "出图", "出视频",
        "先生成", "先", "然后", "再", "吧", "，", ",", " ", "、", "请",
    ):
        remainder = remainder.replace(phrase, "")
    return len(remainder.strip()) < 4


def _fresh_chain_intent_kind(messages: list) -> str | None:
    """本轮是否应忽略画布上的旧活跃链路（避免 LLM 复用旧 text-note id）。"""
    last_user = _last_user_message(messages)
    if not last_user:
        return None

    advance_keywords = ("继续", "下一步", "采纳", "生成节拍", "拆分节拍", "分镜图", "出图", "出视频")
    new_theme_keywords = (
        "宣传片", "我想做", "做一段", "拍一个", "做一个", "创作", "拍一段", "关于",
        "帮我做", "想做", "打算做",
    )
    new_chain_direct_keywords = (
        "重新做", "换一个", "换个", "另外一个", "新建一条", "再建一条", "另一条",
        "新主题", "从头", "重新来", "另起", "第二个", "再做一个", "新开",
    )

    if last_user.startswith("我选择"):
        return "create"
    if any(k in last_user for k in new_chain_direct_keywords) and not any(
        k in last_user for k in advance_keywords
    ):
        return "create"
    if any(k in last_user for k in new_theme_keywords) and not any(
        k in last_user for k in advance_keywords
    ):
        return "brainstorm"
    return None


def _multi_chain_clarify_warning(nodes: list) -> str:
    """多链路场景下注入强制澄清规则。"""
    scripts = [n for n in nodes if n.get("type") == "script_table"]
    if len(scripts) < 2:
        return ""
    return (
        "\n⚠️ 当前画布有多条分镜链路。"
        "若用户请求中含模糊指代（「这一镜」「这个角色」「那个」等），"
        "**禁止直接执行 pipeline_step / manage_cast / manage_scene**，"
        "必须先 ask_user 澄清目标是哪条链路或哪一镜。\n"
    )


def _build_pipeline_context(snapshot, messages: list | None = None) -> str:
    data = snapshot.model_dump()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    fresh_kind = _fresh_chain_intent_kind(messages or [])
    if fresh_kind == "brainstorm":
        notes = [n for n in nodes if n.get("type") == "text_note"]
        return (
            "\n\n## 链路进度提示\n"
            "推荐下一步阶段: ask_user\n"
            "说明: 用户提出全新创作主题，本轮仅展示创意方向卡片，禁止 pipeline_step / create_text_note。\n"
            f"活跃链路 text-note: 不适用（禁止推进画布上已有 {len(notes)} 条旧链路节点）\n"
            + _PIPELINE_NEW_CHAIN_NOTE
        )
    if fresh_kind == "create":
        notes = [n for n in nodes if n.get("type") == "text_note"]
        return (
            "\n\n## 链路进度提示\n"
            "推荐下一步阶段: create_text_note\n"
            "说明: 用户已选定方案或要求另开新链路，必须先 create_text_note 新建节点，"
            "禁止对已有 text-note 执行 start_text_generation 或复用其 id。\n"
            "create_text_note 的 data.prompt **必填**（title + focus 合成完整创作意图），禁止为空。\n"
            "活跃链路 text-note: 待新建（本轮 create_text_note 后产生新 id）\n"
            f"画布统计: text-note={len(notes)}（均为旧链路，禁止复用）\n"
            + _PIPELINE_NEW_CHAIN_NOTE
        )

    active_chain = _build_active_chain(nodes, edges)
    if active_chain:
        stage, hint = _infer_stage_from_chain(active_chain)
        note = active_chain.get("note") or {}
        scripts = [n for n in nodes if n.get("type") == "script_table"]
        outlines = [n for n in nodes if n.get("type") == "outline"]
        notes = [n for n in nodes if n.get("type") == "text_note"]
        multi_warn = _multi_chain_clarify_warning(nodes)
        return (
            "\n\n## 链路进度提示\n"
            f"推荐下一步阶段: {stage}\n"
            f"说明: {hint}\n"
            f"活跃链路 text-note: {note.get('id', '')}\n"
            f"文本模式: {_node_text_mode(note)}\n"
            f"画布统计: text-note={len(notes)}, outline={len(outlines)}, script_table={len(scripts)}\n"
            "注意: 画布存在多条主题链路时，仅推进**活跃链路**（最新 text-note 及其下游节点），禁止混用其他主题的节点 id。\n"
            + multi_warn
            + _PIPELINE_NEW_CHAIN_NOTE
        )

    scripts = [n for n in nodes if n.get("type") == "script_table"]
    for st in reversed(scripts):
        if st.get("loading"):
            return (
                "\n\n## 链路进度提示\n"
                "推荐下一步阶段: wait_script_table\n"
                "说明: 分镜表正在生成中，应 ask_user 请用户等待后发送「继续」\n"
            )
        rows = st.get("rows_summary") or []
        if rows:
            stage, hint = _production_stage_hint(st)
            multi_warn = _multi_chain_clarify_warning(nodes)
            return (
                "\n\n## 链路进度提示\n"
                f"推荐下一步阶段: {stage}\n"
                f"说明: {hint}\n"
                f"画布统计: script_table 行数={len(rows)}\n"
                + multi_warn
            )

    notes = [n for n in nodes if n.get("type") == "text_note"]
    responses = [n for n in nodes if n.get("type") == "text_response"]
    outlines = [n for n in nodes if n.get("type") == "outline"]
    last_note = notes[-1] if notes else None
    pipeline_mode = _node_text_mode(last_note)

    stage = "create_text_note"
    hint = "画布为空或尚无文本输入卡，下一步应 create_text_note"

    if notes and not responses:
        if pipeline_mode == "chat":
            stage = "start_text_generation"
            hint = (
                f"下一步 start_text_generation，data.source_id=\"{notes[-1]['id']}\"；"
                "intent=chat，文本完成后链路结束，不要 generate_outline"
            )
        else:
            stage = "start_text_generation"
            hint = f"下一步 start_text_generation，data.source_id=\"{notes[-1]['id']}\""
    elif responses:
        r = responses[-1]
        preview = (r.get("content_preview") or "").strip()
        status = (r.get("status") or "").strip().lower()
        if preview == "[生成中]" or status == "generating" or not preview:
            stage = "wait"
            hint = "文本仍在生成中，应 ask_user 请用户等待后发送「继续」"
        elif pipeline_mode == "chat":
            stage = "pipeline_complete"
            hint = "普通对话模式（text_mode=chat），文本已生成，链路结束，不要 generate_outline"
        elif not outlines:
            stage = "generate_outline"
            hint = f"下一步 generate_outline，data.text_response_id=\"{r['id']}\""
        elif outlines:
            o = outlines[-1]
            op = (o.get("content_preview") or "").strip()
            o_loading = o.get("loading") is True or op == "[生成中]"
            scene_count = o.get("scene_count") or 0
            if o_loading:
                stage = "wait_outline"
                hint = "大纲正在生成中，应 ask_user 请用户等待后发送「继续」"
            elif scene_count > 0 and not scripts:
                stage = "generate_script_table"
                hint = f"下一步 generate_script_table，data.outline_id=\"{o['id']}\""
            elif scene_count > 0 and scripts:
                st = scripts[-1]
                if st.get("loading"):
                    stage = "wait_script_table"
                    hint = "分镜表正在生成中，应 ask_user 请用户等待后发送「继续」"
                else:
                    stage, hint = _production_stage_hint(st)
            elif not op and scene_count == 0:
                stage = "generate_outline"
                hint = f"大纲无内容，重新 generate_outline，text_response_id=\"{r['id']}\""

    multi_warn = _multi_chain_clarify_warning(nodes)
    return (
        "\n\n## 链路进度提示\n"
        f"推荐下一步阶段: {stage}\n"
        f"说明: {hint}\n"
        f"文本模式: {pipeline_mode}\n"
        f"画布统计: text-note={len(notes)}, outline={len(outlines)}, script_table={len(scripts)}\n"
        + multi_warn
        + _PIPELINE_NEW_CHAIN_NOTE
    )


MUTATING_ACTION_TYPES = frozenset({
    "pipeline_step",
    "create_node",
    "update_node",
    "delete_node",
    "move_node",
})


def _enforce_single_step(actions: list) -> list:
    """每轮只保留第一个 mutating action，避免一口气改多张卡。"""
    if not actions:
        return actions
    result = []
    mutating_used = False
    for action in actions:
        atype = action.get("type")
        if atype in ("ask_user", "done"):
            result.append(action)
            continue
        if atype == "create_edge":
            if not mutating_used:
                result.append(action)
            continue
        if atype in MUTATING_ACTION_TYPES:
            if mutating_used:
                continue
            mutating_used = True
            if atype == "create_node" and action.get("node_type") in ("outline", "script_table"):
                continue
            result.append(action)
    if mutating_used and not any(a.get("type") == "done" for a in result):
        result.append({
            "type": "done",
            "summary": "本步操作已提交",
        })
    return result


def _parse_pipeline_data_ids(pipeline_ctx: str) -> dict:
    """从链路进度说明中提取 data 字段 id。"""
    ctx = pipeline_ctx or ""
    data: dict = {}
    for key, pattern in (
        ("script_table_id", r'script_table_id="([^"]+)"'),
        ("row_id", r'row_id="([^"]+)"'),
        ("source_id", r'source_id="([^"]+)"'),
        ("text_response_id", r'text_response_id="([^"]+)"'),
        ("outline_id", r'outline_id="([^"]+)"'),
    ):
        m = re.search(pattern, ctx)
        if m:
            data[key] = m.group(1)
    return data


def _reconcile_advance_pipeline_actions(
    actions: list,
    *,
    recommended_stage: str,
    pipeline_ctx: str,
    messages: list,
) -> list:
    """短指令「继续」等：LLM 返回与链路进度不一致时以 hint 覆盖（单线程纠偏）。"""
    last_user = _last_user_message(messages)
    if not last_user or not _is_advance_only_message(last_user):
        return actions
    # 上一轮仍在等创意卡/配图确认时，禁止用阶段 hint 强推 pipeline
    if _previous_assistant_pending_choice(messages):
        return [
            {
                "type": "done",
                "summary": "还在等你完成选择或确认后再继续。",
                "suggestions": ["现在配图", "先跳过，继续生成"],
            }
        ]

    stage = (recommended_stage or "").strip()
    if not stage or stage == "ask_user":
        return actions

    if stage.startswith("wait"):
        kept = [a for a in actions if a.get("type") not in MUTATING_ACTION_TYPES]
        if not any(a.get("type") == "ask_user" for a in kept):
            kept.insert(
                0,
                {
                    "type": "ask_user",
                    "question": "当前步骤仍在生成中，请稍候再发送「继续」",
                    "options": [],
                },
            )
        if not any(a.get("type") == "done" for a in kept):
            kept.append(
                {
                    "type": "done",
                    "summary": "当前步骤仍在生成中，请稍候再发送「继续」。",
                    "suggestions": ["继续"],
                }
            )
        return kept

    if stage not in _PIPELINE_FORCE_STEPS:
        return actions

    existing = next((a for a in actions if a.get("type") == "pipeline_step"), None)
    if existing and existing.get("step") == stage:
        return actions

    data = _parse_pipeline_data_ids(pipeline_ctx)
    if existing and isinstance(existing.get("data"), dict):
        merged = {**data, **{k: v for k, v in existing["data"].items() if v}}
        data = merged

    forced = {
        "type": "pipeline_step",
        "step": stage,
        "data": data,
        "description": f"按链路进度推进：{stage}",
    }
    out = [forced]
    for a in actions:
        if a.get("type") in ("ask_user", "done"):
            out.append(a)
    if not any(a.get("type") == "done" for a in out):
        out.append({"type": "done", "summary": "本步操作已提交", "suggestions": ["继续"]})
    return out


def _build_user_intent_context(messages: list, snapshot=None) -> str:
    last_user = _last_user_message(messages)
    if not last_user:
        return ""

    advance_keywords = ("继续", "下一步", "采纳", "生成节拍", "拆分节拍", "分镜图", "出图", "出视频")
    new_theme_keywords = (
        "宣传片", "我想做", "做一段", "拍一个", "做一个", "创作", "拍一段", "关于",
        "帮我做", "想做", "打算做",
    )
    new_chain_direct_keywords = (
        "重新做", "换一个", "换个", "另外一个", "新建一条", "再建一条", "另一条",
        "新主题", "从头", "重新来", "另起", "第二个", "再做一个", "新开",
    )

    if last_user.startswith("我选择"):
        return (
            "\n\n## 本轮用户意图\n"
            "用户**已选定创意方案**。应走意图 B：执行 create_text_note 开启**新主题**链路"
            "（intent=screenplay）。"
            "create_text_note 的 data.prompt **必填**，内容为选定方案的 title + focus，"
            "如「北京宣传片，古典与现代碰撞风格」；data.label 为方案 title；"
            "禁止 data.prompt 为空；禁止仅用 done 声称已创建而未执行 pipeline_step create_text_note；"
            "禁止推进画布上其他旧主题链路的节点 id。\n"
        )

    if any(k in last_user for k in new_chain_direct_keywords) and not any(
        k in last_user for k in advance_keywords
    ):
        return (
            "\n\n## 本轮用户意图\n"
            "用户要求**另开一条全新创作链路**。应走意图 B：执行 create_text_note（intent=screenplay），"
            "data.prompt **必填**，取自用户描述的新主题；"
            "**禁止**推进或修改画布上已有链路的节点 id。\n"
        )

    if any(k in last_user for k in new_theme_keywords) and not any(
        k in last_user for k in advance_keywords
    ):
        node_count = 0
        if snapshot is not None:
            data = snapshot.model_dump() if hasattr(snapshot, "model_dump") else (snapshot or {})
            node_count = len(data.get("nodes") or [])
        extra = ""
        if node_count > 0:
            extra = (
                "画布上存在其他主题节点，**禁止**读取或推进那些旧节点；"
                "本轮只为用户**新提出的主题**提供创意方向。\n"
            )
        return (
            "\n\n## 本轮用户意图\n"
            "用户提出了**全新创作主题**（尚未选定具体方向）。"
            "应走意图 D：**禁止** pipeline_step / create_text_note；"
            "用 ask_user + options 给出 2～4 个创意方向卡片供用户选择。\n"
            + extra
        )

    analysis_keywords = (
        "分析", "检查", "看看", "总结", "评估", "审查", "怎么样",
        "如何", "什么问题", "建议", "读一下", "解读", "帮忙看",
    )
    pipeline_keywords = (
        "继续", "下一步", "生成", "创建", "做一段", "宣传片", "剧本", "采纳",
        "节拍", "分镜图", "分镜", "视频",
    )
    beat_keywords = ("节拍", "节拍提示词", "拆分节拍")
    if _previous_assistant_pending_choice(messages) and _is_advance_only_message(last_user):
        return (
            "\n\n## 本轮用户意图\n"
            "上一轮 assistant 仍在等待用户回答（创意方案选择 / 配图确认等），"
            "用户本轮未明确选择 option 也未提出替代新创作方向。"
            "禁止推进 pipeline_step，应 done 引导用户先完成选择或明确意图。\n"
        )
    if any(k in last_user for k in beat_keywords) or (
        "生成" in last_user and "节拍" in last_user
    ):
        return (
            "\n\n## 本轮用户意图\n"
            "用户要求**生成节拍提示词**，应执行 split_shot_beats（一镜一步）。"
            "输出合法 JSON，含 pipeline_step + done，不要只输出纯文字。\n"
        )
    if "分镜图" in last_user and ("生成" in last_user or "出" in last_user):
        return (
            "\n\n## 本轮用户意图\n"
            "用户要求**生成分镜图**，应执行 generate_storyboard。\n"
        )
    if "视频" in last_user and ("生成" in last_user or "出" in last_user):
        return (
            "\n\n## 本轮用户意图\n"
            "用户要求**生成视频**，应执行 generate_video。\n"
        )
    if any(k in last_user for k in analysis_keywords) and not any(
        k in last_user for k in pipeline_keywords
    ):
        return (
            "\n\n## 本轮用户意图\n"
            "用户请求**画布分析/问答**（非推进链路）。"
            "请根据「画布摘要」与快照中的 rows_summary 逐镜说明剧情与进度；"
            "user_status 展示思考过程，done.summary 至少 3 句完整分析。"
            "禁止 pipeline_step；禁止只答是/否。\n"
        )
    if last_user in ("继续", "继续。"):
        return (
            "\n\n## 本轮用户意图\n"
            "用户要求继续推进链路。**必须先读「链路进度提示」里的「推荐下一步阶段」**，"
            "按该阶段执行 pipeline_step，禁止忽略阶段提示回退到 start_text_generation。\n"
            "若推荐阶段为 wait / wait_storyboard / wait_video 等，**禁止** pipeline_step，"
            "应 ask_user 或 done 请用户等待当前步骤完成（单画布单线程，禁止 multitask）。\n"
            "如果上一轮 assistant 输出了 ask_user 尚未得到回答（如 cast_pending / scene_pending / 配图提示），"
            "应先 done 说明仍在等待用户回答，不推进链路。\n"
        )
    return ""


def _build_canvas_digest(snapshot) -> str:
    """人类可读摘要，帮助模型准确读取分镜表等结构化数据。"""
    data = snapshot.model_dump()
    nodes = data.get("nodes") or []
    lines: list[str] = []

    for n in nodes:
        ntype = n.get("type") or ""
        nid = n.get("id") or ""
        if ntype == "script_table":
            rows = n.get("rows_summary") or []
            loading = n.get("loading")
            beat_done = sum(1 for r in rows if _row_has_beats(r))
            beat_note = f"，{beat_done}/{len(rows)} 镜已拆分节拍" if rows and beat_done else ""
            lines.append(f"【分镜表 {nid}】{'生成中' if loading else f'共 {len(rows)} 镜{beat_note}'}")
            for r in rows:
                shot = r.get("shot_number", "?")
                plot = (r.get("plot_preview") or "").strip()
                beats = "已有节拍" if _row_has_beats(r) else "缺节拍"
                sb = "分镜图已完成" if r.get("storyboard_ready") else "分镜图未完成"
                if r.get("has_video"):
                    vid = "视频已完成"
                elif r.get("video_generating"):
                    vid = "视频生成中"
                else:
                    vid = "尚无视频"
                lines.append(f"  镜{shot}：{plot[:160] or '（无剧情描述）'}")
                director_bits = []
                for key, label in (
                    ("camera", "景别"),
                    ("movement", "运镜"),
                    ("lighting", "光影"),
                    ("composition", "构图"),
                    ("color_grade", "色调"),
                    ("lens", "镜头"),
                    ("performance", "表演"),
                    ("sound_design", "声音"),
                ):
                    val = (r.get(key) or "").strip()
                    if val:
                        director_bits.append(f"{label}:{val[:40]}")
                if director_bits:
                    lines.append(f"    导演: {'；'.join(director_bits)}")
                lines.append(f"    → {beats}；{sb}；{vid}")
                for kf in (r.get("keyframes_summary") or [])[:6]:
                    kf_prompt = (kf.get("prompt_en") or kf.get("prompt") or "")[:60]
                    kf_line = (
                        f"    格{kf.get('index')} {kf.get('label') or ''} "
                        f"[{kf.get('status')}] "
                        f"{kf_prompt}"
                    ).strip()
                    lines.append(kf_line)
            cast_lib = n.get("cast_library") or []
            if cast_lib:
                cast_bits = []
                for c in cast_lib:
                    name = (c.get("name") or "").strip()
                    if not name:
                        continue
                    img = "已配图" if c.get("has_image") else "待配图"
                    desc = (c.get("description") or "").strip()
                    bit = f"角色「{name}」({img})"
                    if desc:
                        bit += f"：{desc[:60]}"
                    cast_bits.append(bit)
                if cast_bits:
                    lines.append(f"  角色库：{'；'.join(cast_bits)}")
            scene_lib = n.get("scene_library") or []
            if scene_lib:
                scene_bits = []
                for s in scene_lib:
                    name = (s.get("name") or "").strip()
                    if not name:
                        continue
                    img = "已配图" if s.get("has_image") else "待配图"
                    desc = (s.get("description") or "").strip()
                    bit = f"场景「{name}」({img})"
                    if desc:
                        bit += f"：{desc[:60]}"
                    scene_bits.append(bit)
                if scene_bits:
                    lines.append(f"  场景库：{'；'.join(scene_bits)}")
            loc_rows = [
                r for r in (n.get("rows_summary") or []) if r.get("location_id")
            ]
            if loc_rows:
                lines.append(
                    f"  已绑定场景的镜头：{len(loc_rows)}/{len(n.get('rows_summary') or [])} 镜"
                )
        elif ntype == "outline" and not n.get("loading"):
            scenes = n.get("scenes_preview") or []
            lines.append(f"【大纲 {nid}】{n.get('scene_count', len(scenes))} 个场景")
            for s in scenes[:6]:
                lines.append(
                    f"  场景{s.get('index')}：{(s.get('content') or s.get('title') or '')[:100]}"
                )
            chars = n.get("characters_preview") or []
            if chars:
                lines.append(f"  涉及人物：{'、'.join(chars[:12])}")
        elif ntype in ("text_response", "text_note"):
            preview = (n.get("content_preview") or "").strip()
            if preview and preview != "[生成中]":
                lines.append(f"【{ntype} {nid}】{preview[:120]}")

    if not lines:
        return "\n\n## 画布摘要\n（画布为空或无可读节点）\n"
    return "\n\n## 画布摘要（优先阅读，再对照下方 JSON）\n" + "\n".join(lines) + "\n"


def _build_canvas_context(
    snapshot,
    messages: list | None = None,
    *,
    pipeline_mode: bool = False,
) -> str:
    data = snapshot.model_dump()
    node_ids = [n["id"] for n in data.get("nodes", [])]
    intent_ctx = _build_user_intent_context(messages or [], snapshot)
    digest = _build_canvas_digest(snapshot)
    pipeline_ctx = _build_pipeline_context(snapshot, messages)
    id_list = (
        "\n\n## 当前可用节点 id 列表（只能使用这些 id，禁止编造）\n"
        + json.dumps(node_ids, ensure_ascii=False)
    )
    if pipeline_mode:
        # G32: pipeline 推进轮去掉全量 JSON，digest + pipeline + ids 足够
        return intent_ctx + digest + pipeline_ctx + id_list
    return (
        intent_ctx
        + digest
        + pipeline_ctx
        + "\n\n## 当前画布状态\n"
        + _slim_snapshot_json(snapshot)
        + id_list
    )


def _build_execution_mode_context(mode: str) -> str:
    normalized = (mode or "manual").strip().lower()
    if normalized == "auto":
        return (
            "\n\n## 执行模式\n"
            "自动生成：每步落画布后用户无需手动确认，系统会自动继续下一步。"
            "（execution_mode=auto）\n"
        )
    return (
        "\n\n## 执行模式\n"
        "手动确认：每步落画布后等待用户点击「采纳并继续」再进入下一步。"
        "（execution_mode=manual）\n"
    )


def _trim_messages(messages: list) -> list:
    max_msgs = MAX_HISTORY_ROUNDS * 2
    if len(messages) <= max_msgs:
        return messages
    return messages[-max_msgs:]


def _extract_json_payload(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    while start >= 0:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    raise json.JSONDecodeError("无法从 AI 响应中解析 JSON", text, 0)


_USER_STATUS_RE = re.compile(
    r'"user_status"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)'
)
_THOUGHTS_RE = re.compile(
    r'"thoughts"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)'
)


def _unescape_json_string(s: str) -> str:
    return (
        (s or "")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _extract_user_status_from_buffer(buffer: str) -> str:
    for pattern in (_USER_STATUS_RE, _THOUGHTS_RE):
        match = pattern.search(buffer or "")
        if match:
            return _unescape_json_string(match.group(1)).strip()
    return ""


def _resolve_user_status(parsed: dict) -> str:
    return (
        (parsed.get("user_status") or parsed.get("thoughts") or "").strip()
    )


async def _aiter_with_keepalive(async_iterable, interval: float):
    """Yield items from async_iterable; yield None when idle longer than interval."""
    agen = async_iterable.__aiter__()
    pending = asyncio.create_task(agen.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                break
            yield item
            pending = asyncio.create_task(agen.__anext__())
    finally:
        if not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass


def _sse_ping() -> str:
    return f'data: {json.dumps({"event": "ping"})}\n\n'


async def run_agent_stream(request: AgentRunRequest) -> AsyncGenerator[str, None]:
    api_key, base_url, model, registered_id = _resolve_agent_model()
    if not api_key:
        yield f'data: {json.dumps({"event": "error", "message": "请先在管理后台「模型管理」配置并启用文本 LLM"})}\n\n'
        return

    pipeline_ctx = _build_pipeline_context(request.canvas_snapshot, request.messages)
    use_pipeline = _should_use_pipeline_prompt(request.messages, pipeline_ctx)
    system_prompt = _select_system_prompt(request.messages, pipeline_ctx)
    canvas_context = _build_canvas_context(
        request.canvas_snapshot,
        request.messages,
        pipeline_mode=use_pipeline,
    )
    mode_context = _build_execution_mode_context(request.execution_mode)
    system_content = system_prompt + mode_context + canvas_context
    llm_messages = [{"role": "system", "content": system_content}]
    for msg in _trim_messages(request.messages):
        if msg.role in ("user", "assistant"):
            llm_messages.append({"role": msg.role, "content": msg.content})

    last_user = _last_user_message(request.messages)
    canvas_nodes = len(request.canvas_snapshot.nodes)
    await push_trace(
        "A1",
        "AGENT_INPUT",
        {
            "messages_count": len(llm_messages),
            "canvas_nodes": canvas_nodes,
            "user_msg": (last_user or "")[:100],
            "system_chars": len(system_content),
            "canvas_context_chars": len(canvas_context),
            "pipeline_prompt": use_pipeline,
        },
    )
    studio_print(
        "trace",
        f"A1 AGENT_INPUT messages_count={len(llm_messages)} canvas_nodes={canvas_nodes} "
        f"user_msg_len={len(last_user or '')} system_chars={len(system_content)} "
        f"canvas_context_chars={len(canvas_context)} pipeline_prompt={use_pipeline}",
    )

    yield f'data: {json.dumps({"event": "status_delta", "content": "→ 正在连接模型…", "append": False}, ensure_ascii=False)}\n\n'

    parsed = None
    buffer = ""
    last_status_sent = ""
    llm_content_started = False
    stream_usage: dict | None = None
    max_retries = max(1, int(settings.agent_llm_max_retries))
    base_delay = float(settings.agent_llm_retry_base_delay)
    llm_timeout = float(settings.llm_http_timeout)
    keepalive_sec = float(settings.agent_sse_keepalive_sec)

    for attempt in range(max_retries):
        buffer = ""
        last_status_sent = ""
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=llm_timeout) as http:
                client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=llm_timeout,
                    http_client=http,
                )
                create_task = asyncio.create_task(
                    client.chat.completions.create(
                        model=model,
                        messages=llm_messages,
                        stream=True,
                        max_tokens=4000,
                        temperature=0.3,
                        stream_options={"include_usage": True},
                    )
                )
                while True:
                    done, _ = await asyncio.wait({create_task}, timeout=keepalive_sec)
                    if not done:
                        yield _sse_ping()
                        continue
                    stream = create_task.result()
                    break

                async for item in _aiter_with_keepalive(stream, keepalive_sec):
                    if item is None:
                        yield _sse_ping()
                        continue
                    chunk = item
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        stream_usage = {
                            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                            "completion_tokens": int(
                                getattr(usage, "completion_tokens", 0) or 0
                            ),
                            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
                        }
                    delta = ""
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    llm_content_started = True
                    buffer += delta
                    status_preview = _extract_user_status_from_buffer(buffer)
                    if status_preview and status_preview != last_status_sent:
                        if status_preview.startswith(last_status_sent):
                            delta_piece = status_preview[len(last_status_sent):]
                            payload = {
                                "event": "status_delta",
                                "content": delta_piece,
                                "append": True,
                            }
                        else:
                            payload = {
                                "event": "status_delta",
                                "content": status_preview,
                                "append": False,
                            }
                        last_status_sent = status_preview
                        yield f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'

            parsed = _extract_json_payload(buffer)
            if registered_id:
                from services.llm_router import record_usage

                record_usage(registered_id, _estimate_tokens(llm_messages, buffer))
            break
        except json.JSONDecodeError:
            yield f'data: {json.dumps({"event": "error", "message": "AI 返回格式异常，请重新描述需求"})}\n\n'
            return
        except Exception as e:
            retryable, user_message = classify_llm_error(e)
            logger.warning(
                "agent llm failed attempt=%s/%s retryable=%s: %s",
                attempt + 1,
                max_retries,
                retryable,
                e,
            )
            if llm_content_started or not retryable or attempt >= max_retries - 1:
                yield f'data: {json.dumps({"event": "error", "message": user_message}, ensure_ascii=False)}\n\n'
                return
            retry_payload = {
                "event": "status_delta",
                "content": f"→ 连接波动，正在重试（{attempt + 2}/{max_retries}）…",
                "append": False,
            }
            yield f'data: {json.dumps(retry_payload, ensure_ascii=False)}\n\n'
            await sleep_before_retry(attempt, base_delay, e)
    else:
        yield f'data: {json.dumps({"event": "error", "message": "AI 服务暂时不可用，请稍后再试"})}\n\n'
        return

    if parsed is None:
        yield f'data: {json.dumps({"event": "error", "message": "AI 服务暂时不可用，请稍后再试"})}\n\n'
        return

    user_status = _resolve_user_status(parsed)
    if user_status:
        yield f'data: {json.dumps({"event": "thinking", "content": user_status}, ensure_ascii=False)}\n\n'

    actions = _enforce_single_step(parsed.get("actions", []))
    actions = _reconcile_advance_pipeline_actions(
        actions,
        recommended_stage=_extract_recommended_stage(pipeline_ctx),
        pipeline_ctx=pipeline_ctx,
        messages=request.messages,
    )
    action_types = [a.get("type") for a in actions]
    tokens_estimated = not stream_usage
    if stream_usage and stream_usage.get("total_tokens"):
        total_tokens = stream_usage["total_tokens"]
        prompt_tokens = stream_usage.get("prompt_tokens")
        completion_tokens = stream_usage.get("completion_tokens")
    else:
        total_tokens = _estimate_tokens(llm_messages, buffer)
        prompt_tokens = None
        completion_tokens = None
    await push_trace(
        "A1",
        "AGENT_OUTPUT",
        {
            "actions": action_types,
            "user_status": user_status[:50],
            "tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens_estimated": tokens_estimated,
        },
    )
    studio_print(
        "trace",
        f"A1 AGENT_OUTPUT actions={action_types} user_status_len={len(user_status)} "
        f"tokens={total_tokens} prompt_tokens={prompt_tokens} "
        f"completion_tokens={completion_tokens} tokens_estimated={tokens_estimated}",
    )

    paused_at_ask = False
    for i, action in enumerate(actions):
        if paused_at_ask:
            break
        if action.get("type") == "ask_user":
            options = action.get("options") or []
            if isinstance(options, list) and options:
                titles = [
                    str(o.get("title") or "").strip()
                    for o in options
                    if isinstance(o, dict) and (o.get("title") or "").strip()
                ]
                await push_trace(
                    "A1",
                    "CREATIVE_CARDS",
                    {
                        "options_count": len(options),
                        "titles": titles,
                    },
                )
                studio_print(
                    "trace",
                    f"A1 CREATIVE_CARDS options_count={len(options)} titles={titles}",
                )
        yield f'data: {json.dumps({"event": "action", "action": action, "index": i}, ensure_ascii=False)}\n\n'
        if action.get("type") == "ask_user":
            paused_at_ask = True

    done_action = next((a for a in actions if a.get("type") == "done"), {})
    summary = (done_action.get("summary") or "").strip()
    suggestions = done_action.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = []
    suggestions = [str(s).strip() for s in suggestions if str(s).strip()][:3]

    if summary and not paused_at_ask:
        for chunk in re.split(r'(?<=[。！？…\n])', summary):
            piece = chunk.strip()
            if not piece:
                continue
            yield f'data: {json.dumps({"event": "reply_delta", "content": chunk}, ensure_ascii=False)}\n\n'
            await asyncio.sleep(0.04)

    yield f'data: {json.dumps({"event": "done", "suggestions": suggestions}, ensure_ascii=False)}\n\n'


def _fallback_title_from_messages(messages: list[dict]) -> str:
    first_user = next((m for m in messages if m.get("role") == "user"), None)
    text = (first_user.get("content") or "").strip() if first_user else ""
    if not text:
        return "未命名对话"
    return text[:28] + "…" if len(text) > 28 else text


async def generate_chat_title(messages: list[dict]) -> str:
    """根据对话内容生成简短标题（LLM），失败时回退到首条用户消息截断。"""
    if not messages:
        return "未命名对话"

    api_key, base_url, model, registered_id = _resolve_agent_model()
    if not api_key:
        return _fallback_title_from_messages(messages)

    lines = []
    for msg in messages[:8]:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            lines.append(f"{role}: {content[:160]}")
    if not lines:
        return _fallback_title_from_messages(messages)

    prompt = (
        "根据以下对话摘录，用不超过10个中文字生成一个简短的会话标题。\n"
        "只输出标题本身，不要引号、不要解释。\n\n"
        + "\n".join(lines)
    )

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=30.0) as http:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0,
                http_client=http,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=32,
                temperature=0.2,
            )
        usage = getattr(response, "usage", None)
        if registered_id and usage is not None:
            from services.llm_router import record_usage

            total = int(getattr(usage, "total_tokens", 0) or 0)
            if total <= 0:
                total = int(getattr(usage, "prompt_tokens", 0) or 0) + int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
            if total > 0:
                record_usage(registered_id, total)
        title = (response.choices[0].message.content or "").strip()
        title = title.strip("\"'“”‘’").replace("\n", " ").strip()
        if not title:
            return _fallback_title_from_messages(messages)
        return title[:28] + "…" if len(title) > 28 else title
    except Exception:
        return _fallback_title_from_messages(messages)
