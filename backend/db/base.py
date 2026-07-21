from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from core.config import settings

_is_sqlite = settings.sqlalchemy_database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}
_engine_kwargs: dict = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
}
if _is_sqlite:
    # FastAPI request Session + Agent nested SessionLocal must not share QueuePool(size=1),
    # or /api/agent/run hits QueuePool TimeoutError and the handbook A chapter fails.
    # NullPool: one connection per Session, no pool wait; SQLite serializes writes via locks.
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_timeout=30)
engine = create_engine(settings.sqlalchemy_database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def register_orm_models() -> None:
    """导入全部 ORM 模型，供 create_all 注册元数据（避免在模块顶层循环导入）。"""
    import models.model_permission  # noqa: F401
    import models.model_setting  # noqa: F401
    import models.quota  # noqa: F401
    import models.registered_model  # noqa: F401
    import models.task  # noqa: F401
    import models.team  # noqa: F401
    import models.canvas_project  # noqa: F401
    import models.canvas_comment  # noqa: F401
    import models.user_asset  # noqa: F401
    import models.user  # noqa: F401
    import models.agent_conversation  # noqa: F401
