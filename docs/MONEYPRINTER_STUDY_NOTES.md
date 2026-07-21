# MoneyPrinterTurbo 学习笔记（Velora 对照）

> 阶段：第 1 阶段只读分析 | 日期：2026-07-21  
> 上游仓库：https://github.com/harry0703/MoneyPrinterTurbo（MIT）  
> 本地 clone 状态：`/root/autodl-tmp/oss-study/MoneyPrinterTurbo` **已完整存在**（ghfast tarball；`README.md` + `app/` + `webui/` + `main.py` + `cli.py` 校验通过）

---

## A. 架构摘要

MoneyPrinterTurbo 的核心设计是 **封闭线性工厂 + 多入口薄封装**：`app/services/task.py` 编排「主题 → 成片」全链路，各阶段由独立 service 模块承担；配置集中在 `config.toml`（首次运行从 `config.example.toml` 复制），WebUI 与 API 共用同一套 `VideoParams` 与 `task.start()`。

### 文字版流水线图

```text
Input (video_subject / 自定义 video_script)
  │
  ▼
① generate_script ── LLM 生成旁白文案（或直接使用自定义脚本）
  │
  ▼
② generate_terms ── LLM 生成素材搜索关键词（local 素材源跳过）
  │   └─ 可选 TwelveLabs Marengo 语义重排（match_materials_to_script 时禁用）
  │
  ▼
③ generate_audio ── TTS 合成旁白 audio.mp3 + SubMaker 时间轴
  │   └─ 或复用 custom_audio_file / WebUI 试听缓存
  │
  ▼
④ generate_subtitle ── edge（TTS 时间戳）或 whisper（faster-whisper 转写）
  │   └─ 输出 subtitle.srt
  │
  ▼
⑤ get_video_materials ── Pexels/Pixabay/Coverr 下载 或 local 预处理
  │
  ▼
⑥ generate_final_videos
  │   ├─ video.combine_videos：素材切片拼接对齐音频时长
  │   ├─ 可选 Sonilo/ElevenLabs AI BGM
  │   └─ video.generate_video：MoviePy 混音 + 字幕烧录 + BGM
  │
  ▼
⑦ 可选 cross_post ── Upload-Post 发布 TikTok/Instagram/YouTube
  │
  ▼
output/tasks/{task_id}/final-{n}.mp4
```

编排入口：`app/services/task.py::start()` → `_run_pipeline()`，支持 `stop_at` 中间产物（`script` / `terms` / `audio` / `subtitle` / `materials` / `video`）。

### 入口层

| 入口 | 路径 | 说明 |
|------|------|------|
| **Streamlit WebUI（主产品）** | `webui/Main.py` ← `webui.sh` | 默认 `127.0.0.1:8501`；配置 LLM/TTS/素材/字幕全在 UI |
| **FastAPI（程序化）** | `main.py` → `app/asgi.py` | 默认 `0.0.0.0:8080`；`/docs` 可浏览 |
| **CLI** | `cli.py` | `uv run python cli.py --video-subject "..."` |
| **Agent Skill** | `docs/skill/SKILL.md` + `docs/skill/mpt_agent.py` | 外部 Agent 按 Skill 文档驱动安装与生成 |
| **路由聚合** | `app/router.py` | `video.router` + `llm.router` |

### 服务分层（真实路径）

| 层级 | 目录/文件 | 职责 |
|------|-----------|------|
| Controller | `app/controllers/v1/video.py` | 任务提交、查询、下载、素材/BGM 上传 |
| Controller | `app/controllers/v1/llm.py` | 独立 `/scripts`、`/terms`、社交元数据 |
| Task 编排 | `app/services/task.py` | 流水线阶段调度、进度、失败收敛 |
| LLM | `app/services/llm.py` + `app/models/llm_provider.py` | 文案/关键词/社交文案；20 个 Provider Registry |
| TTS | `app/services/voice.py` | Edge/Azure/SiliconFlow/Gemini/MiMo/ElevenLabs/Chatterbox |
| 字幕 | `app/services/subtitle.py` + `voice.create_subtitle()` | Whisper 转写 + Edge 时间轴对齐 |
| 素材 | `app/services/material.py` | Pexels/Pixabay/Coverr 搜索下载 + Key 轮询 |
| 合成 | `app/services/video.py` | MoviePy 拼接/转场/字幕烧录/BGM 混音 |
| BGM | `app/services/bgm.py` + `sonilo.py` / `elevenlabs_music.py` | 本地曲库 + AI 配乐 |
| 任务状态 | `app/services/state.py` + `controllers/manager/` | 内存或 Redis 任务队列 |
| 配置 | `app/config/config.py` + `config.toml` | 全局 TOML 配置 |

### 关键 API 端点（FastAPI v1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/videos` | 完整视频生成 |
| POST | `/api/v1/subtitle` | 仅字幕 |
| POST | `/api/v1/audio` | 仅配音 |
| POST | `/api/v1/scripts` | 仅文案 |
| POST | `/api/v1/terms` | 仅关键词 |
| GET | `/api/v1/tasks` | 任务列表 |
| GET | `/api/v1/tasks/{task_id}` | 任务状态 |
| GET | `/api/v1/download/{file_path}` | 产物下载 |

### 字幕两种模式（如何选）

配置项：`config.toml` → `[app] subtitle_provider = "edge"`（默认）。

| 模式 | 值 | 机制 | 适用场景 |
|------|-----|------|----------|
| **Edge（默认）** | `"edge"` | TTS 阶段 `edge_tts.SubMaker` 产出 word/句级 cues → `voice.create_subtitle()` 按标点切分脚本行并对齐时间轴 → `subtitle.srt` | 快、无 GPU、与 Edge TTS 旁白天然对齐 |
| **Whisper** | `"whisper"` | `faster-whisper` 转写音频 → `subtitle.correct()` 与脚本文案校正 | 需更准确时间轴、自定义音频、或非 Edge TTS 路径 |

**分支逻辑**（`task.py::generate_subtitle`）：

- `subtitle_enabled=false` → 跳过
- 自定义音频且无 `sub_maker` → **仅 whisper 可用**；edge 会跳过并 warning
- Edge 失败 **不会** 自动 fallback 到 Whisper（避免意外下载数 GB 模型）
- Whisper 模型默认 `large-v3`（约 3GB），可改 `large-v3-turbo`；放 `models/whisper-{size}/`

### TTS Provider 路由（`voice.tts()`）

默认分支走 `azure_tts_v1()`，实质为 **Edge TTS**（WebUI 显示「Azure TTS V1」）。按 `voice_name` 前缀分发：

- `no-voice` / `none` → 静音 + 估算时长
- `azure-v2:` → Azure Speech V2
- `siliconflow:` / `gemini:` / `mimo:` / `elevenlabs:` / `chatterbox:` → 各云 TTS
- 其余 → Edge TTS（`edge_tts.Communicate` + `boundary` 参数兼容 7.x）

### 画幅 / 字幕样式参数

`VideoParams`（`app/models/schema.py`）：

| 参数 | 默认 | 说明 |
|------|------|------|
| `video_aspect` | `9:16` | `16:9` → 1920×1080；`9:16` → 1080×1920；`1:1` → 1080×1080 |
| `subtitle_position` | `bottom` | `top` / `bottom` / `center` / `custom`（custom 用 `custom_position` %） |
| `font_name` | `STHeitiMedium.ttc` | 自 `resource/fonts/` 加载 |
| `font_size` | `60` | 字幕字号 |
| `text_fore_color` / `stroke_color` / `stroke_width` | 白字黑描边 | MoviePy TextClip 渲染 |
| `subtitle_background_color` | 可选 | 字幕底板 |
| `voice_name` | `zh-CN-XiaoxiaoNeural-Female` | Edge 音色 |
| `voice_rate` | `1.0` | 语速倍率 |

合成实现：`video.generate_video()` 用 MoviePy `SubtitlesClip` + `TextClip` 烧录 SRT。

### LLM Provider 配置模式

- **Registry**：`app/models/llm_provider.py::LLM_PROVIDER_REGISTRY`（20 个 provider：moonshot/openai/gemini/deepseek/qwen/azure/volcengine/grok/minimax/mimo/cloudflare/modelscope/aihubmix/aimlapi/evolink/ollama/oneapi/litellm/groq/pollinations）
- **配置**：`config.toml` 每 provider 独立 `{id}_api_key` / `{id}_base_url` / `{id}_model_name`；空值走 Registry 默认
- **调用**：`llm.py` 按 `llm_provider` 选 adapter（多数 OpenAI-compatible；gemini/qwen/azure 等有专用路径）
- **与 Velora 对照**：Velora 用 `model_gateway_resolver`（Admin 全局网关 + `registered_models` 行级 `api_base`），工厂脚本层目前硬编码 `providers.qwen`（`SHORT_VIDEO_TEXT_MODEL` 环境变量）

### 可替换模块表

| 模块 | 接口/配置 | 默认实现 | 可替换为 |
|------|-----------|----------|----------|
| **LLM** | `llm_provider` + `{id}_api_key` | Kimi/moonshot | 任意 Registry provider 或 OpenAI-compatible 网关 |
| **素材** | `video_source` | Pexels | Pixabay / Coverr / local /（未来 Velora ComfyUI 出图） |
| **TTS** | `voice_name` 前缀 | Edge TTS | Azure/SiliconFlow/Gemini/MiMo/ElevenLabs/Chatterbox |
| **字幕** | `subtitle_provider` | edge（TTS 时间戳） | whisper（faster-whisper） |
| **合成** | `video.py` | MoviePy + FFmpeg | Velora 可保留 ffmpeg 路径，逐步替换 MoviePy |
| **BGM** | `bgm_type` | 本地 `resource/songs` | Sonilo / ElevenLabs AI 配乐 |
| **任务队列** | `enable_redis` | 内存 | Redis 多进程 |

---

## B. MoneyPrinter vs Velora short-video 对照表

| 维度 | MoneyPrinterTurbo | Velora `short_video_factory` | 差距说明 |
|------|-------------------|------------------------------|----------|
| **产品定位** | 主题→成片量产短视频 | 主题→静图幻灯 MVP | MPT 闭环更完整 |
| **入口** | WebUI + FastAPI + CLI + Agent Skill | `POST /api/short-video/generate` | Velora 仅 API |
| **文案** | LLM 连续旁白 + 搜索词 | LLM JSON 分段 `{narration, visual_prompt}` | Velora 已有多段结构，利于按句 TTS |
| **画面** | 素材库视频检索拼接 | PIL 静图幻灯 `render_slide_image` | Velora 无素材检索 |
| **TTS/旁白** | Edge TTS + SubMaker 时间轴 | **无** | **Velora 最大缺口** |
| **字幕** | SRT + TTS/Whisper 真实时间轴 | 均匀分段 cue（`i * 2s`）+ ffmpeg drawtext | Velora 字幕与旁白不同步 |
| **BGM** | 本地曲库 + AI 配乐 | `video_postprocess` 可选 default 路径 | Velora 已有基础能力 |
| **画幅** | 9:16 / 16:9 / 1:1 | 9:16 / 16:9 / 1:1 | 对齐 |
| **合成** | MoviePy 转场/字幕烧录 | ffmpeg concat + drawtext | Velora 更轻量 |
| **LLM 配置** | TOML 多 provider Registry | `SHORT_VIDEO_TEXT_MODEL` + qwen；网关在其他路径 | 工厂未接 `model_gateway_resolver` |
| **任务状态** | 内存/Redis + 进度 % | DB `Task` 表 async job | 各有方案 |
| **批量** | `video_count` 多版本 | `segment_count` 1–12 | 不同语义 |
| **画布电影级** | 不涉及 | Agent + ComfyUI 分镜链 | **不做替换**，量产线并行存在 |

### Velora 关键文件（已验证）

| 文件 | 现状 |
|------|------|
| `backend/services/short_video_factory.py` | topic → LLM segments → slide PNG → segment mp4 → concat；`SHORT_VIDEO_MOCK_LLM=1` 可 mock |
| `backend/routers/short_video.py` | `burn_captions` / `bgm` 参数；异步 `run_short_video_job` |
| `backend/services/video_postprocess.py` | `burn_subtitles`（drawtext）、`mix_bgm`；模板 `short_video_templates/*.yaml` |
| `backend/services/model_gateway_resolver.py` | Admin 文本网关；`resolve_chat_endpoint()` 供 agent/qwen 使用 |
| `backend/short_video_templates/portrait_default.yaml` | font_size 42、margin_bottom 120 |

### 与画布电影级链关系

Velora 画布 Agent（`velora_canvas.yaml` + ComfyUI）面向 **电影级分镜出图/出视频**；MoneyPrinter 面向 **高吞吐、非电影级、素材+配音+字幕** 量产。两者应 **并存可切换**，而非互相替换。forge-film 多卡 DAG 调度 **已搁置**，本笔记不涉及。

---

## C. 可借鉴 / 需自写

MIT 许可证，可参考实现，**仍建议抽模块自写进 Velora，禁止整仓粘贴**。

### 可直接借鉴（设计 + 算法）

| 借鉴点 | 来源 | Velora 落点 |
|--------|------|-------------|
| TTS → SubMaker → 按句 SRT | `voice.tts()` + `voice.create_subtitle()` | 新 `services/edge_tts_service.py` |
| 流水线阶段 + `stop_at` 中间产物 | `task._run_pipeline` | `short_video_factory` 分阶段函数 |
| 素材 Key 轮询 | `material.get_api_key()` | 选项 2 素材模块 |
| 字幕 edge/whisper 策略 | `generate_subtitle` 分支 | 工厂默认 edge，whisper 作可选 |
| 画幅枚举 + 分辨率映射 | `VideoAspect.to_resolution()` | 已有 `aspect_to_size()`，保持 |
| LLM Provider Registry 模式 | `llm_provider.py` | 对照 `registered_models` + gateway，不必复制 20 provider |

### 需自写适配（不直接搬）

| 项 | 原因 |
|----|------|
| MoviePy 全链路 | Velora 已用 ffmpeg + PIL；只借鉴字幕时间轴逻辑 |
| Streamlit WebUI | Velora 有 React 画布 + Admin |
| Redis 任务管理器 | Velora 用 DB Task + asyncio |
| config.toml 配置面 | 合入 Velora env + Admin 设置 |
| Pexels/Pixabay 下载 | 选项 2 再建；注意 API Key 与存储路径 |
| Upload-Post 跨平台发布 | 非当前量产优先级 |

### 不可抄

- 整仓依赖树（`moviepy`、`edge-tts`、`faster-whisper` 等按需引入）
- WebUI 大量 sponsor/硬编码文案

---

## D. 最小切片提案 — **推荐选项 1**

三选一对比：

| 选项 | 价值 | 风险/成本 | 与 Velora 现状关系 |
|------|------|-----------|-------------------|
| **1 Edge-TTS + 按句字幕时间轴** | 补齐配音与字幕同步；不依赖 Pexels Key | 低~中；新增 edge-tts 依赖 | 直接增强已有 `short_video_factory` + `video_postprocess` |
| **2 素材库路线（Pexels/本地匹配）** | 画面从幻灯升级为真实视频素材 | 中~高；外网 Key、存储、与幻灯/生成式切换 | 第二步 |
| **3 画布「短视频工厂」节点** | 入口统一到画布 | 低产品价值；不提升成片质量 | 选项 1/2 完成后再做 |

**选定：选项 1** — 给 `short_video_factory` 加 **Edge-TTS + 按句字幕时间轴**（先不接 Pexels）。

**理由**：

1. 直接补齐 Velora 工厂最大缺口（配音 + 字幕同步），服务「API 量产短视频」。
2. 不依赖 Pexels/外网素材 API，本机可 MOCK TTS 分段验证。
3. 复用现有 `/api/short-video/*` 与 `video_postprocess.burn_subtitles`。
4. 选项 2 素材库与选项 3 画布节点可在配音字幕闭环后再做。

目标流水线：

```text
topic → LLM segments（已有）
     → Edge-TTS per segment / per sentence（新增）
     → 按 TTS duration 生成字幕 cues（新增，替换均匀 2s 切分）
     → 静图幻灯仍作画面（暂保留）
     → ffmpeg 合成 + burn_subtitles + BGM（已有）
```

---

## E. 推荐切片实施步骤（5–8 步）

1. **新增 Edge-TTS 服务模块**  
   - 文件：`backend/services/edge_tts_service.py`  
   - 封装 `synthesize_segment(text, voice, rate) -> (audio_path, duration_sec, cues[])`  
   - 参考 MPT `voice.create_edge_tts_communicate()` + `SubMaker.cues` 提取逻辑（自写，不复制文件）

2. **扩展分段模型**  
   - `ShortVideoSegment` 增加可选 `audio_path`、`duration_sec`  
   - `generate_segments` 保持不变；新增 `synthesize_segments_audio(segments) -> list[cue]`

3. **改造 `build_factory_video`**  
   - 每段 `duration_sec` 取自 TTS 实际时长（替换固定 `DEFAULT_SEGMENT_SECONDS=2.0`）  
   - 可选：幻灯上显示该段 narration 文字（已有）

4. **字幕 cue 生成**  
   - 由 TTS cues 合并为每段一条或每句一条（与 `burn_subtitles` drawtext 兼容）  
   - 替换 `run_short_video_job` 里 `i * DEFAULT_SEGMENT_SECONDS` 均匀切分

5. **API 参数扩展（向后兼容）**  
   - `ShortVideoGenerateRequest` 增加 `voice_name`（默认 `zh-CN-XiaoxiaoNeural`）、`enable_tts: bool = true`  
   - `SHORT_VIDEO_MOCK_TTS=1` 环境变量用于无网络 pytest

6. **文本 LLM 接网关（可选同 PR）**  
   - `generate_segments` 改走 `resolve_chat_endpoint()` 而非硬编码 qwen  
   - 与 Admin Model Gateway 对齐

7. **测试**  
   - `backend/tests/test_edge_tts_service.py`：mock SubMaker / 时长计算 / cue 对齐  
   - `backend/tests/test_short_video_factory.py`：端到端 mock LLM+TTS → 断言 cue 非均匀

8. **文档**  
   - `SHORT_VIDEO_TEXT_MODEL` / `SHORT_VIDEO_MOCK_*` 说明写入 env 注释或 Admin 帮助

**拟改文件汇总**：

| 操作 | 路径 |
|------|------|
| 新建 | `backend/services/edge_tts_service.py` |
| 新建 | `backend/tests/test_edge_tts_service.py` |
| 修改 | `backend/services/short_video_factory.py` |
| 修改 | `backend/routers/short_video.py`（可选 voice 参数） |
| 可选 | `backend/services/video_postprocess.py`（cue 格式微调） |
| 可选 | `requirements.txt` / `pyproject.toml` 增加 `edge-tts` |

---

## F. 验收标准（3 条可测）

1. **`POST /api/short-video/generate`** 在 `enable_tts=true` 时，成片各段时长之和与 TTS 音频总时长误差 **< 0.5s**（非固定 2s×段数）。

2. **字幕同步**：`burn_captions=true` 时，每段旁白文字在对应时间段内显示（抽查 3 段：start/end 与 TTS cue 一致，而非 `i*2` 均匀分布）。

3. **Mock 可测**：`SHORT_VIDEO_MOCK_LLM=1` + `SHORT_VIDEO_MOCK_TTS=1` 下 pytest 全绿，无需外网 Edge TTS 与 LLM Key。

---

## G. 一次「主题→成片」依赖清单

### MoneyPrinterTurbo 真跑通依赖

| 依赖 | 必需 | 说明 |
|------|------|------|
| Python 3.11+ | 是 | `pyproject.toml` |
| ffmpeg | 是 | 自动下载或 `ffmpeg_path` |
| LLM API Key | 是（无自定义脚本时） | 默认 moonshot/Kimi |
| Edge TTS 网络 | 是（默认 TTS） | 无需 Key；需能访问微软 Edge TTS |
| Pexels API Key | 是（默认素材源） | `pexels_api_keys` |
| GPU | 否 | Whisper 可选加速 |
| faster-whisper 模型 | 仅 whisper 模式 | `models/whisper-large-v3` 约 3GB |

### Velora 选项 1 最小依赖

| 依赖 | 必需 | MOCK 策略 |
|------|------|-----------|
| ffmpeg | 是 | 已有 `video_enhance_probe._ffmpeg_executable()` |
| LLM（文案） | 是 | `SHORT_VIDEO_MOCK_LLM=1` |
| edge-tts | 是 | `SHORT_VIDEO_MOCK_TTS=1` 返回固定时长 + 假 cue |
| Pexels | **否**（选项 1） | 继续静图幻灯 |
| PIL | 是 | 已有 |

### 本阶段真跑通

本阶段 **未真跑通** MoneyPrinter 成片（只读拆解）。下轮选项 1 落地后，用 Velora API + mock 先验，再选一台能访问 Edge TTS 的机器做集成冒烟。

---

## 附录：目录结构速查

```text
MoneyPrinterTurbo/
├── main.py                 # FastAPI 启动
├── cli.py                  # CLI 入口
├── webui.sh / webui.bat    # Streamlit 启动
├── webui/Main.py           # WebUI 主界面
├── config.example.toml     # 配置模板
├── app/
│   ├── asgi.py             # FastAPI app
│   ├── router.py           # API 路由聚合
│   ├── config/             # 配置加载
│   ├── controllers/v1/     # video.py, llm.py
│   ├── models/             # schema, llm_provider, const
│   └── services/           # task, llm, voice, subtitle, material, video, bgm
├── resource/
│   ├── fonts/              # 字幕字体
│   └── songs/              # 默认 BGM
└── docs/skill/             # Agent Skill
```

---

## 选项1落地记录（2026-07-21）

### 改动文件

| 操作 | 路径 |
|------|------|
| 新建 | `backend/services/edge_tts_service.py` |
| 新建 | `backend/tests/test_edge_tts_service.py` |
| 修改 | `backend/services/short_video_factory.py` |
| 修改 | `backend/routers/short_video.py` |
| 修改 | `backend/tests/test_short_video_factory.py` |
| 修改 | `backend/scripts/_short_video_factory_probe.py` |
| 修改 | `backend/requirements.txt`（+ `edge-tts`） |

### 行为摘要

- `enable_tts=true`（默认）：每段 `synthesize_segment` → 静图幻灯时长对齐 TTS → segment mp4 混 aac → `build_timeline_cues` 累加全局字幕
- `enable_tts=false`：保持 `DEFAULT_SEGMENT_SECONDS=2.0` 均匀幻灯 + 均匀字幕 cue（向后兼容）
- MOCK：`SHORT_VIDEO_MOCK_TTS=1` 按字数估算时长（`max(0.8, len*0.12)`），不访问 Edge TTS

### mock vs 真 TTS

| 环境变量 | 作用 |
|----------|------|
| `SHORT_VIDEO_MOCK_LLM=1` | 脚本分段 mock，不调 LLM |
| `SHORT_VIDEO_MOCK_TTS=1` | TTS 时长/cues mock，不调 Edge TTS |
| 两者均不设 | 需 LLM Key + 本机可访问 Edge TTS 服务 |

### pytest

```bash
cd backend
SHORT_VIDEO_MOCK_LLM=1 SHORT_VIDEO_MOCK_TTS=1 pytest tests/test_edge_tts_service.py tests/test_short_video_factory.py -q
# 11 passed
```

### API 示例（7788）

```bash
# 登录获取 token 后：
curl -s -X POST http://127.0.0.1:7788/api/short-video/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topic":"人工智能如何改变生活","segment_count":3,"burn_captions":true,"enable_tts":true,"voice_name":"zh-CN-XiaoxiaoNeural"}'

curl -s http://127.0.0.1:7788/api/short-video/{task_id} \
  -H "Authorization: Bearer $TOKEN"
```

### 已知限制

- 画面仍为静图幻灯，未接 Pexels/素材库
- 真 TTS 依赖外网访问微软 Edge TTS；国内环境可能需代理
- `generate_segments` 仍走 `providers.qwen`，未接 Admin Model Gateway
- TTS 开启时 segment 带音频轨，关闭时无声；concat 行为不同
- MOCK 模式不写真实 mp3 内容，仅用于测试时间轴逻辑

---

## 选项2/3落地与项目收尾（2026-07-21）

### 阶段 A — 选项2：素材库

| 操作 | 路径 |
|------|------|
| 新建 | `backend/services/stock_material_service.py` |
| 新建 | `backend/tests/test_stock_material_service.py` |
| 修改 | `backend/services/short_video_factory.py`（`visual_source`、`stock_to_segment_mp4`、按段回退 slide） |
| 修改 | `backend/routers/short_video.py`（`visual_source`） |
| 修改 | `backend/.env.example` |

**行为**：

- `visual_source=slide`（默认）：与选项1一致
- `visual_source=stock`：每段用 `visual_prompt`/`narration` 搜 Pexels；失败 WARN 并回退该段 slide
- `SHORT_VIDEO_MOCK_STOCK=1`：ffmpeg 色块短视频，无需外网
- `PEXELS_API_KEY`：env 配置，支持逗号多 key 轮询；本地素材目录 `data/short_video_stock/`

### 阶段 B — 选项3：画布节点

| 操作 | 路径 |
|------|------|
| 新建 | `frontend/src/components/canvas/ShortVideoFactoryNode.jsx` + `.css` |
| 新建 | `frontend/src/services/shortVideoApi.js` |
| 修改 | `frontend/src/pages/Canvas.jsx`（`NODE_TYPES`） |
| 修改 | `CanvasLeftToolbar.jsx` / `NodePickerMenu.jsx` / `CanvasRightClickMenu.jsx` |
| 修改 | `frontend/src/utils/canvas/nodeHelpers.js` / `locale.js` / `localeCanvas.js` |
| 修改 | `backend/routers/short_video.py`（`GET /api/short-video/{id}/file` + `result_url`） |

**画布添加**：左侧工具栏「+」→「短视频工厂」；或双击空白画布 / 右键菜单添加 `short-video-factory` 节点。

**节点行为**：表单提交 `POST /api/short-video/generate` → 轮询 `GET /api/short-video/{id}` → 预览 `result_url`（`/file` 端点 + media ticket）。

### 回归 pytest

```bash
cd backend
SHORT_VIDEO_MOCK_LLM=1 SHORT_VIDEO_MOCK_TTS=1 SHORT_VIDEO_MOCK_STOCK=1 \
  pytest tests/test_edge_tts_service.py tests/test_short_video_factory.py tests/test_stock_material_service.py -q
# 17 passed
```

### API 示例（含 stock）

```bash
curl -s -X POST http://127.0.0.1:7788/api/short-video/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "城市夜景短视频",
    "segment_count": 3,
    "burn_captions": true,
    "enable_tts": true,
    "visual_source": "stock"
  }'

curl -s http://127.0.0.1:7788/api/short-video/{task_id}/file \
  -H "Authorization: Bearer $TOKEN" -o final.mp4
```

### 项目状态

**MoneyPrinterTurbo → ✅ 学习完成**（选项1 TTS/字幕 + 选项2 素材切换 + 选项3 画布入口）。

### 已知限制（收尾）

- 真 Pexels 需外网 + `PEXELS_API_KEY`；无 Key 时 stock 按段回退 slide
- 画面质量仍为量产短视频级别，非电影级 Agent 链
- `generate_segments` 未接 Admin Model Gateway（遗留）
- 无 Agent tool 自动建节点；需手动从画布菜单添加
- forge-film 多卡 DAG 已搁置

---

*笔记版本：v2.0 | 2026-07-21 | 选项2/3落地 + 项目收尾*
