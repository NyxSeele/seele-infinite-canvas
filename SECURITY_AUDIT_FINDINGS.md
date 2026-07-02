# AI Studio 基础安全检查 — 现状清单

> 审计日期：2026-06-25  
> 依据：[SECURITY_CHECK_DIRECTION.md](c:\Users\小布丁\Downloads\SECURITY_CHECK_DIRECTION.md)  
> **本轮只读代码 + 少量 API 冒烟，未改业务代码。**

## 运行环境（审计时）

| 服务 | 状态 |
|------|------|
| 后端 `http://127.0.0.1:7788` | 已在运行（新启 uvicorn 因端口占用未重复绑定） |
| 前端 | `8173` 占用，Vite 落在 `http://127.0.0.1:8174/` |

## 动态冒烟（2026-06-25）

| 用例 | 结果 |
|------|------|
| 未登录 `GET /api/exports/{id}/download` | **401** |
| 未登录 `GET /api/uploads/images/...` | **401** |
| `testuser` → `GET /api/admin/users` | **403** 需要管理员权限 |
| `testuser2` → `GET /api/admin/stats/overview` | **403** |
| `admin` → `GET /api/admin/users` | **200** |
| `testuser` → 猜测 export UUID | **404** 导出任务不存在 |

---

## 一、高优先级：权限边界

### 1.1 导出下载 `GET /api/exports/{export_id}/download`

| 项 | 内容 |
|----|------|
| **当前行为** | 必须登录（`get_current_user`）。`get_export_job_for_user` → `get_accessible_project(db, user, job.project_id)`：团队项目需为团队成员；个人项目仅创建者。路径 `resolve()` + `startswith(uploads根)` 防穿越。 |
| **代码** | [`backend/routers/exports.py`](backend/routers/exports.py) L57-75；[`backend/services/export_service.py`](backend/services/export_service.py) `get_export_job_for_user`；[`backend/services/canvas_access.py`](backend/services/canvas_access.py) L13-34 |
| **风险等级** | **低**（不存在「仅登录、任意 id 下载他人项目」） |
| **说明** | 不校验 `ExportJob.created_by`：同一团队内任意成员（含 **viewer**）可下载他人发起的导出 zip。若产品期望「仅编辑者 / 创建者可下」，当前未实现。 |
| **本地四人用是否必改** | 否 |
| **公网部署前** | 确认 viewer 下载全项目 zip 是否符合预期；若否，加 `created_by` 或 `require_edit` |

### 1.2 媒体访问 `media_access.py`（「不按 project_id」）

| 项 | 内容 |
|----|------|
| **当前行为** | `/api/uploads/{rel}`：`user_can_access_upload` — admin 全通；本人 `Task.result` / `UserUpload`；**任意共团队队友**的 upload 与头像 URL 均可访问。**不查** `CanvasProject` / `project_id`。`/api/view`（Comfy 输出）同理，按 Task + 队友 Task 匹配文件名。`exports/` **不在** `_UPLOAD_PATH` 白名单，不能经媒体路由直读。 |
| **代码** | [`backend/services/media_access.py`](backend/services/media_access.py) `_teammate_user_ids` L89-107；`user_can_access_upload` L243-282；`user_can_access_comfy_output` L214-240 |
| **风险等级** | **中**（设计取舍，非明显实现 bug） |
| **产品待确认** | **同团队、但未参与项目 A 的成员，能否访问项目 A 里生成/上传的图片？** 当前答案：**能**（只要文件落在队友 Task/UserUpload 且你们在同一个 Team）。这是否符合「团队共享资产库」预期，需小布丁拍板。 |
| **本地四人用是否必改** | 否（先确认产品） |
| **公网部署前** | 若需项目级隔离，媒体鉴权须引入 `project_id` 或任务-项目关联 |

### 1.3 Admin 后台 `routers/admin.py`

| 项 | 内容 |
|----|------|
| **当前行为** | 全部路由 `Depends(require_admin)`：`user.role != "admin"` → **403**。前端改路由无法绕过 API。禁止自我降权/自禁用。 |
| **代码** | [`backend/core/dependencies.py`](backend/core/dependencies.py) L78-81；[`backend/routers/admin.py`](backend/routers/admin.py) 各端点 |
| **风险等级** | **低** |
| **本地四人用是否必改** | 否 |
| **公网部署前** | 保持；另确保生产无 seed 默认 admin 账户（见 §二） |

### 1.4 任务参考图本地路径读盘（附加发现）

| 项 | 内容 |
|----|------|
| **当前行为** | `tasks.py` `_image_url_to_base64`、`comfyui.py` `_resolve_local_upload_path`：对已登录用户提交的 `reference_images` 路径，**直接读盘**，不调用 `user_can_access_upload`。候选路径含 `Path(rel)`、`backend/rel`、`repo/rel`。 |
| **代码** | [`backend/routers/tasks.py`](backend/routers/tasks.py) ~L1084；[`backend/providers/comfyui.py`](backend/providers/comfyui.py) L285-296 |
| **风险等级** | **中～高**（取决于攻击者能否构造路径） |
| **本地四人用是否必改** | 可缓 |
| **公网部署前** | **建议修**：限制在 `uploads/images|videos/` 下且校验 `user_can_access_upload` |

### 1.5 Agent `POST /api/agent/run`

| 项 | 内容 |
|----|------|
| **当前行为** | 登录 + `get_accessible_project(..., require_edit=True)`，无项目只读越权。 |
| **代码** | [`backend/routers/agent.py`](backend/routers/agent.py) L110-116 |
| **风险等级** | **低**（权限边界） |
| **频控** | 见 §四（成本/滥用） |

---

## 二、高优先级：凭证与密钥

### 2.1 JWT 签发 / 校验

| 项 | 内容 |
|----|------|
| **当前行为** | 密钥来自环境变量 `JWT_SECRET` / `JWT_SECRET_KEY`（**非**硬编码在 `security.py`）。启动拒绝空串、短于 16、及若干弱占位符。算法 HS256；access / refresh 分 `type` 校验；bcrypt 存密码。 |
| **代码** | [`backend/core/config.py`](backend/core/config.py)；[`backend/core/security.py`](backend/core/security.py)；[`backend/services/auth.py`](backend/services/auth.py) 为重导出 |
| **风险等级** | **低～中** |
| **细节** | `.env.example` 示例 `change-me-to-a-long-random-string-at-least-16-chars` **不在**弱密钥黑名单，复制即用可启动 → **中**。JWT 密钥还派生 API Key 加密与媒体票据 HMAC（[`secret_store.py`](backend/core/secret_store.py)、`media_access.py`）→ 轮换 JWT 需一并考虑。 |
| **本地四人用是否必改** | 否（本地 `.env` 自有密钥即可） |
| **公网部署前** | **必改**：强随机 `JWT_SECRET`；勿用 example 值；Docker 侧建议强制校验 |

### 2.2 种子账号

| 项 | 内容 |
|----|------|
| **当前行为** | [`backend/services/seed.py`](backend/services/seed.py) 明文：`admin` / `Admin@2026!`，`testuser` / `Test@2026!`，`testuser2` / `Test2@2026!`。仅当 `APP_ENV != production` 时 `init_db` 执行 seed（[`db/init_db.py`](backend/db/init_db.py) L26-36）。已存在用户**不覆盖**密码。 |
| **暴露面** | HANDOFF、多份探针脚本、本仓库源码均可见默认密码。 |
| **风险等级** | **高**（源码泄露 = 已知管理员口令模式） |
| **本地四人用是否必改** | 否 |
| **公网部署前** | **部署清单必做**：`APP_ENV=production`、禁用/删除 seed 账户或强制改密；勿将开发 seed 带入生产初始化 |

### 2.3 Docker / 部署默认值

| 项 | 内容 |
|----|------|
| **当前行为** | 根 [`docker-compose.yml`](docker-compose.yml)：`POSTGRES_PASSWORD`、`REDIS_PASSWORD` 未设则 compose **失败**（`:?` 语法）。`JWT_SECRET` 依赖 `backend/.env`，compose **未强制**。 |
| **风险等级** | **中**（DB/Redis 较好；JWT 靠人工） |
| **公网部署前** | 文档化生产 env 检查清单 |

---

## 三、中优先级：输入面

### 3.1 文件上传

| 项 | 内容 |
|----|------|
| **当前行为** | `POST /api/upload/image`、`POST /api/assets/upload`：登录；MIME 白名单（jpeg/png/webp/gif）；最大 **10MB**；后缀白名单；写入 `uploads/images/{uuid}.ext` + `UserUpload` 归属。团队资产上传需 `require_team_editor`。 |
| **缺口** | 无 magic bytes / 图片内容校验，信任客户端 `content_type`。`POST /api/assets` 的 `image_url` 仅 `strip()`，不校验 URL 归属。 |
| **代码** | [`backend/routers/upload.py`](backend/routers/upload.py)；[`backend/routers/assets.py`](backend/routers/assets.py) |
| **风险等级** | **中** |
| **本地四人用是否必改** | 否 |
| **公网部署前** | 建议内容嗅探；外链 URL 白名单或 SSRF 防护 |

### 3.2 CORS

| 项 | 内容 |
|----|------|
| **当前行为** | `allow_origins=settings.cors_origin_list`；未配置 `CORS_ORIGINS` 时默认 localhost/127.0.0.1 的 **5173、3000、8173、8174**（历史 Vite 端口 + 当前 dev **8173**）。`allow_credentials=True`；非 `*`。 |
| **代码** | [`backend/main.py`](backend/main.py) L89-95；[`backend/core/config.py`](backend/core/config.py) L132-146 |
| **风险等级** | **低**（开发）；**中**（若生产未设 `CORS_ORIGINS` 则浏览器跨域失败而非过宽） |
| **公网部署前** | 设置 `CORS_ORIGINS` 为正式前端域名；Vite 备用端口需一并列入 |

---

## 四、中优先级：速率限制

### 4.1 登录 `POST /api/auth/login`

| 项 | 内容 |
|----|------|
| **当前行为** | **显式跳过**全站 IP 限流（[`main.py`](backend/main.py) L70-76 `_RATE_LIMIT_SKIP_PREFIXES`）。账号级：同一 `username_or_email` **5 次失败锁 15 分钟**（Redis 优先，无 Redis 则进程内 dict）。统一 401 文案，不枚举用户。 |
| **风险等级** | **中～高** |
| **说明** | 无 IP 维度 → 可对**不同账号**无限尝试；无 Redis 多 worker 不共享计数。与已知 seed 密码组合时，撞库 admin 风险上升。 |
| **本地四人用是否必改** | 否 |
| **公网部署前** | 建议：login 纳入 IP 限流或 CAPTCHA；确保 Redis；收紧失败阈值 |

### 4.2 Agent / 生成任务

| 项 | 内容 |
|----|------|
| **当前行为** | 一般 `/api/*` 受 IP 限流（默认 120/min，`.env` 可调）。`/api/agent/run` 与 `/api/agent/chat-title` 在路由层调用 **`check_agent_rate_limit`**（默认 `AGENT_RATE_LIMIT_USER_PER_MINUTE=20`，Redis 优先）。`check_user_rate_limit` 另用于 **image/video 任务**（[`generation_guard.py`](backend/services/generation_guard.py)）。 |
| **风险等级** | **低～中**（已有 per-user Agent 频控；公网仍可按套餐收紧配额） |
| **本地四人用是否必改** | 否 |
| **公网部署前** | 确认 Redis 已开；按需调低 `AGENT_RATE_LIMIT_USER_PER_MINUTE` 或增加日配额 |

---

## 五、汇总表（按风险排序）

| # | 发现 | 等级 | 本地四人用 | 公网前 |
|---|------|------|------------|--------|
| 1 | seed 明文默认 admin 密码写在源码 | **高** | 可接受 | **必处理** |
| 2 | 登录跳过 IP 限流 + 仅账号锁 | **中～高** | 可接受 | 建议修 |
| 3 | 任务参考图读盘无归属校验 | **中～高** | 可缓 | 建议修 |
| 4 | 团队媒体不按 project_id（队友可见） | **中** | **待产品确认** | 按产品决策 |
| 5 | `.env.example` JWT 可预测占位符 | **中** | 可接受 | 必换密钥 |
| 6 | Agent 用户级频控（`AGENT_RATE_LIMIT_*`） | **低～中** | 可接受 | 确认 Redis；按需收紧 |
| 7 | 上传无 magic bytes | **中** | 可接受 | 建议加 |
| 8 | 导出：团队 viewer 可下他人 zip | **低～中** | 可接受 | 确认策略 |
| 9 | JWT 密钥多用途（API Key/媒体票） | **中** | 可接受 | 知悉轮换影响 |
| 10 | 导出下载 / Admin API 鉴权 | **低** | OK | OK |
| 11 | CORS 非 `*`、credentials 模式 | **低** | OK | 配 `CORS_ORIGINS` |

---

## 六、建议下一步（不改代码，供决策）

1. ~~**小布丁确认**：团队内媒体是否允许「未参与项目但同队友」访问（§1.2）。~~ **已确认：同团队成员可见团队内全部历史项目，当前实现符合预期。**
2. **公网部署清单**（与代码解耦）：`APP_ENV=production`、强 JWT、Redis、删/改 seed 账户、CORS 域名。
3. ~~**若决定继续加固**~~ → **2026-06-25 已实施**，见下方 **§八 修复记录**。

---

## 八、修复记录（2026-06-25）

| 审计项 | 处理 |
|--------|------|
| seed 明文密码 | 迁至 `SEED_*_PASSWORD` 环境变量；`seed.py` 无硬编码 |
| 登录跳过 IP 限流 | `/api/auth/login` 纳入全站 IP 限流 + 专用 `LOGIN_RATE_LIMIT_PER_MINUTE` |
| 参考图路径穿越 | `assert_user_can_read_upload_url`；任务/ComfyUI 本地读盘必经鉴权 |
| `.env.example` JWT 占位 | 加入 `WEAK_JWT_SECRETS` 黑名单 |
| Agent 无用户频控 | `check_agent_rate_limit` on `/run` 与 `/chat-title` |
| 上传无 magic bytes | `services/upload_validation.py` |
| 资产 `image_url` 无校验 | `create_asset` 校验可读上传 |
| CORS 8174 | 默认 origin 列表已含 8174 |
| 团队媒体不按 project | **按产品确认保留** |

---

## 七、涉及文件索引

```
backend/core/config.py          # JWT、CORS、APP_ENV
backend/core/security.py        # JWT 签发/验签、bcrypt
backend/core/dependencies.py    # get_current_user、require_admin
backend/services/auth_service.py # 登录锁、refresh 黑名单
backend/services/seed.py        # 种子账号
backend/services/media_access.py
backend/services/canvas_access.py
backend/services/export_service.py
backend/routers/exports.py
backend/routers/admin.py
backend/routers/upload.py
backend/routers/assets.py
backend/routers/tasks.py
backend/routers/agent.py
backend/main.py                 # CORS、IP 限流中间件
backend/providers/comfyui.py    # 参考图路径解析
docker-compose.yml
backend/.env.example
.env.example
```
