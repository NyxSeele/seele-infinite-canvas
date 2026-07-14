# AI Studio · AutoDL 服务器部署交接（HANDOFF_SERVER）

> **文档性质**：2026-07-06 在 AutoDL 实例上完成的**服务器侧部署与模型准备**交接记录。  
> **与仓库 HANDOFF 的关系**：本文件记录「这台机器上做了什么」；**产品功能、Phase 进度、探针清单、GPU 验收标准**仍以仓库根目录 [**`HANDOFF.md`**](HANDOFF.md) 为**后续开发主指南**（尤其 **§六 部署**、**§八 B 真实 GPU 验收**）。  
> **部署操作细节**：[`backend/docs/AUTODL_DEPLOY_RUNBOOK.md`](backend/docs/AUTODL_DEPLOY_RUNBOOK.md) · 本机实操备忘 [`/root/autodl-tmp/AUTODL_ACTUAL_RUNBOOK.md`](/root/autodl-tmp/AUTODL_ACTUAL_RUNBOOK.md)

最后更新：**2026-07-14 (UTC+8)**（Supervisor 五段硬约束 · 双 GPU comfyui0/1 · Tunnel 1033 事故备忘）

---

## 0. 当前进度摘要（2026-07-13）

| 维度 | 状态 |
|------|------|
| **产品能力** | G31–G45 闭环 + **视频审阅公开站** + **R2 团队文件/审阅媒资**；Hunyuan / AudioGen 上线；Phase4–7 完成 |
| **公网** | **`https://velora.seele0420.cloud`** → Cloudflare Tunnel（`cloudflared`）→ Nginx `:6006` |
| **pytest** | **121 passed**（2026-07-13） |
| **迁移** | Alembic head **026**（025 R2 · 026 review） |
| **磁盘** | `/root/autodl-tmp` **350G** · 已用 **~182G** · 可用 **~169G** |
| **服务** | ComfyUI `:8000` · 后端 `:7788` · Nginx `:6006` · **cloudflared**（Supervisor；开机自启已修） |
| **下轮优先** | ① 主观质量表（G47） ② 审阅加固（可选） ③ Seedance **最后再说** |

产品细节与待排期清单以 [`HANDOFF.md`](HANDOFF.md) 文首为准。

---

## 0a. 2026-07-13 运维增量（视频审阅 / R2 / Tunnel）

| 步骤 | 状态 | 说明 |
|------|------|------|
| 数据盘扩容 | ✅ | **300G → 350G**；可用约 **169G** |
| 迁移 025 / 026 | ✅ | `r2_files` + `review_videos` / `review_comments`；`alembic upgrade head` → **026** |
| R2 | ✅ | bucket `seele`；`.env` 配 `R2_*` / `R2_PUBLIC_URL`；浏览器 **presign PUT**；CORS 在 CF 控制台配置 |
| Cloudflare Tunnel | ✅ | Supervisor 进程 **`cloudflared`**；域名 `velora.seele0420.cloud` → `localhost:6006` |
| Nginx | ✅ | `client_max_body_size 2048m`；`/api` `proxy_read_timeout 3600s`（大文件上传） |
| 前端 dist | ✅ | 生产须 **`VITE_API_BASE_URL=`**（空）再 `npm run build`；同域 `/api` |
| 健康 | ✅ | 公网首页 **200**；本地 7788/8000/6006 正常 |

**生产管理员账号（2026-07-14）**：**`seele`**（`role=admin`，由原 `admin` 更名；探针团队 A owner、无限配额等不变）· 密码 **`dfy042005`** · `SEED_ADMIN_PASSWORD` 已同步至 `backend/.env`。探针种子 **`testuser` / `testuser2`** 见 `.env`（勿写入 git）。临时注册测试号 `testinv2` / `testinv3` 已删除。

**硬约束 · Admin 文本模型**：未经负责人明确同意，**禁止**修改 Admin 后台「模型管理」中的文本模型配置，也**勿重跑** `scripts/_enable_text_models.py`（会覆盖 DB 里已配默认/启用项）。详见 [`HANDOFF.md`](HANDOFF.md) 文首同条约束。

**硬约束 · Supervisor / Tunnel（Cursor 改代码必读）**：`deploy/supervisor-autodl.conf` → `/etc/supervisor/conf.d/aistudio.conf` 必须**始终含 5 个 `[program:]` 段**：

| 段名 | 作用 | 删掉后果 |
|------|------|----------|
| `comfyui0` / `comfyui1` | 双卡 ComfyUI `:8000` / `:8001` | GPU 推理不可用 |
| `aistudio-backend` | FastAPI `:7788` | API 不可用 |
| **`nginx`** | 反代前端 + `/api` → `:6006` | Tunnel 回源失败 |
| **`cloudflared`** | Cloudflare Tunnel → 公网域名 | **Error 1033**（本地 `:6006` 可能仍 200） |

- **禁止**为改 `COMFYUI_NODES` / `--database-url` 等而**整文件覆盖** supervisor 配置（2026-07-14 事故根因）。
- **正确做法**：在仓库 `deploy/supervisor-autodl.conf` 上**只改需要的行** → `diff` 确认五段都在 → `cp` → `/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf update`。
- **验收**：`curl -s -o /dev/null -w "%{http_code}\n" https://velora.seele0420.cloud/api/health` → **200**；`supervisorctl status` 中 `cloudflared` 为 RUNNING。
- `supervisorctl` 用 **`/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf`**（勿用 miniconda 默认路径）。

---

## 0b. 阅读顺序（新对话恢复上下文）

| 优先级 | 文档 | 用途 |
|--------|------|------|
| 1 | **本文件 `HANDOFF_SERVER.md`** | 这台 AutoDL 服务器当前状态、已装服务、已下模型、待办 |
| 2 | **[`HANDOFF.md`](HANDOFF.md)** | 产品 Phase、API 契约、探针、Admin `enabled` 策略、验收定义 |
| 3 | **[`AUTODL_DEPLOY_RUNBOOK.md`](backend/docs/AUTODL_DEPLOY_RUNBOOK.md)** | 通用 AutoDL 部署步骤（模板来源） |
| 4 | **`/root/autodl-tmp/AUTODL_ACTUAL_RUNBOOK.md`** | 针对本镜像（ComfyUI_2024 + 4090）的实操版 |

---

## 1. 实例与环境快照

| 项 | 值 |
|----|-----|
| **当前实例 ID** | `2db141bceb-853ff7b9`（**269 机** · 2026-07-08 自 107 机克隆） |
| 镜像 | `comfyanonymous/ComfyUI/ComfyUI_2024`（云绘社区版） |
| GPU | **NVIDIA RTX 4090 24GB** |
| Python | 3.11.13 |
| Node（系统） | 20.20.2（NodeSource 安装；原镜像仅 Node 12） |
| CUDA 驱动 | 580.105.08 · 运行时 CUDA 13.0 |
| `nvcc` | **未安装**（纯推理无影响） |
| 区域 | AutoDL `nm-B1` / `neimengDC3` |
| 对外端口 | Nginx **6006**（控制台「自定义服务」查公网 URL） |
| 主机名 | `autodl-container-2db141bceb-853ff7b9` |

### 磁盘（2026-07-13 复核）

| 挂载点 | 容量 | 已用 | 可用 | 说明 |
|--------|------|------|------|------|
| `/` 系统盘 | 30G | ~19G | ~12G | ComfyUI 已迁出 |
| `/root/autodl-tmp` | **350G** | **~182G** | **~169G** | 含 Flux/Wan/HiDream/SeedVR2 + PuLID + LTX2-fp4 + HunyuanVideo + AudioGen（已从 300G 扩容） |

### 关键路径（增补）

```
/root/autodl-tmp/scripts/
├── download_models_aria2.sh      # aria2 批量下载（HF 镜像）
├── download_models_resume.sh     # 续传 Wan 整包 + Z-Image（顺序）
├── download_hidream_aria2.sh     # HiDream-i1 fp8 全套（~31GB，跳过 ae）
└── zimage_download.log           # Z-Image 并行下载日志（/root/autodl-tmp/logs/）
```

### 关键路径

```
/root/autodl-tmp/
├── AIStudio/                          # git 浅克隆（--depth 1）
│   ├── backend/.venv/                 # 后端 + ComfyUI 共用 Python 环境
│   ├── backend/.env                   # 生产配置（勿提交 git）
│   ├── frontend/dist/                 # npm run build 产物
│   └── HANDOFF_SERVER.md              # 本文件
├── ComfyUI/                           # 从 /root/ComfyUI 迁入
├── AUTODL_ACTUAL_RUNBOOK.md           # 本机实操手册副本
└── logs/                              # Supervisor 日志
    ├── comfyui.out.log / .err.log
    └── backend.out.log / .err.log

/root/ComfyUI -> /root/autodl-tmp/ComfyUI   # 软链接（兼容旧路径）
```

---

## 2. 今日工作流水（2026-07-06）

### 2.1 环境与代码

| 步骤 | 状态 | 说明 |
|------|------|------|
| SSH 环境确认 | ✅ | root · RTX 4090 · 系统盘原 81% 满 |
| 克隆 `seele-infinite-canvas` → `AIStudio` | ✅ | 方案 B：`git -c http.version=HTTP/1.1 clone --depth 1`（~3s） |
| 数据盘扩容 | ✅ | 用户控制台扩至 **200GB** |
| 环境摸底 | ✅ | ComfyUI 在系统盘、npm/redis/nginx 缺失、镜像无大模型 |

### 2.2 服务部署（按 `AUTODL_ACTUAL_RUNBOOK.md`）

| 步骤 | 状态 | 说明 |
|------|------|------|
| ComfyUI 迁数据盘 + 软链 | ✅ | 释放系统盘 ~8GB |
| apt 安装 redis-server、nginx、supervisor | ✅ | |
| Node 20.20.2 + npm 10.8.2 | ✅ | 移除 `libnode-dev` 冲突后 NodeSource 安装 |
| Redis 启动 + `requirepass` | ✅ | 与 `.env` 中 `REDIS_URL` 一致 |
| 后端 venv + `requirements.txt` | ✅ | |
| ComfyUI `requirements.txt` 装入同一 venv | ✅ | PyTorch 2.12 + CUDA 13 |
| `.env` 配置 | ✅ | 自本地 env 写入；`APP_ENV=production` |
| `alembic upgrade head` | ✅ | 至 **022** |
| `init_db` 种子账号 | ✅ | 一次性 `APP_ENV=development` 执行 seed |
| 前端 `npm ci && npm run build` | ✅ | |
| Nginx `:6006` | ✅ | `deploy/nginx-autodl.conf` |
| Supervisor 常驻 | ✅ | ComfyUI `:8000` + 后端 `:7788` |
| 补装 `python-multipart` | ✅ | 后端启动缺依赖已修复 |
| Nginx 读 `/root` 权限 | ✅ | `chmod 711 /root` |

### 2.3 模型与下载调研

| 步骤 | 状态 | 说明 |
|------|------|------|
| `/autodl-pub` 调研 | ✅ | 仅学术数据集，**无**生成式 AI 权重 |
| `HF_ENDPOINT=https://hf-mirror.com` 写入 `~/.bashrc` | ✅ | |
| FLUX.1-dev fp8 全家桶 | ✅ | 见 §4；BFL gated，改用公开源 |
| 云绘工作流 / `new_dl_comm.yaml` 调研 | ✅ | 86 预设工作流 + ModelScope `nahz202/*` 下载表 |

### 2.4 Phase 2 执行（2026-07-07）

| 步骤 | 状态 | 说明 |
|------|------|------|
| 测速选源（hf-mirror / modelscope / HF） | ✅ | hf-mirror 可用；nahz202 ModelScope **404**；大文件用 **aria2c** |
| 清理权重 | ✅ | 删 anything-v5、z_image_turbo、qwen_3_4b（~21GB） |
| 下载 Wan i2v UNET ×2 | ✅ | `wan2.2_i2v_*` 各 ~14GB → `diffusion_models/` |
| `build_wan_i2v_workflow` + registry | ✅ | `wan-i2v` **enabled**；探针 `--model wan-i2v` **PASS** |
| Prompt Compiler + 前端 Phase 2 | ✅ | `POST /api/prompt/compile`；CharacterCardNode；分镜表 compile |
| §八 B GPU 回归 | ✅ | `_gpu_acceptance_8b_probe.py` **PASS** |
| Supervisor 纳管 | ✅ | `comfyui` / `aistudio-backend` / **`nginx`** 由 `/etc/supervisor` 实例管理（见 §3.1） |

### 2.5 HiDream-i1 落盘（2026-07-07 下午）

| 步骤 | 状态 | 说明 |
|------|------|------|
| aria2 下载 i1 全套 | ✅ | `download_hidream_aria2.sh`；HF `Comfy-Org/HiDream-I1_ComfyUI`；~31GB |
| registry + workflow 对齐 | ✅ | `hidream_i1_dev_fp8` + QuadrupleCLIP 四编码器；`enabled=True` |
| 结构探针 | ✅ | `--model hidream` **PASS** |
### 2.6 Phase 2 收尾验收（2026-07-07 下午）

| 步骤 | 状态 | 说明 |
|------|------|------|
| HiDream API smoke test | ✅ | `POST /api/tasks/image` model=hidream；VRAM 22.87GB；26s；1.2MB PNG |
| Wan i2v API smoke test | ✅ | `POST /api/tasks/video` + `/api/uploads/` 参考图；VRAM 21.15GB；150s；655KB MP4 |
| Supervisor 重启恢复 | ✅ | stop all → supervisord → start；comfyui/backend **RUNNING** |
| pytest 全量 | ✅ | **64 passed**（`python -m pytest tests/ -q`） |
| §八 B GPU 探针 | ✅ | `_gpu_acceptance_8b_probe.py` **PASS** |
| 临时文件清理 | ✅ | `/tmp/test_dl*`、`.aria2` 残留已删 |

### 2.7 核心链路双项修复（2026-07-07 晚）

| 步骤 | 状态 | 说明 |
|------|------|------|
| `_real_media_pipeline_probe.py` 默认模型 | ✅ | `stable-diffusion` → **`flux-dev`**（SD 无 ComfyUI provider，原提交 500） |
| i2v `/api/view` 参考图 | ✅ | `resolve_image_reference_path()`；`_resolve_comfy_output_path` 增 `ComfyUI/output` |
| 单元测试 | ✅ | `tests/test_media_access.py`；pytest **61 passed** |
| 探针回归 | ✅ | `_real_media_pipeline_probe.py` **PASS**（~16s 出图） |
| i2v `/api/view` smoke | ✅ | flux 出图 → `wan-i2v` + `/api/view` 参考图 submit **200**（不再「非法上传路径」） |

### 2.8 Prompt 调试 GPU 验收（2026-07-07 晚）

| 步骤 | 状态 | 说明 |
|------|------|------|
| 阶段一 Flux T1–T4 | ✅ | 图像 translate-only + suffix 注入；日志 `prompt_debug_phase1*.json` |
| 阶段二 Wan i2v V1–V4 | ✅ | 视频 suffix 后置；双参考图路径；V3-retest 同图 PASS；`00008_`～`00011_.mp4` |
| 阶段三 FLF2V K1–K4 | ✅ | `build_wan_flf2v_workflow`；`WanFirstLastFrameToVideo` + **i2v UNET**；`00013_`～`00016_.mp4` |
| K4 配额补跑 | ✅ | testuser 曾 429；`reset_quota` + `video_limit=100` 后单跑 K4 **completed** |
| pytest | ✅ | **64 passed**（+`test_wan_flf2v.py` 3 例） |
| 探针账号文档 | ✅ | [`backend/docs/PROBE_ACCOUNTS.md`](backend/docs/PROBE_ACCOUNTS.md) |

**日志路径**（`/root/autodl-tmp/logs/`）：

| 文件 | 内容 |
|------|------|
| `prompt_debug_phase1*.json` | Flux T1–T4 |
| `prompt_debug_phase2_postfix.json` | Wan i2v V1–V4 |
| `prompt_debug_phase3_keyframe.json` | FLF2V K1–K4 全批 |
| `prompt_debug_phase3_k4.json` | K4 补跑 |

**脚本**：`_prompt_debug_phase1.py` · `_prompt_debug_phase2.py` · `_prompt_debug_phase3_keyframe.py`（可单跑 `K4`）

**说明**：FLF2V（`wan-i2v`）使用 **i2v high/low UNET**；G34 另启 `wan-fun-inpaint`（`WanFunInpaintToVideo` + fun_inpaint 双 UNET），二者并存。

### 2.9 实例迁移 + 新机验收（2026-07-08）

| 步骤 | 状态 | 说明 |
|------|------|------|
| 107→269 数据盘克隆 | ✅ | 源 `8b78499521` 锁定；目标 `2db141bceb`；`autodl-tmp` **178G** 完整 |
| Supervisor 修复 | ✅ | 系统 `/usr/bin/supervisord -c /etc/supervisor/supervisord.conf`；三进程 RUNNING |
| Nginx `:6006` | ✅ | `sites-enabled/aistudio` |
| Redis 自启 | ✅ | `update-rc.d redis-server enable` |
| `python-multipart` | ✅ | 已装 + 写入 `requirements.txt` |
| text 模型 DB | ✅ | `scripts/_enable_text_models.py`（**勿随意重跑**；仅首次或负责人明确要求）；默认 **qwen-plus** |
| `model_checker` | ✅ | 扫描 `diffusion_models`（Flux/Wan 在盘可检出） |
| `stable-diffusion` | ⏸ | DB **disabled**（`checkpoints/` 无 v1-5 权重） |
| 全量探针 | ⚠️ | 22 探针批跑；15 PASS / 部分超时或环境限制；日志 `all_probes_20260708_1439.log` |
| 关键重跑 | ✅ | `task_records` · `agent_trace_baseline` · `gpu_acceptance_8b` · `real_media_pipeline` **PASS** |
| pytest | ✅ | **67 passed** |

**Supervisor 注意**：克隆后勿用 miniconda 默认 `supervisorctl`（缺模块）；平台 init supervisord（`/init/supervisor`）**不**管 AI Studio 进程。

**百炼额度**：`qwen-max`/`qwen-turbo` 免费档耗尽（403）；DB 已禁用，仅 **qwen-plus** 用于 A2。

---

## 3. 服务状态与验收

### 3.1 Supervisor（AI Studio 专用 · `/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf`）

> **注意**：AutoDL 平台另有 init supervisord（`unix:///tmp/supervisor.sock`，管 jupyter/sshd/tensorboard 等），**不**管理 ComfyUI/Backend/Nginx。勿混用默认 `supervisorctl`（会连错 socket 或报 refused）。

> **硬约束（2026-07-14）**：勿整文件覆盖 `aistudio.conf`。五段缺一不可，尤其 **`nginx` + `cloudflared`**（公网 Tunnel）。见 §0a 上表。

| 进程 | 命令要点 | 端口 | 典型状态 |
|------|----------|------|----------|
| `comfyui0` | `ComfyUI/main.py --port 8000 --database-url ...8000.db` · `CUDA_VISIBLE_DEVICES=0` | **8000** | RUNNING |
| `comfyui1` | `ComfyUI/main.py --port 8001 --database-url ...8001.db` · `CUDA_VISIBLE_DEVICES=1` | **8001** | RUNNING |
| `aistudio-backend` | `uvicorn main:app --host 127.0.0.1 --port 7788` · `COMFYUI_NODES=8000,8001` | **7788** | RUNNING |
| `nginx` | `/usr/sbin/nginx -g "daemon off;"` | **6006** | RUNNING |
| `cloudflared` | `/usr/local/bin/cloudflared tunnel run --token …` → `velora.seele0420.cloud` | — | RUNNING |

配置文件：**仓库** [`deploy/supervisor-autodl.conf`](deploy/supervisor-autodl.conf)（单一真相来源）→ **`/etc/supervisor/conf.d/aistudio.conf`**

```bash
# 改配置的安全流程（勿跳过 diff）
diff -u /etc/supervisor/conf.d/aistudio.conf /root/autodl-tmp/AIStudio/deploy/supervisor-autodl.conf
cp /root/autodl-tmp/AIStudio/deploy/supervisor-autodl.conf /etc/supervisor/conf.d/aistudio.conf
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf reread
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf update
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf status

# 公网 Tunnel 验收
curl -s -o /dev/null -w "%{http_code}\n" https://velora.seele0420.cloud/api/health   # 期望 200

# 若 status 报 refused connection，先启动守护进程（须 -d：本机为 Go supervisord）：
/usr/bin/supervisord -d -c /etc/supervisor/supervisord.conf
# 或：bash /root/autodl-tmp/start.sh
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf restart comfyui0 comfyui1 aistudio-backend nginx cloudflared
```

**Cloudflare Error 1033 排错**：本地 `curl http://127.0.0.1:6006/` 为 200 但公网 1033 → 几乎总是 **`cloudflared` 未 RUNNING**；查 `tail /root/autodl-tmp/logs/cloudflared.err.log` 与 `ps aux | grep cloudflared`。

### 3.2 健康检查与 GPU Smoke Test（2026-07-07 更新）

```bash
curl http://127.0.0.1:7788/health
# {"status":"ok","env":"production","redis":true,"agent_mock_generation":false,"comfyui_url":"http://127.0.0.1:8000"}

curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/    # 200
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:6006/    # 200
```

**GPU Smoke Test（AI Studio API · 真实推理）**

| 测试项 | 日期 | VRAM 峰值 | 耗时 | 输出 | 结果 |
|--------|------|-----------|------|------|------|
| hidream smoke test | 2026-07-07 | 22.87 GB | 25.9 s | 1.19 MB PNG | **PASS** |
| wan-i2v smoke test | 2026-07-07 | 21.15 GB | 150.2 s | 670 KB MP4 | **PASS** |
| Supervisor 重启恢复 | 2026-07-07 | — | — | comfyui/backend RUNNING；7788/8000/6006 均 200 | **PASS** |

Smoke 脚本与日志：`backend/scripts/_phase2_smoke_tests.py` · `/root/autodl-tmp/logs/phase2_smoke_results.json`

**探针回归（2026-07-07 晚）**：`python -m pytest tests/ -q` → **64 passed**；`AGENT_MOCK_GENERATION=false python scripts/_gpu_acceptance_8b_probe.py` → **PASS §八B**；`_real_media_pipeline_probe.py`（默认 **flux-dev**）→ **PASS**；Prompt 调试 K1–K4 FLF2V → **completed**

### 3.3 登录账号（种子数据）

| 用户 | 密码来源 |
|------|----------|
| `seele`（**admin**） | `SEED_ADMIN_PASSWORD` in `backend/.env`（2026-07-14 自 `admin` 更名） |
| `testuser` | `SEED_TESTUSER_PASSWORD` |
| `testuser2` | `SEED_TESTUSER2_PASSWORD` |

> 生产环境请在首次登录后改密。密钥与 API Key 见 `backend/.env`，**勿写入本 HANDOFF 或提交 git**。

### 3.4 环境变量要点（`backend/.env`）

| 变量 | 本机值 |
|------|--------|
| `APP_ENV` | `production` |
| `COMFYUI_URL` | `http://127.0.0.1:8000` |
| `REDIS_URL` | `redis://:<password>@127.0.0.1:6379/0` |
| `AGENT_MOCK_GENERATION` | `false` |
| `DASHSCOPE_API_KEY` | 已配置（百炼） |
| `JWT_SECRET` | 已配置 |

---

## 4. 模型资产清单

### 4.1 镜像预装（迁移前即存在）

- **Checkpoint**：~~`anything-v5-PrtRE.safetensors`~~ **已删除**（2026-07-07 Phase 2）；SD 1.5 改用 `v1-5-pruned-emaonly.safetensors`
- **辅助小模型**：人脸修复、YOLO、SAM、RealESRGAN、embeddings 等（合计约数 GB）
- **自定义节点**：44 个（含 WanVideoWrapper、SeedVR2、ComfyUI-nunchaku 等）
- **大模型目录**：仅有空文件夹结构（`vae/FLUX1`、`LTX23`、`loras/` 等），**无权重**（2026-07-06 状态；此后已补 Flux/Wan/SeedVR2）

### 4.2 已下载 / 对齐（2026-07-07 · Phase 2 最终清单）

| 模型 | 文件名 | 大小 | 用途 | AI Studio 启用 |
|------|--------|------|------|----------------|
| Flux fp8 | `flux1-dev-fp8.safetensors` | 17G | 文生图主力 | ✅ `flux-dev` |
| HiDream i1 fp8 | `hidream_i1_dev_fp8.safetensors` | 16G | 文生图备选 | ✅ `hidream` |
| Wan2.2 t2v high/low | `wan2.2_t2v_*_14B_fp8_scaled` ×2 | 28G | 文生视频 | ✅ `wan-2.6` |
| Wan2.2 i2v high/low | `wan2.2_i2v_*_14B_fp8_scaled` ×2 | 28G | 图生视频 | ✅ `wan-i2v` |
| Wan2.2 fun_inpaint | `wan2.2_fun_inpaint_*` ×2 | 31G | 首尾帧 Fun Inpaint（专用 UNET） | ✅ G34 `wan-fun-inpaint` 已接入；与 i2v FLF2V 并存 |
| SeedVR2 3B fp8 | `seedvr2_ema_3b_fp8_e4m3fn.safetensors` | 3.2G | 画质增强 | ✅ `video-enhance-seedvr2` |
| **Nunchaku FLUX int4** | `svdq-int4_r32-flux.1-dev.safetensors` | 6.4G | PuLID 人物一致性 DiT | ✅ `flux-pulid`（GPU smoke PASS） |
| **PuLID 套件** | pulid + antelopev2 + EVA-CLIP + t5 fp16 | ~18G | 人脸身份锚定 | ✅ |
| **LTX-2 fp4** | checkpoint + gemma + upscaler + 2× LoRA | ~36G | 19B 文生视频 | ✅ `ltx2-fp4` 结构探针 PASS |

**能力链路（2026-07-09 G30 闭环）**：原六条 + **flux-pulid**（GPU smoke + phash 对照 PASS）+ **ltx2-fp4**（权重落盘 + API + 结构探针 PASS）。详见 [`G30_RESUME.md`](G30_RESUME.md)。

#### G30 / PuLID / LTX2 运维要点

| 项 | 说明 |
|----|------|
| nunchaku | venv `import nunchaku` OK；ComfyUI 节点 `NunchakuPuLIDLoaderV2` 等已注册 |
| facexlib | 权重须在 `ComfyUI/models/facexlib/*.pth` **根目录**（`detection_Resnet50_Final.pth` / `parsing_bisenet.pth` / `parsing_parsenet.pth`）；放子目录会导致 align face fail |
| 参考脸 | PuLID 需真实人脸图；合成图会失败。官方测试图：`/tmp/face_ref.png` |
| VRAM | **勿同时加载** LTX2 19B 与 PuLID Flux（24GB） |
| 关机后 | ✅ **开机自启**：`/etc/autodl.sh` → `/root/autodl-tmp/start.sh`（`supervisord -d -c /etc/supervisor/supervisord.conf`） |
| 探针日志 | `g30_pulid_smoke.json` · `g30_phash_compare.json` · `route_c_results.json`（含 `consistency_phash`） |

#### Flux fp8（✅ 已验收出图）

| 文件 | 路径 | registry 对齐 |
|------|------|---------------|
| `flux1-dev-fp8.safetensors` | `diffusion_models/` | `flux-dev` → 同名 |
| `clip_l.safetensors` | `text_encoders/` | 不变 |
| `t5xxl_fp8_e4m3fn.safetensors` | `text_encoders/` | `comfyui.py` `_FLUX_CLIP_T5` 已改 |
| `ae.safetensors` | `vae/` | 软链 → `flux-vae-bf16` |

探针：`python scripts/_comfyui_workflow_structure_probe.py --model flux-dev` **PASS**；API 出图 **PASS**（`flux-dev`）。

#### SeedVR2 3B fp8（✅ 完成）

| 文件 | 路径 | 大小 | 来源 |
|------|------|------|------|
| `seedvr2_ema_3b_fp8_e4m3fn.safetensors` | `models/SEEDVR2/` | 3.16GB | `numz/SeedVR2_comfyUI`（HF 镜像） |
| `ema_vae_fp16.safetensors` | `models/SEEDVR2/` | 478MB | 同上 |

代码对齐：`client.py` / `model_registry.py` / `video_enhance_seedvr2.json` 已改为 3B fp8；`video-enhance-seedvr2.enabled=True`。

ComfyUI 插件：`ComfyUI-SeedVR2_VideoUpscaler` 已加载（venv 补装 `requirements.txt`）。

#### Wan 2.2 T2V 四步（✅ T2V 核心完成，整包续传）

| 文件 | 路径 | 状态 |
|------|------|------|
| `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | ✅ 14.3GB |
| `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | ✅ 14.3GB |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `text_encoders/` | ✅ 6.3GB |
| `wan_2.1_vae.safetensors` | `vae/` | ✅ 242MB |
| `wan2.2_t2v_lightx2v_*_noise.safetensors` | `loras/` | ✅ 各 1.1GB |
| `wan2.2_fun_inpaint_*` / `wan2.2_i2v_lightx2v_*` | 各目录 | ✅ 整包续传完成（`download_models_resume.sh`） |
| `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | ✅ 14.3GB（2026-07-07 aria2 + hf-mirror） |
| `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | ✅ 14.3GB（同上） |

来源：**`Comfy-Org/Wan_2.2_ComfyUI_repackaged`**（非 `nahz202/Wan-Video-ComfyOrg` 的 Wan2.1 权重）。

Backend：`build_wan_video_workflow()` 已改为 Wan2.2 原生双 UNET + Lightx2v 四步链；**`build_wan_i2v_workflow()`** 图生视频（`LoadImage` + `WanImageToVideo`）；**`build_wan_flf2v_workflow()`** 首尾帧（双 `LoadImage` + `WanFirstLastFrameToVideo`，仍用 i2v UNET）；视频输出 `CreateVideo`+`SaveVideo`；API id `wan-2.6`（T2V）、**`wan-i2v`**（I2V/FLF2V，`mode=image2video` / `flf2v`）。结构探针 `--model wan` / **`--model wan-i2v`** **PASS**。

#### Z-Image Turbo（~~已落盘~~ **已删除，不纳入 API**）

| 文件 | 路径 | 状态 |
|------|------|------|
| ~~`z_image_turbo_bf16.safetensors`~~ | ~~`diffusion_models/`~~ | **已删除**（~19GB，2026-07-07） |
| ~~`qwen_3_4b.safetensors`~~ | ~~`text_encoders/`~~ | **已删除**（配套 encoder） |

决策：Z-Image 从未注册 AI Studio API；权重删除以腾出 i2v UNET 磁盘空间。工作流 JSON 仍保留于云绘镜像供 ComfyUI 手跑参考。

#### HiDream-i1 fp8（✅ 2026-07-07 落盘 + 结构探针 PASS）

| 文件 | 路径 | 大小 | 来源 |
|------|------|------|------|
| `hidream_i1_dev_fp8.safetensors` | `diffusion_models/` | 15.9GB | `Comfy-Org/HiDream-I1_ComfyUI`（HF 镜像） |
| `clip_l_hidream.safetensors` | `text_encoders/` | 237MB | 同上 |
| `clip_g_hidream.safetensors` | `text_encoders/` | 1.3GB | 同上 |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | `text_encoders/` | 4.9GB | 同上（**独立于** Flux 的 `t5xxl_fp8_e4m3fn.safetensors`） |
| `llama_3.1_8b_instruct_fp8_scaled.safetensors` | `text_encoders/` | 8.5GB | 同上 |
| `ae.safetensors` | `vae/` | 复用 Flux 软链 | 跳过下载（`→ flux-vae-bf16`） |

Backend：`providers/comfyui.py` → `_build_hidream_workflow`（UNETLoader + QuadrupleCLIPLoader + ModelSamplingSD3 + KSampler）；`model_registry.py` → **`hidream`**（`enabled=True`）；采样参数 steps=28 / cfg=1.0 / lcm / shift=6.0。

探针：`python scripts/_comfyui_workflow_structure_probe.py --model hidream` **PASS**；API smoke test **PASS**（2026-07-07）。

下载脚本：`/root/autodl-tmp/scripts/download_hidream_aria2.sh`；日志：`/root/autodl-tmp/logs/hidream_download.log`。

### 4.3 历史：2026-07-06 FLUX 首次下载记录

| 文件 | 路径 | 大小 | 来源 |
|------|------|------|------|
| `flux1-dev-fp8.safetensors` | `models/diffusion_models/` | 17G | `Comfy-Org/flux1-dev`（HF 镜像） |
| `clip_l.safetensors` | `models/text_encoders/` | 235M | `comfyanonymous/flux_text_encoders` |
| `t5xxl_fp8_e4m3fn.safetensors` | `models/text_encoders/` | 4.6G | 同上 |
| `flux-vae-bf16.safetensors` | `models/vae/` | 160M | `Kijai/flux-fp8` |
| `ae.safetensors` | `models/vae/` | 软链 → 上者 | 后端期望文件名 |

**注意：**

1. `black-forest-labs/FLUX.1-dev` 为 **gated**，无 HF Token 时 403。
2. VAE 使用 Kijai `flux-vae-bf16`；出图异常时换 BFL 官方 `ae.safetensors`。

### 4.4 下载方式实测（2026-07-07 更新）

| 方式 | 结论 |
|------|------|
| `hf download` + `HF_ENDPOINT=https://hf-mirror.com` | ✅ 主力（`huggingface-cli` 已废弃） |
| `aria2c -x 16` 直链 `hf-mirror.com/.../resolve/main/...` | ✅ 大文件推荐；脚本见 `/root/autodl-tmp/scripts/download_models_resume.sh` |
| `modelscope download nahz202/*` | ❌ 本机 404（nahz202 仓库不可用） |
| `Comfy-Org/Wan_2.2_ComfyUI_repackaged` | ✅ Wan2.2 正确来源（约 38GB+ 整包） |
| `Comfy-Org/HiDream-I1_ComfyUI` | ✅ HiDream-i1 fp8（~31GB）；脚本 `download_hidream_aria2.sh` |

---

## 5. 云绘镜像工作流预设（未下载，供后续）

### 5.1 工作流文件位置

```
/root/LaunchTool311/autodl_img/Comfy_Any/workflows/云绘基础工作流/
```

共 **82** 个 JSON，分类：LTX2视频、Flux图像、Wan视频、QwenImage、SD、双截棍、Z-Image、语音生成等。

### 5.2 模型下载配置表（镜像作者维护）

| 文件 | 说明 |
|------|------|
| `.../Comfy_Any/new_dl_comm.yaml` | **2026+ 更新表**（35 工作流；**无 HiDream**） |
| `.../autodl_img/comfy_dl_comm.yaml` | **旧表**，含 HiDream-i1 / E1.1 等条目 + `size` 字段 |

```
/root/LaunchTool311/autodl_img/Comfy_Any/new_dl_comm.yaml
/root/LaunchTool311/autodl_img/comfy_dl_comm.yaml   # HiDream 见此处
```

- 覆盖工作流的文件清单、目标子目录、`download_basic_link: nahz202/<repo>`（魔搭）
- 本机 **nahz202 ModelScope 404** → 大模型改用 **HF 镜像 `Comfy-Org/*`**

### 5.3 示例：`LTX2-文生视频`（用户截图缺模型）

| 文件 | 目录 | 约大小 |
|------|------|--------|
| `ltx-2-19b-dev-fp8.safetensors` | `checkpoints/` | 25GB |
| `gemma_3_12B_it_fp4_mixed.safetensors` | `text_encoders/` | — |
| `ltx-2-spatial-upscaler-x2-1.0.safetensors` | `latent_upscale_models/` | ~950MB |
| `ltx-2-19b-distilled-lora-384.safetensors` | `loras/` | — |
| `ltx-2-19b-lora-camera-control-dolly-left.safetensors` | `loras/` | ~7GB |

下载源：`modelscope download --model nahz202/LTX-2`（合计约 **45GB**）

> **勿一次下完全部 86 个工作流**（可超 500GB）。按 [`HANDOFF.md` §八 B](HANDOFF.md) 与 [`AUTODL_ACTUAL_RUNBOOK.md`](../AUTODL_ACTUAL_RUNBOOK.md) 模型调试顺序逐个验证。

---

## 6. 与仓库 HANDOFF 的衔接（后续开发做什么）

仓库 [`HANDOFF.md`](HANDOFF.md) 仍是**功能与验收的单一真相**；本机部署完成后，按该文档推进：

| HANDOFF 章节 | 本机下一步 |
|--------------|------------|
| **§六 部署** | 本文件 §2–§3 已完成裸机部署；若换实例，复制本 HANDOFF + Runbook |
| **§八 B 真实 GPU 验收** | ✅ **PASS**（2026-07-08 新机重跑）：Flux API 出图 ✅、Wan 结构 ✅、SeedVR2 ✅ |
| **Agent Trace 基线** | ✅ `_agent_trace_baseline_probe.py` exit 0（2026-07-08）；[`AGENT_TRACE_BASELINE.md`](AGENT_TRACE_BASELINE.md) |
| **路线 B 批量** | ⚠️ 新机 3/3 出图 + 2/3 出视频（第 3 视频探针 20min 超时）；旧机全量 PASS — [`ROUTE_B_RESULT.md`](ROUTE_B_RESULT.md) |
| **Phase 2 产品** | ✅ Prompt Compiler、CharacterCardNode、分镜表 compile — 见 [`HANDOFF.md`](HANDOFF.md) Phase 2 节 |
| **Phase 43 探针** | 可在本机重跑 `backend/scripts/_*.py`（mock 与真实分流） |
| **ComfyUI 切换** | [`COMFYUI_CUTOVER_RUNBOOK.md`](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md) — 权重文件名以 `models/` 实际为准 |

### 建议模型验收顺序（4090 24GB · 2026-07-07 选型）

1. **SeedVR2** 3B fp8 — ✅ 权重 + 插件已就绪
2. **Flux fp8** — ✅ 已对齐 registry + 出图
3. **Wan 2.2** T2V 四步 — ✅ 整包 + 结构探针
4. **Wan 2.2** I2V 四步 — ✅ UNET + `wan-i2v` registry + 结构探针（2026-07-07）
5. ~~**Z-Image Turbo**~~ — **已删权重**，不纳入 API
6. **HiDream-i1** — ✅ 权重落盘 + registry/workflow 对齐 + 结构探针 **PASS**（2026-07-07）
7. LTX / Qwen — 第三批按需

---

## 7. 已知问题与偏离

| 问题 | 处理 / 待办 |
|------|-------------|
| git 浅克隆 | 需完整历史时：`git fetch --unshallow` |
| **实例迁移** | 2026-07-08 已迁至 **269 机**；旧 107 机勿再 SSH |
| `supervisorctl` PATH | 用 `/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf`；miniconda 版已 `pip install supervisor` 但仍建议全路径 |
| Supervisor 双实例 | AutoDL 平台 init supervisord（jupyter/sshd）**≠** AI Studio `/etc/supervisor` |
| ~~关机后 Supervisor 未自启~~ | ✅ **2026-07-09 已修**：方案 B + AutoDL 钩子。PID1=`/init/boot/boot.sh`（**非 systemd**，方案 C 不可用）。开机链：`/init/bin/customer.cmd.sh` → **`/etc/autodl.sh`** → **`/root/autodl-tmp/start.sh`** → `/usr/bin/supervisord -d -c /etc/supervisor/supervisord.conf`。本机 `/usr/bin/supervisord` 为 AutoDL **Go 版**（须 `-d` daemon；勿与 Python `supervisorctl` 混用路径）。模拟重启：stop all → 杀 pidfile → `bash /root/autodl-tmp/start.sh` → 三进程 RUNNING；7788/8000/6006 **200** |
| AI Studio supervisord 未起（排错） | 若钩子异常：`bash /root/autodl-tmp/start.sh`；`refused connection` 时确认 `/var/run/supervisor.sock` 与 `ps` 中 `-c /etc/supervisor/supervisord.conf` |
| **text 模型** | ✅ `_enable_text_models.py`（**勿随意重跑**）；默认 qwen-plus；A2 须 DB 有 `api_key`；Admin 后台配置见 HANDOFF 硬约束 |
| **百炼免费额度** | qwen-max/turbo 403；仅 plus 可用直至控制台开通付费 |
| **SD1.5 checkpoint** | 本机 `checkpoints/` 空；`stable-diffusion` DB disabled；探针改用 `flux-dev` |
| **探针 429** | 批跑前 `UPDATE tasks SET status='failed' WHERE status IN ('pending','running')` |
| Supervisor 模板路径 | 仓库 `deploy/supervisor-autodl.conf` 写 `comfyui` 小写；本机实际 `ComfyUI` |
| **Supervisor 整文件覆盖** | **2026-07-14 事故**：改双 GPU 时 `cp` 删减版配置 → 丢 `nginx`/`cloudflared` → 公网 **1033**。**禁止**整文件覆盖；改前改后 `diff` 五段齐全。见 §0a / §3.1 |
| **Cloudflare 1033** | 本地 `:6006` 200 但公网 1033 → `cloudflared` 未跑；`supervisorctl status cloudflared`；恢复见 §3.1 |
| Cursor shell 的 `node` | 可能指向 Cursor 内置 Node；构建请用 `/usr/bin/npm` |
| FLUX VAE 非官方 | `ae.safetensors` → Kijai `flux-vae-bf16` 软链 |
| 聊天中暴露 API Key | 建议在阿里云控制台**轮换** `DASHSCOPE_API_KEY` |
| AI Studio `enabled` 模型 | `flux-dev` / **`hidream`** / `wan-2.6` / **`wan-i2v`** / `video-enhance-seedvr2` 已在 registry **enabled=True**；DB 已 seed（`scripts/_enable_gpu_models.py`） |
| ComfyUI 插件依赖 | VHS / SeedVR2 需 venv 补装：`opencv-python`、`diffusers>=0.33`、`rotary-embedding-torch`、`omegaconf` 等（见 SeedVR2 `requirements.txt`） |
| Wan 视频输出节点 | 本机 VHS 可用；Wan2.2 workflow 默认 `CreateVideo`+`SaveVideo`（对齐云绘 JSON） |
| Wan VAE 文件名 | Backend `WAN_VAE = wan_2.1_vae.safetensors` 与磁盘一致；T2V/I2V 共用 |
| Wan i2v vs fun_inpaint | **`wan2.2_i2v_*` UNET 不可替代 `fun_inpaint_*`**；I2V 专用 high/low + lightx2v i2v LoRA |
| Flux 软链 | `diffusion_models/flux1-dev.safetensors` → `flux1-dev-fp8.safetensors`（探针/旧文档兼容） |
| `fun_inpaint` 权重 | ✅ G34 已接 API（`wan-fun-inpaint`）；FLF2V（i2v UNET）仍保留 |
| Phase 2 Prompt Compiler | `POST /api/prompt/compile`；`model_target`: flux / wan-t2v / wan-i2v |
| Phase 2 前端 | `CharacterCardNode`（`/api/assets` kind=character）；`ScriptTableNode` 接入 compile + 文本卡一键分镜表 |
| ModelScope `nahz202/*` | 本机 404；改用 HF 镜像 `Comfy-Org/*` / `numz/*` |
| `wan_2.1_vae.safetensors` 与 Wan2.2 | wan-i2v smoke test 出视频 **PASS** → 视为兼容 |
| HiDream T5 与 Flux T5 | **无冲突**：`t5xxl_fp8_e4m3fn.safetensors`（Flux）与 `t5xxl_fp8_e4m3fn_scaled.safetensors`（HiDream）为**独立文件** |
| `fun_inpaint` 首尾帧工作流 | ✅ FLF2V（i2v）+ ✅ G34 Fun Inpaint（专用 UNET，2026-07-09） |
| 磁盘水位 | **~169G 可用**（`/root/autodl-tmp` ~182G/350G）；G30 + Hunyuan + AudioGen + 审阅媒资走 R2（不占本地大盘） |
| ComfyUI 输出作 i2v 参考图 | ✅ **已修复**（2026-07-07）：`/api/view?filename=…` 经 `resolve_image_reference_path` 解析；仍支持 `/api/uploads/…` |

---

## 8. 常用运维命令

```bash
# 开机钩子（AutoDL 已接 /etc/autodl.sh；亦可手动）
bash /root/autodl-tmp/start.sh

# 服务（必须用 -c 指定 AI Studio supervisord 配置）
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf status
/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf restart comfyui aistudio-backend nginx
tail -50 /root/autodl-tmp/logs/backend.err.log
tail -50 /root/autodl-tmp/logs/comfyui.err.log
tail -50 /root/autodl-tmp/logs/nginx.err.log

# 健康
curl -s http://127.0.0.1:7788/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/system_stats | head -c 500

# 磁盘
df -h / /root/autodl-tmp
du -sh /root/autodl-tmp/ComfyUI/models/* | sort -hr | head

# text 模型（仅新机首次初始化或负责人明确要求；会覆盖 Admin 后台配置）
cd /root/autodl-tmp/AIStudio/backend && set -a && source .env && set +a
# .venv/bin/python scripts/_enable_text_models.py   # 勿随意执行

# 探针前清理并发槽位
sqlite3 aistudio.db "UPDATE tasks SET status='failed', error='probe-cleanup' WHERE status IN ('pending','running');"

# 关键 GPU / Agent 探针
export AGENT_MOCK_GENERATION=false SEED_ADMIN_PASSWORD='Admin@2026!'
.venv/bin/python scripts/_gpu_acceptance_8b_probe.py
.venv/bin/python scripts/_agent_trace_baseline_probe.py
.venv/bin/python scripts/_route_b_batch_probe.py   # 建议 timeout 1800
```

---

## 9. 相关文件索引

| 路径 | 说明 |
|------|------|
| [`HANDOFF.md`](HANDOFF.md) | **仓库主 HANDOFF**（产品开发指南） |
| [`HANDOFF_SERVER.md`](HANDOFF_SERVER.md) | **本文件**（服务器部署交接） |
| `backend/routers/review.py` | 视频审阅 API（JWT 发布 + 匿名公开） |
| `backend/services/r2.py` | Cloudflare R2 上传/presign/删对象 |
| `frontend/src/pages/Review*.jsx` | 审阅公开站 / 发布页 |
| [`DEPLOY.md`](DEPLOY.md) | 通用 Docker/部署 |
| [`backend/docs/AUTODL_DEPLOY_RUNBOOK.md`](backend/docs/AUTODL_DEPLOY_RUNBOOK.md) | AutoDL 模板 Runbook |
| `/root/autodl-tmp/AUTODL_ACTUAL_RUNBOOK.md` | 本实例实操 Runbook |
| `/root/LaunchTool311/autodl_img/Comfy_Any/new_dl_comm.yaml` | 云绘工作流 → 模型下载表（2026+） |
| `/root/LaunchTool311/autodl_img/comfy_dl_comm.yaml` | 含 HiDream 等旧条目 |
| `/etc/supervisor/conf.d/aistudio.conf` | Supervisor 运行配置 |
| `/root/autodl-tmp/start.sh` | AI Studio supervisord 开机钩子（`-d` daemon） |
| `/etc/autodl.sh` | AutoDL `customer.cmd.sh` 调用的客户开机脚本 → `start.sh` |
| `/etc/nginx/sites-available/aistudio` | Nginx 配置 |
| `backend/.env` | 运行时密钥（本地 only） |
| `/root/autodl-tmp/logs/phase2_smoke_results.json` | HiDream / wan-i2v GPU smoke 结果 |
| `/root/autodl-tmp/logs/prompt_debug_phase*.json` | Prompt 调试阶段一～七 GPU/鉴权日志 |
| `backend/scripts/_prompt_debug_phase{1,2,3_keyframe,4_hunyuan,5_ltx2,6_wan_t2v,7_pulid}.py` | Prompt 调试探针脚本 |
| `backend/scripts/_g40_reactor_probe.py` | G40 ReActor 结构探针 |
| `backend/docs/PROBE_ACCOUNTS.md` | 探针/验收账号与团队备忘 |
| `PROMPT_DEBUG_PHASE{1..7}.md` | Prompt 调试交接文档（仓库根目录） |
| `/root/autodl-tmp/logs/agent_trace_baseline.json` | Agent Trace 基线探针输出 |
| `/root/autodl-tmp/logs/all_probes_20260708_1439.log` | 2026-07-08 全量探针批跑日志 |
| `backend/scripts/_enable_text_models.py` | text 模型写入 registered_models（**勿随意重跑**；会覆盖 Admin 配置） |
| `AGENT_TRACE_BASELINE.md` | Agent Trace 诊断报告 |
| `ROUTE_B_RESULT.md` | 路线 A/B 验收结果 |
| `G30_RESUME.md` | G30 PuLID + LTX2 完成状态与运维注意 |
| `/root/autodl-tmp/logs/g30_phash_compare.json` | flux-dev vs flux-pulid phash 对照 |
| `/root/autodl-tmp/logs/g30_pulid_smoke.json` | PuLID GPU smoke history |
| `backend/scripts/_download_g30_ltx2_weights.sh` | PuLID + LTX2 权重下载 |

---

## 10. 交接摘要（一句话）

**2026-07-13 视频审阅 + R2 + Tunnel（269 机）**：迁移 **025/026**；公网 **`https://velora.seele0420.cloud`**（`cloudflared`）；Nginx 大上传 `2048m`；pytest **121**；数据盘 **350G / ~169G 可用**。产品细节见 [`HANDOFF.md`](HANDOFF.md)。

**2026-07-10 G40 buffalo_l + Phase7 换脸复测（269 机）**：经 hf-mirror 预置 `buffalo_l`（`_download_g40_buffalo_l.sh`）；Phase7 复跑 T2/T3 **`use_reactor=True` completed**（`ComfyUI_00066_`/`00067_.png`）；T1/T4 仍为预期失败。

**2026-07-10 G40 + Phase4–7（269 机）**：新 G40 ReActor **代码已接线**（`use_reactor` / `flux_pulid_reactor.json` / `test_reactor_g40`）；结构探针 ok。Phase4–6 T1–T4 **全部 completed**。pytest **105 passed**。

**2026-07-09 G39 AudioGen + ReActor 侦察 + Phase4–7 文档（269 机）**：`audiocraft==1.3.0`（`--no-deps`，保留 torch 2.12）；权重 `/root/autodl-tmp/models/audiogen-medium`（~3.7G）；`POST /api/audio/generate` + `CanvasVideoRequest.sound_note` 后混音（跳过 ltx2）；pytest **102**。ReActor：`ComfyUI-ReActor` + inswapper/GFPGAN 已在盘，正式接线为**新 G40**（≠ 旧 GPU_DEBT G40=Hunyuan）。`PROMPT_DEBUG_PHASE4–7.md` 框架已落盘（未跑 GPU）。

**2026-07-09 HunyuanVideo GPU smoke 上线（269 机）**：`hunyuan-video` **enabled=True**；720p/50 步墙钟 **~109 分钟**；显存峰值 **23076 MiB (~22.5G / 24G)**；无致命 CUDA OOM（VAE tiled 回退告警）；产出 `AIStudio_video_00049.mp4`。**建议作高级选项**，勿与 Wan/PuLID 同卡叠跑。

**2026-07-09 G35/G36/G37（269 机）**：HunyuanVideo 权重下载 + `hunyuan-video`（smoke 进行中）；VideoGenerationNode 卡片级 CameraMotionPicker；Seedance 框架（`seedance-2.0` enabled=False，待 Key）；pytest **97**；数据盘 **266G/300G**（剩余约 **35G**）。

**2026-07-09 G34 wan-fun-inpaint（269 机）**：`wan-fun-inpaint` 已启用（`WanFunInpaintToVideo` + fun_inpaint 双 UNET）；与 `wan-i2v` FLF2V 并存；结构探针 PASS；未做 GPU 出片 smoke；pytest **88**。

**2026-07-09 G33/G31/G32 + G30 闭环（269 机）**：数据盘 **300G**（~68G 可用）；**flux-pulid** + **ltx2-fp4**；**G33** CameraMotionPicker；**G31** quality 8 步；**G32** A1 ~1.8k；pytest **84**。**Supervisor 开机自启已修**：`/etc/autodl.sh` → `/root/autodl-tmp/start.sh`。**待办**：LTX2 端到端 MP4 smoke；Seedance Key；百炼付费；`GET /api/assets` 404；SD1.5 权重。
