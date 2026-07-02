# AI Studio 开发进度交接文档

用于开启新对话时快速恢复上下文。最后更新：**2026-07-02**（写实电影预设 + 全片 LUT 统一）

---

## 当前总览（2026-07-02 · 最新）

本轮完成 **写实电影内容风格预设**（项目级 prompt 注入 + 画质增强参数覆盖）与 **全片 LUT 色调统一**（ffmpeg 后处理 + 原始/调色后双版本），LUT 配置存 **script-table 节点 data**（与 modelId/画风同级）。

上一轮：**视频画质增强功能扩展**（智能推荐 + SeedVR2 高级参数 + 一键增强 UI）及 **Prompt Bar / 顶栏分享菜单** UI 修补，均已浏览器验收通过。

### 近期完成一览

| 阶段 | 主题 | 状态 | 要点 |
|------|------|------|------|
| **写实电影-1** | 内容风格预设 | ✅ | `contentStyle` on script-table；`prompt_builder` 写实正/负向 suffix；默认写实电影 |
| **写实电影-2** | 画质增强写实覆盖 | ✅ | `recommend-params` 读 `contentStyle`；`input_noise_scale=0.15`；≤1080p 优先 2x |
| **LUT-1** | 内置预设 + ffmpeg | ✅ | `backend/assets/luts/*.cube`；`video_lut_service`；`task_type=video_lut` |
| **LUT-2** | 前端色调设置 + 双 Tab | ✅ | 分镜表「色调风格」折叠；视频卡「原始/调色后」；生成完成自动 LUT |
| **LUT-3** | API + 探针 | ✅ | `GET/PUT /api/projects/{id}/lut`；`POST .../lut/apply-all`；`_lut_probe.py` |
| **视频增强-2** | 前端一键增强 UI | ✅ | `VideoEnhancePanel` + `videoEnhanceBridge`；`GenerationBrandLoader` |
| **视频增强-3** | Prompt Bar UX 修补 | ✅ | 去取消钮；ⓘ 说明条；亮色 token；`expandInField` 视频卡 |
| **顶栏 UX** | 分享菜单对齐 | ✅ | 左对齐 + 菜单左缘对齐分享钮向右展开（方案 B） |
| **左栏 UX** | 开通会员样式 | ✅ | 文案/紫色/背景框常驻 |
| **部署文档** | P0/P1 补全 | ✅ | HANDOFF §六；AutoDL 配置单一来源；env/Docker/安全审计对齐 |

| **画布交互-1** | 三点菜单 vs 画布双击 | ✅ | `suppressPaneMenu.js`；关菜单后 400ms 抑制 `handlePaneDblClick` / 右键菜单 |
| **画布交互-2** | 画质增强 UI | ✅ | `IconEnhance` 替换 ›；`VideoEnhancePanel` panel 单行紧凑 + 超分/强度标签 |
| **画布交互-3** | 参考图主题 + hover | ✅ | `ImageReferencePicker` 亮色；`add-ref-btn` / `video-style-ref-btn` hover 对齐顶栏 |
| **画布交互-4** | 选中卡片加号常驻 | ✅ | `plusPinned = selected`；`GenerationCardNode` / `VideoGenerationNode` / `TextWorkflowEdgePlugs` |
| **画布交互-5** | 操作方式迁入头像菜单 | ✅ | 左栏移除 nav 图标；头像菜单 flyout；悬浮 **140ms** 自动展开 |
| **画布交互-6** | 三点菜单画质增强 flyout | ✅ | 去分隔线；`cell-dots-submenu` 右侧弹出，避免菜单内纵向空白 |
| **UX 修补** | Tab 灰底规则 | ✅ | **仅 hover** 有灰底；选中 Tab 仅加粗 + 展开下划线；取消画质增强不切出灰底态 |
| **Backlog v2-1** | 镜头卡按钮布局 | ✅ | 主区仅「生成分镜图」「生成视频」；「拆解成多镜头」移入头部次要按钮 |
| **Backlog v2-2** | 删除批量语气调整 | ✅ | 前后端移除 `batch_adjust_tone` / `ScriptBatchToneModal` / 相关 locale 与测试 |
| **Backlog v2-3/4** | 使用频次 + 失败重试 | ✅ | `libraryUsage.js` 最近使用排序；`generationRetryPolicy.js` 分级重试（验收通过） |
| **Backlog v2-5** | 分镜表视觉层级 | ✅ | 项目设定默认折叠摘要；描述区视觉重心；主操作按钮降饱和 |
| **UX 修复** | 设定库折叠互斥 | ✅ | 折叠态仅摘要行；展开仅人物库/场景库；**工具栏（模型/画风/批量生成）始终可见** |
| **UX 修复** | 转场分隔线 | ✅ | `segment` 字段不参与生成 prompt；`ScriptSegmentHeader` 改为紫色分隔线标签（18px） |
| **UX 修复** | 导演参数 | ✅ | 默认**收起** + 「展开/收起」按钮；收起时显示摘要一行 |
| **UX 修复** | 交互与定位 | ✅ | 镜头六点拖排序修复；节拍卡标题栏可拖画布；生成节点贴近分镜表；分镜表内右键不弹画布菜单 |
| **37b** | 镜头级视频风格参考 | ✅ | 双路径 API；数据挂 `video-gen.data.styleReference`；回滚项目级（021） |
| **构图参考** | 节拍格下线 | ✅ | `keyframes[].referenceImage` deprecated；出图走 entityRefs / referenceImages |
| **探针 v1** | V1 画布覆盖补全 | ✅ | 7 个新探针 + 文档；`GET /api/tasks/records` 路由修复；mock 环境全套 exit 0 |
| **主题过渡** | 圆形扩散切换 | ✅ | `useThemeTransition`；三入口；250ms；`prefers-reduced-motion` / 无 API 降级 |

### 分镜表当前 UI 形态（速查）

| 区域 | 行为 |
|------|------|
| **项目设定摘要行** | 默认折叠，文案 `人物库（n）· 场景库（n）`；细线 SVG 上下 chevron |
| **展开后** | 仅渲染人物设定库 + 场景设定库完整表单（unmount，非 CSS 隐藏） |
| **工具栏** | 图像/视频/画风/应用到全部/一键生成/高级选项 — **始终在摘要行下方，不随设定库折叠** |
| **转场片段** | Excel 导入标记（如「夜晚」）→ `—— 夜晚 ——` 紫色分隔线，无时长/简述表单 |
| **镜头卡** | 描述为视觉重心；底部次要按钮「生成分镜图」「生成视频」；左侧六点拖排序 |
| **导演参数** | 默认收起；有内容时显示摘要行；点「展开」显示完整表单 |
| **节拍卡** | 独立 `script-beat-card` 节点；拖标题栏移动画布；出图节点贴在分镜表右侧一列 |

### 生成节点定位常量（`nodeHelpers.js`）

| 常量 | 值 | 说明 |
|------|-----|------|
| `SCRIPT_TABLE_WIDTH` | **1100** | 与 `.st-wrapper` CSS 对齐（原 1360 导致节点过远） |
| `SCRIPT_TABLE_TO_IMAGE_GAP` | 48 | 分镜表右缘 → 节拍卡/出图列间距 |
| `SCRIPT_TABLE_CHROME_Y` | 300 | 表头+摘要+工具栏高度，用于行/节拍卡 Y 对齐 |
| `SCRIPT_TABLE_ROW_Y_OFFSET` | 210 | 每镜纵向步进（与虚拟列表估算一致） |

出图/视频统一用 `computeScriptTableGenX()` / `computeScriptTableShotY()`；**已有画布上的旧节点不会自动重定位**，需重新生成或手拖。

### 当前产品形态速查

| 能力 | 粒度 / 入口 | 存储 | 注入范围 |
|------|-------------|------|----------|
| **视频风格参考** | 镜头级；Prompt Bar → `VideoReferencePanel` | `video-gen.data.styleReference`（canvas JSON） | **仅视频生成** |
| **构图 / 自由参考图** | 单次出图；图片生成卡片 / Prompt Bar「添加参考图」 | `image-gen.data.referenceImages`（最多 5 张） | 图片 img2img |
| **角色/场景参考** | 分镜 @提及 / 设定库 | 出图时由 `entityRefs` 解析，写入 `image-gen` 节点 | 分镜批量出图自动带入 |
| ~~项目级风格参考~~ | ~~顶栏~~ | ~~`canvas_projects.style_reference`~~ | ❌ 已回滚（021） |
| ~~节拍格构图参考~~ | ~~节拍拆分格~~ | `keyframes[].referenceImage`（deprecated，只读） | ❌ 已下线 |

### 验证与本地服务

| 项 | 说明 |
|----|------|
| 前端构建 | `cd frontend && npm run build` ✅（2026-07-02 视频增强 + 分享菜单 UI 后） |
| 后端测试 | `cd backend && .venv\Scripts\python.exe -m pytest tests/ -q` → **42 passed** |
| 视频增强探针 | `scripts/_video_enhance_probe.py`（mock 全链路；GPU 前 workflow `enabled=False`） |
| 探针覆盖文档 | [`backend/docs/V1_CANVAS_PROBE_COVERAGE.md`](backend/docs/V1_CANVAS_PROBE_COVERAGE.md)（功能清单 + 缺口 + 运行手册） |
| 数据库迁移 | `alembic upgrade head`（含 **020** 增列、**021** 删 `style_reference` 列） |
| 风格分析依赖 | `DASHSCOPE_API_KEY` + ffmpeg（`imageio-ffmpeg`） |
| 前端刷新 | 改 UI 后 **Ctrl+Shift+R** 硬刷新 |
| 后端重启 | 改 `style_reference.py` / `canvas_style_ref.py` / `shot_prompt_package.py` / `tasks.py` 后重启 uvicorn |

### 待排期（自检结论，本轮未做）

- **非法上传路径**：画质增强 mock/真实链路偶发 `media_access` 鉴权失败（与本轮 UI 无关，待查视频 URL ticket）
- 批量出图前逐格预置构图参考（低频）：若强需求，在出图前于 `image-gen` 节点预填 `referenceImages`，约 **0.5–1 天**
- 纯前端项自动化（可选）：`libraryUsage` / `generationRetryPolicy` 若需 Vitest，单独立项

---

## 详情：视频画质增强 + Prompt Bar/顶栏 UI（2026-07-02 · ✅ 已验收）

### A. 后端 — 智能推荐与 SeedVR2 参数

| 项 | 说明 |
|----|------|
| 视频探针 | `backend/services/video_enhance_probe.py`：ffprobe/ffmpeg 读 width/height/duration/fps |
| 参数推荐 | `video_enhance_recommend.py`：LLM 推荐 + 规则降级 + 校验；`reasoning` 含完整说明句 |
| API | `POST /api/tasks/video-enhance/recommend-params`（[`routers/tasks.py`](backend/routers/tasks.py)） |
| Schema | `VideoEnhanceRequest`：`upscale_factor` 支持 **1.0**；`input_noise_scale` / `batch_size` / `color_correction` / `model_size` |
| ComfyUI | [`client.py`](backend/comfyui/client.py) 3B/7B 映射、1.0 超分、高级参数转发；workflow `video_enhance_seedvr2.json` / `realesrgan.json` |
| Mock | `mock_generation.run_mock_video_enhance_task`；探针 [`_video_enhance_probe.py`](backend/scripts/_video_enhance_probe.py) |
| 模型注册 | `model_registry.py` capabilities 含 `1.0`；默认 SeedVR2 优先、RealESRGAN fallback（见 ComfyUI Runbook） |

**推荐逻辑要点**：1080p+ 可推荐 `upscale_factor=1.0`（仅增强不放大）；时长影响 `batch_size`；LLM 失败走规则模板。

### B. 前端 — 一键增强与高级选项

| 项 | 说明 |
|----|------|
| 面板 | [`VideoEnhancePanel.jsx`](frontend/src/components/canvas/VideoEnhancePanel.jsx)：`variant="panel"` 紧凑单行「一键增强 + 高级选项」；`variant="menu"` 用于三点 flyout |
| 桥接 | [`videoEnhanceBridge.js`](frontend/src/components/canvas/videoEnhanceBridge.js)：`CanvasPromptBar` ↔ `VideoGenerationNode.handleSmartEnhance` |
| 高级区 | 手动配置 checkbox；超分/强度；精细控制四参 + **ⓘ 点击展开说明条**（对齐 `ScriptTableNode` `st-continuity-info-btn` 模式，非 hover 问号） |
| 加载态 | [`GenerationBrandLoader`](frontend/src/components/canvas/GenerationBrandLoader.jsx) 品牌 loading |
| 展开 icon | `CanvasPromptBar`：`expandInField={isText \|\| isVideo}` 落入输入框右上角 |
| 取消 | Prompt Bar 内 **无** 取消钮；三点菜单 flyout 内仍保留取消 |

### C. 分享菜单与头像菜单

| 项 | 说明 |
|----|------|
| 分享菜单 | [`CanvasShareMenu.jsx`](frontend/src/components/canvas/CanvasShareMenu.jsx)：四项 **左对齐**，固定 18px 图标列；`padding` 左右对称 |
| 定位 | **方案 B**：`left = shareBtnRect.left`，菜单向右展开；`requestAnimationFrame` 二次量宽防首帧偏移 |
| 开通会员 | `locale.js`「开通会员」；`Canvas.css` `.clt-menu-quota-upgrade` 紫色 `#7c3aed` + **常驻**淡紫底 |

### D. 浏览器验收 checklist（2026-07-02 · ✅ 已通过）

- [x] 视频卡画质增强 Tab：一键增强 + 高级选项；无取消钮；ⓘ 说明条点击展开/收起
- [x] 高级选项亮色可读；说明条与分镜表高级选项风格一致
- [x] 分享菜单：图标列对齐；左右内边距对称；菜单左缘对齐分享钮
- [x] 头像菜单「开通会员」：字号/紫色/常驻背景框
- [x] `npm run build` 通过

**关键文件**：

```
backend/services/video_enhance_probe.py
backend/services/video_enhance_recommend.py
backend/comfyui/client.py
backend/comfyui/workflows/video_enhance_seedvr2.json
backend/comfyui/workflows/video_enhance_realesrgan.json
backend/scripts/_video_enhance_probe.py
backend/schemas/tasks.py
backend/routers/tasks.py

frontend/src/components/canvas/VideoEnhancePanel.jsx|css
frontend/src/components/canvas/videoEnhanceBridge.js
frontend/src/components/canvas/VideoGenerationNode.jsx
frontend/src/components/canvas/CanvasPromptBar.jsx
frontend/src/components/canvas/GenerationBrandLoader.jsx|css
frontend/src/components/canvas/CanvasShareMenu.jsx
frontend/src/pages/Canvas.css                    # ctb-share-menu, clt-menu-quota-upgrade
frontend/src/utils/locale.js, localeCanvas.js
```

---

## 详情：画布交互六项优化 + UX 修补（2026-07-01 · ✅ 已实现）

### A. 六点菜单与画布交互

| 项 | 说明 |
|----|------|
| 抑制画布菜单 | `frontend/src/utils/canvas/suppressPaneMenu.js`：`markSuppressPaneMenu(400ms)` / `isPaneMenuSuppressed()` |
| 接入点 | `GenerationCardNode` / `VideoGenerationNode` / `NodeCardDotsMenu` 外部 mousedown 关菜单时标记抑制 |
| 画布钩子 | `useCanvasInteraction.js`：`handlePaneDblClick` / `handlePaneContextMenu` 开头检查抑制；`closest` 排除 `.cell-menu-portal, .gn2-dots-menu, .cell-dots-submenu` |
| 画质增强 flyout | 视频三点菜单：去 `gn2-dots-menu-separator`；画质增强选项右侧 `cell-dots-submenu` 弹出（非菜单内纵向展开） |

### B. 画质增强 UI（Prompt Bar + 三点菜单）

| 项 | 说明 |
|----|------|
| 三点入口 | `IconEnhance`（`CanvasTopbarIcons.jsx`）；无 `submenu-arrow` |
| Prompt Bar 紧凑行 | `VideoEnhancePanel variant="panel"`：单行「一键增强 + 高级选项」；精细控制 ⓘ 说明条（2026-07-02 改版） |
| 三点下拉内 | `variant="menu"` 保持纵向布局（在 flyout 子菜单内） |
| 取消行为 | 取消时 `panelMode` 回 `referenceMode`（首尾帧/全能参考）；`referenceSlotsOpen: false` |

### C. 参考图与主题

| 项 | 说明 |
|----|------|
| 浏览画布选图 | `ImageReferencePicker` 根节点 `rf-page--${theme}`；CSS 改 `--tl-*` token + 亮色覆盖 |
| 添加参考图 hover | `.add-ref-btn` padding + `--tl-toolbar-btn-hover`；亮色 `.nb-banner .add-ref-btn:hover` |

### D. 选中卡片加号常驻

| 项 | 说明 |
|----|------|
| 逻辑 | `plusPinned = selected`；`(leftVisible \|\| plusPinned)` → `gn2-plus-zone--visible`；mouseLeave 时若 pinned 不隐藏 |
| 节点 | `GenerationCardNode`、`VideoGenerationNode`、`TextWorkflowEdgePlugs`（各文本工作流父节点传 `selected`） |
| CSS | `.gn2-root--selected` / `.tn-wrapper--selected` 下加号区 transform 加强 |

### E. 画布操作方式（左栏头像菜单）

| 项 | 说明 |
|----|------|
| 移除 | `CanvasLeftToolbar` `TOOLBAR_ITEMS` 中 `id:"nav"` 独立图标 |
| 迁入 | 头像菜单项「画布操作方式」→ `activePanel === "nav"` 时右侧 `CanvasNavModePanel` flyout |
| 悬浮展开 | `onMouseEnter` **140ms** 后 `setActivePanel("nav")`；离开 flyout 区 **200ms** 收起到 `"avatar"`；点击仍可切换 |
| 未改 | `canvasNavMode.js` / `canvasStore.canvasNavMode` / `Canvas.jsx` `getCanvasNavFlowProps` 消费逻辑 |

### F. Tab 样式规则（视频 Prompt Bar 顶栏）

| 规则 | 说明 |
|------|------|
| 选中 + 展开 | `.mode-tab.active.expanded` → 下划线 |
| 选中 + 收起 | **无背景**（勿恢复 `active:not(.expanded)` 灰底） |
| 悬浮 | `.mode-tab:hover` → 灰底（唯一常驻灰底来源） |
| 二次点击收起 | 首尾帧/全能参考/画质增强均不额外加灰底 class |

**浏览器验收 checklist（画布交互）**：

- [ ] 三点菜单打开 → 点空白关菜单 → 双击空白：**不**出现节点选取器/右键菜单
- [ ] 三点「画质增强」：左侧 icon，无 ›；子面板在**右侧** flyout 弹出
- [ ] 视频输入框画质增强 Tab：单行；有「超分倍数」「增强强度」标签；取消后 Tab **无灰底**
- [ ] 亮色：浏览画布选参考图为浅面板；「添加参考图」hover 有灰底
- [ ] 未选中卡片加号 hover 出现；选中后左右加号常驻
- [ ] 左栏无独立操作方式图标；头像菜单悬浮 ~140ms 展开 flyout；切换滚轮/缩放行为正确
- [ ] Tab 灰底**仅 hover**；二次点击收起 Tab 不出现灰底框

**关键文件**：

```
frontend/src/utils/canvas/suppressPaneMenu.js
frontend/src/hooks/canvas/useCanvasInteraction.js
frontend/src/components/canvas/VideoEnhancePanel.jsx|css
frontend/src/components/canvas/VideoGenerationNode.jsx|css
frontend/src/components/canvas/GenerationCardNode.jsx|css
frontend/src/components/canvas/CanvasTopbarIcons.jsx          # IconEnhance
frontend/src/components/canvas/ImageReferencePicker.jsx|css
frontend/src/components/canvas/VideoReferencePanel.jsx|css  # Tab 仅 hover 灰底
frontend/src/components/canvas/VideoReferencePanel.css
frontend/src/components/canvas/CanvasPromptBar.jsx            # enhance onCancel → panelMode
frontend/src/components/canvas/CanvasLeftToolbar.jsx        # nav flyout + 140ms hover
frontend/src/components/canvas/TextWorkflowEdgePlugs.jsx
frontend/src/components/canvas/CanvasShared.css               # selected plus zones
frontend/src/pages/Canvas.css                                 # clt-menu-item--has-flyout
```

---

## 详情：V1 画布探针覆盖补全（2026-06-30 · ✅ 已验收）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 覆盖文档 | ✅ | [`backend/docs/V1_CANVAS_PROBE_COVERAGE.md`](backend/docs/V1_CANVAS_PROBE_COVERAGE.md)：功能清单 + 现有探针盘点 + 缺口表 + 运行手册 |
| 导出 HTTP | ✅ | `_export_project_probe.py`：POST → poll → 下载 zip（含 docx） |
| 导入 HTTP | ✅ | `_import_document_http_probe.py`：内置最小 xlsx；scan → parse → apply |
| 风格参考 row | ✅ | `_style_reference_probe.py` 扩展 `/api/shots/{row_id}/style-reference` |
| 视频首尾帧 | ✅ | `_video_keyframe_mode_probe.py`：keyframe + first/last frame mock |
| 协作 API | ✅ | `_collab_api_probe.py`：迁移团队、编辑锁、评论@通知 |
| 团队生成历史 | ✅ | `_task_records_probe.py`；**修复** `tasks.py` 中 records 路由须在 `{task_id}` 之前 |
| Admin LLM | ✅ | `_admin_llm_routing_probe.py`：GET/PUT 分流 + set-default-text 不 422 |
| 真实 GPU | ✅ 脚本就绪 | `_real_media_pipeline_probe.py`；mock 开启时 exit 2 SKIP |
| segment 不进 prompt | ✅ | `test_rule_package_ignores_segment_context`（pytest 42 passed） |
| mock 失败分支 | ✅ | `_mock_generation_acceptance.py --with-failure`（需 `AGENT_MOCK_FAILURE_RATE=1`） |

**一键跑 mock 探针（本地）**：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\_export_project_probe.py
.\.venv\Scripts\python.exe scripts\_import_document_http_probe.py
.\.venv\Scripts\python.exe scripts\_collab_api_probe.py
.\.venv\Scripts\python.exe scripts\_task_records_probe.py
.\.venv\Scripts\python.exe scripts\_admin_llm_routing_probe.py
.\.venv\Scripts\python.exe scripts\_video_keyframe_mode_probe.py
.\.venv\Scripts\python.exe scripts\_style_reference_probe.py
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

---

## 详情：主题切换圆形扩散（2026-06-30 · ✅ 已验收）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| Hook | ✅ | `useThemeTransition.js`：`startViewTransition` + `flushSync(toggleTheme)` + WAAPI `clip-path` 圆形扩散 250ms |
| 样式 | ✅ | `themeTransition.css` 关闭 root 默认 cross-fade；`main.jsx` 全局引入 |
| 三入口 | ✅ | 画布左栏头像菜单、工作区顶栏太阳钮、个人资料弹窗主题钮 |
| 降级 | ✅ | 无 `startViewTransition` 或 `prefers-reduced-motion` → 瞬时切换，无报错 |
| 隔离 | ✅ | 与 `useScopeSwitchTransition` / `ScopeSwitchPanel` **不复用、不混用** |

**浏览器验收**：点击位置圆形扩散约 250ms；降级路径正常；scope 切换动画不受影响。

**关键文件**：

```
frontend/src/hooks/useThemeTransition.js
frontend/src/styles/themeTransition.css
frontend/src/components/canvas/CanvasLeftToolbar.jsx
frontend/src/components/workspace/WorkspaceTopbar.jsx
frontend/src/components/canvas/CanvasProfileModal.jsx
```

## 详情：转场片段字段自检（2026-06-30）

Excel 导入产生的场景/时间切换标记（如「夜晚」）在分镜表中对应 `segments[]` 条目，由 [`ScriptSegmentHeader`](frontend/src/components/canvas/ScriptSegmentHeader.jsx) 展示。

| 字段 | 是否进入图像/视频生成 API prompt | 实际用途 |
|------|----------------------------------|----------|
| `segment.description`（本段剧情简述） | **否** | UI 编辑；[`castLibrarySync.js`](frontend/src/utils/canvas/castLibrarySync.js) `rowContextText` 辅助角色 @ 自动关联（非提交 prompt） |
| `segment.duration`（片段时长） | **否** | UI 展示；[`scriptDurationNormalize.js`](frontend/src/utils/canvas/scriptDurationNormalize.js) 有归一化逻辑但**未被调用方 import** |
| `segment.title`（如「夜晚」） | **否** | Excel 导入分组标记（[`excel_shot_parser.py`](backend/services/excel_shot_parser.py)）；导出作 `# 标题` 分隔；列表分组展示 |

**生成链路仅读 row 级数据**：

- 直连出图/视频：[`useScriptTableGenerate.js`](frontend/src/hooks/canvas/useScriptTableGenerate.js) → `shotPromptText(row)` + `appendDirectorFieldsToDescription`
- Prompt 包：[`scriptPromptPackage.js`](frontend/src/utils/canvas/scriptPromptPackage.js) / 后端 [`shot_prompt_package.py`](backend/services/shot_prompt_package.py) → 无 `segment` 参数

**结论**：片段字段不参与生成 prompt，属分组/展示用途；UI 为轻量分隔线（紫色 `#a78bfa` / 亮色 `#7c3aed`，**18px** 加粗标签），`segments[]` 数据结构保留。

---

## 详情：Backlog v2 + 分镜表 UX 修复（2026-06-30）

### Backlog v2 五项

| # | 任务 | 关键文件 |
|---|------|----------|
| 1 | 镜头卡：头部「拆解成多镜头」；主区「生成分镜图」+「生成视频」 | `ScriptShotCard.jsx`、`localeCanvas.js` |
| 2 | 彻底删除批量语气调整 | 删 `ScriptBatchToneModal`；`prompt.py` / `shot_prompt_package.py`；`test_storyboard_backlog.py` |
| 3 | 人物/场景库「最近使用」排序 + 分配记频次 | `libraryUsage.js`、`ScriptCastLibrary` / `ScriptSceneLibrary`、`Canvas.jsx` touch |
| 4 | 生成失败分级重试 | `generationRetryPolicy.js` → `GenerationCardNode` / `VideoGenerationNode` |
| 5 | 项目设定折叠摘要 + 描述视觉重心 + 按钮降饱和 | `ScriptTableNode.jsx/css`、`ScriptRowPromptField.css`、`ScriptShotCard.css` |

### UX 四轮 + 后续修补

| 项 | 改动 |
|----|------|
| 设定库折叠互斥 | `projectSettingsOpen` 仅包裹 `st-lib-compact`；工具栏移出折叠区 |
| 转场分隔线 | `ScriptSegmentHeader.jsx` 重写；见上节自检结论 |
| 导演参数 | `ScriptShotDirectorPanel`：`expanded` 默认 `false`，保留展开/收起与摘要行 |
| 纵向留白 | 镜头卡 padding/间距/按钮高度收紧 |
| 六点拖排序 | `st-shot-drag-handle` 改 `<div draggable>`，去掉 `mousedown preventDefault` |
| 节拍卡拖动 | `sbc-head` 去掉 `nodrag`，`cursor: grab` |
| 生成节点距离 | `SCRIPT_TABLE_WIDTH` 1100；`computeScriptTableGenX/ShotY` 统一出图列 |
| 右键菜单 | `useCanvasInteraction`：`.react-flow__node` 内不弹画布菜单；`st-root` stopPropagation |
| 设定库 chevron | `ProjectSettingsChevron` 细线 SVG（10px），非 Unicode 大三角 |

**关键文件**：

```
frontend/src/components/canvas/ScriptTableNode.jsx
frontend/src/components/canvas/ScriptShotCard.jsx
frontend/src/components/canvas/ScriptShotDirectorPanel.jsx
frontend/src/components/canvas/ScriptSegmentHeader.jsx
frontend/src/components/canvas/ScriptBeatCardNode.jsx
frontend/src/hooks/canvas/useScriptTableGenerate.js
frontend/src/hooks/canvas/useCanvasInteraction.js
frontend/src/utils/canvas/nodeHelpers.js
frontend/src/utils/canvas/libraryUsage.js
frontend/src/utils/canvas/generationRetryPolicy.js
```

**浏览器验收 checklist（含分镜表画布）**：✅ **2026-06-30 已全部通过**

- [x] 折叠态仅见设定摘要行 + 工具栏 + 镜头列表
- [x] 展开设定库后人物/场景库完整表单出现
- [x] 转场为紫色分隔线，非完整卡片
- [x] 导演参数默认收起，可展开
- [x] 镜头六点可拖排序；节拍卡标题栏可拖画布
- [x] 新生成 image-gen / video-gen 贴近分镜表右侧

---

## 详情：构图参考下线（2026-06-30）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 节拍格 UI 下线 | ✅ | `ScriptBeatTimeline` 移除「构图参考」块；格内仅分镜图预览 + 出图描述 + 台词 |
| 交互清理 | ✅ | 删除 `rowRef` 画布拾取、`handleUploadKeyframeRef`；`Canvas.jsx` 不再写入 `referenceImage` |
| 出图逻辑 | ✅ | `useScriptTableGenerate` 不再优先读 `keyframe.referenceImage`；改走角色/场景/连贯性 ref |
| 字段 deprecated | ✅ | `keyframes[].referenceImage` 保留于 JSON，JSDoc 标注废弃；历史项目可打开 |
| Prompt 文案 | ✅ | `scriptPromptPackage` / `shot_prompt_package` 去掉构图参考行 |

**图片生成卡片自检结论**：

| 问题 | 结论 |
|------|------|
| 图片生成卡片参考图机制？ | `image-gen` 节点 `referenceImages`（最多 5 张）+ Prompt Bar `RefPickerTrigger`；生成时走 img2img |
| 分镜表自动参考？ | `entityRefs.js` 解析 @角色/@场景，服务于**实体一致性**，非构图锁定 |
| 是否已有自由参考图？ | **是**，等同 ComfyUI reference image |
| 未来若补，数据挂哪？ | **`image-gen` 节点** `referenceImages`，不应回到节拍格或项目级 |

**关键文件**：

```
frontend/src/components/canvas/ScriptBeatTimeline.jsx
frontend/src/hooks/canvas/useScriptTableGenerate.js
frontend/src/utils/canvas/scriptTableKeyframes.js
backend/services/shot_prompt_package.py
```

---

## 详情：Phase 37b 镜头级视频风格参考（2026-06-30）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 镜头级 API | ✅ | 双路径 `POST/GET/PUT/DELETE /api/shots/{row_id}` + `/api/video-nodes/{node_id}`；服务端 patch `canvas_data` |
| 分析链路 | ✅ | ffmpeg + Qwen-VL + LLM 汇总；写入 `video-gen.data.styleReference`（分镜行可镜像 `row.styleReference`） |
| UI 入口 | ✅ | `VideoReferencePanel` 顶栏「风格参考」→ `VideoStyleReferencePanel`；移除 `CanvasTopbar` 项目级入口 |
| Prompt 注入 | ✅ | **仅视频**：`VideoGenerationNode` / `CanvasPromptBar` / `useScriptTableGenerate` 出视频 |
| 回滚项目级 | ✅ | 删除 `canvas_projects.style_reference`（迁移 021）；移除 canvas 四端点 + `canvasStore.styleReference` |
| 探针 / 单测 | ✅ | `_style_reference_probe.py` 双镜头隔离；`test_style_reference.py` + `test_canvas_style_ref_patch.py` |

**风格参考 — 当前形态**：

| 项 | 说明 |
|----|------|
| 粒度 | **镜头级**：canonical 在 `video-gen` 节点 `data.styleReference` |
| 入口 | `VideoReferencePanel`（Prompt Bar 选中视频节点时） |
| API | `/api/shots/{row_id}/style-reference`（需 `project_id` + `script_table_node_id`）；`/api/video-nodes/{node_id}/style-reference` |
| 注入格式 | `[风格参考：{color_tone}，{lighting}，{shot_language}]` + 英文 keywords |

**关键文件**：

```
backend/alembic/versions/021_drop_project_style_reference.py
backend/services/canvas_style_ref.py
backend/routers/style_reference.py
backend/services/style_reference_service.py
backend/scripts/_style_reference_probe.py
backend/tests/test_style_reference.py
backend/tests/test_canvas_style_ref_patch.py

frontend/src/components/canvas/VideoReferencePanel.jsx
frontend/src/components/canvas/VideoStyleReferencePanel.jsx
frontend/src/components/canvas/VideoGenerationNode.jsx
frontend/src/services/styleReferenceApi.js
frontend/src/hooks/canvas/useScriptTableGenerate.js
frontend/src/components/canvas/CanvasPromptBar.jsx
```

---

## 详情：Phase 37 项目级风格参考（已废弃）

| 模块 | 状态 | 说明 |
|------|------|------|
| Phase 37 项目级 | ❌ 已由 37b 取代 | `canvas_projects.style_reference`、顶栏 `StyleReferencePanel`、出图注入均已移除 |

迁移 **020** 曾增列，**021** 已删除。勿再使用 `/api/canvas/projects/{id}/style-reference`。

---

### 上轮对话完成项速览（2026-06-29～30 · Phase 34～38）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| **Phase 34** Prompt Bar 回归 | ✅ | 去 `nb-banner--prompt-layout` grid（`1fr` 撑高）；flex 紧凑；去紫边；视频顶栏 32px 对齐；`RefPickerTrigger` 始终 `(n/5)`；freeref 恢复 `ref-tags-scroll` |
| **Phase 35** 视频顶栏间距 | ✅ | `.nb-banner--prompt-video` 顶栏 `margin-bottom: 10px` + 媒体区 `margin-top: 4px`；slots `padding-top: 4px` |
| **Phase 35** 亮色分镜表模型栏 | ✅ | Prompt Bar 亮色覆盖限定 `.nb-banner` 内；`textWorkflowTheme` 兜底 `st-toolbar-pills .nb-model-btn-bare` 浅灰 pill |
| **Phase 35** 生成历史 | ✅ | `getCanvasTeamId()`；`list_task_records` 返回签名 `result`；Flyout 个人/团队 ⇄；`normalizeTimestamp` 修时间戳；`pushGenHistory` 带 `teamId` |
| **Phase 36** 切换动画 | ✅ | `useScopeSwitchTransition` + `ScopeSwitchPanel`；工作区/项目页团队切换卡片出入场 + 网格 stagger；资产库/历史 scope 切换动画；`prefers-reduced-motion` 降级 |
| **Phase 37** V1 探针覆盖 | ✅ | 7 个新探针 + [`V1_CANVAS_PROBE_COVERAGE.md`](backend/docs/V1_CANVAS_PROBE_COVERAGE.md)；`tasks.py` records 路由顺序修复 |
| **Phase 38** 主题切换过渡 | ✅ | `useThemeTransition` + View Transitions API 圆形扩散（250ms）；三入口：左栏菜单 / 工作区顶栏 / 资料弹窗；不支持 API 或 `prefers-reduced-motion` 瞬时降级 |
| 构建 | ✅ | `npm run build` 通过 |

**Prompt Bar 回归要点（Phase 34）**：

| 问题 | 根因 | 修复 |
|------|------|------|
| 文本/图卡中间大块白 | grid `minmax(..., 1fr)` 撑满中间行 | 删 grid；compact 改 flex；高度仅落输入区 token |
| 紫色外边框 | `.nb-banner--visible.nb-banner--compact` accent | 删除紫边/glow |
| 视频顶栏三元素不齐 | mode-tab padding + 行高不一致 | 32px 统一；active `border-bottom` |
| 参考图 `(0/5)` 不可见 | `count>0` 才显示 | `labelWithCount` + `max` 时始终显示 |
| freeref 无横向 tags | slots 区被删 | 恢复 `ref-tags-scroll` +「+」 |

**生成历史 — 当前形态（Phase 35）**：

| scope | 数据源 | 说明 |
|-------|--------|------|
| 个人 | `localStorage` + 当前画布节点 merge | 过滤 `!teamId` |
| 团队 | `GET /api/tasks/records?team_id=` | 仅 `completed` image/video 且有 `result`；全员可见 |
| 团队上下文 | `projectTeamId ?? activeTeamId` | `teamIdPayload()` / `pushGenHistory` / `fetchTaskRecords` 统一 |
| 时间戳 | `normalizeTimestamp` | 支持 ms/秒/ISO；merge 禁止 `Date.now()` 回退 |

**切换动画 — 当前形态（Phase 36）**：

| 场景 | `switchKey` | 动效 |
|------|-------------|------|
| 工作区首页 / 项目列表 | `activeTeamId \|\| 'personal'` | 出场 180ms → 入场 240ms；项目卡 `--i` stagger |
| 资产库 / 生成历史 | `scopeTab`（mine/team） | header 以下内容区同一套出入场 |
| 主题切换 | `useThemeTransition` | View Transitions 圆形扩散 250ms；与 scope 动画独立 |

**关键文件（Phase 34～36）**：

```
frontend/src/components/canvas/prompt-bar.css, PromptBarShell.jsx
frontend/src/components/canvas/VideoReferencePanel.jsx|css
frontend/src/components/canvas/RefPickerTrigger.jsx, GenerationHistoryFlyout.jsx|css
frontend/src/components/canvas/AssetLibraryFlyout.jsx
frontend/src/components/canvas/textWorkflowTheme.css
frontend/src/utils/canvas/genHistory.js, teamContext.js
frontend/src/pages/Workspace.jsx, WorkspaceProjects.jsx
frontend/src/hooks/useScopeSwitchTransition.js
frontend/src/hooks/useThemeTransition.js
frontend/src/styles/themeTransition.css
frontend/src/components/common/ScopeSwitchPanel.jsx
frontend/src/styles/scopeSwitchTransition.css
backend/routers/tasks.py                    # list_task_records + result 签名
```

**本地服务**：前端 `http://127.0.0.1:8173`；后端 `http://127.0.0.1:7788`；改前端后 **Ctrl+Shift+R**；改 `tasks.py` 后须**重启后端**。

---

### 上轮对话完成项速览（2026-06-29 · Phase 33 全产品 UI 自验 + Portal/Admin 实色统一）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 自启服务 + 浏览器走查 | ✅ | Redis/后端 `:7788`/前端 `:8173`；矩阵 A～H 亮暗截图；`UI_AUDIT.md` 无 blocker |
| 画布底栏 Batch1 | ✅ | 文本卡 `nb-banner--text` 收紧 padding；发送胶囊 `SendArrowIcon` 居中；无分隔重影 |
| 图/视频 + 分镜表 Batch2～3 | ✅ | `cell-menu-portal` 亮色实色；分镜次级钮 `#eef0f3`/`#dfe3ea`；ref-panel token |
| Portal 浮层 Batch4 | ✅ | 导出弹窗 overlay 挂 `rf-page--*`；导入/导出 modal 暗色 `rgba(16,16,20,0.98)` |
| 工作区 Batch5 | ✅ | `ws-btn-outline` 亮色浅灰底对齐横切规范 |
| Admin Batch6 | ✅ | 暗色 `--adm-surface` 0.96/0.98 实色，修复 Velora 背景叠字 |
| Join Batch7 | ✅ | 取消钮亮色次级样式与登录/工作区一致 |
| 构建 | ✅ | `npm run build` 通过 |

**关键文件（Phase 33）**：

```
UI_AUDIT.md
frontend/src/components/canvas/NodeBanner.css, ExportProjectModal.jsx|css
frontend/src/components/canvas/ImportDocumentModal.css, GenerationCardNode.css
frontend/src/components/canvas/textWorkflowTheme.css
frontend/src/pages/Workspace.css, Admin/Admin.css, JoinTeam.css
```

**本地服务**：前端 `http://127.0.0.1:8173`；后端 `http://127.0.0.1:7788`；改前端后 **Ctrl+Shift+R**。

---

### 上轮对话完成项速览（2026-06-29 · C2 移除 + 粘贴阈值 + 视觉一致）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| C2 图/视频剧本识别 | ✅ | **已拍板移除**：图/视频卡不再调 `classify-intent`、无确认弹窗；识别仅保留文本卡 |
| 意图 gate 收紧 | ✅ | `PromptIntentGateContext` 仅文本路径；删除 `promptIntentPrefs.js`（120 字跳过勾选） |
| 阈值收拢 | ✅ | `promptIntentConfig.js`：`0.6` / `PASTE_HINT_MIN=400` / `TEXT_CLASSIFY_MIN=200` / `TEXT_CONFIRM_MIN=120`；后端 `0.82` 规则兜底不收前端 |
| 文本意图弹窗 | ✅ | screenplay 时主钮「切换剧本模式」、次钮「仍要生成」；亮色主钮黑底与分镜表一致 |
| 文本卡剧本横幅 | ✅ | 琥珀提示色（对齐 `pic-warn`）；CTA 黑底主钮 |
| 图/视频卡亮色 | ✅ | `.card-model-select` → `--tl-*`；`GenerationCardNode` 生成态/缩略图栏亮色可读 |

**粘贴剧本判定 — 当前形态（2026-06-29）**：

| 路径 | 行为 |
|------|------|
| 文本卡 ≥400 字 | 内联琥珀横幅 +「切换剧本模式」 |
| 文本卡 ≥200 字点生成 | 可调 `classify-intent`；剧本意图弹窗：取消 / 仍要生成 / **切换剧本模式（主）** |
| 图/视频卡任意字数 | **不**调 classify；点生成直接提交任务 |
| 后端 API | `context=image|video` 仍保留供探针；前端不再调用 |

**前端阈值（`promptIntentConfig.js`）**：

| 常量 | 值 | 用户可见行为 |
|------|-----|--------------|
| `SCREENPLAY_CONFIDENCE_THRESHOLD` | 0.6 | 横幅 + 弹窗「像剧本」 |
| `PASTE_HINT_MIN` | 400 | 文本卡内联横幅 |
| `TEXT_CLASSIFY_MIN` | 200 | 文本卡点生成触发 gate |
| `TEXT_CONFIRM_MIN` | 120 | 低置信度时长文仍弹窗 |

**浏览器验收（亮/暗各一遍）**：
1. 图卡/视频卡粘贴长剧本 → 生成 → **0** 次 `classify-intent`
2. 文本卡 ≥400 字 → 琥珀横幅 + 黑底 CTA
3. 文本卡聊天模式 ≥200 字生成 → 弹窗三钮层级正确
4. 图卡模型下拉、生成进度文案亮色可读

**关键文件（本轮）**：

```
frontend/src/utils/canvas/promptIntentConfig.js
frontend/src/services/promptIntentApi.js
frontend/src/components/canvas/PromptIntentGateContext.jsx, PromptIntentConfirm.jsx|css
frontend/src/components/canvas/CanvasPromptBar.jsx, TextNode.jsx|css
frontend/src/components/canvas/GenerationCardNode.jsx, VideoGenerationNode.jsx
frontend/src/components/canvas/CanvasShared.css, GenerationCardNode.css
```

**本地服务**：前端 `http://127.0.0.1:8173`；后端 `http://127.0.0.1:7788`；改前端后 **Ctrl+Shift+R**。

---

### 上轮对话完成项速览（2026-06-26 · 文档导入 + Admin LLM + 模型页修复）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| Excel/Word 导入审阅 UX | ✅ | 选集页常驻「一键勾选/清除/处理选中」；审阅按钮统一；去 `sheetDisposition`、跳过项 |
| 智能划分（LLM 大镜） | ✅ | `shot_grouping_llm.py` + `POST /api/import/document/group-suggest?mode=llm`；审阅页按钮「智能划分」；单大镜 ≤15s |
| 智能划分 bug 修复 | ✅ | `_call_llm` 返回 tuple 未解构 → `'tuple' object has no attribute 'strip'`；已修 `shot_grouping_llm.py` + `import_parse_fix.py` |
| 选集页工具栏 | ✅ | `.idm-pick-toolbar` 移出 `.idm-body` 滚动区，不再 sticky 遮挡首行 |
| 大镜头色块分组 | ✅ | `.idm-macro-block` 四色交替；顶部 macro-chip 与 tone 对齐 |
| Admin 默认 LLM + 分流 | ✅ | 迁移 `019`；`llm_router.py`（固定默认 / 低价优先 / 均衡分流）；Redis 24h 用量 |
| Admin 模型 API | ✅ | `GET/PUT /api/admin/models/llm-routing`；`POST .../set-default-text`；模型单价 `input_price_per_million` |
| Admin 模型页修复 | ✅ | 静态路由提前注册（修 PUT llm-routing 422）；`formatApiError.js`；卡片/抽屉实色背景；分流面板在「全部」tab |
| 节拍构图按钮文案 | ✅ | `canvas.script.ref`：「参考」→「上传」（`ScriptBeatTimeline` → `AddRefHoverPanel`） |

**文档导入 — 审阅流程（当前形态）**：

| 步骤 | 行为 |
|------|------|
| 上传 Excel/Word | 扫描 sheet → 选集页列表 |
| 选集 | 工具栏在列表**上方**固定；列表单独滚动 |
| 审阅分镜表 | 默认一行一大镜（`identityGroups`）；可点「智能划分」触发 LLM；「恢复为表格行」回退 |
| 智能划分失败 | 回退规则划分 + 提示「智能划分不可用，已使用规则划分」 |

**Admin LLM 分流（仅后台，用户端不选模型）**：

| 模式 | 行为 |
|------|------|
| 固定默认 | 使用标记为「默认 Agent」的 text/api 模型；未设则第一个已启用 |
| 低价优先 | 已启用文本模型中 `input_price_per_million` 最低 |
| 均衡分流 | `score = 近24h_tokens × (单价/最低单价)`，选最低 |

- 图/视频模型仍由用户在画布选择；Agent、智能划分、剧本/分镜生成等走 `llm_router.resolve_text_model()`
- Admin → 模型管理 → **全部** tab 顶部可见分流面板；文本模型卡片可「设为默认」、填单价、看 24h tokens

**已知修复（勿回归）**：

| 问题 | 根因 | 修复 |
|------|------|------|
| 分流选项 422 | `PUT /llm-routing` 被 `PUT /{model_id}` 抢先匹配 | `admin_models.py` 静态路由须在 `/{model_id}` **之前** |
| React 崩溃 `Objects are not valid as a React child` | 422 的 `detail` 为对象数组直接传给 `message.error` | `formatApiError.js` |
| 编辑抽屉透明叠字 | `--adm-surface` 6% 透明 + blur | 卡片/抽屉/分流面板 `rgba(14–16,…,0.94–0.98)` |

**关键文件（本轮）**：

```
backend/services/shot_grouping_llm.py, import_parse_fix.py, llm_router.py
backend/services/qwen.py, agent_service.py          # 统一 llm_router
backend/routers/import_document.py, admin_models.py
backend/models/registered_model.py, system_setting.py
backend/alembic/versions/018_excel_import_log.py, 019_llm_routing.py
backend/scripts/_excel_import_probe.py              # --llm-group 验收

frontend/src/components/canvas/ImportDocumentModal.jsx|css
frontend/src/utils/canvas/importDocumentApply.js, importDocumentApi.js
frontend/src/pages/Admin/ModelManagement.jsx, ModelDrawer.jsx, formatApiError.js, Admin.css
frontend/src/utils/localeCanvas.js                  # import.* / script.ref
```

**探针 / 验收**：

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head   # 含 018、019
.\.venv\Scripts\python.exe scripts\_excel_import_probe.py --llm-group   # source=llm
# 智能划分需：至少一个 enabled text/api 模型 + DASHSCOPE 或注册模型 Key
```

**本地服务**：前端 `http://127.0.0.1:8173`；后端 `http://127.0.0.1:7788`；改 `admin_models.py` / `llm_router.py` 后须**重启后端**。

---

### 上轮对话完成项速览（2026-06-25 · 安全加固 + 粘贴剧本 + 输入框）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 安全审计清单 | ✅ | 产出 [`SECURITY_AUDIT_FINDINGS.md`](SECURITY_AUDIT_FINDINGS.md)（按 `SECURITY_CHECK_DIRECTION.md`） |
| 认证与种子账号 | ✅ | `SEED_*_PASSWORD` 环境变量；JWT 弱占位符黑名单；`seed.py` 不再硬编码默认密码 |
| 登录 / Agent 频控 | ✅ | `rate_limit.py`：登录 IP 限流、Agent 用户频控；Redis 优先、无 Redis 内存降级 |
| 参考图读盘 | ✅ | `media_access.assert_user_can_read_upload_url`；`upload_validation` magic bytes；uploads 路径限制 |
| CORS | ✅ | 开发端口补 `8174` |
| 安全冒烟 | ✅ | pytest 6 passed；未登录 401、非 admin 403、路径穿越 400 |
| 粘贴剧本手测 A–F | ✅ | 浏览器 MCP + XHR 监控；清单 A1–A5 / B1 / C1–C3 / D / E / F 已填（见下节） |
| 输入框撑高 bug | ✅ | 文本卡 / 底栏 MentionTextarea / nb-textarea / ShotScriptNode 统一 `max-height` + 内部滚动 |
| 粘贴判定 API 探针 | ✅ | `_paste_script_checklist_probe.py`：冒烟 + **E1 弱剧本 399/401×8 永久回归**（改 `prompt_intent.py` 后 `--only e1`） |
| 阈值统一 + 图/视频死胡同 | ✅ | `promptIntentConfig.js` 统一 `SCREENPLAY_CONFIDENCE_THRESHOLD=0.6`；弹窗 screenplay 可点「仍要生成」 |
| E1 弱剧本漂移 | ✅ | `CLASSIFY_SYSTEM` 补边界 few-shot；探针 16/16 `chat` conf=0.6（399/401 一致） |

**粘贴剧本判定 — 手测结论摘要**（对照 `PASTE_SCRIPT_DETECTION_TEST_CHECKLIST.md`）：

| 组别 | 结论 |
|------|------|
| A 文本卡 80/400 | A1 79 字无 API；A2 81 字有 `classify-intent`；A4 401 字结构化剧本出横幅（conf≥0.6）；A5 剧本模式跳过 |
| B 图/视频仅粘贴 | 不点生成 → **0** 次 `classify-intent` |
| C 图/视频点生成 | **2026-06-29 已移除**：不弹窗、**0** 次 `classify-intent`，直接生成 |
| D 横幅+弹窗 | 文本卡可同时出现卡片内横幅 + 底栏确认弹窗（体验易困惑） |
| E 弱剧本阈值 | few-shot 前 399→`screenplay` 0.9 / 401→`chat` 0.6；**已修** — 探针 E1 各 8 次均为 `chat` 0.6 |
| F LLM 失败 | `prompt_intent.py` 异常 → `_rule_classify` 兜底（`strong_screenplay` 规则 conf=0.82） |

**阈值**：前端四处常量见 `promptIntentConfig.js`（`0.6` / `400` / `200` / `120`）；规则兜底 **0.82** 仅 `prompt_intent.py` LLM 失败时。

**E1 永久回归探针**（仿 `_adversarial_regression_probe.py` 模式）：
```powershell
cd backend
$env:SEED_ADMIN_PASSWORD="…"   # 与 .env 一致
.\.venv\Scripts\python.exe scripts\_paste_script_checklist_probe.py --only e1
```
- **为何 399/401**：紧贴 `PASTE_HINT_MIN=400` 两侧，最易暴露「差两字跳戏」
- **为何各 8 次**：平衡 LLM 成本与方差；断言同字数 intent 一致、399/401 一致、全为 `chat`、conf∈[0.5, 0.75]
- **改 `prompt_intent.py` / `CLASSIFY_SYSTEM` 后必跑**；失败 exit 3

**待拍板（非 bug）**：（无 — C2 已于 2026-06-29 拍板为图/视频不做识别）

**输入框固定高度 — 改动要点**：

| 文件 | 默认上限 | 展开上限 |
|------|----------|----------|
| `MentionTextarea.css` `.mention-editor` | 160px | 320px（`--expanded`） |
| `NodeBanner.css` `.nb-textarea` / wrap | 160px | 320px |
| `TextNode.css` `.tn-content-slot` + 展示/编辑 | 240px 卡内滚动 | — |
| `ShotScriptNode` | 固定 `rows={4}` + CSS max 200px | — |

**验证**：文本卡粘贴 3000 字 `tn-root` 仍 340px；图卡底栏 `mention-editor` 720 字仍 160px 内滚。

**安全审计 — 已加固 vs 仍待确认**：

| 项 | 状态 |
|----|------|
| 种子密码 / JWT 弱密钥 | ✅ 已环境变量化 + 黑名单 |
| 登录爆破 / Agent 滥用频控 | ✅ 已加 |
| 参考图路径穿越 / 未鉴权读盘 | ✅ 已收紧 |
| 同团队可见全部历史媒体（不按 project_id） | ⚠️ **产品确认保留现状** |
| 导出 zip viewer 可下载 | ⚠️ 见 `SECURITY_AUDIT_FINDINGS.md` §1.1 |
| 公网前 | `APP_ENV=production`、强 JWT、无 seed 默认账号 |

**关键文件（本轮）**：

```
SECURITY_AUDIT_FINDINGS.md
backend/services/rate_limit.py, auth_service.py, media_access.py, upload_validation.py, seed.py
backend/services/prompt_intent.py
backend/scripts/_paste_script_checklist_probe.py   # 冒烟 + E1 399/401×8 回归
backend/scripts/_comfyui_workflow_structure_probe.py   # 前序轮次已加

frontend/src/components/canvas/
  MentionTextarea.css, NodeBanner.css, TextNode.css
  ShotScriptNode.jsx|css, VideoReferencePanel.css
  TextNode.jsx, CanvasPromptBar.jsx, PromptIntentGateContext.jsx, PromptIntentConfirm.jsx|css
frontend/src/utils/canvas/promptIntentConfig.js
frontend/src/services/promptIntentApi.js
```

**本地服务**：前端 `http://127.0.0.1:8173`；后端 `http://127.0.0.1:7788`；手测 classify 需登录 + `DASHSCOPE_API_KEY`。

---

### 同日前序轮次（2026-06-25 · 分镜表 UI + ComfyUI + E2E 回归）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| E2E 回归断言 | ✅ | `backend/scripts/_adversarial_regression_probe.py`：6 条对抗性修复用例机器可读断言 |
| HiDream 出图 workflow | ✅ | `providers/comfyui.py` → `_build_hidream_workflow` |
| Wan / Hunyuan 视频 workflow | ✅ | `comfyui/client.py` → `build_wan_video_workflow` / `build_hunyuan_video_workflow` + submit |
| 视频任务分派 | ✅ | `routers/tasks.py` 按 `video_backend`（`wan` / `ltx` / `hunyuan`）路由；`model_registry.resolve_video_backend()` |
| 分镜表 UI 一轮修复 | ✅ | 工作区主题固定太阳图标；`IconAgent` 居中 Sparkle；折叠标题 `castLib`/`sceneLib`；去内层灰底 |
| 分镜表 UI 二轮修复 | ✅ | 资产库并入 `AddRefHoverPanel`/`CanvasImageQuickPicker`；模型栏仅下拉钮有灰底；高级选项 ⓘ 说明互斥展开 |
| 分镜表 UI 三轮修复 | ✅ | 设定库紧凑圆角卡片；选图面板去底部空白；高级选项 checkbox 同行、说明在下方 |
| 分镜表 UI 四轮修复 | ✅ | 场景库去绿色改黑/中性灰；「一键生成全部」黑底主钮；亮色模式可点击项统一浅灰底 |
| 画风默认 auto | ✅ | `SCRIPT_QUALITY_PRESETS` 新增「由模型自己选择」；工具栏 + 各镜默认 `auto`；旧 `cinematic` 空 id 迁移 |
| 设定图添加入口 | ✅ | 未填名称禁用「添加设定图」；人物/场景库背景框样式统一 |

**分镜表 UI 要点（当前形态）**：
- 人物/场景设定库：各自 `st-lib-card` 圆角浅底框；标题 **人物设定库** / **场景设定库**（14px）
- 工具栏：图像/视频/默认画风 — **仅模型名下拉钮**（`nb-model-btn-bare`）有淡灰底；标签与容器透明
- 默认画风首项：**由模型自己选择**（不注入导演参数字段）；应用到全部镜头可批量同步
- 高级选项：剧情连贯 / 视觉参考上一镜 旁 ⓘ，**同时只展开一条**说明
- 亮色模式：镜头操作钮、高级选项、生成节拍、添加格等统一 `#eef0f3` 浅灰底 + 细边框

**ComfyUI workflow 覆盖更新**：

| 模型类型 | workflow 位置 | 实现状态 | 说明 |
|----------|---------------|----------|------|
| SD 1.5 / SDXL / Flux | `providers/comfyui.py` | ✅ | 已有 |
| **HiDream** | `providers/comfyui.py` | ✅ **本轮补全** | `_build_hidream_workflow` |
| LTX Video | `comfyui/client.py` | ✅ | 画布视频默认链路之一 |
| **Wan 2.6** | `comfyui/client.py` | ✅ **本轮补全** | `build_wan_video_workflow` + `submit_wan_video_prompt` |
| **HunyuanVideo** | `comfyui/client.py` | ✅ **本轮补全** | `build_hunyuan_video_workflow` + `submit_hunyuan_video_prompt` |

> 上表为**代码 workflow 已编写**；真实 GPU 验收仍待 HANDOFF **第八节 B**（服务器权重文件名可能与 registry 占位不一致，切换前对照 Runbook）。

**关键文件（本轮）**：

```
backend/providers/comfyui.py              # _build_hidream_workflow
backend/comfyui/client.py                 # Wan / Hunyuan video workflow + submit
backend/routers/tasks.py                  # video_backend 分派
backend/model_registry.py                 # resolve_video_backend()
backend/scripts/_adversarial_regression_probe.py

frontend/src/components/canvas/
  ScriptTableNode.jsx|css
  ScriptCastLibrary.jsx|css
  ScriptSceneLibrary.jsx|css
  ScriptShotCard.jsx|css
  CanvasImageQuickPicker.jsx|css
  AddRefHoverPanel.jsx
  CanvasTopbarIcons.jsx
  CanvasModelDropup.jsx
  textWorkflowTheme.css
frontend/src/components/workspace/WorkspaceTopbar.jsx
frontend/src/utils/canvas/scriptQualityPresets.js   # auto 预设 + withDefaultQualityPreset*
frontend/src/utils/localeCanvas.js                  # plotContinuityDesc 等 i18n
```

**本地服务**：前端 `http://127.0.0.1:8173`；后端 `http://127.0.0.1:7788`（mock 模式 `AGENT_MOCK_GENERATION=true`）。改 UI 后 **Ctrl+Shift+R** 硬刷新。

### 上轮对话完成项速览（2026-06-25 · 对抗性测试 + Prompt 修复）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 对抗性 Prompt 探针 | ✅ | `backend/scripts/_adversarial_prompt_probe.py`：6 类 × 3 条 = **18 用例**；逐条 `.md` + `summary.md`；支持 `--category` / `--id` |
| 首次全量跑测 | ✅ | `adversarial_results/RUN_20260625_103635`：18/18 无 HTTP/SSE 错误；**6 条 Agent 行为有问题**（已诊断） |
| Prompt 修复（根因 1～3） | ✅ | `agent_service.py`：「继续」阶段感知、多链路指代强制澄清、ask_user 门禁；SYSTEM_PROMPT few-shot + 约束 #8 |
| 代码层补强 | ✅ | `_infer_stage_from_chain`：无 `text_response` 但有 `script_table` 行时按制作阶段推断；`_previous_assistant_pending_choice` 拦截未答创意卡 |
| 探针增强 | ✅ | 记录完整 **SSE 事件流**（调试空 actions）；`run_agent(..., return_events=True)` |
| 修复后全量复跑 | ✅ | `RUN_20260625_135922`：**18/18** 无错误；原 6 条问题用例均已修复 |
| E2E 探针复跑 | ⚠️ | R1–R8 Agent 步骤正常；**R8c 视频生成 ComfyUI 超时**（环境问题，非 Prompt 回归） |

**原 6 条问题用例 → 修复后行为**：

| 用例 ID | 修复前 | 修复后 |
|---------|--------|--------|
| `cat1_continue_in_ask_user` | 误 `start_text_generation` | `done`（等待配图确认） |
| `cat1_continue_after_storyboard` | 误 `start_text_generation` | `split_shot_beats`（镜2，符合阶段二推进） |
| `cat3_regenerate_this_shot_video` | 误执行 `split_shot_beats` | `ask_user` 澄清链路/镜头 |
| `cat3_cross_chain_character_reuse` | 空 `actions[]` | `ask_user` 澄清跨链路角色 |
| `cat3_which_script_table` | 直接 `manage_cast` | `ask_user` 澄清分镜表 |
| `cat6_ignore_creative_options` | 未选创意卡就推进 | `done`（提醒先选方案） |

**根因归类**（详见对话内诊断）：
1. 「继续」短指令未读链路进度 → `_build_user_intent_context` + 意图 B few-shot
2. 多链路模糊指代直接执行 → `_multi_chain_clarify_warning` + 约束 #8
3. 创意卡门禁被绕过 → 意图 B ask_user 门禁 + `_is_advance_only_message`

**待办（非阻塞）**：~~将上述 6 条沉淀为 E2E 回归断言~~ → ✅ 已完成（`_adversarial_regression_probe.py`）。

**对抗性探针用法**：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\_adversarial_prompt_probe.py                              # 全量 18 条
.\.venv\Scripts\python.exe scripts\_adversarial_prompt_probe.py --category short_commands  # 按类
.\.venv\Scripts\python.exe scripts\_adversarial_prompt_probe.py --id cat3_cross_chain_character_reuse
```

结果目录：`backend/scripts/adversarial_results/`（`.gitignore` 忽略内容，保留 `.gitkeep`）。

**关键文件（本轮）**：

```
backend/services/agent_service.py          # SYSTEM_PROMPT、_multi_chain_clarify_warning、_infer_stage_from_chain 补强
backend/scripts/_adversarial_prompt_probe.py
backend/scripts/adversarial_cases/         # 6 类用例定义
backend/scripts/_agent_pipeline_e2e_probe.py  # run_agent return_events
```

### 上轮对话完成项速览（2026-06-24 · 验收清零 + 收尾）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| Phase 25 遗留验收 | ✅ | 分镜行拖拽/只读无把手、亮色高级选项复选框 — **双会话人工验证通过** |
| Phase 26 双账号验收 | ✅ | 编辑权三路径、@ 提及在线/离线、红点 vs 高光、评论面板体验、迁移团队 — **全部通过** |
| Phase 27 浏览器验收 | ✅ | 导出全流程、多链路选择、分享菜单明暗主题、主题切换位置、胶囊视觉 — **全部通过** |
| 导出 Modal 亮色文案 | ✅ | `.epm-single` / `.epm-empty` / `.epm-processing` 补亮色 `#1a1a1e` |
| 空态场景 chip 配色 | ⚠️ 已改 | Phase 27 为青绿；**2026-06-25 Phase 29** 分镜表场景库改回中性黑/灰，与人物库对齐 |

**当前唯一阻塞项**：ComfyUI + 百炼额度就绪后 → HANDOFF **第八节 B** 真实出图/视频 `completed` 验收。

**ComfyUI 接入预案（2026-06-25）**：Flux workflow 已实现；`COMFYUI_LOCAL_PROVIDERS` 结构化条目、`uploads/` 持久化说明、超时对照表与 Runbook 已就绪 → [backend/docs/COMFYUI_CUTOVER_RUNBOOK.md](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md)

**ComfyUI workflow 覆盖现状（勿误以为「预案 = 全部模型已就绪」）**：

| 模型类型 | workflow 位置 | 实现状态 | 说明 |
|----------|---------------|----------|------|
| SD 1.5 | `providers/comfyui.py` | ✅ 早期已有 | KSampler + CheckpointLoader |
| SDXL | `providers/comfyui.py` | ✅ 早期已有 | 同 SD 分支，`workflow_type=sdxl` |
| Flux Dev / Schnell | `providers/comfyui.py` | ✅ 2026-06-25 预案补全 | `_build_flux_workflow` |
| LTX Video | `comfyui/client.py` | ✅ 早期已有 | 画布 `POST /api/tasks/video` 链路之一 |
| HiDream | `providers/comfyui.py` | ✅ **2026-06-25 本轮补全** | `_build_hidream_workflow` |
| Wan 2.6 | `comfyui/client.py` | ✅ **2026-06-25 本轮补全** | `build_wan_video_workflow`；`tasks.py` 按 `video_backend` 分派 |
| HunyuanVideo | `comfyui/client.py` | ✅ **2026-06-25 本轮补全** | `build_hunyuan_video_workflow`；`tasks.py` 按 `video_backend` 分派 |

真实 GPU 验收仍待 HANDOFF **第八节 B**；上述「ready」仅指代码 workflow 已编写，未经服务器实测。

### 上轮对话完成项速览（2026-06-24 · 导出 + 胶囊 UI）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 完整项目导出（后端） | ✅ | `ExportJob` 异步任务；`python-docx` 生成 Word + `zipfile` 打包媒体；`POST/GET /api/exports` |
| 完整项目导出（前端） | ✅ | `ExportProjectModal` 选分镜链、轮询状态、下载 zip；分镜表三点菜单 + 顶栏分享菜单均可触发 |
| 分享菜单重构 | ✅ | `CanvasShareMenu` Portal 下拉：复制链接 / 导出项目 / 邀请成员 / 只读查看（后两项占位 `showDevNotice`） |
| 顶栏胶囊图标化 | ✅ | 同屏创作、AI 助手、分享改为纯图标；分享钮打开 `CanvasShareMenu` |
| 主题切换迁移 | ✅ | 从右上胶囊移除；迁入**左侧头像菜单**「管理后台」下方；固定 **太阳** `LineIcon sun` |
| 胶囊间距统一 | ✅ | 右胶囊对齐左工具栏：高 52px、按钮 34×34、gap 4px、padding 0 9px、圆角 9px |
| 半线分割设计 | ✅ | 左栏头像上方半横线；右胶囊在线人数旁半竖线 |
| 分享菜单主题 | ✅ | Portal 实色 fallback |
| 导出服务修复 | ✅ | `_row_prompt` NameError；**改后端须重启 uvicorn** |
| DB 迁移 | ✅ | `017_export_jobs` |

**浏览器验收（Phase 27）**：✅ 已通过（见文首本轮速览）。

**开发注意（仍有效）**：
- `CanvasShareMenu` / `ExportProjectModal` 为 Portal，样式勿只依赖 `.rf-page--*` 变量继承
- 后端 `export_service.py` 改动后必须**重启** uvicorn

**关键文件（本轮新增/重点）**：

```
backend/models/export_job.py, services/export_service.py, routers/exports.py
backend/alembic/versions/017_export_jobs.py
backend/requirements.txt  # +python-docx

frontend/src/services/exportApi.js
frontend/src/components/canvas/ExportProjectModal.jsx|css
frontend/src/components/canvas/CanvasShareMenu.jsx
frontend/src/components/canvas/CanvasTopbar.jsx, CanvasTopbarIcons.jsx
frontend/src/components/canvas/CanvasLeftToolbar.jsx
frontend/src/components/canvas/ScriptTableNode.jsx  # 三点菜单导出入口
frontend/src/components/canvas/NodeCardDotsMenu.jsx  # extraItems
frontend/src/pages/Canvas.css  # ctb-right-capsule, ctb-share-menu, clt-bottom 半线, ctb-capsule-sep--half
frontend/src/utils/locale.js, localeCanvas.js  # shareMenu / topbar.agent 等 i18n
```

### 上轮对话完成项速览（2026-06-24 · 异步协作 + 评论体验）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 主动请求编辑权 | ✅ | 查看者横幅「请求编辑权限」→ WS `edit_request`；编辑者同意/拒绝；`transfer_lock_to_user` 复用现有锁链路 |
| 评论 @ 提及 | ✅ | `mentioned_user_ids` 结构化存储；`CanvasCommentPanel` @ 选择器 |
| 通知系统 | ✅ | `notifications` 表 + `GET/POST /api/notifications`；WS `comment_mention` toast |
| 通知入口 | ✅ | `WorkspaceNotifyPanel` 真实列表；工作区/画布铃铛未读红点（外沿，非菜单内数字） |
| 通知跳转 | ✅ | 同 `project_id+node_id` 线程批量已读；跳转 `?openComment=&highlightComments=` |
| 个人画布迁移团队 | ✅ | `POST /migrate-to-team`；工作区卡片 + 画布菜单「迁移到团队」 |
| 评论未读红点 | ✅ | **他人新消息**即显示 pin/工具栏红点；自己发的消息不触发；打开面板即已读 |
| 评论 @ 高光 | ✅ | **仅 @ 当前用户**的消息灰色高光（`ccp-msg--highlight`）；与红点逻辑分离 |
| 评论资料预览 | ✅ | 点头像 → Portal 简略资料卡（昵称/邮箱/团队角色）；挂 `rf-page--dark/light` 实色背景 |
| 评论 UI 布局 | ✅ | 头像+内容列聊天气泡；收紧昵称/正文间距；打开时 **smooth** 滑到最新消息 |
| 评论其它 | ✅ | 菜单向上弹出；发评后滚到最新；`formatRelativeTime` 支持 ISO 字符串 |
| 编辑权横幅 | ✅ | 修复 `.ctb-share-banner` 层叠导致「同意/拒绝」点不了（`pointer-events`） |
| Agent 思考扫光 | ✅ | `background-clip: text` 仅扫文字，不整块闪 |
| DB 迁移 | ✅ | `016_notifications_and_mentions`（`alembic upgrade head`） |

**双账号验收（Phase 26）**：✅ 已全部通过（编辑权三路径、@ 提及、红点/高光、评论面板、迁移团队）。

**关键文件（本轮新增/重点）**：

```
backend/services/canvas_lock.py, canvas_ws_messages.py
backend/services/notification_service.py, canvas_comments.py, canvas_access.py
backend/models/notification.py, routers/notifications.py
backend/alembic/versions/016_notifications_and_mentions.py

frontend/src/utils/canvas/commentReadState.js      # 红点 vs seenMentionIds 高光
frontend/src/utils/notificationThread.js
frontend/src/hooks/useNotificationUnread.js
frontend/src/components/canvas/CanvasCommentPanel.jsx|css
frontend/src/components/canvas/CanvasCommentMarkers.jsx
frontend/src/components/workspace/WorkspaceNotifyPanel.jsx
frontend/src/components/workspace/MigrateToTeamModal.jsx
frontend/src/pages/Canvas.jsx
```

### 上轮完成项速览（2026-06-24 · 起步模板 + 探针）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 画布起步模板 | ✅ | `CanvasEmptyState` 三模板（广告短片/短剧分镜/产品介绍）→ `sendMessage` 走意图 D |
| 实体库 E2E 探针 | ✅ | `backend/scripts/_entity_library_probe.py` 覆盖 HANDOFF 第八节 C 四条 |
| Phase 25 浏览器复验 | ✅ | Admin/工作区卡片/分镜表场景库/起步模板/拖拽/亮色高级选项 — **全部通过** |
| 种子数据 | ✅ | `seed.py` 新增 `testuser2 / Test2@2026!` + 探针团队 B（团队隔离） |

### 上轮完成项速览（2026-06-23 · UI/体验）

| 模块 | 状态 | 一句话 |
|------|------|--------|
| 分镜表工具栏 | ✅ | 图像/视频/画风四选项 `fit-content` 浅色容器；高级选项亮色可读 |
| 分镜表拖拽排序 | ✅ | 自定义 MIME 防「松开搜索文本」；顶栏提示 + 列表边缘自动滚动 |
| 场景图 Popover | ✅ | `CanvasImageQuickPicker` 跟随画布 `rf-page--light/dark` 主题 |
| 场景设定库样式 | ⚠️ 已迭代 | 06-23 青绿 → **06-25 Phase 29** 中性黑/灰，与人物库统一 |
| 工作区项目卡片 | ✅ | `WorkspaceProjectCard` 已接入全览页 + 首页「我的项目」预览栏（重命名/删除） |
| Admin 管理后台视觉 | ✅ | Velora 登录同款背景 + 玻璃拟态；用户管理四按钮直出（无三点菜单） |
| Admin 主题切换 | 🗑️ | 已按产品要求移除（无实用价值） |
| Mock 出图/视频 | ✅ | 无 ComfyUI 跑通阶段二；`AGENT_MOCK_GENERATION=true` |
| 真实模型 E2E | ⏳ | 待 ComfyUI；mock 已验链路 |

**上轮已完成（仍有效）**：Mock Provider、LLM 容错、团队角色资产库、场景实体库（`scene_library` + `manage_scene`）、画布空态 Tag。

**已知小坑**：
- `Canvas.jsx` 勿重复 import `normalizeSceneLibrary` / `getActiveTeamId`；`characterCastLibrary` 从 `entityRefs.js` 导入
- 评论资料预览 Portal 挂 `body`，须带 `rf-page--dark/light` 才有主题变量（见 `MenuFlyoutPortal` 同款做法）
- `commentReadState.js`：红点看 `lastMessageId`（他人新消息）；高光看 `seenMentionIds`（仅 @）
- 分镜表创建时 React Flow 偶发 `src-right` / `tgt` handle 警告（时序问题，一般非根因）
- 改 `agent_service.py` 等后端需**重启**；前端改完 **Ctrl+Shift+R** 硬刷新
- E2E 探针用 **admin / Admin@2026!**（testuser 无 canvas project）
- 个人画布 `team_id=NULL` 仅创建者可见；`probe-*` 为实体库 E2E 探针自动创建的项目名前缀

### 本地开发注意

- **Redis 必开**：`REDIS_URL=redis://:密码@127.0.0.1:6379/0`；未开则登录慢、协作/Agent 异常
- **种子账号**：`admin` / `testuser` / `testuser2` 密码由 **`SEED_ADMIN_PASSWORD` / `SEED_TESTUSER_PASSWORD` / `SEED_TESTUSER2_PASSWORD`** 注入（见 `backend/.env.example`）；本地默认仍为 `Admin@2026!` 等若已在 `.env` 配置；**E2E 探针用 admin**
- **服务**：前端 `:8173`，后端 `:7788`；改 Agent 后端需**重启**（含 `/api/agent/chat-title`）；前端 **Ctrl+Shift+R** 硬刷新
- **DB 迁移**：`cd backend && .venv\Scripts\python.exe -m alembic upgrade head`（含 013～019；018 `excel_import_log`；019 `llm_routing`）
- **Mock 出图/视频（无 ComfyUI）**：启动后端前设 `AGENT_MOCK_GENERATION=true`；可选 `AGENT_MOCK_FAILURE_RATE=0.1` 测失败 UX
- **探测脚本**（可选，开发辅助）：
  - 覆盖全景文档：**[`backend/docs/V1_CANVAS_PROBE_COVERAGE.md`](backend/docs/V1_CANVAS_PROBE_COVERAGE.md)**
  - 全链路 Agent 意图：`backend/scripts/_agent_pipeline_e2e_probe.py --skip-text admin "Admin@2026!"`
  - **对抗性 Prompt 批量记录**：`backend/scripts/_adversarial_prompt_probe.py`（`--category` / `--id`；依赖真实 LLM）
  - 阶段二 mock 媒体专项（推荐）：`backend/scripts/_mock_pipeline_stage2_probe.py`
  - 实体库/跨项目资产专项：`backend/scripts/_entity_library_probe.py`
  - mock API 冒烟：`backend/scripts/_mock_generation_acceptance.py`（`--with-failure` 需 `AGENT_MOCK_FAILURE_RATE=1`）
  - **V1 新增 mock 探针（2026-06-30）**：
    - `_export_project_probe.py` — 完整项目导出 zip/docx
    - `_import_document_http_probe.py` — Excel 导入 scan/parse/apply HTTP
    - `_video_keyframe_mode_probe.py` — 视频首尾帧 mock
    - `_collab_api_probe.py` — 评论@通知、迁移团队、编辑锁
    - `_task_records_probe.py` — 团队生成历史 `GET /api/tasks/records`
    - `_admin_llm_routing_probe.py` — Admin LLM 分流 GET/PUT
    - `_real_media_pipeline_probe.py` — 真实 GPU（mock 开启时 exit 2 SKIP）
  - `_style_reference_probe.py` — 镜头级风格参考（video-node + row 双路径；`--with-upload` 需 VL）
  - `_video_enhance_probe.py` — 视频画质增强 mock 全链路 + recommend API（2026-07-02）
  - `_lut_probe.py` — 全片 LUT：内置 .cube + mock `video-lut`（需 ffmpeg；2026-07-02）
  - **ComfyUI workflow 结构校验**（不需 GPU 推理）：`backend/scripts/_comfyui_workflow_structure_probe.py`（`--model hidream|wan|hunyuan|all`；需 ComfyUI 已启动 + 占位权重）
  - **粘贴剧本判定 API 探针**：`backend/scripts/_paste_script_checklist_probe.py`（冒烟 + E1 弱剧本 399/401 各 8 次回归；`--only e1` / `--e1-runs N` / `--json`；改 `prompt_intent.py` 后优先跑；需 `SEED_ADMIN_PASSWORD`）
  - 占位素材生成：`backend/scripts/generate_mock_assets.py`
- **画布缩放**：默认滚轮平移；**Ctrl+滚轮** 缩放（`canvasScrollHelpers.js`）

### 占位功能 — 永久不实现

| 入口 | 说明 |
|------|------|
| 邀请成员 / 只读查看 | 分享菜单 `CanvasShareMenu` → `showDevNotice` |
| 同屏创作 | 顶栏胶囊 → `showDevNotice` |
| 加号菜单 | 附件/头脑风暴/技能/思考等级 → `showDevNotice` |
| 充值/升级/账单 | 工作区占位 → `showDevNotice` |
| 画布空态「音频」 | **已删除**（不做音频快捷入口） |

仅「从画布添加」参考图（`refSelect`）为已实现项。画布空态 **角色/场景** tag 已接资产库 Flyout（非占位）。

### Phase 27 — 完整项目导出 + 顶栏/左栏胶囊 UI（2026-06-24，✅ **已验收**）

#### A. 完整项目导出

| 项 | 说明 |
|----|------|
| 数据模型 | `export_jobs`：`project_id`、`script_table_node_id`、`status`、`file_path`、`error_message` |
| 异步执行 | `asyncio.create_task(run_export_job)`；状态 `pending → processing → completed/failed` |
| 产物 | Word（大纲 + 分镜表文字/提示词 + 嵌入分镜图）+ zip 内 `media/` 图片与视频 |
| API | `POST /api/exports`；`GET /api/exports/{id}`；`GET /api/exports/{id}/download` |
| 前端入口 | 顶栏分享菜单「导出项目」；分镜表 `NodeCardDotsMenu` → `extraItems` |
| 依赖 | `python-docx`；`uploads/exports/` 目录（`main.py` 启动时创建） |

#### B. 顶栏分享与胶囊

| 项 | 说明 |
|----|------|
| `CanvasShareMenu` | Portal 下拉；复制链接 / 导出 / 邀请 / 只读（后两项占位）；左对齐 + 菜单左缘对齐分享钮（2026-07-02） |
| 图标化 | `IconCollabScreen`、`IconAgent`、`IconShare`（`CanvasTopbarIcons.jsx`） |
| 右胶囊样式 | 高 52px、按钮 34px、gap 4px；`ctb-capsule-sep` 默认隐藏 |
| 半竖线 | 仅在线人数 `CanvasPresenceBar` 后：`ctb-capsule-sep--half`（高 22px） |
| Portal 主题 | `.ctb-share-menu` 明暗实色背景（勿仅靠 CSS 变量继承） |

#### C. 左栏头像菜单与主题

| 项 | 说明 |
|----|------|
| 主题位置 | 自 `CanvasTopbar` 移除；在 `CanvasLeftToolbar` 头像菜单「管理后台」下 |
| 主题图标 | 固定 `LineIcon name="sun"`；文案 `canvas.topbar.themeLight/Dark` |
| 半横线 | `clt-bottom::before` 宽 22px 居中，替代全宽 `border-top` |

**浏览器验收（Phase 27）**：✅ 导出全流程、多链路选择、分享菜单明暗主题、主题切换位置、胶囊半线/间距 — 已通过。

**关键文件**：见文首「上轮对话完成项速览」关键文件列表。

### Phase 26 — 异步协作 + 评论/通知体验（2026-06-24，✅ **已验收**）

#### A. 后端

| 项 | 说明 |
|----|------|
| 编辑权请求 | `canvas_lock.py`：`edit_request` / `edit_request_resolved` WS；30s 超时；`transfer_lock_to_user` |
| 通知 | `notifications` 表；`comment_mention` 类型；`notification_service.py` |
| 评论 @ | `canvas_comments.py`：`mentioned_user_ids` JSON；发帖时创建通知 + WS 广播 |
| 迁移团队 | `canvas_access.py`：`migrate_project_to_team`；`POST .../migrate-to-team` |

#### B. 评论 UX（`CanvasCommentPanel` / `commentReadState.js`）

| 项 | 说明 |
|----|------|
| 未读红点 | 自上次打开后**他人**新消息 → pin + 左工具栏评论钮红点（~7px `#ff5a5f`） |
| @ 高光 | 仅 `mentioned_user_ids` 含当前用户且未在 `seenMentionIds` 的消息；打开面板不清高光，~3.2s 后记入已看 |
| 打开滚动 | 首次打开/切卡片 → `scrollIntoView({ behavior: 'smooth' })` 滑到最新；非瞬间跳底 |
| 布局 | `ccp-msg` = 头像列 + 内容列（昵称·时间 / 正文）；去掉正文 `margin-left: 32px` |
| 资料预览 | 点头像 → `CommentAuthorPreview` Portal + 主题实色背景 |
| 已读存储 | `localStorage` `canvas-comment-seen:{projectId}` per node |

#### C. 通知与工作区

| 项 | 说明 |
|----|------|
| 铃铛红点 | `useNotificationUnread` + WS；工作区 `WorkspaceUserMenu`、画布顶栏外沿红点 |
| 通知面板 | `WorkspaceNotifyPanel` 列表；同线程 `markThreadNotificationsRead` 批量已读 |
| 跳转画布 | `?openComment={nodeId}&highlightComments={ids}` |
| 迁移团队 | `MigrateToTeamModal`；`WorkspaceProjectCard` + 画布菜单入口 |

**双账号验收（Phase 26）**：✅ 编辑权（同意/拒绝/超时）、@ 提及（在线 toast + 离线通知 + 跳转高光）、未读红点 vs @ 高光分离、评论面板（平滑滚底/资料预览）、迁移到团队 — 已通过。

### Phase 25 — 分镜表 UI 深化 + 工作区卡片 + Admin 视觉（2026-06-23，✅ **已验收**）

三模块体验升级（方向 A/B/C）+ 用户反馈迭代。

#### A. 分镜表（`ScriptTableNode` / `ScriptShotCard`）

| 项 | 说明 |
|----|------|
| 场景设定库 | 独立 `ScriptSceneLibrary.jsx` + CSS；折叠区在角色库下方；与分镜行「场景」下拉、`locationId` 打通 |
| 工具栏布局 | `st-toolbar-pills`：`fit-content` 容器仅包裹图像/视频/画风/应用到全部；右侧独立放「一键生成」「高级选项」 |
| 亮色主题 | 高级选项复选框（剧情连贯/视觉参考）改用 `var(--tl-text-primary)`，不再白字不可见 |
| 行拖拽排序 | 左侧六点把手 `st-shot-drag-handle`；`application/x-st-shot-reorder` MIME（**禁止** `text/plain`，否则 Electron 显示「松开搜索文本」） |
| 拖拽 UX | 拖动时顶栏 Portal 提示「拖动镜头调整顺序，松开放置」；列表 `shotListRef` 边缘 72px 自动上下滚动 |
| 操作栏 | 分镜卡主操作 +「更多」菜单；导演参数区 `ScriptShotDirectorPanel` |
| Bug 修复 | 补 `redistributeKeyframeTimes` import（否则拆分节拍运行时 ReferenceError） |

**拖拽把手位置**：每个分镜卡片**最左侧**竖排六点图标；按住上下拖调整镜头顺序；只读模式不显示。

#### B. Admin 管理后台（`pages/Admin/`，非遗留 `AdminPage.jsx`）

| 项 | 说明 |
|----|------|
| 背景 | `VeloraShellBackground` + `velora-brand.css`，与登录页严格一致 |
| 风格 | 玻璃拟态侧栏/卡片；青绿渐变主色；SVG 导航图标 + 侧栏折叠 |
| 用户管理 | 卡片行布局；**编辑配额 / 升降管理员 / 禁用启用 / 模型权限** 四按钮直出（已去掉三点省略菜单） |
| 概览 | `Dashboard` 六统计卡 + 最近任务动态（后端 `AdminOverviewResponse` 扩展字段） |
| 任务监控 | 提示词展开、强制取消、暂停自动刷新 |
| 范围 | **仅改样式与展示布局**；API / Modal / 分页等业务逻辑未动 |
| 已移除 | 管理后台主题切换按钮（用户要求删除） |

#### C. 工作区项目卡片

| 项 | 说明 |
|----|------|
| 组件 | `WorkspaceProjectCard.jsx`：hover 三点菜单、重命名、删除确认 Modal |
| 全览页 | `WorkspaceProjects.jsx`：网格卡片 + 末尾「+ 新建项目」+ 空状态按钮 |
| 首页预览 | `Workspace.jsx`「我的项目」`ws-project-grid` 已接入同一组件（`variant="preview"`） |
| 样式 | `Workspace.css`：`.ws-project-card` 与 `.ws-grid-card` 共用菜单 hover 规则 |

#### 其他 UI 修复（同轮）

| 项 | 文件 |
|----|------|
| 场景选图 Popover 主题 | `CanvasImageQuickPicker.jsx` + CSS；Portal 挂 `rf-page--${theme}` |
| 场景库配色 | `ScriptSceneLibrary.css`：金/黄 → 青绿 `#34d399` |
| 空态场景 chip | `Canvas.css` `.tl-empty-chip--scene` 青绿 `#34d399`，与场景库一致 |

**浏览器验收（Phase 25）**：✅ 分镜行拖拽/边缘自动滚动、只读查看者无拖拽把手（双会话）、亮色高级选项复选框可读、Admin/工作区卡片 — 已通过。

**关键文件**：

```
frontend/src/components/canvas/ScriptTableNode.jsx|css
frontend/src/components/canvas/ScriptShotCard.jsx|css
frontend/src/components/canvas/ScriptSceneLibrary.jsx|css
frontend/src/components/canvas/CanvasImageQuickPicker.jsx|css
frontend/src/components/canvas/textWorkflowTheme.css
frontend/src/components/workspace/WorkspaceProjectCard.jsx
frontend/src/pages/Workspace.jsx, WorkspaceProjects.jsx, Workspace.css
frontend/src/pages/Admin/AdminLayout.jsx, Admin.css, UserManagement.jsx, Dashboard.jsx
frontend/src/utils/localeCanvas.js  # script.dragShotDropHint 等
backend/routers/admin.py, schemas/admin.py  # 概览扩展字段
```

---

## 零、当前进度摘要

### Mock Generation Provider — 阶段二 E2E 桥梁（2026-06-23，✅ **已实现 + API 验收**）

ComfyUI/GPU 未就绪前，用 **mock provider** 跑通出图/视频 `pending → completed` 状态机；接口形状与真实 provider 一致，**零前端改动**。真实模型接入后仅需 `AGENT_MOCK_GENERATION=false`。

| 项 | 说明 |
|----|------|
| 开关 | `AGENT_MOCK_GENERATION=true\|false`（默认 false）；`AGENT_MOCK_FAILURE_RATE=0～1`（模拟失败，默认 0） |
| 拦截点 | `routers/tasks.py` 的 `canvas_image_task` / `canvas_video_task`；`comfyui_prompt_id="mock"` |
| 核心逻辑 | `services/mock_generation.py`：`asyncio.sleep` + 复制 `assets/mock/` 占位素材 → `uploads/images|videos/` |
| 轮询兼容 | `get_task_by_id`：image/video completed 短路；mock 任务跳过 ComfyUI 轮询 |
| reference_images | mock 出图原样接收并写入任务 `prompt_text` 末尾标记（`mock_reference_images` JSON） |
| 并发槽位 | mock 任务终态时调用 `release_slots`（与真实链路 `_mark_task_terminal` 一致） |
| 占位素材 | 6 张 PNG + 2 个 MP4（`scripts/generate_mock_assets.py`；视频生成依赖 `imageio-ffmpeg` 可选） |

**2026-06-23 验收结果**（后端 `AGENT_MOCK_GENERATION=true`，无需 ComfyUI）：

| 探针 | 结果 | 说明 |
|------|------|------|
| `_mock_generation_acceptance.py` | ✅ PASS | 单次 mock 出图 ~2–4s、视频 ~5–10s → `completed`；URL 带 media ticket |
| `_mock_pipeline_stage2_probe.py` | ✅ PASS | 2 镜：R6 镜1 出图 → R7 镜1 视频 → R8 镜2 出图 → R8c 镜2 视频，均 `completed` |
| `AGENT_MOCK_FAILURE_RATE=1` | ✅ PASS | 任务 `failed`，error=`Mock 模拟失败（AGENT_MOCK_FAILURE_RATE）` |
| `_agent_pipeline_e2e_probe.py --skip-text` | ⚠️ 部分 | 首次跑通 R1–R7 mock 出图/视频；R8 Agent 正确返回镜2 `generate_storyboard`（一镜一步）；第二次因 **R3 LLM Connection error** 连锁失败（与 mock 无关） |

**附带修复（验收过程中）**：`routers/admin_models.py` 补缺失 `router` 定义（否则后端无法启动）；`media_access.py` 允许 `videos/` 上传路径。

**临时性**：代码内标注 `# MOCK PROVIDER — 移除时机：ComfyUI 真实模型接入后`。

### LLM 调用容错（2026-06-23，✅ **已实现**）

触发：E2E 探针第二轮 R3 出现 `Connection error` 导致连锁失败。在 **LLM 请求层** 加指数退避重试，不扩散到 pipeline。

| 项 | 说明 |
|----|------|
| 重试范围 | 仅 `run_agent_stream` 内 `chat.completions.create` + 流式收包；**已开始向前端吐 LLM 内容后不再重试** |
| 策略 | 默认最多 3 次；退避 1s → 2s → 4s；429 至少等 3s |
| 可重试 | 连接/超时/5xx/429 |
| 不可重试 | 401/400 — 立即失败 |
| 用户文案 | 网络类「网络波动，请重试」；服务类「AI 服务暂时不可用，请稍后再试」（不暴露裸异常） |
| 重试提示 | SSE `status_delta`：`→ 连接波动，正在重试（2/3）…`（重置前端 idle 计时） |
| 前端 | `error` 事件：`isRunning` 复位；保留已流出的 thinking 为 assistant 消息；错误条带「重试」按钮 |
| 配置 | `AGENT_LLM_MAX_RETRIES=3`、`AGENT_LLM_RETRY_BASE_DELAY=1.0` |
| 文件 | `services/llm_resilience.py`、`agent_service.py`、`useCanvasAgent.js`、`AgentPanel.jsx` |

### 角色资产库跨项目（2026-06-23，✅ **Phase 1 已实现**）

目标：角色形象从单项目 `cast_library` 升级为**团队级可复用资产**；新项目 Agent `CastPendingCard` 可选用其他项目存过的角色。

| 项 | 说明 |
|----|------|
| 数据模型 | **复用现有 `user_assets` 表**（`team_id` + `kind=character|scene`），未新建 `team_cast_assets` 表 |
| API | 现有 `GET/POST/PATCH/DELETE /api/assets?team_id=`；团队成员鉴权 `_resolve_team_scope` |
| CastPendingCard 资产库 | 数据源改为 `fetchTeamAssets`（`projectTeamId ?? getActiveTeamId()`）；仅展示人物/场景类 |
| 保存为常用角色 | 画布/本地上传 popover 底部勾选（默认不勾选）→ `addAssetFromUrl` 写入团队库 |
| globalAssetId | 从资产库选用或保存成功后，`patchCastImage` 写入 `cast_library.globalAssetId` |
| 管理入口 | 画布左侧 **资产库 Flyout**（`AssetLibraryFlyout`）→ 团队 tab，可浏览/重命名/删除 |
| 鉴权 | `media_access.py` 按 user/teammate + Task.result，**不按 project_id**；团队 upload 队友可访问 |
| 文件 | `AgentPanel.jsx`、`AgentCreativeCards.jsx`、`ScriptCastLibrary.jsx`、`useRefSelectMode.js`、`Canvas.jsx` |

**验收清单**（手动，无需 ComfyUI）：

1. 项目 A：Agent 触发 `cast_pending` → 上传/画布配图并勾选「保存为常用角色」
2. 项目 B（同团队）：`CastPendingCard` → 从资产库 → 可见项目 A 存的角色 → 选用后节点有图 + `globalAssetId`
3. 异团队账号：资产库列表不可见
4. 在 Flyout 删除/重命名团队资产：已引用项目的节点 URL **不受影响**（快照 URL 独立）

### 场景实体库（2026-06-23，✅ **Phase 1 已实现**）

目标：场景复用角色库同一套注入机制；`cast_library` 专指角色，新增平行 `scene_library` + 分镜行 `location_id`。

| 项 | 说明 |
|----|------|
| 数据 | 分镜表节点 `data.sceneLibrary[]`（与 castLibrary 同结构）；行 `locationId` 指向场景实体 |
| Agent | 独立 action **`manage_scene`**（不用 manage_cast 加场景）；`scene_pending` + **`ScenePendingCard`** |
| 镜头绑定 | `manage_scene.row_assignments` 或分镜卡「场景」下拉手动指定 |
| 出图注入 | `entityRefs.js`：`resolveCharacterRefsForRow`（文本匹配）+ `resolveSceneRefsForRow`（locationId + 文本）；`useScriptTableGenerate` 合并 reference_images（角色最多 3 + 场景 1） |
| Prompt 包 | `entity_refs.py` / `scriptPromptPackage.js` 共用 entityLines |
| 画布选图 | `refSelect` → `sceneAssign:{sceneId}`（与 castAssign 平行） |
| 团队资产 | kind=`scene`；保存勾选文案「保存为常用场景…」 |
| 视觉区分 | 角色蓝边/人形徽标；场景青绿边/地点徽标；资产库 Flyout 缩略图 outline |

**验收**（mock 环境只验链路）：manage_scene → ScenePendingCard 配图 → 多镜 locationId → 出图任务 reference_images 含角色+场景 URL。

**关键文件**：`sceneLibrary.js`、`entityRefs.js`、`entity_refs.py`、`agentPipeline.js`（manage_scene）、`AgentCreativeCards.jsx`（ScenePendingCard）、`agent_service.py`（Prompt 段）。

**注意**：`manage_cast` 仅写角色；场景一律 `manage_scene`。历史 `cast_library` 内 `type=scene` 在注入时被过滤。

### 画布空态快捷 Tag（2026-06-23，✅ **已实现**）

空画布 `CanvasEmptyState` 五 pill：**角色 / 场景 / 视频 / 图片 / 文本**。

| Tag | 点击 |
|-----|------|
| 角色 | 打开资产库 → 主体库 → 人物 |
| 场景 | 打开资产库 → 主体库 → 场景 |
| 视频/图片/文本 | 快速创建对应节点 |

- 已删「音频」tag；五 chip 统一淡色边框（蓝/金/紫/绿/灰）
- `canvasStore.openAssetLibrary(pref)` → `AssetLibraryFlyout` 应用一次性筛选

### P1-1 — 短指令走 LLM 验证（2026-06-22，✅ **已 API + 浏览器验证**）

| 项 | 说明 |
|----|------|
| 直执已禁用 | `resolveAgentUserCommand` 恒返回 `null`；「继续」走 SSE → `thinking` / `pipeline_step` |
| Manual 采纳门禁 | 执行后 `reviewRoundId` 锁定输入框；占位「请先采纳并继续，或撤销上一步…」；采纳条可见 |
| 无直执文案 | 不出现 `✓ 已识别指令`（仅 `directCmd` 分支才有） |
| 探测脚本 | `_agent_pipeline_e2e_probe.py` 支持 R1 创意卡 → R1b 选方案；R1–R8 意图全通过 |
| Schema 修复 | `CanvasNodeSnapshot` 补 `rows_summary` / `row_count`，修复阶段二链路进度误判 |

### P1-2-lite — Agent 深化（2026-06-22，✅ **已自测验收**）

维护者已在真实画布环境完成 Manual / Auto、阶段二意图、分析类意图、角色配图等自测；**不以** `_agent_pipeline_e2e_probe.py` 跑绿为准。

| 项 | 说明 |
|----|------|
| Manual 采纳门禁 | 思考过程 + 采纳条 + 输入框锁定；无 `✓ 已识别指令` |
| Auto 模式 | `executionMode=auto` 时 `ap-review-bar` 在输入框上方；「采纳并继续」自动链式「继续」 |
| 阶段二意图 | 继续 → 节拍 / 出图 / 视频；多镜 batch 进度与 `inferProductionStage` 一致 |
| 意图 A | 「帮我分析分镜进度」仅 `done`，无 `pipeline_step` |
| manage_cast | 添加角色 → `CastPendingCard` 三入口配图（画布 / 上传 / 资产库） |
| 无模型失败 UX | 出图/视频不可用时 `skipNotes` 覆盖乐观摘要，显示真实错误 |
| Schema | `CanvasNodeSnapshot` 含 `rows_summary` / `row_count`（阶段二进度不误判） |

**阶段二进度模型**：`inferProductionStage` / `_production_stage_hint` 为**分批**——先全部镜拆节拍 → 再全部镜出分镜图 → 再全部镜出视频（非严格「一镜走完再走下一镜」）。

**开发注意**：修改 `backend/` 触发热重载时，若日志停在 `Waiting for connections to close`，需**手动重启后端**（否则 `/api/auth/login` 会超时）。

### Phase 22 — Agent UI 微打磨 + 全屏二轮 + 思考扫光（2026-06-22，✅ **已浏览器验证**）

| # | 问题 | 修复要点 | 关键文件 |
|---|------|----------|----------|
| 1 | 历史页 header | 左上角仅「← 返回」；去掉「聊天记录」标题；右侧 `+`/聊天/× **始终显示**（不覆盖） | `AgentPanel.jsx` |
| 2 | 历史 hover 竖线 | 「由此开启新对话」与删除按钮去掉 `border-left` 竖线；`overflow: visible` + `max-width` 滑出 | `AgentPanel.css` |
| 3 | 历史列表滚动 | 打开历史页滚到**顶部**（`messagesScrollRef`）；对话模式仍滚到底 | `AgentPanel.jsx` |
| 4 | 全屏 FAB + 去 × | 全屏恢复 `.canvas-agent-fab`；隐藏 `ref-select-banner`/`comment-select-banner`/浮层 `image-viewer` | `Canvas.css` |
| 5 | 为 TA 选图缩小 | `ap-cast-pick-btn`：`padding 2px 8px`、`font-size 11px` | `AgentPanel.css` |
| 6 | + 号对齐 | `.ap-composer__plus`：`margin-top 2px` + `align-self: flex-end` | `AgentPanel.css` |
| 7 | 思考中扫光 | `.ap-thoughts--live` / `.ap-thinking-status` 白光 `ap-shimmer` 动画 | `AgentPanel.css` |

### Phase 21 — 聊天记录重设计 + 配图 Popover + 全屏一轮（2026-06-22，✅ **已浏览器验证**）

| # | 问题 | 修复要点 | 关键文件 |
|---|------|----------|----------|
| 1 | CastPendingCard | 「为 TA 选图」改 Portal 悬浮 Popover；去 ✦ 星号；`width: fit-content`；亮色主题 `body:has(.rf-page--light)` | `AgentCreativeCards.jsx`, `AgentPanel.css` |
| 2 | 聊天记录页 | hover 滑出删除 +「由此开启新对话」；用户消息右下角分支入口；`formatRelativeTime`；活跃会话 `updatedAt` 不再每次 `Date.now()` | `AgentPanel.jsx/css`, `agentChatHistory.js` |
| 3 | AI 标题 | `POST /api/agent/chat-title`；`saveAgentChatHistory` 后异步 LLM 生成标题；`agent-chat-title-updated` 事件刷新列表 | `agent_service.py`, `agentApi.js`, `agentChatHistory.js` |
| 4 | 分支对话 | `startNewChatFromHistory` / `startNewChatFromMessage`：归档当前会话后从指定点分支 | `useCanvasAgent.js` |
| 5 | assistant 无背景 | `.ap-msg--assistant` 透明无描边；suggestion pill 背景淡化 | `AgentPanel.css` |
| 6 | 全屏一轮 | **双重全屏**：`requestFullscreen()` + `rf-page--fullscreen` CSS；`fullscreenchange` 同步退出；画布可操作、Agent 侧栏可见；边缘 hover 显顶/底栏 | `Canvas.jsx`, `Canvas.css` |

**验证要点**：历史页仅「← 返回」+ 右侧 icon；打开历史从顶部开始；hover 无竖线裁剪；全屏右下角 FAB 可见、无画布中央 stray ×；Popover 随滚动定位；思考中有扫光。

### Phase 20 — 五问题 UI/保存/全屏修复（2026-06-22，✅ **已浏览器验证**）

| # | 问题 | 修复要点 | 关键文件 |
|---|------|----------|----------|
| 1 | AgentPanel ask_user Banner | 仅纯文字 ask 保留 `ap-msg--ask` 蓝竖条；`castPending` 的「现在配图/先跳过」改 `ap-suggestion-item` pill；`.ap-cast-pending` 用语义色变量（亮色可读） | `AgentPanel.jsx/css`, `AgentCreativeCards.jsx` |
| 2 | 「为 TA 选图」三选项 | `CastPendingCard` 展开：画布选择 / 本地上传 / 资产库；`handleAssignFromCanvas/Upload/Asset` | `AgentCreativeCards.jsx`, `AgentPanel.jsx` |
| 3 | 三点菜单灰底 | `ncd-dots-btn` / `gn2-dots-btn` / `cell-dots-btn` 默认透明，hover 才显背景 | `NodeCardDotsMenu.css`, `GenerationCardNode.css`, `VideoGenerationNode.css`, `textWorkflowTheme.css` |
| 4 | 保存时间与修改者 | `prevSnapshotRef` 内容比对，无变化不保存；顶栏去绿色「已保存」；文案「修改于 {time} · 由 {who} 修改」；后端 `last_modified_by`（迁移 015）；`formatRelativeTime` 时区偏差 fallback | `useCanvasSave.js`, `CanvasTopbar.jsx`, `canvasStore.js`, `canvas.py`, `canvas_project.py` |
| 5 | 全屏模式（初版） | 左工具栏全屏钮；后被 Phase 21/22 改为双重全屏 + FAB 恢复 | `Canvas.jsx`, `CanvasLeftToolbar.jsx`, `Canvas.css` |

**验证要点**：亮色 CastPendingCard 可读；保存后顶栏显示修改者与相对时间；三点菜单无默认灰底。

### Phase 19 — 角色一致性增强（2026-06-22，✅ **已浏览器验证**）

| 项 | 说明 |
|----|------|
| `cast_library` 序列化 | `serializeCanvasForAgent.js` + `CanvasNodeSnapshot.cast_library`；Agent 可读分镜表角色库 |
| `manage_cast` pipeline | `agentPipeline.js` `case "manage_cast"`：add/update `castLibrary`；`agent_service.py` Prompt 规则 |
| `CastPendingCard` | `ask_user.cast_pending` + `manage_cast` 后引导配图；`useCanvasAgent.js` 持久化 `castPending` |
| 多角色 `reference_images` | 出图/视频 prompt 包携带 `cast_library`（`shot_prompt_package.py`、`split_shot_beats.py`） |
| 画布选图绑定 | `refSelect` 模式 `castAssign:{castId}` → `patchCastImage` 写回节点 |

### Phase 18 — Agent 逻辑/布局/UI 打磨（2026-06-18，✅ **已浏览器验证**）

#### 18a Agent UI 多轮优化

| 项 | 说明 |
|----|------|
| 思考块 | `AgentThoughtBlock`：▼ 在「思考过程」文字**前**；正文正常换行；历史 `thinking` 在气泡外 |
| 消息持久化 | `AgentStoredMessage` 补 `creativeOptions` / `suggestions` / `thinking` / `creativeGroupTitle` 等，刷新不丢 |
| 停止钮 | `IconStop`：白圆底 + 方块 SVG（20×20，方块 10×10） |
| 采纳钮 | `IconContinue`：双右箭头 SVG（`ReviewActions`） |
| Suggestions | ✦ 在 pill **外**、垂直列表、宽度随文字、去掉箭头；✦ `16px` |
| 创意卡布局 | `.ap-messages` 对称 `padding: 16px`；`.ap-msg-wrap--assistant.ap-msg-wrap--creative` `stretch` + `width:100%`，消除右侧大块留白 |
| 消息区边距 | `.ap-messages` 去掉仅左侧 padding 的不对称写法（`16px 0 16px 16px` → `16px`） |

#### 18b Agent 逻辑与布局修复

| 问题 | 修复 |
|------|------|
| 第一次选方案显示「已创建」但无新卡 | `buildCreateTextNotePromptFromUserMessage` 扩展：无引号 `我选择：xxx`、侧重提取、整段 fallback；`done` 时 `executed===0` 且有 `pipeline_step` 则用 `skipNotes` 覆盖 LLM 乐观 summary |
| 分镜表总在上下而非右侧 | `finalizeAgentLayout` **移除** `applyAgentCanvasLayout`（不再调 `organizeCanvasNodes` 从 0,0 全量重排） |
| 分镜表完成后「继续」又生成一次 | `generateScriptTable` 幂等：已有 rows/segments 直接返回 ok；后端 `_build_active_chain` 增 `source_outline_id` / `linked_script_table_id` 回退 |
| 后端快照缺字段 | `serializeCanvasForAgent.js` + `CanvasNodeSnapshot` 补 `source_outline_id`、`linked_script_table_id` |
| LLM 空声称已创建 | `agent_service.py`「我选择」意图注入：禁止仅用 `done` 声称已创建，必须先 `pipeline_step: create_text_note` 且 `prompt` 非空 |

#### 18c 继续指令行为变更

| 项 | 说明 |
|----|------|
| 短指令不再直执 | `resolveAgentUserCommand()` **恒返回 `null`**；「继续」「生成节拍」等一律走 LLM 分析画布 → manual/auto 确认后再执行 |
| 保留工具函数 | `inferContinueAction` / `buildPipelineAction` 等仍供 `runPipelineStep` 使用 |

### Phase 17 — Agent UI/多主题 + 文本链路加号拖线（2026-06-17，✅ **已浏览器验证**）

| 项 | 说明 |
|----|------|
| 思考块 UI | `AgentThoughtBlock` 自定义折叠（无背景框，箭头 + 三点动画）；历史 `msg.thinking` **移出** `.ap-msg` 气泡外部 |
| 多主题 messages 隔离 | `isNewChainTrigger()`：新主题/「我选择」时 `messagesForLLM` 只传当前 user 消息，UI 存档仍完整 |
| 新链路不注入旧节点 | `_fresh_chain_intent_kind()`：新主题/选方案时 pipeline context 不注入旧活跃 text-note id |
| 流式思考 | `status_delta` 增量 `append: true`；SSE 空闲超时 **30s**（`AGENT_SSE_IDLE_TIMEOUT_MS`） |
| create_text_note 兜底 | `buildCreateTextNotePromptFromUserMessage()`；`lastCreatedTextNoteId` 注入后续 `start_text_generation` |
| LLM 输出上限 | `max_tokens` 2000 → **4000**（`agent_service.py`） |
| 文本链路加号拖线 | **已废弃 overlay 层**；`TextWorkflowEdgePlugs.jsx` 内嵌 gn2 同款加号/拖线 |

### Phase 16 — TapNow 创意卡片 + 多链路（2026-06-17）

全展开创意卡、`group_title`/`group_subtitle`、意图 D 先卡片后落卡、新链路关键词。

### Phase 14～15 — 实测修复（2026-06-17）

停止/fitView/chips、创意触发、槽位 TTL 600s、多主题 Prompt 等（见 Git/旧版 HANDOFF）。

### 已稳定交付（Phase 9～11，摘要）

- **剧本 Agent 链路**：阶段一四步 + 阶段二（节拍→分镜图→视频），一镜一步
- **思考区**：`user_status` 时间线；`status_delta` + 终态 `thinking`
- **读画布**：`_build_canvas_digest` 摘要；`beatsSplitAt` 识别；分析类结构化 Prompt
- **侧栏 UX**：手动/自动确认双模式；聊天三写持久化
- **协作**：编辑锁、presence、评论、查看者只读、自动接权（见第二节）

### 下轮优先

| 优先级 | 项 | 状态 |
|--------|-----|------|
| ~~P0~~ | ~~Phase 22：历史 header/icon、历史滚顶、全屏 FAB、思考扫光~~ | ✅ 已完成 |
| ~~P0~~ | ~~Phase 21：Popover 配图、AI 标题、分支对话、assistant 无背景~~ | ✅ 已完成 |
| ~~P0~~ | ~~Phase 19 角色一致性：manage_cast → 配图 → 出图带角色参考~~ | ✅ 已完成 |
| ~~P0~~ | ~~选方案首次落卡：创意卡 → 创建 text-note，失败显示真实错误~~ | ✅ 已完成 |
| ~~P0~~ | ~~分镜表位置：outline 右侧（outline.x + 560）~~ | ✅ 已完成 |
| ~~P0~~ | ~~分镜表幂等：已有 rows 后「继续」不进 generate_script_table~~ | ✅ 已完成 |
| ~~P1~~ | ~~短指令走 LLM：「继续」应先分析再确认，不绕过 LLM 直执~~ | ✅ 已 API + 浏览器验证 |
| ~~P1~~ | ~~P1-2-lite：Manual/Auto、阶段二意图、分析、角色配图、失败 UX~~ | ✅ 已自测验收 |
| ~~P1~~ | ~~阶段二多镜全链路 **completed**（mock provider，无 ComfyUI）~~ | ✅ 2026-06-23 API 验收 |
| ~~P1~~ | ~~团队角色资产库跨项目（CastPendingCard + 团队 user_assets）~~ | ✅ 2026-06-23 |
| ~~P1~~ | ~~场景实体库（scene_library + manage_scene + 参考图注入）~~ | ✅ 2026-06-23 |
| ~~P2~~ | ~~分镜表 UI：ScriptSceneLibrary 独立面板 + 行拖拽 + 工具栏/主题修复~~ | ✅ 2026-06-23 Phase 25 |
| ~~P2~~ | ~~工作区项目卡片（全览 + 首页预览，重命名/删除）~~ | ✅ 2026-06-23 Phase 25 |
| ~~P2~~ | ~~Admin 视觉重做（Velora 背景 + 用户管理直出按钮）~~ | ✅ 2026-06-23 Phase 25 |
| ~~P2~~ | ~~异步协作：编辑权请求 + @ 提及通知 + 迁移团队~~ | ✅ 2026-06-24 Phase 26 |
| ~~P2~~ | ~~评论红点/高光分离 + 资料预览 + 布局/平滑滚动~~ | ✅ 2026-06-24 Phase 26 |
| ~~P2~~ | ~~完整项目导出（Word + 媒体 zip）~~ | ✅ 2026-06-24 Phase 27 |
| ~~P2~~ | ~~顶栏分享菜单 + 胶囊图标化 + 主题迁入左栏菜单~~ | ✅ 2026-06-24 Phase 27 |
| ~~P2~~ | ~~Phase 25～27 浏览器/双账号验收~~ | ✅ 2026-06-24 全部清零 |
| ~~P2~~ | ~~对抗性 Prompt 测试机制（18 用例 + 批量记录）~~ | ✅ 2026-06-25 |
| ~~P2~~ | ~~对抗性测试发现的 6 条 Prompt 问题修复~~ | ✅ 2026-06-25 全量复跑通过 |
| ~~P2~~ | ~~对抗性 6 条问题用例 → E2E 回归断言~~ | ✅ 2026-06-25 `_adversarial_regression_probe.py` |
| ~~P2~~ | ~~分镜表 UI 二次修复（设定库/模型栏/高级说明/亮色按钮/auto 画风）~~ | ✅ 2026-06-25 Phase 29 |
| ~~P2~~ | ~~ComfyUI HiDream + Wan/Hunyuan 视频 workflow 代码补全~~ | ✅ 2026-06-25（待 GPU 实测） |
| ~~P2~~ | ~~安全审计 + 登录/Agent 频控 + 参考图鉴权加固~~ | ✅ 2026-06-25 |
| ~~P2~~ | ~~粘贴剧本手测清单 A–F + 输入框固定高度~~ | ✅ 2026-06-25 |
| ~~P2~~ | ~~Excel/Word 导入智能划分 + 审阅 UX~~ | ✅ 2026-06-26 Phase 31 |
| ~~P2~~ | ~~Admin 默认 LLM + 三路分流（llm_router）~~ | ✅ 2026-06-26 Phase 31 |
| ~~P2~~ | ~~Admin 模型页：422 路由 / 透明卡片 / 分流在「全部」~~ | ✅ 2026-06-26 Phase 31 |
| ~~P2~~ | ~~粘贴剧本 C2：图/视频不做 classify（仅文本卡识别）~~ | ✅ 2026-06-29 Phase 32 |
| ~~P2~~ | ~~粘贴判定阈值收拢 `promptIntentConfig.js`~~ | ✅ 2026-06-29 Phase 32 |
| ~~P2~~ | ~~Phase 33 全产品 UI 自验 + Portal/Admin 实色统一~~ | ✅ 2026-06-29 |
| ~~P2~~ | ~~Phase 34 Prompt Bar 回归（高度/grid/紫边/顶栏/参考图）~~ | ✅ 2026-06-29 |
| ~~P2~~ | ~~Phase 35 小细节：视频间距、亮色模型栏、生成历史团队版~~ | ✅ 2026-06-29 |
| ~~P2~~ | ~~Phase 36 切换动画（团队空间 + 资产库/历史 scope）~~ | ✅ 2026-06-29 |
| ~~P2~~ | ~~V1 画布探针覆盖补全~~ | ✅ 2026-06-30 |
| ~~P2~~ | ~~主题亮暗切换过渡动画（View Transitions 圆形扩散）~~ | ✅ 2026-06-30 |
| ~~P2~~ | ~~分镜表 UI 浏览器复验（Backlog v2 + UX 四轮）~~ | ✅ 2026-06-30 |
| ~~P2~~ | ~~视频画质增强智能推荐 + Prompt Bar/分享菜单 UI~~ | ✅ 2026-07-02 |
| P1 | 阶段二多镜全链路 **completed**（**真实**出图/视频落盘，需 ComfyUI + 百炼额度） | **唯一阻塞项** |
| — | 占位功能永久不实现（见上表） | — |

---

## 一、项目概况

无限画布协作产品（React + FastAPI）：个人/团队工作区、画布编辑锁、评论、邀请、配额、媒体鉴权。

| 服务 | 地址 |
|------|------|
| 前端 | http://127.0.0.1:8173 |
| 后端 | http://127.0.0.1:7788 |
| LLM | 百炼 `DASHSCOPE_API_KEY`；**Agent/文本任务**走 Admin 配置的 `llm_router`（默认 / 低价 / 均衡）；未注册模型时 fallback `AGENT_MODEL` |

团队切换唯一入口：工作区右上角 `WorkspaceUserMenu.jsx`（已删左上角 TeamSwitcher）。

---

## 二、协作机制（摘要）

```
join → 无锁或自己是 holder → acquire + heartbeat
查看者：collabReadOnly；commit 类操作 UI + readOnlyRef 双层拦截
编辑者退出 → release_lock → session_released → 查看者自动接权
presence：HTTP ping 3s + WS；离开调 presence/leave；Redis TTL 45s
```

顶栏胶囊（`CanvasTopbar`）：在线成员 `cprs-` + **半竖线** → 同屏创作（占位）→ 额度 → AI 助手 → 分享（`CanvasShareMenu`）→ **通知铃铛**。**主题切换**：画布左栏头像菜单 / 工作区顶栏 / 资料弹窗，均走 `useThemeTransition` 圆形扩散（太阳图标）。Agent 侧栏打开时胶囊左移 `--ap-panel-width`。

左栏工具栏（`CanvasLeftToolbar`）：工具钮 + 底部头像；头像上方 **半横线**；头像菜单含账户管理 / 管理后台（admin）/ **画布操作方式**（flyout，`CanvasNavModePanel`；悬浮 **140ms** 展开）/ **切换画布主题**（`useThemeTransition`）/ 登出。工作区顶栏、资料弹窗亦有主题钮，三入口动效一致。

**编辑权请求（Phase 26）**：查看者 `CanvasTopbar` 横幅点「请求编辑权限」→ 编辑者见同意/拒绝（注意 banner 勿 `pointer-events: none` 挡住按钮）。

**评论（Phase 26）**：左工具栏评论模式 + 卡片 pin；`CanvasCommentPanel` 浮层；未读红点与 @ 高光规则见 Phase 26 B 节。

---

## 三、Canvas Agent

### 产品形态

- 右侧浮层 `AgentPanel`（TapNow 风格；思源黑体；`ap-` 作用域）
- 执行模式：**manual**（气泡内采纳/撤销）/ **auto**（输入框上确认条）
- Composer：`MentionTextarea` + 参考图 + 加号（仅「从画布添加」）+ 模式胶囊 + 停止钮（`IconStop`）
- 聊天记录：`syncAgentSession` 三写（会话 API + 归档 + localStorage）；按 **projectId** 隔离
- **历史列表**：顶栏 `historyOpen` 时左上角「← 返回」+ 右侧 icon 常驻；hover 滑出「由此开启新对话」/删除；`formatRelativeTime` 显示时间；打开历史滚到顶部（`messagesScrollRef`）
- **AI 标题**：归档时 `POST /api/agent/chat-title` 异步生成；失败 fallback 首条 user 消息截断
- **分支对话**：`startNewChatFromHistory` / `startNewChatFromMessage` 归档当前后从指定点继续

### 剧本链路（`pipeline_step`）

**阶段一**：`create_text_note` → `start_text_generation` → `generate_outline` → `generate_script_table`

**阶段二**（一镜一步）：`split_shot_beats` → `generate_storyboard` → `generate_video` → 循环

**角色库**（分镜表已存在时）：`manage_cast`（add/update `cast_library`，**仅角色**）→ 可选 `ask_user` + `cast_pending` → `CastPendingCard`

**场景库**：`manage_scene`（add/update `scene_library`）→ 可选 `scene_pending` → `ScenePendingCard`；`row_assignments` 写行 `locationId`

**短指令（Phase 18 变更）**：用户输入「继续」等 → `resolveAgentUserCommand` 返回 `null` → LLM 读画布输出 `pipeline_step` → manual/auto 确认 → `runPipelineStep`

### 意图分类

| 意图 | 触发 | 行为 |
|------|------|------|
| A 分析/问答 | 分析、检查、总结… | 只 `done`，禁止 pipeline |
| B 链路推进 | 继续、下一步、我选择…、换个主题… | 一个 `pipeline_step` |
| C 闲聊 | 普通对话 | `create_text_note`（chat）或只 `done` |
| D 创意策划 | 首次提主题、帮我想想… | `ask_user + options`（TapNow 卡片），禁止直接落卡 |

**意图 B 门禁（2026-06-25）**：
- 「继续」须先读「链路进度提示」的推荐阶段，禁止回退 `start_text_generation`（除非阶段提示明确指向）
- 上一轮 `ask_user`（创意卡 / cast_pending / scene_pending）未回答，且用户仅说推进词 → **禁止** pipeline，应 `done` 引导
- 用户给出**新明确创作方向**（非纯推进词）→ 视为放弃旧 ask_user，按 B/D 处理

**多链路指代（2026-06-25）**：画布 `script_table` ≥ 2 且用户含模糊指代（「这一镜」「这个角色」等）→ 必须先 `ask_user` 澄清，禁止直接 `pipeline_step` / `manage_cast` / `manage_scene`。

**新主题流程**：用户提主题 → 意图 D 出创意卡片 → 用户点选「我选择…」→ 意图 B `create_text_note` 开**新**链路。

**多主题隔离**：前端 `isNewChainTrigger` 截断 LLM messages；后端 `_fresh_chain_intent_kind` 避免 pipeline context 带上旧 text-note id。

### Action 协议

| type | 说明 |
|------|------|
| `pipeline_step` | 主路径（见上表） |
| `ask_user` | 创意选择；含 `group_title`、`group_subtitle`、`options`；可含 `cast_pending` / `scene_pending` + `script_table_id` |
| `create_node(image\|video)` | 非剧本链路 |
| `done` | 本步总结 + 可选 `suggestions`（✦ pill 列表） |

SSE：`status_delta`（可 `append: true` 流式）→ `thinking` → `action` → `reply_delta` → `done`

### Agent 关键文件

```
backend/services/agent_service.py       # SYSTEM_PROMPT、generate_chat_title、_build_active_chain
backend/routers/agent.py                # chat-title 端点
backend/schemas/agent_schemas.py        # AgentStoredMessage、CanvasNodeSnapshot（含 source_outline_id）

frontend/src/hooks/canvas/useCanvasAgent.js   # startNewChatFrom*、prompt 兜底、done 摘要纠错
frontend/src/services/agentApi.js               # generateAgentChatTitleApi、AGENT_SSE_IDLE_TIMEOUT_MS
frontend/src/components/canvas/
  AgentPanel.jsx / AgentPanel.css / AgentPanelIcons.jsx
  AgentCreativeCards.jsx / AgentThoughtBlock.jsx  # CastPendingCard + ScenePendingCard（EntityPendingCard）
  CanvasEmptyState.jsx                          # 空画布五 tag
  AssetLibraryFlyout.jsx                        # 团队/个人资产库；kind 徽标 outline
frontend/src/utils/canvas/
  agentChatHistory.js       # AI 标题、formatRelativeTime、活跃会话 updatedAt 修正
  agentPipeline.js          # manage_cast / manage_scene、generateScriptTable 幂等
  castLibrary.js / sceneLibrary.js / entityRefs.js
  formatRelativeTime.js
frontend/src/pages/Canvas.jsx           # castAssign / sceneAssign、openAssetLibrary
frontend/src/stores/canvasStore.js      # openAssetLibrary(pref)、assetLibraryPref
```

### Agent API

```http
POST /api/agent/run                              # SSE；body: project_id, canvas_snapshot, messages, execution_mode
POST /api/agent/chat-title                       # body: { messages } → { title }（LLM 生成会话标题）
GET/PUT /api/agent/conversation/{project_id}
GET/PUT/DELETE /api/agent/chat-history/{project_id}[/{archive_id}]
```

---

## 四、关键文件地图（精简）

```
frontend/src/
├── pages/Canvas.jsx, Canvas.css
├── pages/Workspace.jsx, WorkspaceProjects.jsx, Workspace.css
├── pages/Admin/AdminLayout.jsx, Admin.css, UserManagement.jsx, ModelDrawer.jsx, formatApiError.js, Dashboard.jsx
├── components/workspace/WorkspaceProjectCard.jsx
│   ├── WorkspaceNotifyPanel.jsx, MigrateToTeamModal.jsx
├── components/canvas/
│   ├── CanvasCommentPanel.jsx|css, CanvasCommentMarkers.jsx
│   ├── AgentPanel*, AgentPanelIcons.jsx, AgentThoughtBlock.jsx, AgentCreativeCards.jsx
│   ├── CanvasEmptyState.jsx, AssetLibraryFlyout.jsx
│   ├── TextWorkflowEdgePlugs.jsx          # 文本链路左右加号（gn2 同款，内嵌节点）
│   ├── TextNode / TextResponseNode / OutlineNode / ScriptTableNode / ShotScriptNode
│   ├── ScriptSceneLibrary.jsx, ScriptShotCard.jsx, ScriptShotDirectorPanel.jsx
│   ├── CanvasImageQuickPicker.jsx          # 场景/参考图快捷选图（Portal 主题适配）
│   ├── CanvasTopbar.jsx, CanvasTopbarIcons.jsx, CanvasShareMenu.jsx
│   ├── ExportProjectModal.jsx|css, exportApi.js
│   ├── ImportDocumentModal.jsx|css          # Excel/Word 导入审阅、智能划分
│   ├── CanvasLeftToolbar.jsx              # 头像菜单：画布操作方式 flyout + 140ms hover
│   ├── GenerationCardNode.jsx, VideoGenerationNode.jsx  # 加号拖线 + 三点菜单
│   ├── VideoEnhancePanel.jsx|css, videoEnhanceBridge.js, GenerationBrandLoader.jsx|css
│   ├── VideoReferencePanel.jsx|css
│   ├── ImageReferencePicker.jsx|css
│   └── CanvasShared.css                   # gn2-edge-handle + gn2-plus-* 共享样式
├── hooks/canvas/useCanvasAgent.js, useCanvasSave.js, useScriptTableGenerate.js, useTextGeneration.js
├── hooks/useScopeSwitchTransition.js
├── components/common/ScopeSwitchPanel.jsx
├── stores/canvasStore.js, assetStore.js   # openAssetLibrary、teamAssets
└── utils/canvas/
    suppressPaneMenu.js
    genHistory.js, teamContext.js          # 生成历史 + getCanvasTeamId
    commentReadState.js, notificationThread.js
    agentPipeline.js, agentCommandRouter.js, castLibrary.js, sceneLibrary.js, entityRefs.js
    serializeCanvasForAgent.js, scriptPromptPackage.js, formatRelativeTime.js

backend/
├── services/agent_service.py, agent_conversation_service.py, canvas_lock.py
├── services/export_service.py               # 完整项目导出 Word+zip
├── services/notification_service.py, canvas_comments.py, canvas_access.py
├── services/mock_generation.py, llm_resilience.py
├── services/video_enhance_probe.py, video_enhance_recommend.py
├── comfyui/client.py, comfyui/workflows/video_enhance_*.json
├── routers/notifications.py, routers/exports.py
├── models/notification.py, models/export_job.py
├── services/entity_refs.py, shot_prompt_package.py, split_shot_beats.py
├── routers/assets.py                      # 团队资产 CRUD（复用于角色/场景库）
├── routers/import_document.py             # Excel/Word 解析、group-suggest（rule|llm）
├── services/llm_router.py                   # Admin 文本 LLM 分流 + 24h 用量
├── services/shot_grouping_llm.py            # 导入审阅智能大镜划分
├── assets/mock/                             # 占位图/视频（勿与 uploads/ 混用）
├── scripts/_mock_*.py, _agent_pipeline_e2e_probe.py, _adversarial_prompt_probe.py
├── scripts/_excel_import_probe.py           # 导入解析 + --llm-group
├── scripts/_comfyui_workflow_structure_probe.py   # ComfyUI workflow 结构校验
├── scripts/adversarial_cases/               # 对抗性 Prompt 用例（6 类 × 3）
├── scripts/adversarial_results/             # 跑测输出（gitignore）
├── schemas/agent_schemas.py
├── models/user_asset.py, canvas_project.py
└── alembic/versions/013～019（017: export_jobs；018: excel_import_log；019: llm_routing）
```

**未新建表**：角色/场景团队资产均用 `user_assets`（`team_id` + `kind=character|scene`）；`scene_library` / `cast_library` 存于分镜表节点 `canvas_data` JSON。

### 文本工作流节点加号架构（Phase 17）

```
节点 wrapper（overflow: visible, position: relative）
  └── TextWorkflowEdgePlugs（nodeId, nodeType）
        ├── Handle tgt（隐形接收）
        ├── Handle src-left / src-right（gn2-edge-handle，透明大命中区，z-index 30，负责拖线）
        ├── gn2-plus-left-zone / gn2-plus-right-zone（z-index 21，滑出动画 + 可见 +）
        └── onClick → canvasActions.openPickerAt（与图片卡相同）

❌ 已废弃：Canvas.jsx 内 NodeLeftPlusOverlay / NodeRightPlusOverlay
```

### Agent 布局注意（Phase 18）

```
finalizeAgentLayout → 仅 fitView（双帧 rAF），不再 applyAgentCanvasLayout / organizeCanvasNodes
各 pipeline 步骤创建节点时已按父节点偏移定位（如分镜表 outline.x + 560）
创意卡：ap-msg-wrap--assistant.ap-msg-wrap--creative 必须 stretch 满宽，否则继承 ap-msg-wrap 的 max-width:92% 导致右侧留白
```

---

## 五、技术债要点

1. **CSS 命名空间**：在线横条 `cprs-`，勿用 `cpb-`；Agent 用 `ap-`
2. **text-response**：`normalizeTextResponseNode` **禁止** `generating`→`completed`
3. **outline 渲染**：`flowNodes` 只用 `stripOutlineDragHandle`，勿调 `normalizeOutlineNode`
4. **waitForNodeCondition**：节点缺失时轮询；已接 `AbortSignal`（Phase 14）
5. **Agent 节点读写**：经 `agentWorkflowRef` → `nodesRef`，勿单独 `useReactFlow().setNodes`
6. **has_video**：仅完成态；生成中用 `video_generating`（`rowVideoReady`）
7. **多主题**：`buildActiveChain` 用 edges + `linkedSourceId` / `sourceOutlineId` fallback；配合 `_fresh_chain_intent_kind` + `isNewChainTrigger`
8. **分镜表幂等**：前端 `generateScriptTable` + 后端 `_build_active_chain` 均需识别已存在表；快照须带 `source_outline_id`
9. **Agent 布局**：**禁止**在 `finalizeAgentLayout` 中全量 `organizeCanvasNodes`；会打乱分镜表横向位置
10. **done 摘要**：pipeline 失败时前端必须用 `skipNotes` 覆盖 LLM 乐观文案
11. **短指令**：`resolveAgentUserCommand` 已禁用直执；勿恢复不经 LLM 的「继续」捷径
12. **创意卡片**：TapNow 全展开；`AgentCreativeCards` 在气泡外；`.ap-msg-wrap--creative` 需覆盖 assistant 的 `flex-start` 与 `max-width:92%`
13. **Memory**：按 projectId；LLM 截断 20 条；新主题时 `messagesForLLM` 可只传当前句
14. **占位**：同屏创作、加号占位、账单 — 永久 `showDevNotice`
15. **节点加号拖线**：文本链路必须用节点内 `TextWorkflowEdgePlugs`（gn2 同款）
16. **Redis**：协作锁/presence/生成槽位均依赖
17. **Agent 超时**：SSE 空闲 30s；pipeline 等待与 `waitForNodeCondition` 另计
18. **CanvasNodeSnapshot**：`rows_summary` / `row_count` 已入 schema（P1-1）；其余扩展字段若未入 schema 仍会被 Pydantic 剥离
19. **角色/场景配图**：`castAssign:{id}` / `sceneAssign:{id}`；`CastPendingCard` / `ScenePendingCard` 三入口共用 `patchCastImage` / `patchSceneImage`；资产库读团队 `user_assets`；保存时写 `globalAssetId`；管理见 `AssetLibraryFlyout`
20. **实体参考图**：`entityRefs.js` — 角色 prompt 文本匹配；场景 `locationId` + 文本；出图最多 3 角色 + 1 场景 URL
21. **manage_cast vs manage_scene**：两个独立 Agent action；勿用 manage_cast 加场景；`cast_library` 与 `scene_library` 分存
22. **空态 Tag**：`CanvasEmptyState` 五 chip 均有色边；角色/场景 → `openAssetLibrary(pref)`；无音频 tag
23. **自动保存**：`useCanvasSave` 用 `prevSnapshotRef` 比对序列化快照；加载时 `applyCanvasData` 会初始化快照，避免无变化重复 PUT
24. **全屏 CSS**：`rf-page--fullscreen` = `position:fixed; inset:0; z-index:9999` + 原生 `requestFullscreen()` 双重模式；`fullscreenchange` 同步退出；**Agent 侧栏与 FAB 始终可见**；顶/底栏边缘 hover 淡入（`fullscreenChrome`）；全屏时隐藏 `ref-select-banner`/`comment-select-banner`/body 级 `image-viewer`
25. **last_modified_by**：仅 `canvas_data` 变更时写入；旧项目首次保存后才有修改者名
26. **聊天记录滚动**：`historyOpen` 时 `messagesScrollRef.scrollTo(0)`；对话模式才 `messagesEndRef.scrollIntoView`
27. **CastPickPopover**：Portal 挂 `document.body`；亮色主题用 `body:has(.rf-page--light) .ap-cast-pick-popover`；监听 scroll 父级 + resize 重算位置
28. **AI 标题**：`maybeGenerateAiTitle` 仅新归档或仍为 fallback 标题时触发；勿在每次 `syncAgentSession` 重复调 LLM
29. **Mock Provider**：`AGENT_MOCK_GENERATION=true` 时走 `mock_generation.py`；终态须 `release_slots`；ComfyUI 就绪后关闭
30. **E2E 探针账号**：`testuser` 无 canvas project，全链路/阶段二探针用 **admin**
31. **LLM 重试**：只在 `run_agent_stream`；流式中途失败不重试
32. **import 陷阱**：`characterCastLibrary` 在 `entityRefs.js`；`normalizeSceneLibrary` 在 `sceneLibrary.js` — 勿从 `castLibrary.js` 错导
33. **分镜拖拽 MIME**：行排序 `dataTransfer` 必须用 `application/x-st-shot-reorder`；用 `text/plain` 会触发 Electron「松开搜索文本」
34. **Admin 两套**：新版 `pages/Admin/`（Velora 背景）；遗留 `AdminPage.jsx` 勿混用
35. **WorkspaceProjectCard**：`variant="grid"`（全览页）/ `variant="preview"`（首页 `ws-project-card`）
36. **评论已读**：`commentReadState.js` — 红点=他人新消息 since `lastMessageId`；高光=`seenMentionIds` 仅 @
37. **评论 Portal**：资料预览/通知相关浮层挂 `body` 时需 `rf-page--dark|light` 类或实色 fallback
38. **通知线程**：`notificationThread.js` 同 `project_id+node_id` 批量已读；勿逐条 mark read
39. **迁移团队**：仅个人项目（`team_id` 空）；迁入后 `team_id` 写入，离开个人列表
40. **项目导出**：须先 `alembic upgrade head`（017）；选**一条**分镜链（`script_table_node_id`）；大项目异步轮询；`_row_prompt` 在 `export_service.py`
41. **顶栏胶囊**：主题不在右上；`ctb-capsule-sep` 默认 `display:none`，仅 `--half` 在在线人数后显示
42. **分享/导出 Portal**：`CanvasShareMenu`、`ExportProjectModal` 挂 `document.body`，CSS 需实色 fallback
43. **主题菜单图标**：左栏头像菜单用 `sun` 固定图标，勿再用 `moon`（对齐问题已规避）
44. **对抗性探针**：依赖真实 LLM（非 mock）；结果在 `adversarial_results/`；改 `agent_service.py` 后须重启后端再跑
45. **空 actions 诊断**：LLM 返回缺 `actions` 或 `actions:[]` 时 SSE 无 `error`、无 `thinking`；探针已记录完整 SSE 流辅助判断
46. **链路阶段推断**：`_infer_stage_from_chain` 在快照无 `text_response` 但有 `script_table` 行时，仍应按 `_production_stage_hint` 推断（勿一律 `start_text_generation`）
47. **创意卡门禁**：`_previous_assistant_pending_choice` + `_is_advance_only_message`；「继续，先生成节拍」≠ 新明确方向
48. **分镜表画风 auto**：`qualityPresetId: "auto"` = 不注入 `atmosphereNote`/导演字段；旧数据 `cinematic` 或空 id 在加载时 `withDefaultQualityPreset` 迁移
49. **设定图添加**：`AddRefHoverPanel` 须先填名称再点开；资产库导入在面板内第三段（`CanvasImageQuickPicker` `assetEntries`）
50. **模型工具栏背景**：`st-toolbar-pills` 容器透明；仅 `.nb-model-btn-bare` 有 `--tl-toolbar-btn-bg`（勿再给整条 pills 加灰底）
51. **亮色分镜表按钮**：`textWorkflowTheme.css` 中 `.rf-page--light .st-shot-action-btn` 等须保留 `#eef0f3` 底，勿设 `transparent`
52. **Admin LLM 路由**：`PUT /api/admin/models/llm-routing` 等**静态路径**必须注册在 `PUT /{model_id}` 之前，否则 422
53. **API 错误展示**：FastAPI 422 的 `detail` 常为数组；Admin 页须用 `formatApiError()`，勿直接 `message.error(detail)`
54. **`_call_llm` 返回值**：`tuple[str, str|None]`；调用方须 `raw, _ = await _call_llm(...)` 再 `clean_json_response(raw)`
55. **导入智能划分**：默认 `identityGroups`（一行一大镜）；LLM 仅按钮触发；失败回退 `suggest_groups` 规则
56. **ImportDocumentModal 选集工具栏**：`.idm-pick-toolbar` 在 `.idm-body` **外**，勿再 sticky 于滚动区内
57. **粘贴剧本 classify**：**仅文本卡**（`TEXT_CLASSIFY_MIN=200` 点生成；`PASTE_HINT_MIN=400` 横幅）；图/视频**禁止**恢复 `requestIntentGate`
58. **意图阈值**：四处常量均在 `promptIntentConfig.js`；后端 `0.82` 仅规则兜底，勿收到前端
59. **Prompt Bar 高度**：compact 勿恢复 `nb-banner--prompt-layout` grid（`1fr` 会撑高文本/图卡中间区）；高度仅由 `--prompt-input-min-h-*` token 控制
60. **Prompt Bar 亮色覆盖**：`.rf-page--light .nb-model-btn-bare` 等须限定在 `.nb-banner` 内，否则会清空分镜表模型下拉灰底
61. **生成历史**：个人 scope = localStorage 无 `teamId`；团队 scope = API `task records`（须有 `result`）；勿用 `Date.now()` 回填缺失 `ts`
62. **团队上下文**：`getCanvasTeamId()` = `projectTeamId ?? activeTeamId`；`teamIdPayload()` 须用此函数（非仅 `getActiveTeamId()`）
63. **切换动画**：`ScopeSwitchPanel` + `useScopeSwitchTransition`；出场冻结子树防闪屏；`prefers-reduced-motion` 已降级
64. **主题切换动画**：`useThemeTransition` + `themeTransition.css`；`flushSync` 内 `toggleTheme`；`prefers-reduced-motion` 或无 `startViewTransition` 时瞬时切换；勿接入 `ScopeSwitchPanel`
65. **项目设定折叠**：`projectSettingsOpen` 仅 unmount 人物/场景库；**工具栏不得**包进折叠 fragment
66. **镜头拖排序**：`st-shot-drag-handle` 须用 `<div draggable>`，**禁止** `<button>` + `mousedown preventDefault`
67. **生成节点 X**：`SCRIPT_TABLE_WIDTH` 须与 `.st-wrapper`（1100px）一致；用 `computeScriptTableGenX()`，勿硬编码 1360 或 `beatCard.x + 400`
68. **转场 segment**：`segment.*` 不进生成 prompt；UI 仅分隔线，勿恢复完整表单除非产品改需求
69. **导演参数**：默认 `expanded=false`；产品要求保留展开/收起 + 摘要行，勿改为常显或常隐
70. **画布右键**：`handlePaneContextMenu` 须跳过 `.react-flow__node`；分镜表 `st-root` 宜 `stopPropagation`
71. **批量语气**：`batch_adjust_tone` / `ScriptBatchToneModal` 已删除，勿恢复；单镜「审阅提示词」仍保留
72. **三点菜单关菜单后双击**：关 `gn2-dots-menu` / `cell-menu-portal` 时须 `markSuppressPaneMenu()`，否则双击画布仍弹选取器
73. **画质增强 Tab 灰底**：`.mode-tab` **禁止**对 `active` 或 `collapsed` 加背景；灰底仅 `.mode-tab:hover`；取消 enhance 须 `panelMode` 回 `referenceMode`
74. **视频三点画质增强**：用右侧 `cell-dots-submenu` flyout，勿在菜单内纵向插入 `VideoEnhancePanel`（会产生大块空白）
75. **选中加号常驻**：`plusPinned = selected`；mouseLeave 时若 pinned 勿 `setVisible(false)`
76. **画布操作方式**：仅在头像菜单 flyout；`NAV_HOVER_OPEN_MS = 140`；勿恢复左栏独立 nav 图标
77. **画质增强说明**：精细控制用 **ⓘ + 下方说明条**（对齐 `ScriptTableNode`）；勿恢复 hover `?` 上标
78. **画质增强 Prompt Bar**：compact 面板**无取消钮**；三点 flyout 内仍可有取消
79. **分享菜单定位**：`left = shareBtnRect.left` 向右展开；四项 `flex-start` 左对齐；勿改回整块居中对齐按钮（会显左空右挤）
80. **视频增强推荐**：`reasoning` 由后端带完整句；前端勿再拼 `enhanceReasoningPrefix` 前缀

---

## 六、部署

**完整指南**：[`DEPLOY.md`](DEPLOY.md)（架构、环境变量、生产检查清单、常见问题）。

| 路径 | 一句话 | 文档 |
|------|--------|------|
| **AutoDL 云 GPU（内测推荐）** | 裸机 + Nginx `:6006` + Supervisor + 本机 ComfyUI | [`backend/docs/AUTODL_DEPLOY_RUNBOOK.md`](backend/docs/AUTODL_DEPLOY_RUNBOOK.md) |
| **Docker Compose** | `bash deploy/deploy.sh` → Postgres + Redis + backend + web | [`DEPLOY.md`](DEPLOY.md) 方式二 |
| **手动裸机** | venv + `alembic` + uvicorn + Nginx 反代 | [`DEPLOY.md`](DEPLOY.md) 方式三 |

**本地开发**：前端 `http://127.0.0.1:8173`（`npm run dev`）· 后端 `http://127.0.0.1:7788`（uvicorn）· 模板见 `frontend/.env.development` / `backend/.env`。

**任何环境必做**：

```bash
cd backend && alembic upgrade head   # 001–021
# REDIS_URL 必配 — 未开 Redis 则协作/Agent/生成槽位/限流异常
# DASHSCOPE_API_KEY 必填（Agent / 文本 / classify / 风格参考 VL）
# uploads/ 持久化（images / videos / exports）
```

**ComfyUI**：`COMFYUI_URL` 指向内网；真实模型切换见 [`backend/docs/COMFYUI_CUTOVER_RUNBOOK.md`](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md)。无 GPU 内测可设 `AGENT_MOCK_GENERATION=true`。

**公网部署前必读**：[`SECURITY_AUDIT_FINDINGS.md`](SECURITY_AUDIT_FINDINGS.md)（JWT、seed 账号、CORS、`APP_ENV=production` 等）。

---

## 八、阶段二全链路验收清单

### A. Mock 环境（✅ 2026-06-23 已通过）

无需 ComfyUI。启动：`AGENT_MOCK_GENERATION=true`，重启后端。

```powershell
cd backend
$env:AGENT_MOCK_GENERATION="true"
$env:AGENT_MOCK_FAILURE_RATE="0"
.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 7788

# 另开终端
.\.venv\Scripts\python.exe scripts\_mock_pipeline_stage2_probe.py          # 推荐：阶段二专项
.\.venv\Scripts\python.exe scripts\_mock_generation_acceptance.py         # mock API 冒烟
.\.venv\Scripts\python.exe scripts\_agent_pipeline_e2e_probe.py admin Admin@2026! --skip-text  # 全链路（依赖 LLM 稳定）
```

| # | 检查项 | 状态 |
|---|--------|------|
| 1 | 2 镜：节拍 → 分镜图 **completed** → 视频 **completed** | ✅ stage2 探针 |
| 2 | 出图请求 `reference_images` 写入任务记录 | ✅ prompt_text 含 `mock_reference_images` |
| 3 | `AGENT_MOCK_FAILURE_RATE=1` 失败 UX 返回真实 error | ✅ |
| 4 | 全程不需要 ComfyUI | ✅ |
| 5 | 一镜一步：镜1 视频完成后镜2 先 `generate_storyboard` | ✅ Agent + stage2 探针 |

### C. 角色/场景资产与实体（手动，mock 可验链路）

1. **跨项目角色**：项目 A `cast_pending` 配图 + 勾选「保存为常用角色」→ 项目 B 同团队 CastPendingCard 资产库可见
2. **场景实体**：Agent `manage_scene` → ScenePendingCard 配图 → 分镜行选场景 / `row_assignments` → mock 出图 `reference_images` 含角色+场景
3. **空态 Tag**：点「角色/场景」打开 Flyout 对应筛选；五 chip 边框颜色一致
4. **团队隔离**：异团队账号看不到对方团队资产

### B. 真实模型环境（待 ComfyUI + 百炼额度）

P1-2-lite（意图/UI/采纳/角色配图）已自测通过。下列为 **ComfyUI + 图像/视频模型就绪** 后最后一项：验证真实媒体生成落盘。`AGENT_MOCK_GENERATION=false`。

1. **环境**：Redis 开；`registered_models` 启用 image + video；分镜表默认模型已选；`alembic upgrade head`
2. **后端稳定**：`python main.py` 启动后 `/api/auth/login` < 5s；避免热重载卡死
3. **多镜 completed**：2 镜分镜表 → 节拍 → 分镜图 **completed** → 视频 **completed**
4. **出图带角色+场景**：`reference_images` 含 cast + scene 参考图（`entityRefs.js`；mock 见 `mock_reference_images`）
5. **失败 UX**：模型不可用时 `skipNotes` 覆盖乐观摘要（P1-2-lite 已验 UI；真实错误文案待模型环境复验）

**切换操作清单**：见 [backend/docs/COMFYUI_CUTOVER_RUNBOOK.md](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md)（含回滚步骤与超时阈值复核表）。

---

## 七、新对话建议起手

```
继续 AI Studio 开发。请先读 HANDOFF.md 文首「2026-07-02 当前总览」+ 「视频画质增强 + Prompt Bar/顶栏 UI」详情节 + [`V1_CANVAS_PROBE_COVERAGE.md`](backend/docs/V1_CANVAS_PROBE_COVERAGE.md) + 「占位功能 — 永久不实现」。

【当前状态 · 2026-07-02】
- 视频画质增强：智能推荐 API + 一键增强 UI + SeedVR2 高级参数（✅ 浏览器验收）
- Prompt Bar：紧凑增强行、ⓘ 说明条、无取消钮、视频卡 expandInField（✅）
- 分享菜单：左对齐 + 左缘对齐分享钮展开（✅）
- 画布交互六项 + Backlog v2 + V1 探针 + 主题切换（✅ 历史轮次）
- ComfyUI workflow 代码已补全（含 video enhance）；真实 GPU 全链路仍待第八节 B

【下轮起手 · 唯一阻塞项】
1. ComfyUI + 百炼额度就绪 → HANDOFF **第八节 B** 真实出图/视频 completed 验收

【下轮可选 · 产品/工程】
1. 画质增强「非法上传路径」：查 `media_access` / 视频 URL ticket 鉴权
2. GPU 前：`_video_enhance_probe.py` + ComfyUI Runbook 启用 SeedVR2 workflow
3. Admin 分流：为各文本模型填单价后实测「低价优先」「均衡分流」
4. 公网前：APP_ENV=production、强 JWT（见 SECURITY_AUDIT_FINDINGS.md）

【本地 · 启动】
  cd backend && $env:AGENT_MOCK_GENERATION="true"; .\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 7788
  cd frontend && npm run dev   # :8173
Redis 必开；迁移：alembic upgrade head

【探针 · mock 快速回归】
  .\.venv\Scripts\python.exe scripts\_video_enhance_probe.py
  .\.venv\Scripts\python.exe scripts\_lut_probe.py
  .\.venv\Scripts\python.exe scripts\_export_project_probe.py
  .\.venv\Scripts\python.exe scripts\_mock_pipeline_stage2_probe.py
  .\.venv\Scripts\python.exe scripts\_paste_script_checklist_probe.py --only e1

【账号】admin / testuser / testuser2 — 密码见 backend/.env 的 SEED_*_PASSWORD
【前端改完】Ctrl+Shift+R；改 tasks.py / video_enhance 相关后须重启 uvicorn
```

---

## 附录：历史 Phase 索引（详情见 Git 历史）

| Phase | 日期 | 摘要 |
|-------|------|------|
| 1～8 | 06-15～16 | Agent 基础、SSE、持久化、大纲竞态修复、聊天归档 |
| 9 | 06-16 | 分镜制作 pipeline 5～7、思考区时间线、命令路由 |
| 10 | 06-16 | 阶段二 API 探测、创意卡片初版、create_node(video) |
| 11 | 06-16 | 画布摘要、beatsSplitAt、确认双模式、Ctrl+滚轮 |
| 12～13 | 06-17 | reply_delta、suggestions、fitView、多主题追踪（→ Phase 14 修） |
| 14 | 06-17 | 停止/思考/fitView/chips 实测修复 |
| 15 | 06-17 | 创意触发、多主题 Prompt、灰底、槽位 TTL |
| 16 | 06-17 | TapNow 卡片 UI、新链路关键词、group_title 字段 |
| 17 | 06-17 | 思考块 UI、多主题 messages 隔离、流式思考、TextWorkflowEdgePlugs |
| 18 | 06-18 | Agent UI 打磨、逻辑/布局修复、短指令改走 LLM、创意卡满宽对称（✅） |
| 19 | 06-22 | 角色一致性：manage_cast、cast_pending、cast_library 序列化、多角色 reference_images（✅） |
| 20 | 06-22 | 五问题修复：Banner/pill、选图三选项、三点菜单、保存+修改者、全屏初版（✅） |
| 21 | 06-22 | 聊天记录重设计：AI 标题、分支对话、Popover 配图、双重全屏、assistant 无背景（✅） |
| 22 | 06-22 | 历史 header/icon、历史滚顶、全屏 FAB、思考扫光、选图按钮与 + 号对齐（✅） |
| 23 | 06-23 | Mock Generation Provider；LLM 容错；团队角色资产库；场景实体库；画布空态 Tag（✅） |
| 25 | 06-23 | 分镜表 UI 深化（场景库/拖拽/工具栏）；工作区项目卡片；Admin Velora 视觉重做（✅ 已验收） |
| 26 | 06-24 | 异步协作：编辑权请求、@ 通知、迁移团队；评论红点/高光分离、资料预览、布局与平滑滚动（✅ 已验收） |
| 27 | 06-24 | 完整项目导出（export_jobs + Word/zip）；分享菜单；顶栏胶囊图标化；主题迁入左栏菜单；半线分割（✅ 已验收） |
| 28 | 06-25 | ComfyUI Flux workflow 预案；对抗性 Prompt 测试（18 用例）；6 条 Prompt 问题修复 + 全量复跑（✅） |
| 29 | 06-25 | 分镜表 UI 四轮修复（设定库/模型栏/高级说明/亮色主题）；auto 默认画风；E2E 回归断言；HiDream/Wan/Hunyuan workflow 代码补全（✅ 待 GPU 实测） |
| 30 | 06-25 | 安全审计加固；粘贴剧本手测 A–F；输入框 max-height；阈值 0.6 统一 + 图/视频「仍要生成」；E1 few-shot + `_paste_script_checklist_probe.py` 永久回归（✅） |
| 31 | 06-26 | Excel/Word 导入审阅 UX + LLM 智能划分；`llm_router` Admin 三路分流；模型页 422/透明/全部 tab；节拍构图「上传」（✅） |
| 32 | 06-29 | C2：图/视频移除剧本 classify；`promptIntentConfig` 阈值收拢；文本横幅/意图弹窗/图视频卡亮色视觉一致（✅） |
| 33 | 06-29 | 全产品 UI 自验；Portal/Admin 实色；分镜表亮色次级钮；`UI_AUDIT.md` 无 blocker（✅） |
| 34 | 06-29 | Prompt Bar 回归：去 grid 撑高、去紫边、视频顶栏对齐、参考图 `(n/5)` + freeref tags（✅） |
| 35 | 06-29 | 视频顶栏间距；亮色分镜表模型 pill；生成历史团队版 + 时间戳 + API result（✅） |
| **36** | **06-30** | **Backlog v2** + **分镜表 UX 四轮** + 交互/定位修补（✅ 浏览器验收） |
| 36 | 06-29 | 切换动画：`ScopeSwitchPanel`；团队空间 + 资产库/历史 scope（✅） |
| **37** | **06-30** | **V1 画布探针覆盖补全**（7 探针 + 文档 + `tasks/records` 路由修复）（✅） |
| **38** | **06-30** | **主题切换圆形扩散** `useThemeTransition` + View Transitions API（✅） |
| **39** | **07-01** | **画布交互六项优化**：suppressPaneMenu、画质增强紧凑 UI、参考图亮色、选中加号常驻、操作方式头像 flyout（✅） |
| **39b** | **07-01** | **UX 修补**：三点画质增强右侧 flyout、Tab 仅 hover 灰底、操作方式 140ms 悬浮展开（✅） |
| **40** | **07-02** | **部署文档 P0/P1**：HANDOFF §六重写；AutoDL 复制 deploy 配置模板；env/Docker/ffmpeg/安全审计对齐（✅） |
| **41** | **07-02** | **视频画质增强**：智能推荐 + SeedVR2 高级参数 + 一键增强 UI；分享菜单方案 B；ⓘ 说明条；开通会员样式（✅ 已验收） |
