from core.config import settings
from db.base import Base, SessionLocal, engine, register_orm_models
from database import init_db
from models import (  # noqa: F401
    CanvasShare,
    CanvasState,
    QuotaPlan,
    RegisteredModel,
    Task,
    Team,
    TeamMember,
    User,
    UserAsset,
    UserModelPermission,
    UserQuota,
    UserUpload,
    Notification,
)
from services.api_key_service import migrate_plaintext_api_keys
from services.seed import seed_database


def init_database() -> None:
    """开发环境建表并写入种子数据；生产环境仅做 API Key 迁移（schema 由 Alembic 管理）。"""
    register_orm_models()
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
        init_db(engine)
        print("init_db: 已执行 Base.metadata.create_all")
    else:
        print("init_db: 生产模式，跳过 create_all（请使用 alembic upgrade head）")
    db = SessionLocal()
    try:
        if not settings.is_production:
            seed_database(db)
            print("init_db: 种子数据就绪（admin / testuser）")
        migrated = migrate_plaintext_api_keys(db)
        if migrated:
            print(f"init_db: 已加密 {migrated} 条明文 API Key")
        print("init_db: registered_models 表已确保存在（不自动 seed）")
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
    print("数据库初始化完成")
