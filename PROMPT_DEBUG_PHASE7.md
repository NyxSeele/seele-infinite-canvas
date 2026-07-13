# Prompt 调试 · 阶段七：flux-pulid（有/无参考图）

**日期**：2026-07-09  
**范围**：画布图像 `flux-pulid`；有参考图 / 无参考图两条路径  
**环境**：`AGENT_MOCK_GENERATION=false`，ComfyUI + backend RUNNING  
**本轮状态**：**GPU/鉴权 + ReActor 换脸复测通过**（2026-07-10 · 已预置 `buffalo_l`；T2/T3 `use_reactor=True` completed）

---

## 1. 模型链路说明

| 层 | 路径 |
|----|------|
| API | `POST /api/tasks/image` · `model=flux-pulid` · 可选 `reference_image(s)` |
| 解析 | registry `flux-pulid` · PuLID 工作流 |
| Builder | ComfyUI PuLID / Flux 节点链（见 `client` / workflow 探针） |
| Comfy 要点 | 有参考图：身份条件注入；无参考图：退化为近似 flux 文生图或拒绝（以实现为准） |

G30 已闭环 phash / smoke；本阶段聚焦 **Prompt Trace** 与参考图鉴权。

---

## 2. L0–L4 观测字段

| 层 | 标签 | 关注字段 |
|----|------|----------|
| L0 | 环境 | 勿与 LTX2/Hunyuan 重负载同载 |
| L1 | SUBMIT | `reference_image` 有/无、`quality_preset_id`、`mentions` |
| L2 | RECEIVED | 参考图 URL 是否解析成功 |
| L3 | TRANSLATED | 图像中译英（translate-only） |
| L4 | WORKFLOW | PuLID 权重、guidance、是否加载参考图文件名 |

---

## 3. 用例矩阵 T1–T4

| 用例 | 语言 | preset | 负向 | 边界 |
|------|------|--------|------|------|
| **T1** | 中文 | 无 | 默认 | **无**参考图 |
| **T2** | 中文 | cinematic | 显式 | **有**参考图（`/api/view`） |
| **T3** | 英文 | 无 | 空 | 有参考图（`/api/uploads`） |
| **T4** | 中文 | 无 | 强负向 | 非法/无权限参考图 URL（鉴权失败） |

---

## 4. 预期行为

- 有合法参考图：身份一致性提升（对照 G30 phash）
- 无参考图：行为与产品约定一致（降级或 400）
- 非法 URL：400/403，不泄漏他用户输出

---

## 5. 已知风险

- **参考图鉴权**：`media_access` ticket / 归属校验失败会导致 403
- 与视频重负载同卡易 OOM
- L3 扩写可能削弱身份相关描述（应保持 translate-only）

---

## 阶段七 gate（2026-07-10）

| 项 | 状态 |
|----|------|
| 框架文档 | ✅ |
| 探针脚本 | ✅ `backend/scripts/_prompt_debug_phase7_pulid.py` |
| T1–T4 GPU / 鉴权实测 | ✅ 已跑完（见下表） |
| G40 接线（结构） | ✅ `use_reactor` + `ReActorFaceSwap`；`tests/test_reactor_g40.py`；`_g40_reactor_probe.py` PASS |
| 与 G30 phash 对照 | ⏳ 可选 |
| 日志 | `/root/autodl-tmp/logs/prompt_debug_phase7_pulid.json`（`phase7_pulid_buffalo_rerun`） |
| 离线权重 | ✅ `ComfyUI/models/insightface/models/buffalo_l/*.onnx`；脚本 `_download_g40_buffalo_l.sh` |

| 用例 | 结果 | 备注 |
|------|------|------|
| T1 | submit_failed（预期） | 无参考图 → `flux-pulid 需要角色正脸参考图` |
| T2 | **completed** | `use_reactor=True` → `ComfyUI_00066_.png` |
| T3 | **completed** | `use_reactor=True` → `ComfyUI_00067_.png` |
| T4 | submit_failed（预期） | 非法参考图 → `404: 参考图文件不存在` |

**G40 换脸运行时**：已预置 `buffalo_l`（hf-mirror）后，T2/T3 端到端换脸 **completed**。`inswapper_128.onnx` + GFPGAN + buffalo_l 均在盘。
