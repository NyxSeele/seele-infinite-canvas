# Prompt 调试 · 阶段四：HunyuanVideo T2V

**日期**：2026-07-09  
**范围**：画布视频 `hunyuan-video` 文生视频（L0→L4），720p / steps=50  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING  
**本轮状态**：**GPU 实测完成**（2026-07-10 · T1–T4 completed）

---

## 1. 模型链路说明

| 层 | 路径 |
|----|------|
| API | `POST /api/tasks/video` · `model=hunyuan-video` |
| 解析 | `resolve_video_backend` → `hunyuan` |
| Builder | `build_hunyuan_video_workflow`（`comfyui/client.py`） |
| 提交 | `submit_hunyuan_video_prompt` |
| Comfy 要点 | HunyuanVideo checkpoint · 默认 **1280×720** · **steps=50** · T2V（无首尾帧） |

**注意**：勿把 `start_image_b64` / `end_image_b64` 传入 Hunyuan submit（仅显式 kwargs）。

---

## 2. L0–L4 观测字段

| 层 | 标签 | 关注字段 |
|----|------|----------|
| L0 | 环境 | `AGENT_MOCK_GENERATION`、显存空闲、是否与 Wan/PuLID 同卡 |
| L1 | SUBMIT | `model`、`prompt`、`ratio`、`resolution`、`duration`、`sound_note` |
| L2 | RECEIVED | `video_backend=hunyuan`、`workflow_route=text2video` |
| L3 | TRANSLATED | 中译英前后长度；video translate-only |
| L4 | WORKFLOW | `steps`、`width/height`、checkpoint 名、seed |

---

## 3. 用例矩阵 T1–T4

| 用例 | 语言 | preset | 负向 | 边界 |
|------|------|--------|------|------|
| **T1** | 中文短句 | 无 | 默认 | 最短合法 duration |
| **T2** | 中文 | cinematic | 显式 negative | 720p + steps=50 |
| **T3** | 英文 | 无 | 空 negative | 确认 L3 不误扩写 |
| **T4** | 中文长描述 | documentary | 强负向 | 边界：超长 prompt / 高负载排队 |

---

## 4. 预期行为

- L2 `video_backend=hunyuan`；成片为 mp4
- L4 steps 默认 50；分辨率对齐 1280×720（或 registry 约定）
- 单条约 **1.5–2 小时**；显存峰值约 **22.5G**
- `sound_note` 非空时走 G39 后混音（非 ltx2）

---

## 5. 已知风险

- **时长与显存**：重负载；避免与 Wan / PuLID 同卡叠跑
- VAE tiled 告警可能出现，非致命
- 建议作为高级选项，勿作为默认 T2V

---

## 阶段四 gate（2026-07-10）

| 项 | 状态 |
|----|------|
| 框架文档 | ✅ |
| 探针脚本 | ✅ `backend/scripts/_prompt_debug_phase4_hunyuan.py` |
| T1–T4 GPU 实测 | ✅ 全部 **completed**（成片 `AIStudio_video_00050`～`00053.mp4`） |
| 日志 | `/root/autodl-tmp/logs/prompt_debug_phase4_hunyuan.json` · `prompt_debug_phase4_run.log` |

**说明**：本轮为轻量 Hunyuan 探针（`phase4_hunyuan_light`）；与全量 720p/50 步墙钟 ~109 分钟的 G35 smoke 互补。
