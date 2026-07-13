# Prompt 调试 · 阶段三：首尾帧 FLF2V

**日期**：2026-07-07  
**范围**：画布视频 `generation_mode=keyframe` + `first_frame` / `last_frame` → Wan 2.2 **FLF2V**（`WanFirstLastFrameToVideo` + i2v UNET）  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING，`duration=3`，`720P`，`16:9`

---

## Step 0：实现摘要

| 组件 | 变更 |
|------|------|
| [`backend/comfyui/client.py`](backend/comfyui/client.py) | 新增 `build_wan_flf2v_workflow`；`submit_wan_video_prompt` 支持 `mode=flf2v` + 双图 base64 |
| [`backend/routers/tasks.py`](backend/routers/tasks.py) | keyframe 双帧 → `flf2v`；仅首帧 → `image2video`；仅尾帧 → 400；L1/L2 trace 增帧字段与 `workflow_route` |
| [`backend/trace_bus.py`](backend/trace_bus.py) | L4：`workflow_mode=flf2v`，`start_reference_filename` / `end_reference_filename` |
| [`frontend/.../VideoGenerationNode.jsx`](frontend/src/components/canvas/VideoGenerationNode.jsx) | 双帧 keyframe 自动 `wan-i2v`；提交带 `trace_id` |
| [`backend/scripts/_prompt_debug_phase3_keyframe.py`](backend/scripts/_prompt_debug_phase3_keyframe.py) | GPU 探针 K1–K4 |

**未接入**：`wan2.2_fun_inpaint_*`（留作后续增强）。

---

## Step 1：路由矩阵

| 条件 | `workflow_route` | ComfyUI |
|------|------------------|---------|
| `keyframe` + `first_frame` + `last_frame` | `flf2v` | `WanFirstLastFrameToVideo` |
| `first_frame` 或 `reference_image`（无 last） | `image2video` | `WanImageToVideo` |
| 仅 `last_frame` | — | **400** 首尾帧模式需要首帧图片 |
| 无参考图 | `text2video` | Wan T2V |
| `freeref` + `reference_images` | `image2video`（首图） | 不变 |

---

## Step 2：K1–K4 GPU 结果

日志：[`/root/autodl-tmp/logs/prompt_debug_phase3_keyframe.json`](/root/autodl-tmp/logs/prompt_debug_phase3_keyframe.json)

| 用例 | 首帧 | 尾帧 | 状态 | L2 route | L4 mode | 结果 |
|------|------|------|------|----------|---------|------|
| K1 | `/api/view` A | `/api/view` B | **completed** | flf2v | flf2v | `AIStudio_video_00013_.mp4` |
| K2 | `/api/view` A | `/api/uploads` B | **completed** | flf2v | flf2v | `AIStudio_video_00014_.mp4` |
| K3 | `/api/view` A | 无 | **completed** | image2video | image2video | `AIStudio_video_00015_.mp4` |
| K4 | A | A（同图） | **completed**（补跑） | flf2v | flf2v | `AIStudio_video_00016_.mp4` |

补跑日志：[`prompt_debug_phase3_k4.json`](/root/autodl-tmp/logs/prompt_debug_phase3_k4.json)（testuser 配额已重置为 0/100 后执行）

### K1 FLF2V trace 摘要

| 层 | 内容 |
|----|------|
| L2 | `workflow_route=flf2v` |
| L3 | 22 → 99 → 317（与阶段二 i2v 一致） |
| L4 | `start_reference_filename=upload (4).png`，`end_reference_filename=upload (5).png` |
| L4 | steps=4，1280×720，frames=73 |

### K3 i2v 回归

- L2 `workflow_route=image2video`
- L4 `workflow_mode=image2video`，单 `reference_filename=upload (4).png`
- 证明仅首帧时仍走阶段二 i2v 链路，无回归。

### K4 同图首尾 FLF2V（补跑 2026-07-07）

- **status**：completed
- L2 `workflow_route=flf2v`
- L4 `start_reference_filename` = `end_reference_filename` = `upload (6).png`（同图双帧）
- 成片：`AIStudio_video_00016_.mp4`

### K4 原批次说明（已解决）

首次全批时 testuser 视频配额 **10/10 用尽** 导致 429；已 `reset_quota` 并将 `video_limit` 提至 **100**。探针账号说明见 [`backend/docs/PROBE_ACCOUNTS.md`](backend/docs/PROBE_ACCOUNTS.md)。

---

## Step 3：Prompt Trace 字段（PT）

| 层 | 新增/强化字段 |
|----|----------------|
| L1 | `generation_mode`，`first_frame`，`last_frame`（有/无） |
| L2 | `workflow_route`：`flf2v` \| `image2video` \| `text2video` |
| L3 | 复用阶段二（video 中文 translate-only + suffix 后置） |
| L4 | `workflow_mode`，`start_reference_filename`，`end_reference_filename` |

探针用法：

```bash
cd /root/autodl-tmp/AIStudio/backend
.venv/bin/python scripts/_prompt_debug_phase3_keyframe.py
```

---

## Step 4：主观质量（待填写）

| 用例 | 首尾过渡 | 场景一致性 | 运动符合 prompt | 备注 |
|------|----------|------------|-----------------|------|
| K1 | | | | FLF2V 双 view 路径 |
| K2 | | | | 尾帧 uploads 路径 |
| K3 | | | | i2v 单帧回归 |
| K4 | | | | 同图首尾 FLF2V；`AIStudio_video_00016_.mp4` |

---

## Step 5：回归

```bash
cd /root/autodl-tmp/AIStudio/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```

**结果**：**64 passed**（含 `tests/test_wan_flf2v.py` 3 例）

---

## 阶段三 gate

| 项 | 状态 |
|----|------|
| 首尾帧 API → ComfyUI FLF2V | ✅ K1/K2 completed |
| 单帧 i2v 回归 | ✅ K3 image2video |
| PT L1–L4 可观测 | ✅ workflow_route + 双 reference |
| fun_inpaint | ⏳ 未接入（非本期） |

**可进入分镜表多镜承接**（K1–K4 均已 GPU completed）。

探针账号与团队：`backend/docs/PROBE_ACCOUNTS.md`
