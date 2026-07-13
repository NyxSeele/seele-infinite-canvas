# Prompt 调试 · 阶段二：Wan i2v

**日期**：2026-07-07  
**范围**：画布视频 `wan-i2v` 图生视频（L1→L4），含参考图双路径与 cinematic preset  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING，`duration=3`，`resolution=720P`，`ratio=16:9`

> **执行说明**：代码修复（疑点 A/C + L4 trace）在 GPU 跑批前已合入；V1–V4 为 **post-fix** 单次跑批（标签 `postfix`），无独立 pre-fix baseline。日志见 [`/root/autodl-tmp/logs/prompt_debug_phase2_postfix.json`](/root/autodl-tmp/logs/prompt_debug_phase2_postfix.json)。

---

## Step 1：三项疑点代码结论

### 疑点 A：运动描述前置在 L3 后是否成立 — **修复前高风险，修复后 PASS**

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 视频/图像是否同一翻译分支？ | **否**。图像中文走 translate-only；视频走 `VIDEO_SYSTEM_PROMPT` optimize（会扩写、重排） | **是**。`mode=="video"` + 中文同样优先 `translate_to_english(..., mode="video")` |
| 运动词序是否受保护？ | **否** | **是**。`VIDEO_TRANSLATE_PLAIN_SYSTEM` 约束镜头/运动描述句首、句号分句、不添加 smooth motion/cinematic |

**改动文件**：`backend/services/prompt.py`、`backend/comfyui/llm.py`

### 疑点 B：两条参考图路径 — **PASS（V3-retest 同图验收）**

数据流：`reference_image` URL → `resolve_image_reference_path` → base64 → `upload_image_base64` → workflow `LoadImage.inputs.image`

| 路径 | 用例 | 提交 | L4 `reference_filename` |
|------|------|------|---------------------------|
| `/api/view`（Flux 出图） | V1/V2 | 200 completed | `upload (2).png` |
| `/api/uploads/images/...` | V3（原）/ V4 | 200 completed | `upload (3).png`（原 V3 为随机 fixture 图） |
| `/api/uploads/images/...` | **V3-retest** | 200 completed | `upload (2).png`（与 V1 同 Flux 图） |

**原 V3 作废说明**：来源 B 曾用 `test_image.jpg`（picsum 512×288 爬山图），路径通但**内容干扰验收**，非 bug。

**V3-retest**（2026-07-07）：下载 V1 的 `ComfyUI_00024_.png` → `POST /api/upload/image` → 重跑 V3。L3/L4 与 V1 完全一致（`after_len=99`，`final_len=317`，同 positive/negative），成片为雨中胡同女人场景。双路径 **同图验收 PASS**。

### 疑点 C：cinematic suffix 注入时机 — **修复前中风险，修复后 PASS**

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| suffix 在 enrich 之后？ | 是，且在 **L3 之前** 注入 | suffix 在 **L3 之后** 追加到 `positive` |
| L3 会处理 suffix？ | **会**（整段含 cinematic 英文 suffix 送入 optimize） | **否**。L3 仅翻译运动描述；`after_final` = 翻译 + suffix |
| V1 L2 `prompt_len` vs V4 | 修复前可能相同或混乱 | V1/V3 L2=22（纯中文）；V1 `final_len=317` vs V4 `final_len=99` |

**改动文件**：`backend/routers/tasks.py` `canvas_video_task`

---

## Step 2：测试用例与 API 适配

| 草案字段 | 实际字段 |
|----------|----------|
| `image_url` | `reference_image` |
| `num_frames` / `fps` | `duration`（wan-i2v：**3 或 5** 秒，本次用 3） |
| — | `resolution: 720P`，`ratio: 16:9`，必填 `node_id` |
| `POST /api/uploads` | `POST /api/upload/image` |

| 用例 | prompt | 参考图 | preset |
|------|--------|--------|--------|
| V1 | 中文运动描述 | 来源 A `/api/view` | cinematic |
| V2 | 英文运动描述 | 来源 A | cinematic |
| V3 | 同 V1 | 来源 B `/api/uploads` | cinematic |
| V4 | 同 V1 | 来源 B | 无 preset |

中文 prompt：`镜头缓缓后拉，女人转身离开，雨水打在青石板上`

脚本：[`backend/scripts/_prompt_debug_phase2.py`](backend/scripts/_prompt_debug_phase2.py)

---

## Step 3：L4 Trace 提取增强

`extract_workflow_trace`（`backend/trace_bus.py`）已补充：

- 双 `CLIPTextEncode` → `positive_prompt` / `negative_prompt`
- `LoadImage.inputs.image` → `reference_filename`
- `WanImageToVideo` → `width` / `height` / `num_frames`
- `KSamplerAdvanced` → `steps` / `cfg`
- `workflow_mode`: `image2video`

L4 日志行现含 `trace_id`、`task_type`、`duration`。

---

## Step 4：问题定位矩阵（post-fix 实测）

| 检查项 | 判定 | 证据 |
|--------|------|------|
| 运动词在句首 | **PASS** | V1 L4 positive 以 `The camera slowly pulls back.` 开头；V2 以 `camera slowly pulls back` 开头 |
| 参考图双路径 | **PASS** | V3-retest 同 Flux 图经 uploads 路径；L4 与 V1 一致 |
| cinematic suffix | **PASS** | V1 L2 `prompt_len=22`（无 suffix）；L4 含 `photorealistic, cinematic photography, 35mm film…`；V4 L4 无 cinematic 词 |
| negative 模板 | **PASS** | V4 negative = `worst quality, inconsistent motion, blurry, jittery, distorted`；V1/V3 为 cinematic 负向模板 |

---

## Step 5：V1–V4 Trace 对比表（post-fix）

### V1：中文 + `/api/view` + cinematic

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L1 | SUBMIT | 镜头缓缓后拉，女人转身离开，雨水打在青石板上 |
| L2 | RECEIVED | prompt_len=22，preset=cinematic |
| L3 | before_len / after_len / final_len | 22 → 99 → **317**（suffix 在 L3 后追加） |
| L3 | after（翻译段） | The camera slowly pulls back. The woman turns and walks away. Rain falls on the bluestone pavement. |
| L4 | positive | 上句 + `, photorealistic, cinematic photography, 35mm film, natural lighting, film grain…` |
| L4 | negative | anime, cartoon, illustration…（cinematic 负向） |
| L4 | steps/frames | steps=4，cfg=1.0，1280×720，frames=73 |
| — | reference | `upload (2).png` |
| — | result | `AIStudio_video_00008_.mp4` |

### V2：英文 + `/api/view` + cinematic

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L1 | SUBMIT | camera slowly pulls back, woman turns and walks away, rain on cobblestones |
| L2 | RECEIVED | prompt_len=74，preset=cinematic |
| L3 | before/after | 74 → 74（optimized=False，英文跳过翻译） |
| L3 | final_len | 292 |
| L4 | positive | 原英文运动描述 + cinematic suffix |
| L4 | negative | cinematic 负向 + WAN 默认负向合并 |
| — | result | `AIStudio_video_00009_.mp4` |

### V3：中文 + `/api/uploads` + cinematic（原跑批，**测试图干扰，仅供参考**）

与 V1 L3/L4 prompt 结构一致，但参考图为 picsum `test_image.jpg`（爬山场景），成片内容不可用于路径对比。result `AIStudio_video_00010_.mp4`。

### V3-retest：中文 + `/api/uploads`（V1 同图）+ cinematic

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L1 | SUBMIT | 镜头缓缓后拉，女人转身离开，雨水打在青石板上 |
| L2 | RECEIVED | prompt_len=22，preset=cinematic |
| L3 | before / after / final_len | 22 → 99 → **317**（与 V1 一致） |
| L4 | positive / negative | 与 V1 **完全相同** |
| L4 | steps/frames | steps=4，cfg=1.0，1280×720，frames=73 |
| — | reference | `upload (2).png` |
| — | result | `AIStudio_video_00012_.mp4`（`/tmp/v3_retest_result.mp4`） |

日志：[`prompt_debug_v3_retest.json`](/root/autodl-tmp/logs/prompt_debug_v3_retest.json)

### V4：中文 + `/api/uploads` + 无 preset

| 层 | 标签 | 内容摘要 |
|----|------|----------|
| L2 | RECEIVED | prompt_len=22，preset=None |
| L3 | final_len | **99**（仅翻译，无 suffix） |
| L4 | positive | The camera slowly pulls back. The woman turns and walks away. Rain falls on the bluestone pavement. |
| L4 | negative | worst quality, inconsistent motion, blurry, jittery, distorted |
| — | result | `AIStudio_video_00011_.mp4` |

---

## Step 5：修复 diff 摘要

| 文件 | 变更 |
|------|------|
| `backend/comfyui/llm.py` | 新增 `VIDEO_TRANSLATE_PLAIN_SYSTEM`；`translate_to_english(..., mode)` 按 image/video 选 system prompt |
| `backend/services/prompt.py` | `mode=="video"` + 中文优先 translate-only（镜像 image 分支） |
| `backend/routers/tasks.py` | `canvas_video_task`：移除 L2 前 `pos_suffix` 注入；L3 后追加 suffix；L3 trace 增加 `after` / `after_final` / `final_len` |
| `backend/trace_bus.py` | Wan i2v 完整 L4 字段（双 CLIP、LoadImage、WanImageToVideo、KSamplerAdvanced） |
| `backend/scripts/_prompt_debug_phase2.py` | 阶段二探针；`v3-retest` 模式；来源 B 改为上传 Flux 同图（移除 picsum fixture） |

---

## Step 6：视频质量主观评估

| 用例 | 运动流畅度 | 参考图一致性 | cinematic 风格 | 备注 |
|------|------------|--------------|----------------|------|
| V1 | 跟焦跟随 | 雨中胡同女人 | 有 | 中文输入 → 镜头跟随女人走（跟焦运动）；`/tmp/v1_result.mp4` |
| V2 | 后拉更符合意图 | 雨中胡同女人 | 有 | 英文输入 → 镜头固定、女人走远（后拉）；`/tmp/v2_result.mp4` |
| V3（原） | — | **爬山场景（fixture 干扰）** | — | 非 bug，测试图选错；作废 |
| V3-retest | 与 V1 相近 | 雨中胡同女人 | 有 | 同图 uploads 路径验收 PASS；`/tmp/v3_retest_result.mp4` |
| V4 | — | — | 无 preset | postfix 已跑 `AIStudio_video_00011_.mp4`，未主观观看，不影响 gate |

### V1 vs V2 结论（主观 + trace）

- **L3 翻译质量够用**：`镜头缓缓后拉，女人转身离开` → `The camera slowly pulls back. The woman turns and walks away.` 语义正确。
- **运动差异来自 Wan 模型解读**，非翻译失真：V1 跟焦 vs V2 后拉；`pulls back` + `woman walks away` 组合在 4-step 加速采样下模型敏感度有限。
- **V2 英文 prompt 对「缓缓后拉」意图更清晰**，属模型层行为，非 prompt 管线 bug。

---

## Step 7：回归

```bash
cd /root/autodl-tmp/AIStudio/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```

**结果**：**61 passed**

---

## 阶段三前置检查

| 项 | 状态 |
|----|------|
| Flux + i2v 双链路 trace 可观测 | ✅ L2/L3/L4 + `reference_filename` / frames / steps |
| 视频 L3 运动词稳定 | ✅ 中文翻译句首为镜头运动；suffix 不干扰 L3 |
| 双参考图路径 PASS | ✅ V3-retest：同 Flux 图经 `/api/view` 与 `/api/uploads` 均 completed，L4 与 V1 一致 |

**阶段二 gate 已关闭，可进阶段三（分镜表多镜）。**

**建议阶段三关注点**：分镜表多镜承接时 `reference_image` 来源切换、mention 注入与 L3 批量一致性。
