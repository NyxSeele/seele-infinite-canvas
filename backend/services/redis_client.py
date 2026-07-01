"""Redis 连接（限流、会话锁、生成并发、Pub/Sub）。"""

from __future__ import annotations

import logging

import redis

from core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _connect(url: str) -> redis.Redis:
    """创建 Redis 客户端。Redis 5.x 仅支持 RESP2，禁用 RESP3 的 HELLO 握手。"""
    return redis.Redis.from_url(
        url,
        decode_responses=True,
        protocol=2,
    )


def get_redis() -> redis.Redis | None:
    """获取 Redis 客户端；连接断开时会自动重连。"""
    global _client
    url = (settings.redis_url or "").strip()
    if not url:
        logger.warning("REDIS_URL 未配置，相关能力将降级为内存/数据库")
        return None
    if _client is not None:
        try:
            _client.ping()
            return _client
        except Exception:
            _client = None
    try:
        client = _connect(url)
        client.ping()
        _client = client
        return _client
    except redis.AuthenticationError:
        logger.warning(
            "Redis 需要密码：请在 REDIS_URL 中填写，例如 "
            "redis://:你的密码@127.0.0.1:6379/0（与 redis.conf 的 requirepass 一致）"
        )
        return None
    except Exception as exc:
        err = str(exc)
        if "HELLO" in err:
            logger.warning(
                "Redis 协议不兼容（多为 Redis 5.x + 新版 redis-py）：已使用 RESP2，若仍失败请检查密码"
            )
        else:
            logger.warning("Redis 连接失败，将降级: %s", exc)
        return None


def redis_available() -> bool:
    return get_redis() is not None
