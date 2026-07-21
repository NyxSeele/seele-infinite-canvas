# Agent 主链手测清单（Pipeline Manifest 回归）

> **给 Tester / 实习生**  
> **目的**：验证选项 1（Pipeline Manifest）落地后，画布 Agent 主链前三步行为不退化。  
> **环境**：生产公网 `https://velora.seele0420.cloud`（或团队给出的内网/本地地址）  
> **预计耗时**：15–25 分钟（仅前三步）；完整到分镜表约 30–45 分钟  
> **日期模板**：____年__月__日　测试人：________　结果：□ PASS　□ FAIL

---

## 0. 测前准备

### 0.1 账号

| 角色 | 用户名 | 密码 | 说明 |
|------|--------|------|------|
| 管理员（推荐） | `seele` | 问主程要（生产密码） | 权限全、不易配额卡死 |
| 备选探针 | `testuser` | 问主程 | 普通用户 |

> 不要用错环境账号。登录失败先刷新；连续失败可能触发登录限流，等几分钟再试。

### 0.2 浏览器

- Chrome / Edge 最新版  
- 打开 **开发者工具**（F12）→ **Network（网络）**  
- 勾选 **Preserve log（保留日志）**  
- 过滤框输入：`agent/run`（用来抓 SSE）

### 0.3 执行模式（很重要）

Agent 面板有两种模式：

| 模式 | 含义 | 本清单建议 |
|------|------|------------|
| **手动确认** | 每步完成后要点「采纳并继续」才往下走 | **必测（默认）** |
| **自动生成** | 确认后自动连跑多步 | 可选；易跳步难观察，本清单前三步先用手动 |

进入画布后打开 Agent 面板，确认当前是 **「手动确认」**。

### 0.4 本轮验收范围（必须）

只强制验收这三步（与开发交付一致）：

| 步序 | `pipeline_step` | 画布应出现 |
|------|-----------------|------------|
| 1 | `create_text_note` | 文本输入卡（text-note） |
| 2 | `start_text_generation` | 文本生成开始 → 出现/更新 text-response |
| 3 | `generate_outline` | 大纲节点（outline） |

**本轮不强制**：`generate_script_table`、出图、出视频、角色库（可作加分项）。

### 0.5 行为变更（测试时注意）

`split_shot_beats`（拆节拍）现在是 **可选步**，系统 **不会** 再强制纠偏去推这一步。  
→ 到分镜阶段时，允许跳过拆节拍直接出分镜图，**不算 Bug**。

---

## 1. 标准流程（主测：空画布宣传片 → 前三步）

### 步骤 A — 登录并新建空项目

1. 打开 `https://velora.seele0420.cloud`  
2. 用 `seele` 登录  
3. 进入 **工作区 / 项目列表**  
4. **新建画布项目**（空项目；不要导入旧剧本）  
5. 进入画布页面，确认画布基本为空（可有引导，但不应已有完整链路节点）

**记录**：项目名称 / URL：`________________________`

---

### 步骤 B — 打开 Agent，固定手动模式

1. 点击画布上的 **Agent 浮动按钮**（或侧栏 Agent）打开面板  
2. 确认执行模式 = **手动确认**  
3. 输入框可输入中文；先不要点技能（技能多为占位）

---

### 步骤 C — 发起宣传片需求（第 0 轮，可能出创意卡）

在 Agent 输入框发送（可直接复制）：

```text
帮我做一个 30 秒品牌宣传片，主题是重庆火锅，要有故事感，先给几个方向方案
```

**预期（二选一都算正常）**：

| 情况 | 现象 | Tester 操作 |
|------|------|-------------|
| **有创意卡片** | Agent 弹出多个方案选项（ask_user） | 点选 **某一个方案**（记住方案名），再等下一轮或点「采纳并继续」 |
| **直接落卡** | 无创意卡，直接开始建 text-note | 进入步骤 D 检查 |

**不要**在创意卡未选时反复狂点发送。

---

### 步骤 D — 验收第 1 步：`create_text_note`

**操作**：若停在「待确认」，点 **「采纳并继续」**；或发送：

```text
继续
```

**画布预期**：

- [ ] 出现一张 **文本输入卡**（text-note / 文本节点）  
- [ ] 卡片内容与主题相关（含火锅/重庆/宣传片意图）  
- [ ] 不是 outline，也不是分镜表

**Network 预期**（F12 → `agent/run` → EventStream / Response）：

- [ ] 响应里出现 `"type":"pipeline_step"`  
- [ ] 且 `"step":"create_text_note"`

**截图要求**：画布节点 + Network 里含 `create_text_note` 的一段（可打码 token）。

| 结果 | □ PASS　□ FAIL | 备注：____________ |

---

### 步骤 E — 验收第 2 步：`start_text_generation`

**前提**：text-note 已存在。

**操作**：发送：

```text
继续
```

若出现「采纳并继续」，先点它。

**画布预期**：

- [ ] 从 text-note **连出** 或旁边出现 **text-response / 剧本文本** 卡  
- [ ] 文本开始生成（loading / 流式 / 完成后有成段中文剧本或文案）  
- [ ] 等待生成 **完成**（不要在一半时点继续）

**Network 预期**：

- [ ] `"step":"start_text_generation"`

| 结果 | □ PASS　□ FAIL | 备注：____________ |

**常见正常慢**：LLM 生成可能要几十秒；转圈不算挂死。超过 **3 分钟** 仍无字 → 记 FAIL，截图 Agent 报错/日志。

---

### 步骤 F — 验收第 3 步：`generate_outline`

**前提**：text-response **已完成**（有完整正文，非空白）。

**操作**：发送：

```text
继续
```

**画布预期**：

- [ ] 出现 **大纲（outline）** 节点  
- [ ] 大纲含场景/结构条目（scenes 一类内容，非空）  
- [ ] 与 text-response 有连接关系或同属一条链路

**Network 预期**：

- [ ] `"step":"generate_outline"`

| 结果 | □ PASS　□ FAIL | 备注：____________ |

---

### 步骤 G — 本轮结论（主测）

| 检查项 | PASS/FAIL |
|--------|-----------|
| D `create_text_note` | |
| E `start_text_generation` | |
| F `generate_outline` | |
| **主测总评** | 三项皆 PASS → **主测 PASS**；任一项 FAIL → **主测 FAIL** |

主测 PASS 即可回复主程：「Manifest 前三步手测通过」。

---

## 2. 加分项（可选，有时间再做）

> 非本轮强制。做了请单独标注「加分项」。

### 2.1 生成分镜表

text-response + outline 都就绪后发「继续」：

- 预期：`generate_script_table`，画布出现 **分镜表（script_table）**，带多行镜头  
- Network：`"step":"generate_script_table"`

### 2.2 可选步不被强推

分镜表就绪后连续「继续」：

- **允许**：直接 `generate_storyboard`（出分镜图）  
- **允许**：不出现 `split_shot_beats`  
- **算 Bug**：系统反复纠偏、强制要求必须先拆节拍才能出图（与现设计不符）

### 2.3 Manifest API 冒烟（技术向）

登录后浏览器访问（或用主程提供的 token）：

```http
GET /api/agent/pipeline/velora_canvas
```

- 预期：200，JSON 里 `stages` 含 9 个 name（含 `create_text_note` … `manage_scene`）

---

## 3. 如何在 Network 里确认 `pipeline_step`（小白版）

1. F12 → Network  
2. 过滤 `agent/run`  
3. 点 Agent「发送」后出现的那条请求  
4. 看 **Response / EventStream / 预览**  
5. 搜索关键字：`pipeline_step`、`create_text_note`  

示例片段（示意）：

```json
{
  "type": "pipeline_step",
  "step": "create_text_note",
  "data": { "prompt": "...", "intent": "screenplay" }
}
```

若只能看到 UI、看不到 Network：至少用画布节点类型对照上表；并在报告里写「未抓到 SSE，仅 UI 验收」。

---

## 4. 失败时怎么报（请复制填空）

```text
【手测 FAIL】Pipeline Manifest 主链
- 测试人：
- 时间：
- 环境 URL：
- 账号：
- 失败步骤：D / E / F（圈一个）
- 预期：
- 实际：
- 截图：画布 + Agent 面板 +（如有）Network
- 是否可复现：是 / 否
- 额外信息：浏览器、是否手动模式、是否选了创意卡
```

发给主程或提 Issue；**不要自己改代码**。

---

## 5. 常见现象对照（别误报 Bug）

| 现象 | 是否 Bug | 说明 |
|------|----------|------|
| 第一次先出创意方案卡 | 否 | 正常；选一个再继续 |
| 输入很明确「3 个镜头」时跳过创意卡 | 否 | 产品规则允许直落 text-note |
| 手动模式每步要点「采纳并继续」 | 否 | 设计如此 |
| `split_shot_beats` 被跳过 | 否 | 现为 optional |
| text 生成转圈 1–2 分钟 | 否 | 等完成再「继续」 |
| 同时推进多镜出图/出视频 | 视情况 | 主链设计是单线程；乱序狂点可能导致异常，记操作步骤 |
| Cloudflare 1033 / 整站打不开 | 是（运维） | 不是 Manifest 问题，报给主程查 Tunnel |
| Agent 一直报错 / 401 | 是 | 登录过期或服务异常 |

---

## 6. 回传模板（PASS 时）

```text
【手测 PASS】Pipeline Manifest 主链前三步
- 测试人：
- 时间：
- 环境：https://velora.seele0420.cloud
- 项目名：
- D create_text_note：PASS（已截图）
- E start_text_generation：PASS
- F generate_outline：PASS
- 模式：手动确认
- 加分项（如有）：无 / 已做到 generate_script_table
```

---

## 7. 给主程的对照（Tester 可忽略）

| 项 | 值 |
|----|-----|
| Manifest | `backend/pipelines/velora_canvas.yaml` |
| API | `GET /api/agent/pipeline/velora_canvas` |
| 自动化 | `cd backend && python -m pytest tests/test_pipeline_manifest.py -q`（11 passed） |
| 本手测覆盖缺口 | 浏览器真实画布执行（探针无法覆盖 React Flow 落盘） |
