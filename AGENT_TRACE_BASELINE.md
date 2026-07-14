# Agent Trace 基线验收报告

最后更新：**2026-07-10**（Agent 质量校准 · 探针场景：`雨夜重庆，一个女人独自等待，3个镜头`）

原始数据：[`/root/autodl-tmp/logs/agent_trace_baseline.json`](/root/autodl-tmp/logs/agent_trace_baseline.json) · 校准汇总：[`/root/autodl-tmp/logs/agent_quality_calibration.json`](/root/autodl-tmp/logs/agent_quality_calibration.json)

---

## 1. Instrumentation 摘要

| 层 | 位置 | 标签 | 方式 |
|----|------|------|------|
| A1 | `agent_service.py` | `AGENT_INPUT` / `AGENT_OUTPUT` / `CREATIVE_CARDS` | `push_trace` + `studio_print` |
| A2 | `tasks.py` `_run_text_generation` | `TEXT_INPUT` / `TEXT_OUTPUT` | `studio_print` |
| A3 | `screenplay_structure.py` | `STRUCTURE_INPUT` / `STRUCTURE_OUTPUT` | `studio_print` |
| A4 | `qwen.py` `generate_shots` | `SHOTS_INPUT` / `SHOTS_OUTPUT` | `push_trace` + `studio_print` |
| A5 | `split_shot_beats.py` | `BEATS_INPUT` / `BEATS_OUTPUT` | `studio_print` |

`trace_bus.push_trace` 已扩展为 `layer: int | str`（兼容 L0–L4 整数层与 A1/A4 字符串层）。

---

## 2. 基线跑测结果

| 项 | 结果 |
|----|------|
| 探针 | `scripts/_agent_trace_baseline_probe.py` **exit 0** |
| 链路 | create_text_note → start_text_generation → generate_outline → generate_script_table |
| A3 | `scenes_count=3` · `elapsed_ms=13271` |
| A4 | `segments=3` · `total_shots=3` · `shots_target=3` |
| pytest | **67 passed**（含 `test_trace_bus.py`） |

**环境说明**（首轮跑测 · 2026-07-08 上午）：

- DB 无已注册 `text` 模型，A2 剧本文本阶段使用探针内 **MOCK_SCREENPLAY** 兜底（未产生 `A2 TEXT_*` 日志行）。
- 本轮 Agent R1 未出创意卡片，直接 `create_text_note`（用户输入已含「3个镜头」明确约束）；更早一轮跑测曾出现 `CREATIVE_CARDS`（3 张卡片）。

**A2 复验**（§7）：注册 `qwen-plus` 后重跑，真实 `TEXT_INPUT` / `TEXT_OUTPUT` 已采集。

---

## 3. 诊断问题回答

### 3.1 Agent 编排 LLM 实际 token 消耗

来自 `A1 AGENT_OUTPUT`（`tokens_estimated=False`，为 DashScope 流式 `include_usage` 真值）：

**优化前（2026-07-08）**

| 轮次 | canvas_nodes | actions | tokens |
|------|--------------|---------|--------|
| 末轮（分镜表前） | 3 | pipeline_step + done | **5596** |
| 典型中间轮 | 1–2 | pipeline_step + done | 4501–5369 |
| 含创意卡片轮（历史） | 0 | ask_user + done | 4676 |

**优化后（2026-07-09 · G32）**：阶段化短 system prompt + pipeline 轮去掉全量画布 JSON。

| 轮次 | canvas_nodes | pipeline_prompt | tokens | prompt_tokens |
|------|--------------|-----------------|--------|---------------|
| R1 创意 ask_user | 0 | False | **5212** | 4336 |
| R2 create_text_note | 0 | True | **1857** | 1195 |
| R3 start_text_generation | 1 | True | **1705** | 1249 |
| R4 generate_outline | 2 | True | **1738** | 1368 |
| R5 generate_script_table | 3 | True | **1778** | 1402 |

**结论**：pipeline「继续」轮约 **1.7–1.9k tokens**（相对原 ~5.5k 降 **≥65%**）；创意/ask_user 轮仍用全量 SYSTEM_PROMPT（~5k，预期内）。`studio_print` 已落盘 `prompt_tokens` / `completion_tokens` / `pipeline_prompt`。

**2026-07-10 校准**：G32 形态 pipeline 样本 median **1676**（min 1491 / max 2243）；建议观测区间 **1600–2100**（soft 1500–2200；**>2500 仍判 G32 回退 FAIL**）。不收紧创意轮。

---

## 校准 2026-07-10

编排：[`backend/scripts/_agent_quality_calibration_probe.py`](backend/scripts/_agent_quality_calibration_probe.py)（默认跳过 GPU；`--with-gpu` 跑 Route-C）。汇总 JSON：[`/root/autodl-tmp/logs/agent_quality_calibration.json`](/root/autodl-tmp/logs/agent_quality_calibration.json)。

| 指标 | 状态 | 详情 |
|------|------|------|
| pytest g32+trace | PASS | 5 passed |
| baseline A1–A4 | PASS | 到达 `generate_script_table`；A2 遇 429 可 mock 回退 |
| pipeline tokens | PASS | median **1676**；golden 建议 **1600–2100** |
| creative tokens | OBS | median ~5.2k |
| A3 scenes | PASS | 3 |
| A4 shots | WARN | `total_shots=9`（目标 3）— 镜数膨胀，**不放宽**门禁 |
| A2 screenplay | PASS | len≥500 |
| 对抗回归 6 条 | FAIL | **4/6**（同日最佳 **5/6**）；稳定失败 `cat1_continue_after_storyboard`；另见 `cat6_ignore_creative_options`。**不自动放宽断言** |
| e2e mock | WARN | LLM 阶段顺序偶发偏差（已知） |
| Route-C GPU | SKIP | 本轮未跑 |

### 阈值结论

1. **Token**：继续轮 golden → **1600–2100**；FAIL 线仍 **>2500**。
2. **对抗**：`cat1_continue_after_storyboard` 期望已语义更正为 **`generate_video`（完成当前镜视频）**（2026-07-14：按镜单线程，非放宽到错误出图）。
3. **A4 镜数**：要 3 出 9 → 已加显式镜数硬约束与后处理裁剪；门禁仍按目标镜数验收。
4. **运维**：连跑易 429 / 后端断开；编排含 health 等待与间隔；baseline 对 429/5xx mock 回退。

### 修复 2026-07-14

- `_production_stage_hint` / 前端 `inferProductionStage`：按镜号单线程（出图→视频），生成中 `wait_*`，禁止跨镜 multitask。
- 「继续」短指令与 hint 不一致时后端确定性纠偏。
- 对抗 `cat1_continue_after_storyboard` expect → `generate_video`。

## 校准 2026-07-14（5090 · 含 Route-C）

环境：北京 B 区 RTX 5090；supervisord 托管 `aistudio-backend` / `comfyui`；已补齐 `registered_models` 文本模型（`_enable_text_models.py`）；探针侧 `structure-from-text` / `generate-shots` 异步轮询；`flux-dev` 禁用链式 reference（API 400）。

汇总：[`/root/autodl-tmp/logs/agent_quality_calibration.json`](/root/autodl-tmp/logs/agent_quality_calibration.json)（编排次）· [`/root/autodl-tmp/logs/route_c_results.json`](/root/autodl-tmp/logs/route_c_results.json)（GPU 单独复跑）· [`/root/autodl-tmp/logs/route_c_run6.log`](/root/autodl-tmp/logs/route_c_run6.log)

| 指标 | 状态 | 详情 |
|------|------|------|
| pytest g32+trace | PASS | 5 passed |
| baseline A1–A4 | PASS | 到达 `generate_script_table`；A2/A3/A4 实跑通过 |
| pipeline tokens | PASS | median **1563**（soft 1500–2200）；建议观测带 **1463–1900** |
| creative tokens | OBS | median ~4.8k |
| A3 scenes | PASS | 3 |
| A4 shots | PASS | **total_shots=3**（硬约束生效） |
| A2 screenplay | PASS | len≥1000 |
| 对抗回归 6 条 | FAIL | **4/6**；`cat1_*`/`cat6` PASS；稳定失败 `cat3_regenerate_this_shot_video`、`cat3_which_script_table`（多链路应 ask_user，LLM 偶发直接 pipeline；**不放宽断言**） |
| e2e mock | WARN | 阶段顺序/并发槽位偶发（已知） |
| Route-C GPU | WARN | **3/3 图 + 3/3 视频均 completed**；探针 exit=1 因 L0 主题词 / L4 appearance 关键词（生成链路已通，质量断言未绿） |

### 建议手测

多镜分镜表下点「继续」应只推进**当前镜**；分镜图/视频生成中再点应 busy 拦截。

```bash
cd /root/autodl-tmp/AIStudio/backend
.venv/bin/python scripts/_agent_quality_calibration_probe.py
.venv/bin/python scripts/_agent_quality_calibration_probe.py --with-gpu  # 可选
```

### 3.2 `generate_shots` 输入大纲质量

```
A4 SHOTS_INPUT outline_len=1825 shots_target=3
```

- 输入为结构化 JSON（`title` + `scenes[]`），含 3 个 scene、目标时长 **24s**（`target_duration_sec`）。
- `shots_target=3` 与用户需求「3个镜头」一致。
- **弱点**：上游剧本文本为 MOCK（非真实 LLM 扩写），A3 实际 `input_len=296` 偏短，大纲信息量依赖 mock 三段时间轴段落，未经过完整 A2 剧本文本链路。

### 3.3 分镜描述质量（A4 输出）

三镜 `prompt` 均含：**场景（雨夜重庆）+ 人物动作/表情 + 景别 + 运镜 + 光影**，非简单一句话。

**镜 1 摘要**（`shot-1-1`）：

> 中景镜头缓慢推近，冷色路灯与暖色霓虹在积水路面上交叠闪烁……女人伫立灰蓝色雨棚下，手指无意识攥紧手机……

| 镜号 | camera | movement | 导演字段完整度 |
|------|--------|----------|----------------|
| 001 | 中景 | 缓慢推近 | 光影 ✅ |
| 002 | 全景转中景 | 横摇 | 光影 ✅ |
| 003 | 远景 | 固定后缓慢拉远 | 剪影/霓虹 ✅ |

**结论**：在 MOCK 剧本输入下，A4 `SHOTS_SYSTEM_PROMPT` 产出质量 **良好**，符合「导演级中文描述句」要求。

### 3.4 瓶颈判断（最需调优环节）

| 优先级 | 环节 | 证据 | 说明 |
|--------|------|------|------|
| ~~**P0**~~ | ~~**A2 剧本文本**~~ | ✅ 2026-07-08 下午复验 | `_enable_text_models.py` + `call_openai_compatible` env 兜底；真实 A2 trace 见 §7 |
| **P1** | **A1 编排** | 每轮 ~5k tokens；偶发跳过创意卡片 | 超长 system + 画布 JSON；意图 D（创意卡）与明确「N镜」约束冲突时需规则兜底 |
| **P2** | **A3 结构化** | `elapsed_ms=13271`；`input_len=296`（首轮 MOCK） | 耗时长；真实 A2 后 `input_len=550`（§7） |
| P3 | A4 分镜 | 输出质量本轮 **最好** | 非瓶颈 |

**综合**：A2 环境断路已修复；当前主瓶颈为 **A1 高 token / 意图分流不稳定**；分镜生成（A4）在现有 prompt 下表现最好。

---

## 4. Trace grep 样例

```bash
grep -E '\[AIStudio:trace\] A[1-5]' /root/autodl-tmp/logs/backend.out.log | tail -15
```

```
[AIStudio:trace] A1 AGENT_OUTPUT actions=['pipeline_step', 'done'] ... tokens=5369 tokens_estimated=False
[AIStudio:trace] A3 STRUCTURE_INPUT input_len=296
[AIStudio:trace] A3 STRUCTURE_OUTPUT scenes_count=3 elapsed_ms=13271
[AIStudio:trace] A1 AGENT_OUTPUT ... tokens=5596 tokens_estimated=False
[AIStudio:trace] A4 SHOTS_INPUT outline_len=1825 shots_target=3
[AIStudio:trace] A4 SHOTS_OUTPUT segments=3 total_shots=3
```

---

## 5. 复现命令

```bash
supervisorctl -c /etc/supervisor/supervisord.conf restart aistudio-backend
cd /root/autodl-tmp/AIStudio/backend
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/_agent_trace_baseline_probe.py
```

---

## 6. 后续建议（仅观测结论，未改 prompt）

1. ~~注册并启用 `text` 类模型，重跑基线以采集真实 **A2** trace。~~ ✅ 见 §7
2. A1 `AGENT_OUTPUT` 增加 `prompt_tokens` / `completion_tokens` 分项（若 provider 返回）。
3. ~~探针/前端在调用 `structure-from-text` 时传完整剧本文本，避免仅用 `content_preview` 截断。~~ ✅ 见 §8（前端本就传 `data.content`）

---

## 7. A2 真实文本链路复验（2026-07-08 下午）

### 7.1 根因

| 问题 | 说明 |
|------|------|
| `registered_models` 无 text 模型 | `init_db` 不 seed API 模型；`_enable_gpu_models.py` 仅写 image/video |
| `_enable_text_models.py` 逻辑缺陷 | 旧版用 `DEFAULT_ENABLE_IDS` 硬编码，未按 env 非空决定 `enabled` |
| `call_openai_compatible` 无 env 兜底 | `row.api_key` 空时直接 `ValueError`，与 A1/A3/A4 的 `.env` 回退不一致 |

### 7.2 修复摘要

| 变更 | 文件 |
|------|------|
| 从 `ALL_MODELS` 筛 `category=text` + `type=api` upsert；仅 env 非空 `enabled=True`；`qwen-plus` 设 `is_default_text` | `scripts/_enable_text_models.py` |
| `row.api_key` 空时按 `MODEL_MAP[id].api_key_env` 读 `os.environ` | `providers/qwen.py` |
| 探针 `get_text_model()` 优先 `is_default_text DESC` | `scripts/_agent_trace_baseline_probe.py` |

### 7.3 DB 快照（`scripts/_enable_text_models.py` 执行后）

```
qwen-turbo|1|text|0
qwen-plus|1|text|1
qwen-max|1|text|0
gpt-4o|0|text|0
claude-sonnet-4|0|text|0
claude-opus-4|0|text|0
```

### 7.4 探针结果

| 项 | 结果 |
|----|------|
| 探针 | `_agent_trace_baseline_probe.py` **exit 0**（~54s） |
| 链路 | R1 `create_text_note` → R2 `start_text_generation`（**真实 qwen-plus**）→ R3 `generate_outline` → R4 `generate_script_table` |
| A2 | `TEXT_INPUT` ×4 · `TEXT_OUTPUT` ×2（`output_len` 1052–1102） |
| A3 | `input_len=550` · `scenes_count=2` · `elapsed_ms=10030` |
| A4 | `outline_len=1342` · `segments=2` · `total_shots=4` |
| pytest | **67 passed** |
| issues | `[]`（无 MOCK 兜底） |

**A2 grep 样例**：

```
[AIStudio:trace] A2 TEXT_INPUT mode=screenplay input_len=319
[AIStudio:trace] A2 TEXT_OUTPUT mode=screenplay output_len=1102
[AIStudio:trace] A2 TEXT_INPUT mode=screenplay input_len=313
[AIStudio:trace] A2 TEXT_OUTPUT mode=screenplay output_len=1052
```

### 7.5 复现命令

```bash
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf restart aistudio-backend
cd /root/autodl-tmp/AIStudio/backend
set -a && source .env && set +a
.venv/bin/python scripts/_enable_text_models.py
sqlite3 aistudio.db "SELECT id, enabled, is_default_text FROM registered_models WHERE category='text';"
.venv/bin/python scripts/_agent_trace_baseline_probe.py
grep -E 'A2 TEXT_(INPUT|OUTPUT)' /root/autodl-tmp/logs/backend.out.log | tail -5
.venv/bin/python -m pytest tests/ -q
```

---

## 8. A3 剧本文本截断修复（2026-07-08 晚）

### 8.1 根因

| 环节 | 问题 |
|------|------|
| 基线探针 `apply_text_response` | 仅写 `content_preview=content[:500]`，无 `content` 字段 |
| 探针 `generate_outline` 步骤 | 读 `content_preview` 送 `structure-from-text` → 日志 `text_len=500` |
| 后果 | 第三段【00:30-00:60】被截掉 → `only 2 scenes` WARNING · A3 `scenes_count=2` |

**前端**：`agentPipeline.generateOutline` 已用 `responseNode.data.content`（完整 `tasks.result`），**无需改动**。

### 8.2 修复摘要

| 变更 | 文件 |
|------|------|
| 节点增加 `content` 全文；`generate_outline` 优先读 `content` | `scripts/_agent_trace_baseline_probe.py` |
| 同上（e2e 探针） | `scripts/_agent_pipeline_e2e_probe.py` |
| `A3 STRUCTURE_SCENE_TITLES` trace（标题列表 ≤200 字） | `services/screenplay_structure.py` |

### 8.3 重跑对比（基线探针 exit 0 · ~233s）

| 指标 | §7 修复前 | §8 修复后 |
|------|-----------|-----------|
| `structure-from-text` `text_len` | 500 | **724** |
| A3 `STRUCTURE_INPUT input_len` | 550 | **774** |
| A3 `scenes_count` | 2 | **3** |
| `only 2 scenes` WARNING | 有 | **无**（本轮） |
| A4 `outline_len` | 1342 | **2376** |
| A4 `segments` / `total_shots` | 2 / 4 | **2 / 3**（`shots_target=3` 已对齐镜数） |
| `outline_scenes_count` | 2 | **3** |
| pytest | 67 passed | **67 passed** |

**A3 trace 样例**（修复后）：

```
[AIStudio:trace] A3 STRUCTURE_INPUT input_len=774
[AIStudio:trace] A3 STRUCTURE_OUTPUT scenes_count=3 elapsed_ms=40778
[AIStudio:trace] A3 STRUCTURE_SCENE_TITLES 场景一 | 场景二 | 场景三
```

（最后一行为 instrumentation 冒烟；基线跑测期间若后端重启，可能仅见前两行，属运维抖动。）

**A4 trace 样例**：

```
[AIStudio:trace] A4 SHOTS_INPUT outline_len=2376 shots_target=3
[AIStudio:trace] A4 SHOTS_OUTPUT segments=2 total_shots=3
```

### 8.4 复现命令

```bash
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf restart aistudio-backend
cd /root/autodl-tmp/AIStudio/backend
set -a && source .env && set +a
.venv/bin/python scripts/_agent_trace_baseline_probe.py
grep -E 'A3 STRUCTURE|only [0-9] scenes' /root/autodl-tmp/logs/backend.out.log | tail -8
.venv/bin/python -m pytest tests/ -q
```
