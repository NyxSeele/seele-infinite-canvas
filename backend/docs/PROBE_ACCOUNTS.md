# 探针 / GPU 验收账号备忘

**更新**：2026-07-07（查库核对）

## 结论：`kiana` 账号

当前 SQLite 与代码种子中 **不存在** `kiana` 用户。团队相关 E2E 使用的是：

| 账号 | 团队 | 用途 |
|------|------|------|
| **admin** | 探针团队 A（owner） | 管理接口、无限配额、多数 GPU/E2E 探针 |
| **testuser2** | 探针团队 B（owner） | 团队隔离、@提及、实体库 C4（[`_entity_library_probe.py`](../scripts/_entity_library_probe.py)、[`_collab_api_probe.py`](../scripts/_collab_api_probe.py)） |

若你记得的「kiana + admin 同团队」可能是 **计划名/口头称呼** 或与其他环境混淆；本仓库对应角色是 **testuser2（团队 B）** 与 **admin（团队 A）** 做**跨团队**隔离测试，并非同一团队。

## 种子账号（`backend/.env`）

| 用户名 | 密码环境变量 | 角色 | 图像/视频配额 | 团队 |
|--------|--------------|------|---------------|------|
| `admin` | `SEED_ADMIN_PASSWORD` | admin | **无限**（-1） | 探针团队 A |
| `testuser` | `SEED_TESTUSER_PASSWORD` | user | 50 / **10** 每月 | 无 |
| `testuser2` | `SEED_TESTUSER2_PASSWORD` | user | 50 / **10** 每月 | 探针团队 B |

本地 `.env` 示例：`Admin@2026!` / `Test@2026!` / `Test2@2026!`

## 探针选型建议

| 场景 | 推荐账号 | 原因 |
|------|----------|------|
| 连跑多段 GPU（Prompt 调试 K1–K4、阶段二 V1–V4） | **admin** | 视频配额无限 |
| 模拟普通用户配额路径 | testuser | 需跑前 `reset_quota` 或提高 `video_limit` |
| 团队隔离 / 跨用户 @提及 | admin + **testuser2** | 已种子两个团队 |
| Prompt 调试阶段一/二脚本（历史） | testuser | 与画布 testuser 一致；易撞 10 次上限 |

## 配额操作

```bash
# 管理端（admin token）
POST /api/admin/users/{user_id}/reset_quota
PATCH /api/admin/users/{user_id}/quota   # 调整 image_limit / video_limit
```

Python（开发机）：

```python
from db.session import SessionLocal
from services.quota_service import reset_user_quota, get_or_create_user_quota
from models import User

db = SessionLocal()
u = db.query(User).filter(User.username == "testuser").one()
reset_user_quota(db, u.id)
q = get_or_create_user_quota(db, u.id)
q.video_limit = 100  # 可选：抬高上限
db.commit()
```

## 固定团队 ID（探针复现）

见 [`services/seed.py`](../services/seed.py)：

- 探针团队 A：`a1000000-0000-4000-8000-000000000001`（admin）
- 探针团队 B：`a2000000-0000-4000-8000-000000000002`（testuser2）
