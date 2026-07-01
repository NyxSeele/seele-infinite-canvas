# AI Studio 部署指南

> 最后更新：2026-06-30 · 本地开发端口 **8173**（前端）/ **7788**（后端）

## 架构概览

```
用户浏览器
    │
    ▼
Nginx (web) ──静态──► frontend/dist
    │
    ├── /api/*  ──► backend:7788 (FastAPI)
    └── /ws     ──► backend:7788 (WebSocket)
              │
              ├── PostgreSQL 或 SQLite
              ├── Redis（协作/限流/生成槽位 — 必开）
              └── ComfyUI（内网，仅 backend 可访问）
```

前端生产构建时 **`VITE_API_BASE_URL` 留空**（Nginx 同源反代 `/api`、`/ws`）。分域名部署时在 `backend/.env` 设置 `CORS_ORIGINS`，并构建时设置 `VITE_API_BASE_URL`。

**ComfyUI 真实模型切换**（权重文件名、启用模型、验收）：[backend/docs/COMFYUI_CUTOVER_RUNBOOK.md](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md)

---

## 方式一：AutoDL 云 GPU（团队内测 · 推荐路径）

单机部署前端 + 后端 + Redis + ComfyUI，4 人通过 AutoDL **自定义服务** 访问。

| 项 | 说明 |
|----|------|
| 文档 | **[backend/docs/AUTODL_DEPLOY_RUNBOOK.md](backend/docs/AUTODL_DEPLOY_RUNBOOK.md)**（资源清单、48G 选型、Cursor SSH、Supervisor） |
| 形态 | **裸机 + Nginx + Supervisor**（非 Docker；便于 SSH 改代码与 GPU 直连） |
| 文本/Agent | 百炼 `DASHSCOPE_API_KEY`（不占 GPU） |
| HTTPS | AutoDL 自定义服务提供；内测可不配自有域名 |

简要步骤：扩容数据盘 250–300GB → 代码放 `/root/autodl-tmp/AIStudio` → Redis/Nginx/Supervisor → `alembic upgrade head` → ComfyUI 本机 `:8000` → Nginx `:6006` + 自定义服务映射。

---

## 方式二：Docker Compose（通用 Linux 服务器）

### 0. 一键部署脚本（可选）

| 环境 | 命令 |
|------|------|
| Linux | `bash deploy/deploy.sh` |
| Windows（Docker Desktop） | `powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1` |

脚本：**检查 Docker → 生成 `.env` 密码与 `JWT_SECRET` → `docker compose up -d --build`**。  
**不会**自动部署 ComfyUI，也不会填 `DASHSCOPE_API_KEY`。

### 1. 准备环境变量

```bash
cp .env.example .env                    # POSTGRES_PASSWORD、REDIS_PASSWORD
cp backend/.env.example backend/.env    # JWT_SECRET、APP_ENV=production、DASHSCOPE、COMFYUI_URL
```

### 2. 启动

```bash
docker compose up -d --build
```

backend 容器启动时自动 `alembic upgrade head`。

### 3. 验证

- `http://<服务器IP>/health`
- `http://<服务器IP>` 打开前端

### 4. 数据持久化

| 卷 | 用途 |
|----|------|
| `postgres_data` | 数据库 |
| `redis_data` | Redis |
| `uploads_data` | 头像、出图/视频、导出 zip |

ComfyUI 仍在宿主机或另一容器，通过 `COMFYUI_URL` 连接。

---

## 方式三：手动部署（不用 Docker）

### 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

export APP_ENV=production
# 内测可用 SQLite（路径建议在数据盘）：
# DATABASE_URL=sqlite:////path/to/aistudio.db
# 生产多实例：postgresql+psycopg2://...

alembic upgrade head    # 001–021
uvicorn main:app --host 0.0.0.0 --port 7788
```

### 前端

```bash
cd frontend
npm ci
# 开发：见 frontend/.env.development（VITE_API_BASE_URL=http://127.0.0.1:7788）
# 生产同源：不设置 VITE_API_BASE_URL
npm run build
```

### Nginx

参考 [deploy/nginx.conf](deploy/nginx.conf)，将 `backend` 改为 `127.0.0.1:7788`。AutoDL 示例见 AUTODL Runbook §9。

---

## 本地开发

| 服务 | 地址 |
|------|------|
| 前端 | `npm run dev` → http://127.0.0.1:**8173** |
| 后端 | http://127.0.0.1:**7788** |
| 环境 | `frontend/.env.development` · `backend/.env` |

```bash
# 后端
cd backend && source .venv/bin/activate
# Redis 必开；可选 AGENT_MOCK_GENERATION=true（无 ComfyUI）
uvicorn main:app --host 127.0.0.1 --port 7788

# 前端
cd frontend && npm run dev
```

数据库迁移：

```bash
cd backend && alembic upgrade head   # 含 001–021
```

---

## 生产 / 内测检查清单

### 必做（P0）

- [ ] `JWT_SECRET` 强随机（≥32 字符）
- [ ] `APP_ENV=production`（关闭 debug 路由、种子账号、`create_all`）
- [ ] `alembic upgrade head`（**001–021**）
- [ ] `uploads/` 在持久化盘（images / videos / exports）
- [ ] **Redis 已启动**（协作、WS 广播、生成槽位、限流）
- [ ] `DASHSCOPE_API_KEY` 已配置
- [ ] `COMFYUI_URL` 指向内网 ComfyUI；`AGENT_MOCK_GENERATION=false`（真实验收）
- [ ] ComfyUI workflow：SD/SDXL/Flux/LTX/HiDream/Wan/Hunyuan **代码均已 ready**（见 COMFYUI Runbook）

### 建议（P1）

- [ ] 公网正式环境：HTTPS、`CORS_ORIGINS`
- [ ] AutoDL 内测：可用平台自定义服务 URL，跳过自有证书
- [ ] 备份 `uploads/` 与数据库
- [ ] ComfyUI 切换日按 [COMFYUI_CUTOVER_RUNBOOK.md](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md) 核对权重文件名

### 功能占位（不阻塞内测）

同屏创作、充值/账单、工作区 AI 生剧本（未接 LLM）等 — 见 HANDOFF「占位功能 — 永久不实现」。

---

## 环境变量参考（`backend/.env`）

完整模板：[backend/.env.example](backend/.env.example)

| 变量 | 说明 |
|------|------|
| `JWT_SECRET` | 必填 |
| `APP_ENV` | `production` / `development` |
| `DATABASE_URL` | SQLite 或 PostgreSQL |
| `REDIS_URL` | **必配** |
| `CORS_ORIGINS` | 逗号分隔；同源反代可留空用默认开发端口列表 |
| `COMFYUI_URL` | 如 `http://127.0.0.1:8000` |
| `COMFYUI_WS_URL` | 可选 |
| `DASHSCOPE_API_KEY` | Agent / 文本 / classify / 风格参考 |
| `JIMENG_API_KEY` | 仅即梦 `jimeng-5.0-lite` |
| `GENERATION_MAX_CONCURRENT` | 默认 3；4 人内测建议 2 |
| `GENERATION_MAX_CONCURRENT_TEAM` | 默认 10 |
| `RATE_LIMIT_*` / `LOGIN_*` / `AGENT_RATE_LIMIT_*` | 见 `.env.example` |
| `AGENT_MOCK_GENERATION` | `true` 无 GPU 测链路；生产 `false` |
| `AGENT_MOCK_FAILURE_RATE` | 0–1，测失败 UX |
| `AGENT_LLM_MAX_RETRIES` | LLM 重试 |
| `MEDIA_TOKEN_TTL_SECONDS` | 媒体票据 TTL |
| `SEED_*_PASSWORD` | 仅 `development` 时 seed 使用 |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/.env.development` | `VITE_API_BASE_URL=http://127.0.0.1:7788` |
| 生产构建 | **不设置**或留空 `VITE_API_BASE_URL` |

---

## 常见问题

**Q: 前端请求打到 127.0.0.1？**  
A: 生产须 `npm run build` 且 `VITE_API_BASE_URL` 留空（或设为公网 API）；勿直接部署含 dev 地址的 `dist`。

**Q: WebSocket 连不上？**  
A: Nginx `/ws` 需 `Upgrade` 头；AutoDL 自定义服务需支持 WS。

**Q: 协作/Agent 异常？**  
A: 先查 Redis：`curl /health` 中 `redis` 应为 `true`。

**Q: 头像/出图丢失？**  
A: `uploads/` 未在数据盘或未挂 Docker 卷。

**Q: 真实出图怎么验收？**  
A: HANDOFF 第八节 B + `scripts/_real_media_pipeline_probe.py`。

---

## 文档索引

| 文档 | 用途 |
|------|------|
| [HANDOFF.md](HANDOFF.md) | 功能进度、本地服务、探针 |
| [backend/docs/AUTODL_DEPLOY_RUNBOOK.md](backend/docs/AUTODL_DEPLOY_RUNBOOK.md) | AutoDL 全流程 |
| [backend/docs/COMFYUI_CUTOVER_RUNBOOK.md](backend/docs/COMFYUI_CUTOVER_RUNBOOK.md) | 模型切换与回滚 |
| [backend/docs/V1_CANVAS_PROBE_COVERAGE.md](backend/docs/V1_CANVAS_PROBE_COVERAGE.md) | 探针覆盖 |
