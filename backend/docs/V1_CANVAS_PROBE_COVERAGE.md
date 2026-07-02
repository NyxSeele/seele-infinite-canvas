# V1 画布探针覆盖文档

最后更新：**2026-06-30**

本文档对应方向文档 `V1_CANVAS_PROBE_COVERAGE_GAPS.md` 的交付物：功能清单、现有探针盘点、缺口表与运行手册。

---

## §1 V1 画布完整功能清单

可测性标注：**API** = 可用 `backend/scripts/_*.py` 或 pytest 重复验收；**浏览器** = 需手测；**GPU/LLM** = 需 ComfyUI 或百炼。

| # | 阶段 | 核心能力 | 可测性 |
|---|------|----------|--------|
| 1 | 脚本输入 | 文本卡粘贴 / `classify-intent`（仅文本卡）；Excel/Word 导入；空态模板与 Tag | API + 浏览器 |
| 2 | Agent 阶段一 | 创意卡 → 文本 → 大纲 → 分镜表；manual/auto；聊天归档 / AI 标题 | API（LLM）+ 浏览器 |
| 3 | 分镜表编辑 | 镜头描述、导演参数、画风 preset、拖拽排序、转场 segment、高级选项、拆解节拍 | 逻辑 API + 浏览器 |
| 4 | 实体库 | cast/scene 库、entityRefs、跨项目 `user_assets`、`manage_cast`/`manage_scene` | API |
| 5 | 出图 | 分镜直连、`image-gen`、自由参考图（≤5）、mock/ComfyUI | API + GPU |
| 6 | 出视频 | 分镜直连、首尾帧模式、镜头级风格参考、wan/ltx/hunyuan | API + GPU |
| 7 | 节拍卡 | `script-beat-card`、时间线、格级出图 | 浏览器 + API |
| 8 | 协作 | 编辑锁、编辑权请求（WS）、presence、评论/@、通知、迁移团队 | API（部分）+ 浏览器 |
| 9 | 导出 | 异步 `export_jobs`、Word + zip | API |
| 10 | Admin | LLM 三路分流、默认文本模型、单价 | API（admin） |
| 11 | 横切 | 画布持久化、prompt 包、生成历史、失败重试、库频次排序 | API / 纯前端 |
| 12 | 已排除 | 占位功能、项目级风格参考、节拍格构图参考、批量语气调整 | 不写探针 |

### 近期增补（2026-06-30 Backlog v2）

| 功能 | 探针策略 |
|------|----------|
| 生成失败分级重试 | 纯前端 `generationRetryPolicy.js` → 浏览器手测 |
| 库使用频次排序 | 纯前端 `libraryUsage.js` → 浏览器手测 |
| 项目设定折叠 / 转场线 / 导演参数收起 | 浏览器手测 |
| 镜头级风格参考 row API | `_style_reference_probe.py`（扩展 row 路径） |
| segment 不进 prompt | pytest `test_rule_package_ignores_segment_context` |

---

## §2 现有探针实际覆盖范围

### 2.1 `backend/scripts/_*.py`（11 个）

| 脚本 | 实际断言 | 环境 | 深度 |
|------|----------|------|------|
| `_agent_pipeline_e2e_probe.py` | R1–R8b 全链路 `pipeline_step`；mock 出图/视频 `completed`；`split-shot-beats` API | LLM + mock | 深 |
| `_mock_pipeline_stage2_probe.py` | 预置 2 镜阶段二 R6–R8c 状态机 | LLM + mock | 深 |
| `_entity_library_probe.py` | C1–C4 跨项目资产、场景、团队隔离、mock `reference_images` | LLM + mock | 深 |
| `_adversarial_regression_probe.py` | 6 条 Agent 行为固定断言 | LLM | 深 |
| `_adversarial_prompt_probe.py` | 18 条记录型 Markdown，**无自动 pass/fail** | LLM | 记录 |
| `_paste_script_checklist_probe.py` | classify 冒烟 + E1 399/401×N 稳定性 | LLM | 深 |
| `_excel_import_probe.py` | 本地 xlsx 解析/分组/hash；可选 `--llm-group` | 本地 / LLM | 深 |
| `_style_reference_probe.py` | video-node 双镜头隔离、GET/DELETE、prompt 注入；**row 路径**（扩展） | API | 深 |
| `_mock_generation_acceptance.py` | mock 图/视频 `completed`；可选 `--with-failure` | mock | 深 |
| `_comfyui_workflow_structure_probe.py` | ComfyUI workflow 无 `node_errors`（不推理） | ComfyUI | 结构 |
| `_agent_pipeline_probe.py` | 早期调试，无断言 | LLM | 浅（deprecated） |

### 2.2 本轮新增探针（§4）

| 脚本 | 用途 |
|------|------|
| `_export_project_probe.py` | 完整项目导出 HTTP 全流程 |
| `_import_document_http_probe.py` | 文档导入 scan → parse → apply |
| `_video_keyframe_mode_probe.py` | 视频首尾帧模式 mock 提交 |
| `_collab_api_probe.py` | 评论@通知、迁移团队、编辑锁 HTTP |
| `_task_records_probe.py` | 团队生成历史 `GET /api/tasks/records` |
| `_admin_llm_routing_probe.py` | Admin LLM 路由 GET/PUT + set-default-text |
| `_real_media_pipeline_probe.py` | 真实 GPU 出图（默认 SKIP） |
| `_video_enhance_probe.py` | 视频画质增强 API + mock 端到端；workflow 注册 enabled=False |
| `_lut_probe.py` | LUT 内置资产 + GET/PUT lut + mock `video-lut` 产出非空 mp4 |

### 2.3 pytest 补充（`backend/tests/`，41 passed）

| 文件 | 覆盖 |
|------|------|
| `test_prompt_builder.py` | prompt 构建、风格、连贯性；**segment 不进包** |
| `test_style_reference.py` | 风格参考格式化与 prompt 注入 |
| `test_canvas_style_ref_patch.py` | canvas JSON patch、row 镜像 |
| `test_storyboard_backlog.py` | 阶段提示、导出 URL 辅助函数 |
| `test_script_shot_strategy.py` | 新主体/连贯性策略 |
| `test_llm_resilience.py` | LLM 重试分类 |
| `test_upload_validation.py` | 上传 magic bytes |

---

## §3 覆盖缺口清单

### P0 — 核心主链路（mock 可跑）— **本轮已补**

| 功能点 | 原状态 | 新探针 / 测试 |
|--------|--------|----------------|
| 完整项目导出 | 仅单元测试辅助函数 | `_export_project_probe.py` |
| 文档导入 HTTP | 仅本地 `_excel_import_probe` | `_import_document_http_probe.py` |
| 镜头级风格参考 row API | 仅 video-node 路径 | `_style_reference_probe.py` 扩展 |
| 视频首尾帧模式 | 无 | `_video_keyframe_mode_probe.py` |
| Mock 失败 UX | `test_failure_rate` 未接入 main | `_mock_generation_acceptance.py --with-failure` |
| segment 不进 prompt | 无 | `test_rule_package_ignores_segment_context` |

### P1 — 协作 / Admin — **本轮已补**

| 功能点 | 新探针 |
|--------|--------|
| 评论 + @ 通知 | `_collab_api_probe.py` |
| 迁移团队 | `_collab_api_probe.py` |
| 编辑锁 HTTP | `_collab_api_probe.py` |
| 团队生成历史 | `_task_records_probe.py` |
| Admin LLM 路由 | `_admin_llm_routing_probe.py` |

### P2 — 需真实环境 — **本轮已写，默认 SKIP**

| 功能点 | 探针 | 说明 |
|--------|------|------|
| 真实 GPU completed | `_real_media_pipeline_probe.py` | `AGENT_MOCK_GENERATION=false` + ComfyUI |
| 视频画质增强 | `_video_enhance_probe.py` | mock 全链路；GPU 前 workflow `enabled=False` |
| 全片 LUT 调色 | `_lut_probe.py` | 内置 .cube + mock `video-lut`；需 ffmpeg |
| 风格参考 VL 上传 | `_style_reference_probe --with-upload` | 已有，文档化前置 |

### 浏览器必手测（不写后端探针）

项目设定折叠、转场分隔线 UI、导演参数收起、六点拖排序、节拍卡定位、Prompt Bar、scope 切换动画、`libraryUsage` / `generationRetryPolicy`。

### 已覆盖 / 不重复

Agent 全链路、阶段二 mock、实体库、粘贴 E1、Excel 本地解析、对抗性 6 条、ComfyUI 结构、mock 单次图/视频；占位与已下线功能。

---

## §4 运行手册

前置：后端 `http://127.0.0.1:7788`；mock 模式 `AGENT_MOCK_GENERATION=true`；Redis 开启；`alembic upgrade head`。

```powershell
cd d:\Xiaobuding\Xiaobuding\AIStudio\backend

# 既有探针
.\.venv\Scripts\python.exe scripts\_mock_pipeline_stage2_probe.py
.\.venv\Scripts\python.exe scripts\_entity_library_probe.py
.\.venv\Scripts\python.exe scripts\_paste_script_checklist_probe.py --only e1
.\.venv\Scripts\python.exe scripts\_adversarial_regression_probe.py
.\.venv\Scripts\python.exe scripts\_excel_import_probe.py

# 本轮新增（mock 环境）
.\.venv\Scripts\python.exe scripts\_export_project_probe.py
.\.venv\Scripts\python.exe scripts\_import_document_http_probe.py
.\.venv\Scripts\python.exe scripts\_style_reference_probe.py
.\.venv\Scripts\python.exe scripts\_video_keyframe_mode_probe.py
.\.venv\Scripts\python.exe scripts\_mock_generation_acceptance.py
.\.venv\Scripts\python.exe scripts\_mock_generation_acceptance.py --with-failure   # 需 AGENT_MOCK_FAILURE_RATE=1 重启后端
.\.venv\Scripts\python.exe scripts\_collab_api_probe.py
.\.venv\Scripts\python.exe scripts\_task_records_probe.py
.\.venv\Scripts\python.exe scripts\_admin_llm_routing_probe.py
.\.venv\Scripts\python.exe scripts\_video_enhance_probe.py
.\.venv\Scripts\python.exe scripts\_lut_probe.py

# 真实 GPU（默认 SKIP exit 2）
.\.venv\Scripts\python.exe scripts\_real_media_pipeline_probe.py

# pytest
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

### 退出码约定（本轮新探针）

| 码 | 含义 |
|----|------|
| 0 | PASS |
| 1 | 基础设施失败（连不上后端、登录失败） |
| 2 | SKIP（环境不满足，如未开 ComfyUI / mock 仍开启） |
| 3 | 断言失败 |

### 运行结果记录（2026-06-30 本地验收）

| 探针 / 测试 | 退出码 |
|-------------|--------|
| `pytest tests/ -q` | 0（42 passed） |
| `_export_project_probe.py` | 0 |
| `_import_document_http_probe.py` | 0 |
| `_style_reference_probe.py`（含 row 路径） | 0 |
| `_video_keyframe_mode_probe.py` | 0 |
| `_mock_generation_acceptance.py` | 0 |
| `_collab_api_probe.py` | 0 |
| `_task_records_probe.py` | 0 |
| `_admin_llm_routing_probe.py` | 0 |
| `_real_media_pipeline_probe.py` | 0 或 2（mock 开启时应为 2 SKIP） |

**附带修复**：`GET /api/tasks/records` 路由须注册在 `/api/tasks/{task_id}` 之前（`tasks.py`），否则历史 Flyout 团队 scope 恒 404。
