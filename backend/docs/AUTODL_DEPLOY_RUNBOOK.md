# AutoDL 部署操作手册

> 团队内测专用：单机部署前端 + 后端 + Redis + ComfyUI，供 4 人远程访问。  
> 文本/Agent 走百炼 API（`DASHSCOPE_API_KEY`），不占 GPU。  
> 版本：2026-06-30 · 对应 HANDOFF 第八节 B 真实 GPU 验收

**阅读顺序**：先读本手册 §1–§2 确认 GPU/磁盘 → 按 §3–§11 开机部署 → §12 验收与排错。

通用 Linux/Docker 部署见仓库根目录 [DEPLOY.md](../../DEPLOY.md)。ComfyUI 模型切换细节见 [COMFYUI_CUTOVER_RUNBOOK.md](./COMFYUI_CUTOVER_RUNBOOK.md)。

---

## §1 项目资源需求清单

### 1.1 模型与显存（保守估算）

ComfyUI **通常一次只跑一个 workflow**，峰值显存 ≈ **当前任务所用最大模型**，不是全部权重之和。全模型权重可都装在磁盘上，通过 Admin **分阶段 `enabled`** 控制启用范围。

| 模型 ID | 类型 | 磁盘权重（约） | 单次推理显存（保守） | workflow 代码 |
|---------|------|----------------|---------------------|---------------|
| stable-diffusion | 图 | ~4 GB | 4–6 GB | ready |
| sdxl | 图 | ~7 GB | 6–8 GB | ready |
| flux-dev | 图 | ~12–24 GB（视 fp8） | 12–24 GB | ready |
| flux-schnell | 图 | ~12 GB | 10–16 GB | ready |
| hidream | 图 | ~15–20 GB | 14–20 GB | ready |
| wan-2.6 | 视频 | ~20–40 GB（含 wrapper） | 16–24 GB | ready |
| ltx-video | 视频 | ~5–8 GB | 8–12 GB | ready |
| hunyuan-video | 视频 | ~30–50 GB（含 VAE/TE） | 18–24 GB+ | ready |

代码注册表：[`model_registry.py`](../model_registry.py) · `COMFYUI_LOCAL_PROVIDERS`

**磁盘合计（权重 + ComfyUI 自定义节点）**：约 **120–180 GB**（不含日常生成缓存）。  
**建议数据盘**：**250–300 GB**（含 `uploads/`、导出 zip、余量增长）。

**显存结论（全模型集）**：

| GPU | 适用性 |
|-----|--------|
| **48GB（RTX 6000 Ada / A6000 48G 等）** | **推荐**：全模型「一次一模型」验收，img2img/参考图有余量 |
| RTX 4090 24GB | 可跑 SD/SDXL/LTX；Flux/HiDream/Wan/Hunyuan 全精度易 OOM，需 fp8 权重或延后启用 |
| 省钱过渡 | 4090 + 先启用 SDXL + LTX + flux-schnell，验收通过后再换 48G 卡 |

### 1.2 AutoDL 存储布局

| 路径 | 大小 | 用途 |
|------|------|------|
| `/` 系统盘 | 30 GB（默认） | 系统、Python venv、Redis、Nginx、Supervisor |
| `/root/autodl-tmp` | **扩容 250–300 GB** | ComfyUI、模型权重、`uploads/`、SQLite、日志 |
| `/root/autodl-fs` | 可选 20GB+ | 跨实例备份（非必须） |

**目录规划（推荐）**：

```
/root/autodl-tmp/
├── AIStudio/                 # 项目代码（Cursor SSH 打开此目录）
│   ├── backend/
│   │   ├── uploads/          # 必须在此数据盘下（images/videos/exports）
│   │   └── aistudio.db       # SQLite 可选路径见 §6
│   └── frontend/dist/        # npm run build 产物
├── comfyui/                  # ComfyUI 安装目录
└── models/                   # 大权重集中存放（软链到 comfyui/models 子目录）
```

`uploads/` 子目录（后端启动自动创建）：

```
uploads/
├── images/
├── videos/
└── exports/
```

### 1.3 并发与队列（4 人团队）

| 机制 | 说明 |
|------|------|
| ComfyUI | 单 GPU **串行**执行；多人同时生成 → **排队**（正常） |
| `generation_slots.py` | 默认个人 `GENERATION_MAX_CONCURRENT=3`、团队 `10`；**依赖 Redis** |
| 协作 / WS / 限流 | 均依赖 Redis（HANDOFF：未开 Redis 协作异常） |

**建议内测 `.env`**：`GENERATION_MAX_CONCURRENT=2`，减少 4 人同时堆任务导致长时间排队无反馈。

### 1.4 非 GPU 依赖

| 依赖 | 用途 |
|------|------|
| `DASHSCOPE_API_KEY` | Agent、文本生成、粘贴剧本 classify、风格参考 VL |
| `ffmpeg` | 风格参考分析（`imageio-ffmpeg` 可选） |
| `alembic upgrade head` | 迁移 **001–021**（含 export_jobs、llm_routing、style_reference 等） |
| Node 20+ | `npm ci && npm run build`（**不用** `npm run dev` 常驻） |
| Redis | **必装** |

---

## §2 AutoDL 选型建议

### 2.1 推荐配置（性能优先 · 全模型集）

| 项 | 建议 |
|----|------|
| GPU | **48GB 显存单卡**（控制台可选 RTX 6000 Ada 48G / A6000 48G 等，以当日可租为准） |
| CPU/内存 | 1 卡约 8 核 / 32GB（平台按 GPU 数分配，够 4 人 Web + ComfyUI） |
| 系统盘 | 默认 30GB |
| 数据盘 | **扩容至 250–300 GB** |
| 镜像 | **PyTorch 2.x + CUDA 12.x** 基础镜像 |
| 计费 | **按量计费**；下班 **关机** 停 GPU 费 |

### 2.2 备选配置（性价比）

| 项 | 建议 |
|----|------|
| GPU | RTX 4090 24GB |
| 数据盘 | 200 GB |
| 策略 | 先启用 SDXL + LTX + flux-schnell；Wan/Hunyuan/HiDream 用 fp8 或延后 |
| 风险 | HANDOFF 第八节 B 全模型验收可能需降分辨率或换卡 |

### 2.3 平台机制（必读）

| 项 | 说明 |
|----|------|
| 关机 | GPU **按量停计**；数据盘扩容容量可能 **按日计费**（关机仍扣存储费，以 [AutoDL 计费说明](https://www.autodl.com/docs/) 为准） |
| 数据保留 | 关机数据保留；**连续关机约 15 天可能释放实例** → 定期开机或备份到网盘 |
| 团队访问 | 服务绑定 `0.0.0.0` + 控制台 **「自定义服务」** 映射端口（建议 **6006**） |
| 开发 | **SSH** + Cursor Remote SSH 改代码；ComfyUI 仅 `127.0.0.1:8000`，不对外暴露 |
| 费用粗算 | 48G 卡约 ¥3–6/小时 × 工作日 10h ≈ ¥30–60/天 + 数据盘约 ¥0.5–1/天（**以控制台实时单价为准**） |

---

## §3 创建实例

1. 登录 [AutoDL 控制台](https://www.autodl.com/) → **租用新实例**
2. 选择：**按量计费**、地区、**48G GPU**（或备选 4090）
3. **数据盘扩容**至 250–300 GB（创建时或控制台扩容）
4. 镜像：**PyTorch 2.x + CUDA 12.x**
5. 开机后确认状态为 **运行中**（开始 GPU 计费）

---

## §4 目录与代码部署

### 4.1 终端初始化目录

```bash
mkdir -p /root/autodl-tmp/{AIStudio,comfyui,models}
cd /root/autodl-tmp
```

### 4.2 获取代码

**方式 A：Git（推荐）**

```bash
cd /root/autodl-tmp
git clone <你的仓库地址> AIStudio
```

**方式 B：本地上传**

- 控制台打开 **JupyterLab** → 上传到 `/root/autodl-tmp/AIStudio`
- 或使用 FileZilla / `scp`（见 AutoDL「上传数据」文档）

### 4.3 Cursor Remote SSH

1. AutoDL 实例页复制 **SSH 连接命令**（含 `-p` 端口）
2. 本机 `~/.ssh/config` 添加：

```
Host autodl-aistudio
    HostName <region-xxx.autodl.com>
    Port <实例SSH端口>
    User root
    IdentityFile ~/.ssh/id_rsa
```

3. Cursor → **Remote-SSH: Connect to Host** → `autodl-aistudio`
4. 打开文件夹：`/root/autodl-tmp/AIStudio`

之后改代码、跑终端均在 Cursor 内完成。

---

## §5 系统依赖

```bash
apt-get update
apt-get install -y nginx redis-server supervisor ffmpeg git

# 确认 Redis
redis-cli ping   # 应返回 PONG

# Node 20（若镜像未带）
# curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
# apt-get install -y nodejs
node -v   # 建议 v20+
python3 --version   # 建议 3.10+
nvidia-smi          # 确认 GPU 可见
```

---

## §6 后端部署

```bash
cd /root/autodl-tmp/AIStudio/backend

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

cp .env.example .env
```

编辑 `backend/.env`（**生产内测最低配置**）：

```ini
APP_ENV=production
JWT_SECRET=<随机32+字符>

# 数据盘上的 SQLite（4 人内测够用）
DATABASE_URL=sqlite:////root/autodl-tmp/AIStudio/backend/aistudio.db

REDIS_URL=redis://127.0.0.1:6379/0

DASHSCOPE_API_KEY=<百炼Key>
COMFYUI_URL=http://127.0.0.1:8000

AGENT_MOCK_GENERATION=false

# 内测建议
GENERATION_MAX_CONCURRENT=2
GENERATION_MAX_CONCURRENT_TEAM=8
```

迁移与目录：

```bash
source .venv/bin/activate
alembic upgrade head    # 001–021

mkdir -p uploads/images uploads/videos uploads/exports
```

**注意**：`APP_ENV=production` 时 **不会** 自动创建种子账号 `admin/testuser`。首次需通过 **注册** 或手动插入管理员，或由开发机导出用户后迁移。

验证启动（前台试跑）：

```bash
uvicorn main:app --host 127.0.0.1 --port 7788
curl http://127.0.0.1:7788/health
# 期望：{"status":"ok","env":"production","redis":true}
```

---

## §7 前端构建

```bash
cd /root/autodl-tmp/AIStudio/frontend
npm ci

# 同源反代：不设置 VITE_API_BASE_URL（或留空）
npm run build
# 产物：frontend/dist/
```

重新构建前端后需 `nginx -s reload`（若 Nginx 已运行）。

---

## §8 ComfyUI 部署

### 8.1 安装

```bash
cd /root/autodl-tmp
git clone https://github.com/comfyanonymous/ComfyUI.git comfyui
cd comfyui
pip install -r requirements.txt
# 若需 xformers 等按 ComfyUI 官方说明安装
```

### 8.2 自定义节点（全模型集）

| 模型 | 常见依赖 |
|------|----------|
| Wan 2.6 | **ComfyUI-WanVideoWrapper**（见 `_comfyui_workflow_structure_probe.py` docstring） |
| Hunyuan | ComfyUI 内置 HunyuanVideo 节点（视 ComfyUI 版本） |
| Flux | 标准 ComfyUI + clip/vae/unet 分目录 |

```bash
cd /root/autodl-tmp/comfyui/custom_nodes
# git clone <各节点仓库> 后重启 ComfyUI
```

### 8.3 模型权重

1. 将大文件下载到 `/root/autodl-tmp/models/`
2. 软链到 ComfyUI 对应目录，例如：

```bash
ln -sf /root/autodl-tmp/models/checkpoints/*.safetensors \
  /root/autodl-tmp/comfyui/models/checkpoints/
```

3. SSH 列出实际文件名，对照 [`model_registry.py`](../model_registry.py) 修改 `comfyui_checkpoint` / `ALL_MODELS[].comfyui_model_file`（**不要猜文件名**）
4. 重启 backend → Admin 模型管理中对 `workflow_impl=ready` 的项 **enabled=true**（建议先 SDXL + LTX，再逐个启用大模型）

### 8.4 启动 ComfyUI（仅本机）

```bash
cd /root/autodl-tmp/comfyui
python main.py --listen 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/system_stats
```

结构探针（不需完整推理）：

```bash
cd /root/autodl-tmp/AIStudio/backend
source .venv/bin/activate
python scripts/_comfyui_workflow_structure_probe.py
python scripts/_comfyui_workflow_structure_probe.py --model wan
```

---

## §9 Nginx（团队访问入口）

创建 `/etc/nginx/sites-available/aistudio`（或 `conf.d/aistudio.conf`）：

```nginx
server {
    listen 6006;
    server_name _;

    root /root/autodl-tmp/AIStudio/frontend/dist;
    index index.html;

    client_max_body_size 20m;

    location /api/ {
        proxy_pass http://127.0.0.1:7788;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /health {
        proxy_pass http://127.0.0.1:7788;
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:7788;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
nginx -t && nginx -s reload
```

**AutoDL 控制台** → 实例 → **自定义服务** → 添加端口 **6006** → 获取团队访问链接（HTTPS 由平台提供）。

---

## §10 Supervisor 常驻进程

创建 `/etc/supervisor/conf.d/aistudio.conf`：

```ini
[program:comfyui]
command=/root/autodl-tmp/comfyui/.venv/bin/python main.py --listen 127.0.0.1 --port 8000
directory=/root/autodl-tmp/comfyui
autostart=true
autorestart=true
stderr_logfile=/root/autodl-tmp/logs/comfyui.err.log
stdout_logfile=/root/autodl-tmp/logs/comfyui.out.log
environment=CUDA_VISIBLE_DEVICES="0"

[program:aistudio-backend]
command=/root/autodl-tmp/AIStudio/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 7788
directory=/root/autodl-tmp/AIStudio/backend
autostart=true
autorestart=true
stderr_logfile=/root/autodl-tmp/logs/backend.err.log
stdout_logfile=/root/autodl-tmp/logs/backend.out.log
```

```bash
mkdir -p /root/autodl-tmp/logs
supervisorctl reread
supervisorctl update
supervisorctl status
```

Redis 使用系统服务：`systemctl enable redis-server`。

若 ComfyUI 与 backend 共用 backend 的 venv，将 `comfyui` 的 `command` 改为对应 python 路径。

---

## §11 团队访问与首次登录

1. 将 AutoDL **自定义服务** 生成的 URL 发给团队（4 人）
2. `curl http://127.0.0.1:6006/health` 在本机通过
3. 浏览器打开自定义服务 URL → 注册第一个账号 → Admin 后台将其设为 `admin`（或提前在 DB 插入）
4. Admin → 模型管理：启用已就绪的 image/video 模型；配置 LLM 分流与 `DASHSCOPE`
5. 确认 `AGENT_MOCK_GENERATION=false`

---

## §12 验收与排错

### 12.1 验收清单（HANDOFF 第八节 B）

- [ ] Redis 连通（`/health` 中 `redis: true`）
- [ ] `alembic upgrade head` 无报错（021）
- [ ] ComfyUI `system_stats` 200
- [ ] 2 镜分镜表 → 节拍 → 分镜图 **completed** → 视频 **completed**
- [ ] 出图 `reference_images` 含角色 + 场景
- [ ] 失败时显示真实错误（非 mock 乐观文案）

探针：

```bash
cd /root/autodl-tmp/AIStudio/backend
source .venv/bin/activate
python scripts/_comfyui_workflow_structure_probe.py --model all
python scripts/_real_media_pipeline_probe.py   # mock 开启时 SKIP
```

### 12.2 常见问题

| 现象 | 排查 |
|------|------|
| 自定义服务 502 | `supervisorctl status`；backend 是否监听 7788 |
| WebSocket 断连 | Nginx `/ws` 是否配置 `Upgrade`；自定义服务是否支持 WS |
| `redis: false` | `redis-cli ping`；`REDIS_URL` |
| ComfyUI OOM | `nvidia-smi`；换 fp8 权重或 48G 卡；一次只启用一个大模型 |
| 生成一直 pending | `COMFYUI_URL`；ComfyUI 日志；队列是否被僵尸任务占用 |
| 权重 404 | 文件名与 `model_registry.py` 不一致；`ls comfyui/models/checkpoints` |
| 协作异常 | 几乎总是 Redis 未连 |
| 前端连 127.0.0.1 | 未用 `npm run build` 或构建时误设 `VITE_API_BASE_URL` |

### 12.3 回滚到 Mock

```bash
# backend/.env
AGENT_MOCK_GENERATION=true
supervisorctl restart aistudio-backend
python scripts/_mock_generation_acceptance.py
```

详见 [COMFYUI_CUTOVER_RUNBOOK.md](./COMFYUI_CUTOVER_RUNBOOK.md) 第五节。

### 12.4 关机与备份

- 下班：**控制台关机**（停 GPU 费）
- 定期：将 `/root/autodl-tmp/AIStudio/backend/uploads` 与 `aistudio.db` 打包到网盘或 `autodl-fs`
- 避免连续 **15 天** 不开机导致实例释放

---

## 附录 A：环境变量速查（完整见 `backend/.env.example`）

| 变量 | AutoDL 内测 |
|------|-------------|
| `APP_ENV` | `production` |
| `JWT_SECRET` | 必填，≥32 字符随机 |
| `DATABASE_URL` | 数据盘 SQLite 路径 |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |
| `DASHSCOPE_API_KEY` | 必填 |
| `COMFYUI_URL` | `http://127.0.0.1:8000` |
| `AGENT_MOCK_GENERATION` | `false`（真实验收） |
| `GENERATION_MAX_CONCURRENT` | 建议 `2` |
| `SEED_*_PASSWORD` | 生产不执行 seed，可忽略 |

---

## 附录 B：与 Docker 方案的关系

仓库 [`docker-compose.yml`](../../docker-compose.yml) + [`deploy/deploy.sh`](../../deploy/deploy.sh) 适用于**通用 Linux 服务器**。  
**AutoDL 推荐本手册裸机路径**（Cursor SSH、ComfyUI 直连 GPU、数据盘放模型）。两者环境变量与 Nginx 反代逻辑一致。

---

*确认 §2 GPU/磁盘方案后，再按 §3 起实际开机。有问题对照 HANDOFF.md 与 `SECURITY_AUDIT_FINDINGS.md`。*
