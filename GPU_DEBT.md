# GPU / 生成链路技术债台账

最后更新：**2026-07-10**（清理债项四件套 + G45）

与 [`HANDOFF.md`](HANDOFF.md) 文首「当前总览」互补：本节只跟踪 **GPU、Prompt Trace、批量生成、模型能力** 相关债项。

**环境**：AutoDL 269 机 · RTX 4090 · 数据盘 **~31G 可用**（~270G/300G）· pytest **114 passed**

---

## 状态图例

| 标记 | 含义 |
|------|------|
| ✅ | 已闭环（探针或 GPU 验收通过） |
| ⚠️ | 部分缓解（有 workaround，未根治） |
| 🔴 | 未解（产品/模型级限制） |
| ⏳ | 待资源或排期 |

---

## 已闭环（2026-07-07 ～ 07-08）

| ID | 条目 | 闭环方式 | 文档/探针 |
|----|------|----------|-----------|
| G1 | Flux 图像中文未走 translate-only | `prompt.py` / `llm.py` translate-only | [`PROMPT_DEBUG_PHASE1.md`](PROMPT_DEBUG_PHASE1.md) T1–T4 |
| G2 | 图像路径缺 `quality_preset` suffix | 对齐视频 suffix 注入 | Prompt 阶段一 |
| G3 | L0–L4 trace 盲区（compile/build 无日志） | `L0 COMPILED` / `L0 BUILT`；L3/L4 全链路 | 路线 B 二轮 · route_c |
| G4 | Wan i2v `/api/view` 参考图不可用 | 双路径：`/api/view` + `/api/uploads` | Prompt 阶段二 V3-retest |
| G5 | 视频 cinematic suffix 污染 L3 翻译 | suffix **L3 之后**追加 | Prompt 阶段二 |
| G6 | 视频 L3 背影场景丢外貌关键词 | `VIDEO_TRANSLATE_PLAIN_SYSTEM` 保留姓名/发型/服装 | 路线 B 二轮 · 003 L4 断言 |
| G7 | 分镜表多镜承接（L0「承接上一镜头」） | 路线 B 3 镜串行 img2img + prior_shots | [`ROUTE_B_RESULT.md`](ROUTE_B_RESULT.md) |
| G8 | 路线 B 第 3 镜视频探针超时 | `POLL_TIMEOUT=1800` | route_b / route_c 均 3/3 视频 |
| G9 | registered_models 无 text 模型 | `_enable_text_models.py`；默认 qwen-plus | [`AGENT_TRACE_BASELINE.md`](AGENT_TRACE_BASELINE.md) §7 |
| G10 | A3 剧本文本截断致镜数不足 | 探针存 `content` 全文；`STRUCTURE_SCENE_TITLES` | [`AGENT_TRACE_BASELINE.md`](AGENT_TRACE_BASELINE.md) §8 |
| G11 | Agent Trace 不可观测 | A1–A5 instrumentation + 基线探针 | `_agent_trace_baseline_probe.py` |
| G12 | 路线 C：Agent 分镜 → 批量 GPU 断开 | `_route_c_agent_gpu_probe.py`；A4 rows 驱动 SHOTS | [`ROUTE_C_RESULT.md`](ROUTE_C_RESULT.md) |
| G13 | 首尾帧 FLF2V API | `build_wan_flf2v_workflow`；keyframe 路由 | [`PROMPT_DEBUG_PHASE3.md`](PROMPT_DEBUG_PHASE3.md) K1–K4 |
| G14 | 路线 A：图像卡缺 preset 选择器 | `CanvasPromptBar` + `VideoStylePicker` | [`ROUTE_B_RESULT.md`](ROUTE_B_RESULT.md) §路线 A |
| **G30** | 人物一致性（模型级） | phash + flux-pulid 全栈 | [`G30_RESUME.md`](G30_RESUME.md) |
| **G31** | 视频运动可控 | 出视频注入运镜/景别；`sampling_profile=quality`→8 步比例分段；compile 英文运镜前置 | `_g31_motion_prompt_probe.py` · wan-i2v 结构 PASS |
| **G32** | A1 Agent token 成本 | 阶段化短 SYSTEM_PROMPT + pipeline 轮去掉全量 JSON；继续轮 **~1.7–1.9k**（原 ~5.5k） | [`AGENT_TRACE_BASELINE.md`](AGENT_TRACE_BASELINE.md) §3.1 |
| **G33** | 运镜/景别 UI | `CameraMotionPicker`（非画风 `VideoStylePicker`）；`camera_move`/`shot_scale` compile 显式注入 | `_g33_video_style_picker_probe.py` |

---

## 部分缓解（workaround 有效，未根治）

| ID | 条目 | 现状 | 缓解手段 | 根治方向 |
|----|------|------|----------|----------|
| G20 | 多镜视觉连贯 | 镜间风格可延续，人脸/服装仍漂移 | `visualContinuity` + 上一镜 img2img（denoise ~0.7） | 角色参考图 + 更强 identity 模型 / IP-Adapter |
| G21 | 背影/侧脸镜头外貌 | L3 翻译已保留关键词 | Prompt 工程 + L4 英译约束 | 模型级 identity lock |
| G22 | Flux 不支持传统 img2img | 承接走 reference + workflow 变体 | `use_visual_reference` 路径 | 换支持 img2img 的模型或专用 continuity workflow |

---

## 未解（产品薄弱项 · 优先排序）

| ID | 条目 | 严重度 | 说明 | 建议优先级 |
|----|------|--------|------|------------|
| ~~**G30**~~ | ~~人物一致性~~ | — | ✅ 2026-07-09 闭环 | — |
| ~~**G31**~~ | ~~视频运动可控~~ | — | ✅ 2026-07-09 闭环：运镜注入 + quality 8 步 | — |
| ~~**G32**~~ | ~~A1 token~~ | — | ✅ 2026-07-09 闭环：继续轮 ≤2k tokens | — |
| ~~**G33**~~ | ~~运镜/景别 UI~~ | — | ✅ 2026-07-09：`CameraMotionPicker` + compile 显式字段 | — |

### G30 人物一致性 — 细节

- **2026-07-09 G30 闭环**：nunchaku + PuLID 权重落盘；ComfyUI 节点验收；`scripts/_g30_pulid_smoke.py` GPU PASS；facexlib 权重需置于 `models/facexlib/*.pth` 根目录
- 路线 B/C 探针：L0 承接 + L4 含 `woman` / `trench coat` 等关键词 **技术指标 PASS**
- 实际短板：镜 002/003 经 img2img 后，**面部特征、体型比例**仍可能变化（flux-dev 基线）；PuLID 正脸锚定已缓解
- 现有能力：角色卡 `entityRefs`、`character_refs` compile、上一镜 reference、PuLID 正脸锚定

### G31 视频运动可控 — 细节（✅ 已闭环）

- **Prompt**：分镜表出视频路径调用 `appendDirectorFieldsToDescription`；`prompt_builder` 将「运镜/景别」映射为英文前置句
- **采样**：`sampling_profile=fast|quality`（默认 fast=4；有 `movement` 时前端传 quality=8）；`KSamplerAdvanced` 分段 `0→steps//2`、`steps//2→steps`
- **探针**：`scripts/_g31_motion_prompt_probe.py`；结构探针 `--model wan-i2v` PASS
- 仍挂 Lightx2v 4-step LoRA（未换专用 8-step 权重）；极端运镜主观质量可再观察

### G32 A1 token 成本 — 细节（✅ 已闭环）

- **阶段化 prompt**：pipeline「继续」轮用 `SYSTEM_PROMPT_CORE` + `SYSTEM_PROMPT_PIPELINE`（~1.9k 字 vs 全量 ~9.3k）
- **去重**：pipeline 轮 `_build_canvas_context(..., pipeline_mode=True)` 不再 `json.dumps` 全量快照
- **观测**：`AGENT_INPUT` 打 `system_chars` / `pipeline_prompt`；`AGENT_OUTPUT` 打 `prompt_tokens` / `completion_tokens`
- **验收**（2026-07-09）：继续轮 total **1705–1857**；创意 ask_user 轮仍 ~5k（全量 prompt，预期内）

### G33 运镜/景别 UI — 细节（✅ 已闭环）

- **组件**：[`CameraMotionPicker.jsx`](frontend/src/components/canvas/CameraMotionPicker.jsx) 挂在 [`VideoReferencePanel`](frontend/src/components/canvas/VideoReferencePanel.jsx)（视频 PromptBar）；**勿与**画风 [`VideoStylePicker`](frontend/src/components/canvas/VideoStylePicker.jsx) 混淆
- **节点 data**：`cameraMove` / `shotScale`（默认 `auto`）；非 auto 运镜时写 `samplingProfile=quality`
- **API**：`/api/prompt/compile` 可选 `camera_move` / `shot_scale`；Wan `build_prompt` 显式非 auto 时跳过 G31 文本「运镜：」解析，避免双重注入
- **探针**：`scripts/_g33_video_style_picker_probe.py` 4 case PASS

---

## 待资源 / 排期

| ID | 条目 | 阻塞 | 备注 |
|----|------|------|------|
| G40 | HunyuanVideo 权重 | ✅ G35 已下载并对齐启用（720p bf16 + DualCLIP/VAE；steps=50） | **历史编号**；勿与「新 G40=ReActor」混淆。Hunyuan smoke 已上线 |
| G39 | AudioCraft AudioGen | ✅ 权重 + API + sound_note 混音 | `audiogen-medium`；跳过 ltx2 |
| G40b / 新 G40 | ReActor face swap（出图） | ✅ 接线 + buffalo_l + Phase7 T2/T3 换脸 completed | 视频逐帧见 **G45** |
| G41 | LTX-2 fp4 权重 + API | ✅ 五类权重落盘（~36G）；`ltx2-fp4` 结构探针 PASS；`submit_ltx2_video_prompt` 已接线 | GPU T2V smoke 可选（勿与 PuLID 同载） |
| G42 | SD1.5 产品入口 | ✅ 产品入口与 registry 已移除；本机无权重 | DB 行已删；内部 `sd15` workflow 可暂留 |
| G43 | fun_inpaint 专用 UNET API | ✅ `wan-fun-inpaint` 已接入（G34） | 与 `wan-i2v` FLF2V 并存；结构探针 PASS；未做 GPU 出片 smoke |
| G44 | mock 参考图缺失 → 探针 `POST /api/assets` 404（曾误记为 GET 路由 404） | ✅ `generate_mock_assets` 同步 `uploads/images/mock-*-ref.jpg` + 探针自检 | 路由本身正常 |
| G45 | ReActor 视频逐帧换脸 | ✅ `CanvasVideoRequest.use_reactor` + `reactor_video.py`；独立帧工作流；探针 PASS | 临时目录 `tmp_reactor_*` finally 清理 |
| G47 | 主观质量评估表（原 G45） | 需人工观看 MP4 | [`ROUTE_B_RESULT.md`](ROUTE_B_RESULT.md) Step 4 待填 |
| **G46** | **Seedance API 接入 + prompt 编译** | ✅ G37 框架已就绪（`seedance-2.0` enabled=False；`compress_for_seedance`；Ark client） | **最后再说 / 不排期**；上线仍阻塞于 `SEEDANCE_API_KEY` |

---

## 推荐攻关顺序（供产品决策）

G30–G45 / G42–G44 已闭环；**G46 Seedance 最后再说**。后续优先：

1. **G47 主观质量表** — 人工观看 MP4
2. ~~**G46 Seedance Key**~~ — **不排期**（框架就绪，被动等待）
3. ~~**G45 ReActor 视频逐帧**~~ — ✅ 独立帧工作流 + 探针 PASS
4. ~~**G44 mock 参考图 / 探针 POST 404**~~ — ✅ 路由正常；已修 generate + 自检
5. ~~**Prompt Phase4–7 GPU 实测**~~ — 全阶段完成（含 Phase7 换脸）
6. **G41 LTX2 GPU T2V smoke** — 端到端 MP4（勿与 PuLID 同载；Phase5 探针已绿）

---

## 探针速查

```bash
cd backend && set -a && source .env && set +a

# Agent + GPU 全链路（路线 C）
.venv/bin/python scripts/_route_c_agent_gpu_probe.py

# 固定文案批量 GPU（路线 B）
.venv/bin/python scripts/_route_b_batch_probe.py

# Agent trace 基线（无 GPU）
AGENT_MOCK_GENERATION=false .venv/bin/python scripts/_agent_trace_baseline_probe.py

# 单元测试
.venv/bin/python -m pytest tests/ -q   # 114 passed
```
