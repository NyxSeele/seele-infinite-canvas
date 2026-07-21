# OpenMontage 学习笔记（Velora 对照）

> 阶段：第 1 阶段只读分析 | 日期：2026-07-20  
> 上游仓库：https://github.com/calesthio/OpenMontage（AGPL-3.0）  
> 本地 clone 状态：`/root/autodl-tmp/oss-study/OpenMontage` **未成功**（GitHub 443 超时；已用上游 raw 文件核对路径与内容）

---

## A. OpenMontage 三层架构摘要

OpenMontage 的核心设计是 **agent=编排器 / pipeline=剧本 / tools=执行器**。Python 层只做工具与持久化，**没有 Python orchestrator**；编排智能在 AI Agent + Markdown/YAML 指令里。

### 文字版三层架构图

```text
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1 — Orchestrator（编排器）                                 │
│   Cursor / Claude Code 等 AI Agent                               │
│   合约：AGENT_GUIDE.md + IDE 入口（CURSOR.md）+ .cursor/rules/   │
│   职责：选 pipeline、读 stage skill、preflight、checkpoint、审批  │
└────────────────────────────┬────────────────────────────────────┘
                             │ 读 manifest + skill，决定下一步
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Layer 2 — Pipeline（剧本）                                       │
│   pipeline_defs/*.yaml（阶段、门禁、产物、可用工具）              │
│   skills/pipelines/*/*-director.md（每阶段执行指南）             │
│   lib/pipeline_loader.py（加载与校验 manifest）                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ 调用已注册工具
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3 — Tools（执行器）                                        │
│   tools/*（BaseTool 子类）                                       │
│   tools/tool_registry.py（发现、能力信封、provider 菜单）        │
│   lib/checkpoint.py + projects/ 磁盘状态                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ 只读可视化
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backlot（生产看板，非编排层）                                    │
│   backlot/ — 从 projects/ checkpoint/artifacts/events 推导状态   │
│   预算/审批/阶段灯、剧本页、胶片条、replay                       │
└─────────────────────────────────────────────────────────────────┘
```

### 各层证据路径（上游仓库，已 raw 核对）

| 层 | 职责 | 证据文件 |
|----|------|----------|
| **Orchestrator** | Agent 合约与路由；强制先读 AGENT_GUIDE | `AGENT_GUIDE.md`（Rule Zero：所有生产必须走 pipeline） |
| **Orchestrator** | Cursor 强制规则 | `.cursor/rules/openmontage.mdc`（`alwaysApply: true`，MANDATORY 读 AGENT_GUIDE） |
| **Pipeline** | 声明式阶段剧本 | `pipeline_defs/cinematic.yaml`（stages: research→…→publish，每 stage 含 skill、produces、checkpoint、human_approval） |
| **Pipeline** | Manifest 加载器 | `lib/pipeline_loader.py`（`load_pipeline()` + jsonschema 校验） |
| **Tools** | 工具注册与能力信封 | `tools/tool_registry.py`（`discover()`、`support_envelope()`、`provider_menu_summary()`） |
| **Backlot** | 生产状态只读看板 | `backlot/README.md`（SSE + watchfiles，数据源 checkpoint/artifacts/events.jsonl） |

### Pipeline manifest 片段（cinematic 示例）

`pipeline_defs/cinematic.yaml` 每个 stage 声明：

- `skill`：对应 `skills/pipelines/cinematic/*-director.md`
- `required_artifacts_in` / `produces`：阶段输入输出契约
- `tools_available`：本阶段可调工具名
- `checkpoint_required` / `human_approval_default`：门禁
- `review_focus` / `success_criteria`：自审与验收标准

### Agent 被 Markdown 指挥的方式

1. **IDE 入口**：`CURSOR.md` → 指向 `AGENT_GUIDE.md`
2. **强制规则**：`.cursor/rules/openmontage.mdc` 在用户消息前注入「必须先读 AGENT_GUIDE」
3. **阶段技能**：manifest 的 `skill` 字段指向 `skills/pipelines/<name>/*-director.md`
4. **元技能**：`skills/meta/reviewer.md`、`skills/meta/checkpoint-protocol.md` 管自审与检查点

---

## B. Velora vs OpenMontage 对照表

| 维度 | OpenMontage | Velora（AI Studio） | 缺口 |
|------|-------------|---------------------|------|
| **编排器** | 外部 AI IDE（Cursor 等）读 AGENT_GUIDE | 后端 `agent_service.py` 内嵌 LLM + `SYSTEM_PROMPT` | Velora 编排逻辑与 prompt 耦合，不可外置给 IDE |
| **Pipeline 定义** | `pipeline_defs/*.yaml` + schema 校验 | `SYSTEM_PROMPT` 内 Markdown 表格 + `_PIPELINE_FORCE_STEPS` | 无 manifest；改阶段需同时改 Python 与前端 |
| **阶段技能** | `skills/pipelines/*/*-director.md` | 全写在 `SYSTEM_PROMPT`（~250 行） | 无 skills 目录；prompt 臃肿难维护 |
| **工具层** | `tools/tool_registry.py` 自动发现 50+ 工具 | 前端 `agentPipeline.js` switch/case 调画布 API | 无 tool registry；步骤与执行器硬绑定 |
| **门禁/审批** | checkpoint + `human_approval_default` + Backlot | `ask_user` + manual/auto 确认（`useCanvasAgent.js`） | 无结构化 checkpoint；无生产看板 |
| **状态持久化** | `projects/` checkpoint + artifacts JSON | 画布节点状态（React Flow） | 缺项目级流水线进度与版本历史 |
| **Preflight** | `provider_menu_summary()` 能力菜单 | 无统一能力发现 | Agent 不知 GPU/模型/工具可用性 |
| **前端技能 UI** | N/A（IDE 内编排） | `AgentPanel.jsx`「技能」`placeholder: true` | UI 入口未接通 |
| **短指令路由** | N/A | `agentCommandRouter.js` 恒返回 `null` | 「继续」必须走 LLM，无法本地直推 |

### Velora 现有 pipeline 步骤（已核实）

**主链 7 步**（`agentPipeline.js` L358–374 `switch`）：

1. `create_text_note`
2. `start_text_generation`
3. `generate_outline`
4. `generate_script_table`
5. `split_shot_beats`（可选）
6. `generate_storyboard`
7. `generate_video`

**库管理 2 步**：`manage_cast`、`manage_scene`

**后端镜像**：`agent_service.py` `SYSTEM_PROMPT` L38–52 阶段表 + `_PIPELINE_FORCE_STEPS` L351–358。

**编排入口**：`routers/agent.py` → `POST /api/agent/run` SSE → `run_agent_stream()`。

### 为何暂不选选项 2 / 3

| 选项 | 说明 | 暂不选原因 |
|------|------|------------|
| **选项 2：skills 目录** | Markdown 描述各 stage 规则 | 仍缺单一真相源；manifest 未抽离前 skills 会与 SYSTEM_PROMPT 三处重复 |
| **选项 3：tool registry** | 注册 step→执行器，打通技能按钮 | 依赖 step 名与前置条件先标准化；manifest 是前置 |

---

## C. 「可抄设计 / 不可抄代码」清单（AGPL-3.0）

OpenMontage 使用 **GNU AGPL-3.0**。网络服务场景下有 copyleft 义务；**禁止将源码整仓或大块复制进 Velora 闭源商业仓库**。

### 可抄（设计思路，须自写实现）

| 设计模式 | 来源参考 | Velora 自写方向 |
|----------|----------|-----------------|
| Pipeline manifest 结构 | `pipeline_defs/*.yaml` 的 stages / produces / gates | `backend/pipelines/velora_canvas.yaml` |
| Manifest 加载与校验 | `lib/pipeline_loader.py` 思路 | 自写 `pipeline_loader.py` + 简化 schema |
| Stage → skill 指针 | manifest `skill` 字段 | 后续选项 2；本轮仅预留字段 |
| Tool capability envelope | `support_envelope()` / `provider_menu_summary()` 概念 | 后续选项 3；描述 step 所需画布能力 |
| Checkpoint / 人工审批门 | `human_approval_default` + Backlot 可视化 | 对照现有 `ask_user`；长期可做轻量 checkpoint JSON |
| Agent 合约分层 | AGENT_GUIDE + stage director 分离 | SYSTEM_PROMPT 瘦身，阶段规则外置 |
| 单步推进 + 前置条件表 | cinematic.yaml `required_artifacts_in` | manifest `preconditions` 字段 |

### 不可抄（AGPL 代码与文本）

| 禁止项 | 原因 |
|--------|------|
| 复制 `tools/`、`pipeline_defs/`、`skills/` 全文进 AIStudio | AGPL 衍生作品义务 |
| 复制 `AGENT_GUIDE.md` / director skills 原文作 Velora prompt | 版权 + 产品语境不同 |
| 复制 `tool_registry.py`、`base_tool.py` 等 Python 实现 | 须自写等价模块 |
| 复制 `backlot/` UI 与 server | 须自写看板若需要 |
| 保留 OpenMontage 版权声明的「改个名」粘贴 | 合规风险 |

### Velora 产品路径备忘

OpenMontage 用 **Cursor 额度当编排器**；Velora 必须保留 **自有 LLM + GPU 画布** 产品路径。只学「三层分离」结构，不把 Cursor 编排模式照搬进生产。

---

## D. 最小切片提案 — **选项 1：Pipeline Manifest**

**选定：选项 1** — 用 YAML/JSON manifest 描述现有 9 个 `pipeline_step`，让 `agent_service` 从硬编码改为读 manifest 生成阶段表与前置条件。

### 目标

- **单一真相源**：阶段顺序、step 名、前置条件、是否可选 — 只维护一份 manifest
- **SYSTEM_PROMPT 瘦身**：阶段表由 manifest 动态注入，减少 Python/JS 双写
- **为选项 2/3 铺路**：manifest 可扩展 `skill`、`executor`、`capabilities` 字段

### 拟新增 manifest 结构（草案）

```yaml
# backend/pipelines/velora_canvas.yaml
name: velora_canvas_screenplay
version: "1.0"
description: Velora 画布宣传片/剧本主链

stages:
  - name: create_text_note
    order: 1
    phase: script_structure
    optional: false
    preconditions:
      - canvas_has_no_text_note_for_topic
    produces: [text_note]

  - name: start_text_generation
    order: 2
    phase: script_structure
    preconditions:
      - has_text_note
      - missing_or_regen_text_response
    produces: [text_response]

  # ... 其余 7 步同理 ...

  - name: split_shot_beats
    order: 5
    phase: storyboard
    optional: true
    preconditions:
      - script_table_ready
    produces: [beat_card]

  - name: manage_cast
    order: 8
    phase: library
    optional: true
    preconditions:
      - script_table_exists
    produces: [cast_library]

  - name: manage_scene
    order: 9
    phase: library
    optional: true
    preconditions:
      - script_table_exists
    produces: [scene_library]
```

### 不在本轮范围

- 不改 `agentPipeline.js` 执行逻辑（仅对齐 step 名常量，可选）
- 不实现 Backlot 等价物
- 不引入 Cursor 编排

---

## E. 下一轮实施步骤（给 Agent 用）

1. **新建 manifest 文件**  
   - 创建 `backend/pipelines/velora_canvas.yaml`（或 `.json`），完整声明 9 个 step + `phase` + `optional` + `preconditions` + `produces`  
   - 对照 `agent_service.py` L38–52 与 `agentPipeline.js` L358–374 逐条迁移

2. **实现 manifest 加载器**  
   - 新建 `backend/services/pipeline_manifest.py`：`load_pipeline(name)`、`get_stage_order()`、`get_stage_preconditions(step)`  
   - 参考 OpenMontage `lib/pipeline_loader.py` **思路**，自写实现（不复制代码）  
   - 可选：轻量 JSON Schema 校验

3. **改造 agent_service 读 manifest**  
   - `agent_service.py`：启动时加载 `velora_canvas` manifest  
   - 将 `SYSTEM_PROMPT` 内阶段一/二表格改为 `_build_pipeline_prompt_table(manifest)` 动态生成  
   - `_PIPELINE_FORCE_STEPS` 改为从 manifest `optional: false` 的 stage 名派生

4. **暴露 manifest 给前端（可选但推荐）**  
   - `schemas/agent_schemas.py`：新增 `PipelineManifestResponse`  
   - `routers/agent.py`：新增 `GET /api/agent/pipeline/{name}` 只读接口  
   - 前端 `agentCommandRouter.js` 的 `STEP_LABELS` 可从 API 拉取，减少硬编码

5. **保持 agentPipeline.js 执行器不变**  
   - `executeAgentPipelineStep` 的 `case` 分支暂保留  
   - 新增 `frontend/src/utils/canvas/pipelineManifest.js` 仅做 step 名/标签常量与 manifest 对齐校验（开发期 assert）

6. **单元测试**  
   - 新建 `backend/tests/test_pipeline_manifest.py`：  
     - manifest 缺 stage → 加载失败  
     - 未知 step 不在 manifest → `_enforce_single_step` 可检测  
     - 生成的 prompt 表包含全部 9 步

7. **手动回归**  
   - 新建宣传片项目 → 发送「继续」→ 验证 SSE 仍输出合法 `pipeline_step`  
   - 确认 `generate_outline` 前置条件与改前行为一致

8. **文档**  
   - 在 `docs/OPENMONTAGE_STUDY_NOTES.md` 末尾追加「选项 1 落地记录」小节（实施完成后）

### 预计改动文件

| 操作 | 路径 |
|------|------|
| 新建 | `backend/pipelines/velora_canvas.yaml` |
| 新建 | `backend/services/pipeline_manifest.py` |
| 修改 | `backend/services/agent_service.py` |
| 可选修改 | `backend/routers/agent.py`、`backend/schemas/agent_schemas.py` |
| 可选新建 | `frontend/src/utils/canvas/pipelineManifest.js` |
| 新建 | `backend/tests/test_pipeline_manifest.py` |

---

## F. 验收标准（3 条可测）

1. **Manifest 单一真相源**  
   - `velora_canvas.yaml` 包含全部 9 个 `pipeline_step`；`agent_service` 生成的 SYSTEM_PROMPT 阶段表与 manifest `stages` 一致（可通过单元测试比对字符串或 stage 名集合）。

2. **未知/非法 step 可观测失败**  
   - 当 manifest 中不存在的 step 被注入 actions 时，后端校验拒绝或日志告警（`test_pipeline_manifest.py` 覆盖）；加载损坏 manifest 时服务启动或首次请求返回明确错误。

3. **主链行为不退化**  
   - 手动测试：从空画布创建宣传片 → 至少成功推进 `create_text_note` → `start_text_generation` → `generate_outline` 三步，SSE `pipeline_step` 与改前一致，画布节点正确创建/连线。

---

## 附录：本地环境记录

| 项 | 结果 |
|----|------|
| 本地路径 | `/root/autodl-tmp/oss-study/OpenMontage`（约 88M，已落盘） |
| `git clone` 直连 GitHub | 失败（443 连接超时） |
| 落盘方式 | 镜像 tarball：`ghfast.top` → `OpenMontage-main.tar.gz` |
| 第 1 阶段结构核对 | 先 raw 拉取；后与本地目录一致 |
| Velora 业务代码 | 本阶段 **未修改** |

**GitHub 443 不通时的替代下载（不必 git clone）：**

```bash
mkdir -p /root/autodl-tmp/oss-study && cd /root/autodl-tmp/oss-study
curl -fsSL --connect-timeout 15 --max-time 300 \
  -o /tmp/OpenMontage-main.tar.gz \
  "https://ghfast.top/https://github.com/calesthio/OpenMontage/archive/refs/heads/main.tar.gz"
tar -xzf /tmp/OpenMontage-main.tar.gz
mv OpenMontage-main OpenMontage
```

---

## 选项 1 落地记录（2026-07-20）

### 改动文件

| 操作 | 路径 |
|------|------|
| 新建 | `backend/pipelines/velora_canvas.yaml` |
| 新建 | `backend/services/pipeline_manifest.py` |
| 修改 | `backend/services/agent_service.py` |
| 修改 | `backend/schemas/agent_schemas.py` |
| 修改 | `backend/routers/agent.py` |
| 修改 | `backend/requirements.txt`（+PyYAML） |
| 新建 | `backend/tests/test_pipeline_manifest.py` |
| 新建 | `frontend/src/utils/canvas/pipelineManifest.js` |
| 注释 | `frontend/src/utils/canvas/agentCommandRouter.js` |

### name 约定

- **加载名**：`load_pipeline("velora_canvas")` → 读 `backend/pipelines/velora_canvas.yaml`
- **逻辑名**：YAML 内 `name: velora_canvas_screenplay`
- **只读 API**：`GET /api/agent/pipeline/velora_canvas`

### 测试

```bash
cd backend && python -m pytest tests/test_pipeline_manifest.py -q
# 11 passed
```

### 已知限制

- `_PIPELINE_FORCE_STEPS` 现按 `optional: false` 派生，**不再包含** `split_shot_beats`（与改前行为差异：可选步不再被 `_reconcile_advance_pipeline_actions` 强推）
- 前端 `PIPELINE_STEP_NAMES` 仍为手写镜像，未接 API
- `agentPipeline.js` 执行器未改

---

## 选项 2 落地记录（2026-07-20）

### 目标

把各 stage 执行细则外置为 markdown skills；manifest 用 `skill` 字段指向；`agent_service` 组装 prompt 时注入。阶段表仍由选项 1 manifest 负责。

### 改动文件

| 操作 | 路径 |
|------|------|
| 新建 | `backend/agent_skills/velora_canvas/*.md`（9 stage + `_shared.md`） |
| 修改 | `backend/pipelines/velora_canvas.yaml`（每 stage + `skill`，根级 `shared_skill`） |
| 修改 | `backend/services/pipeline_manifest.py`（`load_skill_text` / `build_skills_prompt_section`） |
| 修改 | `backend/services/agent_service.py`（注入 skills，瘦身 SYSTEM_PROMPT） |
| 修改 | `backend/schemas/agent_schemas.py`（`skill` / `shared_skill`） |
| 新建 | `backend/tests/test_agent_skills.py` |
| 修改 | `backend/scripts/_agent_manifest_handtest_probe.py`（禁 MOCK、429 重试、清槽） |

### Skills 目录

```text
backend/agent_skills/velora_canvas/
  _shared.md
  create_text_note.md
  start_text_generation.md
  generate_outline.md
  generate_script_table.md
  split_shot_beats.md
  generate_storyboard.md
  generate_video.md
  manage_cast.md
  manage_scene.md
```

### 测试

```bash
cd backend && python -m pytest tests/test_pipeline_manifest.py tests/test_agent_skills.py tests/test_g32_agent_tokens.py -q
# 19 passed
```

### 探针

```bash
python scripts/_agent_manifest_handtest_probe.py
# MANIFEST_HANDTEST=PASS
# text_generation_mode=real_completed（禁止 mock_fallback_429）
```

### AGPL

未复制 OpenMontage skills 原文；仅采用「一阶段一文件」结构，规则自写自迁。

---

## 选项 3 落地记录（2026-07-20）

### 目标

轻量 **tool registry**：step → `{executor, capabilities, ui_label, optional, phase, skill}`；manifest 为单一真相源延伸；前端 `agentPipeline` 由 switch 改为 registry 查找（语义不变）；AgentPanel「技能」从 API 列 stage，点击发引导文案经 Agent 编排（不直接 `executeAgentPipelineStep`）。

### 改动文件

| 操作 | 路径 |
|------|------|
| 修改 | `backend/pipelines/velora_canvas.yaml`（每 stage + `executor` / `capabilities` / `ui_label`） |
| 新建 | `backend/services/tool_registry.py`（自写；非 OM 源码） |
| 修改 | `backend/services/pipeline_manifest.py` / `schemas/agent_schemas.py` |
| 新建 | `backend/tests/test_tool_registry.py` |
| 新建 | `frontend/src/utils/canvas/toolRegistry.js` |
| 修改 | `frontend/src/utils/canvas/agentPipeline.js`、`pipelineManifest.js` |
| 修改 | `frontend/src/services/agentApi.js`（`getPipelineManifest`） |
| 修改 | `frontend/src/components/canvas/AgentPanel.jsx` / `.css`（技能菜单） |

### Envelope 示例

```json
{
  "pipeline": "velora_canvas_screenplay",
  "steps": ["create_text_note", "start_text_generation", "..."],
  "optional_steps": ["split_shot_beats", "manage_cast", "manage_scene"],
  "capabilities_union": ["api.screenplay.shots", "api.tasks.text", "canvas.nodes.create", "..."]
}
```

### 技能按钮行为

1. 「+」→「技能」→ `GET /api/agent/pipeline/velora_canvas`
2. 列表展示 `ui_label`（可选步标「可选」）
3. 点击某技能 → `sendMessage("请执行 pipeline 步骤：{name}（{ui_label}）")`，仍走 Agent 编排
4. 加载失败只显示错误文案，不崩面板

### 测试

```bash
cd backend && python -m pytest tests/test_pipeline_manifest.py tests/test_agent_skills.py tests/test_tool_registry.py tests/test_g32_agent_tokens.py -q
```

### AGPL

未复制 OpenMontage `tool_registry.py` / `tools/*`；只学「注册表 + capability envelope」思路。

---

*笔记版本：v4 | 选项 1–3：**已落地***
