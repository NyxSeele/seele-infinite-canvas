# ComfyUI 真实模型切换 Runbook

> 服务器（GPU）到位当天按本清单操作。真实验收仍按 HANDOFF **第八节 B**。  
> 版本：2026-06-30 · AutoDL 全流程见 [AUTODL_DEPLOY_RUNBOOK.md](./AUTODL_DEPLOY_RUNBOOK.md)

---

## 前置条件

- [ ] Redis 已启动（`REDIS_URL` 可连通）
- [ ] `DASHSCOPE_API_KEY` 已配置（Agent 文本链路）
- [ ] 数据库迁移至最新：`alembic upgrade head`（含 **001–022**；export_jobs=017、llm_routing=019、style_reference=020/021、**lut_applied=022**）
- [ ] `uploads/` 目录可写且已持久化（见下文 **§ uploads 持久化**）
- [ ] ComfyUI 服务仅内网可达；`COMFYUI_URL` 指向正确地址（见 `backend/.env.example`）

---

## 一、ComfyUI 健康检查

```powershell
# 替换为实际内网地址
curl http://127.0.0.1:8000/system_stats

# 可选：列出 checkpoints
curl http://127.0.0.1:8000/models/checkpoints
```

- [ ] HTTP 200，无连接超时
- [ ] checkpoints 列表含计划启用的模型文件

### 结构探针（无需 GPU 算力）

在 `models/` 下按 **§二** 放置同名占位权重后，可校验 workflow JSON 能否通过 ComfyUI `validate_prompt`（不等生成完成）：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\_comfyui_workflow_structure_probe.py
.\.venv\Scripts\python.exe scripts\_comfyui_workflow_structure_probe.py --model wan
```

- 基准组 `flux-dev` / `sd15` 须 PASS；否则先查占位文件与环境
- `hidream` / `wan` / `hunyuan` 须得明确 PASS 或带字段的 FAIL
- Wan 需 ComfyUI-WanVideoWrapper；占位文件清单见脚本模块 docstring

---

## 二、模型文件名与 Provider 条目核对

**不要猜测文件名。** 以 ComfyUI `models/` 目录实际文件为准。

### 结构化 Provider 注册表

真实 ComfyUI provider 已写入 [`model_registry.py`](../model_registry.py) 的 **`COMFYUI_LOCAL_PROVIDERS`**（非仅注释）。每条含：

| 字段 | 说明 |
|------|------|
| `id` | 与 `ALL_MODELS` / `registered_models.id` 一致 |
| `provider` | 固定 `comfyui` |
| `enabled` | 默认 `false`；切换日在 DB 或 Admin 置 `true` |
| `comfyui_endpoint_env` | 固定 `COMFYUI_URL`（全局 endpoint，非 per-model） |
| `comfyui_checkpoint` | checkpoint 占位文件名 |
| `workflow_module` | 代码路径，如 `backend/providers/comfyui.py` |
| `workflow_builder` | 构建函数名，如 `_build_flux_workflow` |
| `workflow_impl` | `ready` = 代码已实现；`pending` = 尚未实现 |
| `companion_files` | Flux/LTX 等伴随模型（可选） |

`LOCAL_MODEL_PRESETS` 由 `COMFYUI_LOCAL_PROVIDERS` 派生，供 `local_model_sync` 写入 `registered_models`（插入时 `enabled=false`）。

### 文件名替换位置

| 位置 | 说明 |
|------|------|
| `COMFYUI_LOCAL_PROVIDERS[].comfyui_checkpoint` | **主修改点**（同步到 `LOCAL_MODEL_PRESETS`） |
| `ALL_MODELS[].comfyui_model_file` | 与上表保持一致（前端 capabilities 元数据） |
| `providers/comfyui.py` → `_FLUX_CLIP_L` / `_FLUX_CLIP_T5` / `_FLUX_VAE` | Flux 伴随 CLIP/VAE 占位名 |
| `comfyui/client.py` → `DEFAULT_VIDEO_MODEL` | LTX 运行时默认 ckpt（可与 registry 略有版本后缀差异） |

操作步骤：

1. SSH 到 GPU 服务器，列出 `ComfyUI/models/checkpoints/`、`clip/`、`vae/`、`unet/`（视安装方式）
2. 修改 `COMFYUI_LOCAL_PROVIDERS` 中占位文件名为**实际文件名**（仅改不匹配项）
3. 同步更新 `ALL_MODELS` 中对应 `comfyui_model_file`（若与 provider 表不一致）
4. Flux 若 UNET 在 `unet/` 目录，确认 `UNETLoader.unet_name` 与磁盘一致
5. 重启 backend → 触发 `local_model_sync` 或 Admin 手动刷新 → 对 `workflow_impl=ready` 的模型 **enabled=true**

### Workflow 实现范围（切换前必读）

| 模型 | workflow_impl | 说明 |
|------|---------------|------|
| SD 1.5 / SDXL | ready | 早期已实现 |
| Flux Dev / Schnell | ready | `_build_flux_workflow` |
| LTX Video | ready | 画布视频 `video_backend=ltx` |
| HiDream | ready | `_build_hidream_workflow`（2026-06-25+） |
| Wan 2.6 | ready | `build_wan_video_workflow`；需 WanVideoWrapper 节点 |
| Hunyuan Video | ready | `build_hunyuan_video_workflow` |

**建议启用顺序**：先 SDXL + LTX 跑通 HANDOFF 第八节 B → 再逐个启用 Flux / HiDream / Wan / Hunyuan（大显存模型）。文件名必须与磁盘一致后再 `enabled=true`。

### 视频画质增强（SeedVR2 / Real-ESRGAN）

GPU 就绪后单独验收，不嵌入视频生成 workflow。

1. 在 ComfyUI 安装自定义节点：`ComfyUI-SeedVR2_VideoUpscaler`（Manager 搜索 SeedVR2 或 clone `numz/ComfyUI-SeedVR2_VideoUpscaler`）
2. 手测参考 workflow：`backend/comfyui/workflows/video_enhance_seedvr2.json`（ComfyUI UI 导入，5–10s 样片）
3. 确认 VRAM/耗时可接受后，在 `model_registry.py` 的 `COMFYUI_LOCAL_PROVIDERS` 中将 `video-enhance-seedvr2` 的 `enabled` 改为 `True`
4. 后端重启；`AGENT_MOCK_GENERATION=false`；前端画布完成态点「画质增强」做端到端验收
5. Fallback：将 `video-enhance-seedvr2` 设 `enabled=False`、`video-enhance-realesrgan` 设 `enabled=True`，确认 API 自动降级
6. mock 回归（无需 GPU）：`scripts/_video_enhance_probe.py`

| Provider | workflow_builder | 说明 |
|----------|------------------|------|
| `video-enhance-seedvr2` | `submit_seedvr2_enhance_prompt` | 时序一致，默认优先 |
| `video-enhance-realesrgan` | `submit_realesrgan_enhance_prompt` | 逐帧 fallback |

---

## uploads 持久化（Docker / 裸机）

生成产物与导出均落在 `backend/uploads/` 下：

```
uploads/
├── images/    # 出图落盘
├── videos/    # 视频落盘
└── exports/   # 完整项目导出 zip（export_jobs）
```

### Docker Compose（已配置）

仓库根目录 [`docker-compose.yml`](../../docker-compose.yml) 已为 backend 挂载命名卷：

```yaml
backend:
  volumes:
    - uploads_data:/app/uploads

volumes:
  uploads_data:
```

- 容器重建后 `images/`、`videos/`、`exports/` 数据保留
- 备份：对 volume `uploads_data` 做快照，或 `docker run --rm -v uploads_data:/data -v $(pwd):/backup alpine tar czf /backup/uploads-backup.tgz /data`
- 生产建议：改用宿主机 bind mount 便于运维，例如 `- ./data/uploads:/app/uploads`（需确保目录权限与备份策略）

### 裸机 / AutoDL

- 将 `backend/uploads/` 放在**数据盘**（如 `/root/autodl-tmp/AIStudio/backend/uploads`）
- `main.py` 启动时自动 `makedirs` 上述子目录
- 详见 [AUTODL_DEPLOY_RUNBOOK.md](./AUTODL_DEPLOY_RUNBOOK.md) §1.2、§6

---

## 三、切换到真实生成

```powershell
cd backend

# 1. 关闭 Mock（默认即为 false，显式设置更安全）
$env:AGENT_MOCK_GENERATION="false"

# 2. 确认 ComfyUI 地址
$env:COMFYUI_URL="http://<内网IP>:8000"

# 3. 重启后端（改 env 后必须重启）
.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 7788
```

- [ ] `AGENT_MOCK_GENERATION=false`
- [ ] Admin / `registered_models` 中目标 image、video 模型 `enabled=true`
- [ ] 分镜表默认模型已选对

---

## 四、验收（HANDOFF 第八节 B）

按 [HANDOFF.md](../../HANDOFF.md) **第八节 B** 执行：

1. 2 镜分镜表 → 节拍 → 分镜图 **completed** → 视频 **completed**
2. 出图 `reference_images` 含角色 + 场景参考图
3. 失败时 Agent `skipNotes` 显示真实错误（非乐观文案）

可选探针（依赖 LLM 稳定）：

```powershell
.\.venv\Scripts\python.exe scripts\_agent_pipeline_e2e_probe.py admin Admin@2026! --skip-text
```

---

## 五、回滚（验收失败时）

**目标：几分钟内恢复 mock 可用，避免「真实不工作、mock 也关」的中间态。**

```powershell
cd backend
$env:AGENT_MOCK_GENERATION="true"
$env:AGENT_MOCK_FAILURE_RATE="0"
# 重启 uvicorn
.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 7788
```

- [ ] 后端已重启
- [ ] `scripts\_mock_generation_acceptance.py` 或画布手动出图恢复 **completed**
- [ ] 记录失败原因（ComfyUI 日志、workflow 节点缺失、文件名不匹配等）再排期修复

---

## 六、超时阈值复核表

Mock 耗时（秒级）与真实生成（分钟级）差异大。**本次不预先调大数值**；真实环境测速后按表调整。

| 层级 | 配置位置 | 当前值 | Mock 参考 | 预估真实 | 切换时动作 |
|------|----------|--------|-----------|----------|------------|
| Mock 图像 sleep | `mock_generation.py` | 2–3 s | — | 10–60 s | **不改**（仅 mock） |
| Mock 视频 sleep | `mock_generation.py` | 5–8 s | — | 2–5 min | **不改** |
| Agent SSE 空闲 | `agentApi.js` `AGENT_SSE_IDLE_TIMEOUT_MS` | 30 s | — | — | **不改**（与生成超时独立） |
| Agent 请求总超时 | `agentApi.js` `AGENT_REQUEST_TIMEOUT_MS` | 180 s | — | — | 视 LLM 稳定性观察 |
| 分镜图等待 | `agentPipeline.js` `generateStoryboard` | 5 min | 充足 | 待测 | **待真实数据** |
| 视频等待 | `agentPipeline.js` `generateVideo` | 5 min | 充足 | 可能不足 | **待真实数据** |
| 节点条件默认 | `canvasPipelineState.js` | 2 min | — | — | 非媒体主路径 |
| 前端任务轮询停滞 | `taskPollTimeout.js` `TASK_POLL_TIMEOUT_MS` | 10 min | 充足 | 视频可能不足 | **待真实数据** |
| 僵尸任务清理 | `generation_guard.py` `_STALE_ACTIVE_SECONDS` | 15 min | 充足 | 大概率充足 | 观察 |
| ComfyUI reconcile | `generation_guard.py` | 600 s | 充足 | 视频可能不足 | **待真实数据** |
| ComfyUI HTTP | `providers/comfyui.py` `HTTP_TIMEOUT` | 30 s | 充足 | 提交/查询足够 | OK |

**调参原则**：以真实环境单次生成 P95 耗时 × 1.5 为参考，同步调整前端等待与后端 reconcile，避免「任务仍在跑但已被标失败」。

---

## 七、密钥与行政流程（非代码）

| 项 | 说明 |
|----|------|
| `DASHSCOPE_API_KEY` | 百炼文本 / 部分 API 图像；提前申请额度 |
| `JIMENG_API_KEY` | 仅 `jimeng-5.0-lite`；见 `.env.example` |
| ComfyUI 内网 | 勿将 `COMFYUI_URL` 暴露公网 |

---

## 八、相关代码路径

```
backend/providers/comfyui.py      # SD1.5/SDXL/Flux/HiDream 图像 workflow
backend/comfyui/client.py         # LTX / Wan / Hunyuan 视频 + SeedVR2/Real-ESRGAN 画质增强
backend/comfyui/workflows/        # GPU 手测 JSON 模板（不参与运行时加载）
backend/scripts/_video_enhance_probe.py
backend/scripts/_comfyui_workflow_structure_probe.py
backend/scripts/_real_media_pipeline_probe.py     # 真实 GPU 验收探针
backend/model_registry.py         # COMFYUI_LOCAL_PROVIDERS + ALL_MODELS
backend/services/mock_generation.py
backend/services/generation_guard.py
backend/docs/AUTODL_DEPLOY_RUNBOOK.md
frontend/src/components/canvas/taskPollTimeout.js
frontend/src/utils/canvas/canvasPipelineState.js
frontend/src/services/agentApi.js
```

---

*真实 GPU 验证不在本 Runbook 范围；验收标准以 HANDOFF 第八节 B 为准。*
