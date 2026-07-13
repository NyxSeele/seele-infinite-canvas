# Prompt 调试 · 阶段五：LTX2 fp4 T2V（含音频开关）

**日期**：2026-07-09  
**范围**：画布视频 `ltx2-fp4` 文生视频；`audio=True/False` 分支  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING  
**本轮状态**：**GPU 实测完成**（2026-07-10 · T1–T4 completed）

---

## 1. 模型链路说明

| 层 | 路径 |
|----|------|
| API | `POST /api/tasks/video` · `model=ltx2-fp4` · `audio` |
| 解析 | `resolve_video_backend` → `ltx2` |
| Builder | `build_ltx2_fp4_t2v_workflow(..., audio=)` |
| 提交 | `submit_ltx2_video_prompt` |
| Comfy 要点 | LTX-2 fp4 checkpoint · Gemma encoder · `CreateVideo` ± AV 节点 |

结构探针已有：[`backend/scripts/_g38_audio_switch_probe.py`](backend/scripts/_g38_audio_switch_probe.py)。

---

## 2. L0–L4 观测字段

| 层 | 标签 | 关注字段 |
|----|------|----------|
| L0 | 环境 | 勿与 PuLID 同载 24GB |
| L1 | SUBMIT | `audio`、`duration`、`ratio`、`resolution` |
| L2 | RECEIVED | `video_backend=ltx2` |
| L3 | TRANSLATED | video 中译英 |
| L4 | WORKFLOW | `audio` 开关；AV 节点是否剥离；fps / length |

---

## 3. 用例矩阵 T1–T4

| 用例 | 语言 | preset | 负向 | 边界 |
|------|------|--------|------|------|
| **T1** | 中文 | 无 | 默认 | `audio=True` |
| **T2** | 中文 | cinematic | 显式 | `audio=False`（无 AV 节点） |
| **T3** | 英文 | 无 | 空 | 确认 CreateVideo.audio 接线 |
| **T4** | 中文 | 无 | 强负向 | 与 G39：`ltx2` **跳过** sound_note 后混音 |

---

## 4. 预期行为

- `audio=True`：保留 `LTXVAudioVAE*` / `LTXVConcatAVLatent`；`CreateVideo.audio` 有输入
- `audio=False`：剥离音频分支；`CreateVideo.audio is None`
- 端到端 MP4 仍待 GPU smoke

---

## 5. 已知风险

- **与 PuLID 同载**：24GB 易 OOM
- 权重/节点版本漂移会导致结构探针失败
- 自带音频时勿再叠 G39 AudioGen（代码已跳过 ltx2）

---

## 阶段五 gate（2026-07-10）

| 项 | 状态 |
|----|------|
| 框架文档 | ✅ |
| audio 结构探针 | ✅（G38） |
| 探针脚本 | ✅ `backend/scripts/_prompt_debug_phase5_ltx2.py` |
| T1–T4 端到端 MP4 | ✅ 全部 **completed**（`LTX-2_00003_`～`00006_.mp4`） |
| 日志 | `/root/autodl-tmp/logs/prompt_debug_phase5_ltx2.json` · `prompt_debug_phase5_run.log` |

**说明**：覆盖 `audio=True/False` 与 ltx2 跳过 G39 `sound_note` 后混音路径。
