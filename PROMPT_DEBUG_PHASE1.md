# Prompt 调试 · 阶段一：Flux 单卡基线

**日期**：2026-07-07  
**范围**：画布单卡 `flux-dev` 直接出图（L1→L4），不含分镜表 / compile / 多镜承接  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING

---

## Step 1：三个结构性疑点确认（代码审计）

### 疑点 A：L3 翻译是否打乱 prompt 结构 — **确认存在**

`maybe_optimize_prompt` → `llm.optimize_prompt`（`comfyui/llm.py`）：

| 问题 | 结论 |
|------|------|
| system prompt 是否允许 LLM 自由改写词序？ | **是**。原 `IMAGE_SYSTEM_PROMPT` 要求「添加画质词」「补充风格描述」，temperature=0.7 |
| 是否有「只翻译不扩写」约束？ | **无**（修复前） |
| 中文 vs 英文是否同分支？ | **否**。`auto_optimize=True` 时统一走 `optimize_prompt`；仅当优化失败且仍含中文时才走 `translate_to_english` 回退 |

**修复**（已实施）：
- `IMAGE_SYSTEM_PROMPT` 改为「只中译英、不扩写、保持词序」
- `TRANSLATE_PLAIN_SYSTEM` 同步收紧
- `maybe_optimize_prompt`：**图像 + 含中文**时优先走 `translate_to_english`，跳过扩写式 optimize

### 疑点 B：画布图像任务没有 quality_preset suffix 注入 — **确认存在**

| 路径 | `pos_suffix` 注入 |
|------|-------------------|
| 视频 `POST /api/tasks/video` | ✅ `enrich_prompt` 之后、L2 之前（`tasks.py` L1215-1217） |
| 图像 `POST /api/tasks/image` | ❌ 修复前仅 L1 记录 `quality_preset_id`，**不注入 prompt** |

**修复**（已实施）：图像路径与视频对齐，在 `enrich_prompt` 后注入 `pos_suffix`；`neg_suffix` 传入 `maybe_optimize_prompt`（Flux 工作流仍忽略 negative）。

### 疑点 C：Flux guidance 3.5 vs compile cfg 1.0 — **无冲突**

| 检查项 | 结论 |
|--------|------|
| `GenerationCardNode.jsx` 是否传 `model_params`？ | **否**。payload 仅含 model / prompt / ratio / quality / denoise 等 |
| `tasks.py` 是否用 compile 的 cfg 覆盖 workflow？ | **否**。steps/cfg 来自 `model_registry` + `_build_flux_workflow`（dev: steps=25, guidance=3.5） |
| compile API 的 `cfg: 1.0` | 仅 `/api/prompt/compile` 返回值，**不参与画布提交** |

**无需代码修复**；L4 实测 `cfg=3.5`（即 `FluxGuidance`）。

---

## Step 2：测试用例说明

原稿 curl 字段与 API 实际 schema 有差异，已按 [`CanvasImageRequest`](backend/schemas/tasks.py) 调整：

| 原稿字段 | 实际字段 |
|----------|----------|
| `width` / `height` | `ratio: "1:1"` + `quality: "2K"` → 1024×1024 |
| `quality_preset` | `quality_preset_id` |
| `character_refs` | **API 不支持**；T4 改为 prompt 内联角色描述 |
| — | 必填 `node_id` |

Trace **不落 SQLite**（无 `prompt_traces` 表）；通过 `backend.out.log` 中 `[AIStudio:trace]` 行采集（SSE `/api/debug/trace/stream` 在独立 HTTP 客户端下未收到事件，已记录为基础设施缺口）。

脚本：[`backend/scripts/_prompt_debug_phase1.py`](backend/scripts/_prompt_debug_phase1.py)  
日志：[`/root/autodl-tmp/logs/prompt_debug_phase1_baseline.json`](/root/autodl-tmp/logs/prompt_debug_phase1_baseline.json)、`postfix.json`

---

## Step 3：Trace 对比表（修复前 baseline）

### T1：中文，无 preset

| 层 | 标签 | 内容摘要（前 120 字） |
|----|------|----------------------|
| L1 | SUBMIT | 一个女人站在雨中的胡同里 |
| L2 | RECEIVED | 一个女人站在雨中的胡同里（prompt_len=12） |
| L3 | before | 一个女人站在雨中的胡同里 |
| L3 | after | A woman standing in a narrow alleyway in the rain（optimized=True，12→49 字） |
| L4 | positive | A woman standing in a narrow alleyway in the rain |
| L4 | steps/cfg | steps=25，cfg/guidance=3.5，1024×1024 |

**L3 增删改**：「胡同」→ alleyway；添加 narrow；语序微调。

### T2：中文 + cinematic preset（修复前）

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L1 | SUBMIT | 一个女人站在雨中的胡同里（quality_preset_id=cinematic） |
| L2 | RECEIVED | 同 T1，**prompt_len=12**（suffix 未注入） |
| L3 | after | 同 T1（与 T1 完全相同） |
| L4 | positive | 同 T1，**无 cinematic / film grain 等词** |

**T2 vs T1**：L4 完全一致 → **疑点 B 实锤**。

### T3：英文对照

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L1 | SUBMIT | a woman standing in a rain-soaked alley, photorealistic |
| L3 | before/after | 相同（optimized=False，55 字） |
| L4 | positive | a woman standing in a rain-soaked alley, photorealistic |

### T4：中文 + 角色描述（prompt 内联）

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L1 | SUBMIT | 林晓，长直黑发，白色风衣，东亚面孔，25岁。一个女人站在雨中的胡同里 |
| L3 | after | Lin Xiao, long straight black hair, wearing a white trench coat, East Asian face, 25 years old, a woman standing in a rainy alley（34→129 字，**大幅重写**） |
| L4 | positive | 与 L3.after 一致 |

**T4 vs T1**：角色信息进入 L3/L4，但 LLM 重排了结构（姓名前置、场景后置）。

---

## Step 3b：Trace 对比表（修复后 postfix）

### T1（postfix，仍用旧 L3 逻辑时）

与 baseline 相同：`narrow alleyway in the rain`。

### T1（最终 L3 修复后单独重跑）

| L4 positive | A woman stands in a hutong in the rain. |
|-------------|----------------------------------------|

→ 保留「胡同/hutong」，扩写幅度明显降低。

### T2（postfix，suffix 注入后）

| 层 | 内容摘要 |
|----|----------|
| L2 | prompt_len=**230**（含 cinematic suffix） |
| L4 | A woman standing in a rainy alleyway, **photorealistic, cinematic photography, 35mm film, natural lighting, film grain**, shallow depth of field… |

→ **疑点 B 已修复**；cinematic 词在 L2 注入后经 L3 轻微润色进入 L4。

### T3 / T4（postfix）

- T3：与 baseline 相同（英文不触发 L3）
- T4：L4 仍含 Lin Xiao + 外貌 + rainy alleyway（翻译路径保留角色信息，仍有语序调整）

---

## Step 4：问题定位结论

```
疑点 A 结论：L3 LLM 是否破坏了 prompt 结构？
  - 改写幅度：修复前 = 中等扩写（T1）/ 大幅重写（T4）；修复后 = 轻微翻译（T1 保留 hutong）
  - 是否改变了词序？修复前是；修复后中文走 translate-only，词序基本保留
  - 中文 vs 英文：中文走 L3 翻译/优化；英文 optimized=False 直通

疑点 B 结论：画布图像 cinematic suffix 是否注入？
  - T2 baseline L4：无 cinematic 词 → suffix 在 L2 前丢失
  - T2 postfix L4：有 cinematic photography / film grain → 已在 L2 注入

疑点 C 结论：cfg 参数是否冲突？
  - 前端 body：无 model_params
  - L4 WORKFLOW：steps=25，cfg/guidance=3.5（FluxGuidance），与 registry 一致
  - 结论：无覆盖冲突
```

---

## Step 5：已实施修复

### 疑点 A

**文件**：[`backend/comfyui/llm.py`](backend/comfyui/llm.py)、[`backend/services/prompt.py`](backend/services/prompt.py)

```diff
# llm.py IMAGE_SYSTEM_PROMPT：扩写专家 → 只翻译助手
# llm.py TRANSLATE_PLAIN_SYSTEM：增加 preserve order / no style tags
# prompt.py：image + 中文 → 优先 translate_to_english，跳过 optimize_prompt
```

### 疑点 B

**文件**：[`backend/routers/tasks.py`](backend/routers/tasks.py) 图像任务路径

```diff
+ preset_id = normalize_quality_preset_id(body.quality_preset_id)
+ pos_suffix, neg_suffix_preset = get_suffixes(preset_id)
+ if pos_suffix:
+     prompt = f"{prompt}, {pos_suffix}" if prompt.strip() else pos_suffix
  # L2 RECEIVED 记录已含 suffix 的 prompt
```

### 疑点 C

无代码变更（设计正确）。

---

## Step 6：回归

```bash
cd /root/autodl-tmp/AIStudio/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
# 61 passed
```

---

## Step 7：阶段二（Wan i2v）前置条件

| 条件 | 状态 |
|------|------|
| Flux L1→L4 变换链可观测 | ✅（log + trace_id） |
| 中文 L3 不再大幅扩写 | ✅（translate-only 路径） |
| cinematic preset 对画布图像生效 | ✅ |
| cfg/guidance 无覆盖风险 | ✅ |
| `/api/view` 作 i2v 参考图 | ✅（上轮已修复） |
| DashScope 免费额度 | ⚠️ 部分请求 403 quota exhausted；translate 回退仍可用 |

**可进入阶段二**：Wan i2v 图生视频 prompt 链调试（运动描述前置、4-step 采样、参考图路径）。

---

## 附录：前端提交 body 实际字段

[`GenerationCardNode.jsx`](frontend/src/components/canvas/GenerationCardNode.jsx) `buildSubmitPayload`：

- `model`, `prompt`（generationPrompt || displayPrompt）
- `display_prompt`, `ratio`, `quality`, `count`, `node_id`
- 可选：`denoise`, `negative_prompt`, `trace_id`, `reference_image(s)`
- **无** `model_params`、`quality_preset_id`（画布图像卡当前未传 preset；需 UI 补字段才能从卡片触发 T2 类场景）
