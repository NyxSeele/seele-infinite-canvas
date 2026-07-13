# 路线 A 收尾 + 路线 B 验收结果

最后更新：**2026-07-08**（AutoDL 4090 · admin 账号 · `AGENT_MOCK_GENERATION=false`）

---

## 路线 A：图像 preset 选择器

| 项 | 结果 |
|----|------|
| 实现 | [`CanvasPromptBar.jsx`](frontend/src/components/canvas/CanvasPromptBar.jsx) 图像顶栏加入 `VideoStylePicker`（`showUploadSection={false}`） |
| 数据绑定 | `onUpdate` → `image-gen.data.qualityPresetId`；[`useCanvasNodes.js`](frontend/src/hooks/canvas/useCanvasNodes.js) 生成时保留 preset |
| 提交链路 | 既有 `buildSubmitPayload` → `quality_preset_id` 无需改动 |
| pytest | **64 passed** |

**说明**：与视频卡一致，选中图像卡后在 PromptBar 顶栏可见画风选择器（非卡片本体）。

---

## 路线 B：代码变更摘要

| 变更 | 文件 |
|------|------|
| 批量出图串行等待 direct 完成 | [`useScriptTableGenerate.js`](frontend/src/hooks/canvas/useScriptTableGenerate.js) `waitForScriptTableDirectImage` + `runScriptTableGenerateAll` |
| 一键转视频 | 同上 `runScriptTableGenerateAllVideo` + [`ScriptTableNode.jsx`](frontend/src/components/canvas/ScriptTableNode.jsx) 工具栏按钮 |
| 视频 prompt 承接 | 复用 `image-gen.data.generationPrompt`（L0）+ `traceId` 串联 |
| VideoGenerationNode trace | [`VideoGenerationNode.jsx`](frontend/src/components/canvas/VideoGenerationNode.jsx) 优先 `data.traceId` |
| GPU 探针 | [`backend/scripts/_route_b_batch_probe.py`](backend/scripts/_route_b_batch_probe.py) |

---

## Step 3：三镜批量出图 trace 对比

探针场景：雨夜胡同 · 林晓（长直黑发，白色风衣）· `cinematic` · `continuityMode` + `visualContinuity`

| 镜号 | L0 主题/人物 | L0 承接 | 上一镜 img2img | L4 cinematic | 耗时 | 输出 |
|------|-------------|---------|----------------|--------------|------|------|
| 001 | ✅ 雨夜胡同 + 林晓外貌 | — | — | ✅ | 91.0s | `ComfyUI_00030_.png` |
| 002 | ✅ | ✅ `承接上一镜头` | ✅ | ✅ | 15.2s | `ComfyUI_00031_.png` |
| 003 | ✅ | ✅ | ✅ | ✅ | 15.2s | `ComfyUI_00032_.png` |

**L0 样例（002）**：

```
雨夜胡同，电影感叙事。主角林晓：长直黑发，白色风衣。，承接上一镜头：雨夜胡同，女人站在路灯下，女人缓缓转身，侧脸对镜, photorealistic, cinematic photography, ...
```

**L4 样例（002 图像）**：

```
Rainy night in a narrow alley. The woman stands under a streetlamp. She slowly turns her head. Her profile faces the camera. Lin Xiao: long straight black hair; white trench coat. ...
```

原始 JSON：[`/root/autodl-tmp/logs/route_b_batch_results.json`](/root/autodl-tmp/logs/route_b_batch_results.json)

---

## Step 4：三镜批量转视频 trace 对比

| 镜号 | 参考图 L4 | prompt 承接（中文 L0） | L4 cinematic | trace 串联 | 耗时 | 输出 |
|------|-----------|----------------------|--------------|------------|------|------|
| 001 | ✅ `upload (7).png` | —（首镜） | ✅ | ✅ 同 image trace | 147.2s | `AIStudio_video_00018_.mp4` |
| 002 | ✅ `upload (8).png` | ✅ `承接上一镜头` | ✅ | ✅ | 142.1s | `AIStudio_video_00019_.mp4` |
| 003 | ✅ `upload (9).png` | ✅ | ✅ | ✅ | 142.3s | `AIStudio_video_00020_.mp4` |

workflow_mode：**flf2v**（首尾同帧，与分镜表 direct lane 一致）

---

## 主观评估表（MP4 需人工观看填写）

| 镜号 | 运动流畅度 | 人物一致性 | 与上一镜衔接感 | cinematic 风格 | 备注 |
|------|----------|-----------|--------------|--------------|------|
| 001 | 待填 | 待填 | — | 待填 | 探针自动 PASS 技术指标 |
| 002 | 待填 | 待填 | 待填 | 待填 | L0/L4 承接词已 PASS |
| 003 | 待填 | 待填 | 待填 | 待填 | |

下载路径：各镜 `result_url` 见 `route_b_batch_results.json`（需 admin token + media ticket）。

---

## 发现的问题与修复

| 问题 | 处理 |
|------|------|
| 批量出图仅 `sleep(2s)` 不等待完成 | ✅ `waitForScriptTableDirectImage` |
| 无「一键转视频」 | ✅ `runScriptTableGenerateAllVideo` + UI |
| 视频丢失 L0 承接 | ✅ 复用 `generationPrompt` + `traceId` |
| 探针 `result` vs `result_url` 字段 | ✅ `task_result_url()` 辅助函数 |

**未修复（非阻塞）**：

- 镜 001 视频 L4 英文字面未含「承接」（首镜预期）

---

## L3 角色外貌保留 + Trace 可观测性（2026-07-08 二轮）

### 修复摘要

| 项 | 文件 | 说明 |
|----|------|------|
| 视频 L3 背影场景保留外貌 | [`backend/comfyui/llm.py`](backend/comfyui/llm.py) `VIDEO_TRANSLATE_PLAIN_SYSTEM` | 姓名/发型/服装必须完整保留，无论正面/侧面/背影 |
| compile 阶段 trace | [`backend/routers/prompt.py`](backend/routers/prompt.py) | `push_trace(0, "COMPILED")` + `studio_print` L0 COMPILED |
| build-shot 阶段日志 | 同上 | `studio_print` L0 BUILT：`trace_id / shot_number / character_refs_count / positive_len` |
| 前端 trace 串联 | [`promptCompileApi.js`](frontend/src/services/promptCompileApi.js)、[`useScriptTableGenerate.js`](frontend/src/hooks/canvas/useScriptTableGenerate.js) | `trace_id` 提前生成并贯穿 compile + build-shot |
| 探针对齐 UI | [`_route_b_batch_probe.py`](backend/scripts/_route_b_batch_probe.py) | 先 compile 再 build-shot；镜 003 视频 L4 外貌断言 |

### 镜 003 视频 L4（修复后）

背影场景 L4 `positive_prompt` 已含角色外貌词：

```
Rainy night in a hutong. Cinematic storytelling. Protagonist Lin Xiao: long straight black hair, white trench coat. Continuing from the previous shot: the woman slowly turns, her profile facing the mirror. Lin Xiao: long straight black hair, white trench coat. The woman walks into the rain. Her back gradually fades into the distance. ...
```

`l4_has_appearance`: **True**（Lin Xiao + black hair + trench coat）

### Trace grep 样例（`backend.out.log`）

```
[AIStudio:trace] L0 COMPILED trace_id=0f7f48c9-c4f1-4f4f-820b-9af3376b70a8 character_refs_count=1 positive_len=37
[AIStudio:trace] L0 BUILT trace_id=0f7f48c9-c4f1-4f4f-820b-9af3376b70a8 shot_number=3 character_refs_count=1 positive_len=301
[AIStudio:trace] L3 TRANSLATED trace_id=0f7f48c9-c4f1-4f4f-820b-9af3376b70a8 optimized=True ...
[AIStudio:trace] L4 WORKFLOW {... 'positive_prompt': 'Rainy night in a hutong. ... Lin Xiao: long straight black hair, white trench coat. ...'}
```

```bash
grep -E 'L0 COMPILED|L0 BUILT' /root/autodl-tmp/logs/backend.out.log | tail -10
```

### 二轮 GPU 探针结果

| 镜号 | 图像 | 视频 | L0 COMPILED | L4 外貌（视频） |
|------|------|------|-------------|----------------|
| 001 | ✅ `ComfyUI_00033_.png` | ✅ `AIStudio_video_00021_.mp4` | ✅ | ✅ |
| 002 | ✅ `ComfyUI_00034_.png` | ✅ `AIStudio_video_00022_.mp4` | ✅ | ✅ |
| 003 | ✅ `ComfyUI_00035_.png` | ✅ `AIStudio_video_00023_.mp4` | ✅ | ✅ |

- pytest：**65 passed**
- 探针技术指标：**PASS**（6/6 completed；003 视频 L4 外貌；三镜 L0 COMPILED 可见）
- 原始 JSON：[`route_b_batch_results.json`](/root/autodl-tmp/logs/route_b_batch_results.json)

---

## 回归

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
# 65 passed
```

GPU 探针：

```bash
AGENT_MOCK_GENERATION=false .venv/bin/python scripts/_route_b_batch_probe.py
# exit 0 · ~9.5 min（3 flux + 3 wan-i2v）
```

---

## 路线 C 前置条件（简要）

| 项 | 结论 |
|----|------|
| 分镜表 L0 `build-shot` 多镜承接 | ✅ 002/003 承接词 + 视觉参考上一镜 |
| 批量串行稳定性 | ✅ 6/6 task completed |
| Agent 自动生成分镜表 prompt 质量 | **待路线 C**：本探针为手工固定 3 镜文案；Agent `generate_script_table` 产出是否稳定需单独验收 |

---

## 复现命令

```bash
# 前端（路线 A/B UI）
cd frontend && /usr/bin/npm run build

# 服务
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf restart aistudio-backend nginx

# 路线 B GPU
cd backend
AGENT_MOCK_GENERATION=false .venv/bin/python scripts/_route_b_batch_probe.py
```
