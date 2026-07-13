# Prompt 调试 · 阶段六：Wan T2V（wan-2.6）

**日期**：2026-07-09  
**范围**：画布视频 `wan-2.6` 纯文生视频（无参考图）  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING  
**本轮状态**：**GPU 实测完成**（2026-07-10 · T1–T4 completed；shell 392838 exit 0）

---

## 1. 模型链路说明

| 层 | 路径 |
|----|------|
| API | `POST /api/tasks/video` · `model=wan-2.6` · 无 first/last frame |
| 解析 | `resolve_video_backend` → `wan` · `mode=text2video` |
| Builder / 提交 | `submit_wan_video_prompt`（T2V 分支） |
| Comfy 要点 | Wan 2.2 T2V UNET · 默认 fast=**4 步**；quality=8 步（有运镜建议 quality） |

相关：G31 运镜注入、G33/G36 `CameraMotionPicker`、`sampling_profile`。

---

## 2. L0–L4 观测字段

| 层 | 标签 | 关注字段 |
|----|------|----------|
| L0 | 环境 | 与 Hunyuan 错峰 |
| L1 | SUBMIT | `camera_move`、`shot_scale`、`sampling_profile`、`sound_note` |
| L2 | RECEIVED | `workflow_route=text2video` |
| L3 | TRANSLATED | video translate-only + suffix 后置 |
| L4 | WORKFLOW | steps（4/8）、运镜词是否进入 positive、分辨率 |

---

## 3. 用例矩阵 T1–T4

| 用例 | 语言 | preset | 负向 | 边界 |
|------|------|--------|------|------|
| **T1** | 中文 | 无 | 默认 | `sampling_profile=fast`（4 步） |
| **T2** | 中文 | cinematic | 显式 | `camera_move=push_in` + quality |
| **T3** | 英文 | 无 | 空 | 确认运镜词不被 L3 打乱 |
| **T4** | 中文 | documentary | 强负向 | `shot_scale=wide` + sound_note 混音 |

---

## 4. 预期行为

- 无参考图时走 T2V，不误入 i2v / flf2v
- fast：steps=4；quality 或有运镜：steps=8
- 运动幅度受 4 步限制；复杂运镜应升 quality

---

## 5. 已知风险

- **4 步运动**：动作可能偏弱或跳变
- 运镜词依赖 L3 不扩写破坏结构（阶段一/二已收紧）
- 与 Hunyuan / PuLID 同卡叠跑争显存

---

## 阶段六 gate（2026-07-10）

| 项 | 状态 |
|----|------|
| 框架文档 | ✅ |
| 探针脚本 | ✅ `backend/scripts/_prompt_debug_phase6_wan_t2v.py` |
| T1–T4 GPU 实测 | ✅ 全部 **completed**（`AIStudio_video_00054_`～`00057_.mp4`） |
| 与 Phase2/3 回归对照 | ✅ T2V 路由未误入 i2v/flf2v；T3 L3 长度不变；T4 L3 14→60（suffix/混音相关） |
| 日志 | `/root/autodl-tmp/logs/prompt_debug_phase6_wan_t2v.json` · `prompt_debug_phase6_run.log` |

| 用例 | 结果 | 备注 |
|------|------|------|
| T1 | completed | fast 4 步 |
| T2 | completed | push_in + quality |
| T3 | completed | 英文运镜；L4 steps=8 |
| T4 | completed | wide + sound_note；L4 steps=8 |
