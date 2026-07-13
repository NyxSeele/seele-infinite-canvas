# 路线 C 验收计划（ROUTE_C_VALIDATION_PLAN）

## 路线 C 定义

**路线 C** = 在路线 B（分镜表 `compile` + `build-shot` + 串行批量出图/转视频 + L0–L4 trace）之上，将分镜表 **rows 来源** 从手工固定文案改为 **Agent 全链路自动产出**（A1→A4），再执行 GPU 批量验收。

依据：[ROUTE_B_RESULT.md](ROUTE_B_RESULT.md) §路线 C 前置条件、[HANDOFF.md](HANDOFF.md) Route-A/B 描述。

相关文档：

- [AGENT_TRACE_BASELINE.md](AGENT_TRACE_BASELINE.md) — Agent A1–A4 trace 基线
- [ROUTE_B_RESULT.md](ROUTE_B_RESULT.md) — 路线 B 固定文案批量 GPU 验收
- [`backend/scripts/_route_c_agent_gpu_probe.py`](backend/scripts/_route_c_agent_gpu_probe.py) — 路线 C 探针实现

```mermaid
flowchart LR
  subgraph agent [Agent链路 A1-A4]
    U[用户输入] --> A1[A1编排]
    A1 --> Ask[ask_user创意卡]
    Ask --> Pick[用户选择]
    Pick --> A1b[A1第二轮]
    A1b --> Note[create_text_note]
    Note --> A2[A2剧本文本]
    A2 --> A3[A3大纲]
    A3 --> A4[A4分镜表API]
    A4 --> Rows[rows写入画布]
  end
  subgraph gpu [路线B式批量 GPU]
    Rows --> L0["compile+build-shot L0"]
    L0 --> Img[L1-L4出图]
    Img --> Vid[L1-L4转视频]
  end
```

**与路线 B 差异**：路线 B 探针 [`_route_b_batch_probe.py`](backend/scripts/_route_b_batch_probe.py) 使用硬编码 `SHOTS[]`；路线 C 要求 `row.description` 来自 A4 `generate-shots` 产出。

**与 e2e 探针差异**：e2e 在 R4 后用 `apply_script_table()` **手工模拟** 2 镜 rows，不测 A4 描述质量，也不做 3 镜批量 GPU。

---

## 1. 验收矩阵

| 步骤 | 链路位置 | 探针覆盖 | 覆盖文件 | 缺口说明 |
|------|---------|---------|---------|---------|
| 用户输入 | Agent `messages[0]` | ✅ 已有且跑通 | `_agent_trace_baseline_probe.py` · `_agent_pipeline_e2e_probe.py` | 场景固定（雨夜重庆 / 渝爱熊猫），非参数化 |
| A1 Agent 编排 | `POST /api/agent/run` · `agent_service.py` | ✅ 已有且跑通 | 同上 · `_agent_pipeline_probe.py`（前几步） | 仅断言 `pipeline_step` 类型，不校验 `user_status` 与阶段提示一致性 |
| 创意卡片 `ask_user` | A1 `CREATIVE_CARDS` trace | ⚠️ 部分覆盖 | baseline R1 可选处理 · e2e R1 强制 pick | baseline 在输入含「3个镜头」时常 **跳过** ask_user 直接 `create_text_note`（见 [AGENT_TRACE_BASELINE.md](AGENT_TRACE_BASELINE.md) §2）；无断言 `options_count≥2` |
| 用户选择 | 第二轮 `messages` | ⚠️ 部分覆盖 | baseline `pick_msg` · e2e `pick_msg` | 仅选 `options[0]`，未覆盖多卡 UI / cast_pending 门禁 |
| A1 第二轮 | Agent 继续轮次 | ✅ 已有且跑通 | baseline R2+ · e2e R2–R4 | 内存画布快照，**不写** `canvas_projects` DB |
| `create_text_note` | `pipeline_step` · `agentPipeline.createTextNote` | ⚠️ 部分覆盖 | baseline `execute_pipeline_step` · e2e 同 | 探针本地 `nodes[]` 模拟，非 React Flow 持久化 |
| A2 剧本文本 | `POST /api/tasks/text` · A2 trace | ✅ 已有且跑通（baseline） | baseline（真实 qwen-plus） | e2e 在 text 失败时 **MOCK_SCREENPLAY** 兜底 |
| A3 大纲结构化 | `POST /api/screenplay/structure-from-text` | ✅ 已有且跑通（baseline §8） | baseline · e2e（可 mock） | e2e outline API 失败走 `mock_outline_nodes`；无 scenes 字段质量断言 |
| A4 分镜表生成 | `POST /api/screenplay/generate-shots` · A4 trace | ⚠️ 部分覆盖 | baseline 调 API 收集 trace | **未**断言 `segments`/`total_shots` 与用户需求镜数；e2e R4 只验 Agent **意图** 为 `generate_script_table` |
| 分镜行 rows 写入画布 | `useScreenplay.onGenerateScriptTable` → `rows`/`segments` | ❌ 无覆盖 | 仅浏览器 + [`useScreenplay.js`](frontend/src/hooks/canvas/useScreenplay.js) | baseline 仅追加 **无 rows** 的 stub `script_table` 节点；e2e 用 `apply_script_table(row_count=2)` 假数据 |
| compile + build-shot（L0） | `POST /api/prompt/compile` + `build-shot` | ✅ 已有且跑通 | `_route_b_batch_probe.py` | **与 Agent 链路断开**；固定 `SHOTS[]` 描述，非 A4 产出 |
| 批量出图（L1–L4） | `POST /api/tasks/image` 串行 3 镜 | ✅ 已有且跑通 | `_route_b_batch_probe.py` | 同上；新机曾 3/3 PASS（[HANDOFF_SERVER.md](HANDOFF_SERVER.md)） |
| 批量转视频（L1–L4） | `POST /api/tasks/video` keyframe | ⚠️ 部分覆盖 | `_route_b_batch_probe.py` | 旧机全量 PASS；新机 **2/3 超时**（900s 不足）；与 Agent 无关 |
| Agent 单镜 `generate_storyboard`/`generate_video` | `agentPipeline` 生产阶段 | ⚠️ 部分覆盖（mock 标签） | `_agent_pipeline_e2e_probe.py` R6–R8 · `_mock_pipeline_stage2_probe.py` | 调真实 `/api/tasks/*` 但 **2 镜**、prompt 手写；**非**路线 C 批量路径 |
| 画布持久化 + 前端执行 | `useCanvasAgent` → `executeAgentPipelineStep` | ❌ 无覆盖 | 无 HTTP 探针 | 仅人工浏览器；Agent 执行依赖 `setNodes`/`onGenerateScriptTable` |
| 分镜表一键批量（UI） | `runScriptTableGenerateAll` / `AllVideo` | ❌ 无覆盖 | 仅 [`ScriptTableNode.jsx`](frontend/src/components/canvas/ScriptTableNode.jsx) | 路线 C 批量逻辑在 frontend hook，无 headless 探针 |

---

## 2. 缺口补全方案

### 缺口 C1：创意卡片强制路径（可选模式）

- **文件**：扩展 [`_agent_trace_baseline_probe.py`](backend/scripts/_agent_trace_baseline_probe.py) 或新建 `_route_c_agent_gpu_probe.py` 支持 `--require-ask-user`
- **断言**：R1 含 `ask_user` + `A1 CREATIVE_CARDS options_count>=2`；R2 用户 `pick_msg` 后再 `create_text_note`
- **发现问题**：意图 D 与「明确 N 镜」冲突时 Agent 跳过创意卡（产品规则回归）

### 缺口 C2：A4 产出质量门禁

- **文件**：`_route_c_agent_gpu_probe.py`（复用 baseline 的 `generate_shots_api`）
- **断言**：`shots_target` 与场景「3个镜头」一致；`total_shots>=3`；每镜 `prompt` 非空且长度≥50；`parsed.A4.shots_detail` 写入 JSON
- **发现问题**：A4 prompt 过短/重复/丢场景（路线 C 核心风险，见 ROUTE_B §路线 C）

### 缺口 C3：真实 rows 物化（非 stub）

- **文件**：`_route_c_agent_gpu_probe.py` 新增 `apply_script_table_from_shots(segments, rows)`
- **实现**：调用与 [`useScreenplay.js`](frontend/src/hooks/canvas/useScreenplay.js) `segmentsToScriptPayload` 同等逻辑（或直接 `POST generate-shots` 响应 → 映射 `row.id`/`description`/`shot_number`）
- **断言**：`len(rows)==total_shots`；`row.description` 来自 A4 而非 `SHOTS[]` 常量
- **发现问题**：API segments 与前端 rows 映射不一致、duration 归一化错误

### 缺口 C4：Agent rows → 路线 B 批量 GPU

- **文件**：`_route_c_agent_gpu_probe.py` 复用 [`_route_b_batch_probe.py`](backend/scripts/_route_b_batch_probe.py) 的 `build_shot`/`submit_image`/`submit_video`/`parse_traces_from_log`
- **变更**：`SHOTS` 改为从 C3 的 `rows` 动态生成；保留 `THEME_CONTEXT`/`CHARACTER_REFS` 从 A2 剧本文本抽取（可选 regex/LLM 摘要）
- **断言**：3/3 image completed；3/3 video completed；002/003 `L0` 含「承接」；003 视频 L4 含主角外貌关键词（复用 Route-B2）
- **发现问题**：Agent 描述与 preset/角色 ref 不匹配导致 L0 漂移；承接链断裂

### 缺口 C5：画布 API 持久化（可选 P1）

- **文件**：`_route_c_agent_gpu_probe.py` 调 `PUT/PATCH /api/canvas/projects/{id}`（若后端暴露完整 `canvas_data`）
- **断言**：DB 中 `script-table` 节点 `rows.length>0`
- **发现问题**：探针内存态与前端保存格式不一致

### 缺口 C6：批量超时与运维

- **文件**：`_route_b_batch_probe.py` 或 route_c 探针
- **变更**：`POLL_TIMEOUT=1800`；批跑前清理 `tasks` pending（见 HANDOFF_SERVER §8）
- **发现问题**：第 3 镜 wan-i2v 超时误报失败

### 缺口 C7：`STRUCTURE_SCENE_TITLES` / 完整剧本文本

- **文件**：已由 baseline + §8 修复覆盖
- **断言**：`text_len>=1000` · `scenes_count=3` · 无 `only 2 scenes`
- **发现问题**：A3 截断导致镜数不足（已修，回归用）

---

## 3. 现有两探针：重叠与互补

| 维度 | `_agent_trace_baseline_probe.py` | `_agent_pipeline_e2e_probe.py` |
|------|----------------------------------|--------------------------------|
| **目标** | A1–A4 **可观测性** trace 基线 | Agent **阶段机** + 生产步意图（R5–R8） |
| **场景** | 雨夜重庆 3 镜 | 重庆动物园渝爱 |
| **A2/A3** | 真实 LLM（无 mock） | mock 兜底 |
| **分镜表** | `generate-shots` API + stub 节点 | 验 R4 意图 + **假** `apply_script_table` |
| **GPU** | 无 | `/api/tasks/image|video`（2 镜，短 timeout） |
| **产出** | `agent_trace_baseline.json` | stdout issues 列表 |

**结论：不应合并为一个探针。**

- **合并缺点**：单次运行 30–40min+；失败难定位（trace vs 意图 vs GPU）；mock 与真实 LLM 无法同参
- **建议架构**：
  - **保留** baseline：快速（~4min）A1–A4 trace 回归
  - **保留** e2e：Agent 生产阶段意图 + mock-friendly CI
  - **新建** [`_route_c_agent_gpu_probe.py`](backend/scripts/_route_c_agent_gpu_probe.py)：**编排** baseline 前半 + route_b 后半，单一 JSON 报告 `route_c_results.json`

可抽取共享模块 `backend/scripts/_probe_agent_canvas.py`（login、sse、apply_text_response、generate_outline）避免三份重复，但非阻塞。

---

## 4. 建议执行顺序

1. **前置**：`AGENT_MOCK_GENERATION=false` · text 模型 enabled · Supervisor 稳定 · Redis 可选
2. **回归 baseline**：`_agent_trace_baseline_probe.py` exit 0（A3=3 · A2 真实 trace）
3. **回归 route_b**：`_route_b_batch_probe.py` timeout 1800 → 3/3 图 + 3/3 视频
4. **实现并首跑 route_c 探针**（C2–C4）
5. **可选**：`--require-ask-user` 模式跑创意卡路径（C1）
6. **pytest** `67 passed`
7. **文档**：更新 `ROUTE_C_RESULT.md` + HANDOFF 路线 C 行

---

## 5. 路线 C 完成标志（Definition of Done）

满足 **全部** 下列条件，路线 C 视为验收完成：

| # | 条件 |
|---|------|
| 1 | `_route_c_agent_gpu_probe.py` **exit 0**，日志 `route_c_results.json` 存档 |
| 2 | Agent 链路：`create_text_note` → `start_text_generation` → `generate_outline` → `generate_script_table` 四轮 **pipeline_step** 均成功（允许 R1 无 ask_user 的「明确 3 镜」变体，但须在报告中标注 `creative_cards_skipped: true/false`） |
| 3 | A2/A3/A4 trace 齐全：`TEXT_*` · `STRUCTURE_OUTPUT scenes_count=3` · `SHOTS_OUTPUT total_shots=3` |
| 4 | 分镜 **rows 描述 100% 来自 A4**（非硬编码 `SHOTS[]`），`len(rows)>=3` |
| 5 | GPU：**3/3 出图 completed** + **3/3 出视频 completed**（`POLL_TIMEOUT>=1800`） |
| 6 | L0：`002`/`003` 图像 trace 含承接语义；视频 L4 含主角外貌关键词（Route-B2 标准） |
| 7 | `pytest` **67 passed**，无回退 |
| 8 | [`ROUTE_C_RESULT.md`](ROUTE_C_RESULT.md) 记录指标对比表（相对路线 B 固定文案基线） |
