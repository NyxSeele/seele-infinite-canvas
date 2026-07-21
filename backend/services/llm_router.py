"""文本 LLM 路由：默认模型、低价优先、均衡分流（价格 + 近 24h 用量）。"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Literal

from sqlalchemy.orm import Session

from db.session import SessionLocal
from models import RegisteredModel, SystemSetting
from services.redis_client import get_redis

logger = logging.getLogger(__name__)

ROUTING_MODE_KEY = "llm_routing_mode"
DEFAULT_ROUTING_MODE = "fixed"
VALID_MODES = frozenset({"fixed", "cheapest", "balanced"})
USAGE_KEY_PREFIX = "llm:usage:24h:"
USAGE_TTL_SEC = 86400
QUOTA_EXHAUSTED_KEY_PREFIX = "llm:quota_exhausted:"
QUOTA_EXHAUSTED_TTL_SEC = 86400

_memory_usage: dict[str, int] = {}
_memory_quota_exhausted: dict[str, float] = {}
_memory_lock = threading.Lock()


def _usage_key(model_id: str) -> str:
    return f"{USAGE_KEY_PREFIX}{model_id}"


def get_routing_mode(db: Session | None = None) -> str:
    own = db is None
    if own:
        db = SessionLocal()
    try:
        row = db.get(SystemSetting, ROUTING_MODE_KEY)
        mode = (row.value if row and row.value else DEFAULT_ROUTING_MODE).strip().lower()
        return mode if mode in VALID_MODES else DEFAULT_ROUTING_MODE
    finally:
        if own:
            db.close()


def set_routing_mode(mode: str, db: Session | None = None) -> str:
    normalized = (mode or "").strip().lower()
    if normalized not in VALID_MODES:
        raise ValueError(f"无效分流模式: {mode}")
    own = db is None
    if own:
        db = SessionLocal()
    try:
        row = db.get(SystemSetting, ROUTING_MODE_KEY)
        if row is None:
            row = SystemSetting(key=ROUTING_MODE_KEY, value=normalized)
            db.add(row)
        else:
            row.value = normalized
        db.commit()
        return normalized
    finally:
        if own:
            db.close()


def _is_vision_text_model(row: RegisteredModel) -> bool:
    """视觉专用模型不应作为纯文本翻译/优化候选。"""
    mid = (row.id or "").strip().lower()
    mstr = (getattr(row, "model_string", None) or "").strip().lower()
    blob = f"{mid} {mstr}"
    return "-vl-" in blob or blob.endswith("-vl") or "vl-max" in blob or "vision" in blob


def _list_enabled_text_api(db: Session) -> list[RegisteredModel]:
    rows = (
        db.query(RegisteredModel)
        .filter(
            RegisteredModel.enabled.is_(True),
            RegisteredModel.category == "text",
            RegisteredModel.type == "api",
        )
        .order_by(RegisteredModel.id)
        .all()
    )
    return [r for r in rows if not _is_vision_text_model(r)]


def _default_text_model(db: Session, enabled: list[RegisteredModel]) -> RegisteredModel | None:
    for row in enabled:
        if row.is_default_text:
            return row
    return enabled[0] if enabled else None


def _price_or_inf(row: RegisteredModel) -> float:
    price = row.input_price_per_million
    if price is None or price <= 0:
        return math.inf
    return float(price)


def get_usage_24h(model_id: str) -> int:
    r = get_redis()
    if r is not None:
        try:
            raw = r.get(_usage_key(model_id))
            return int(raw or 0)
        except Exception as exc:
            logger.warning("Redis 读取 LLM 用量失败 model=%s: %s", model_id, exc)
    with _memory_lock:
        return int(_memory_usage.get(model_id, 0))


def _quota_exhausted_key(model_id: str) -> str:
    return f"{QUOTA_EXHAUSTED_KEY_PREFIX}{model_id}"


def mark_model_quota_exhausted(model_id: str) -> None:
    """默认模型免费额度用尽时标记，fixed 模式下自动降级到均衡分流。"""
    if not model_id:
        return
    logger.warning(
        "[LLM_QUOTA_FALLBACK] model=%s marked quota exhausted ttl=%ss",
        model_id,
        QUOTA_EXHAUSTED_TTL_SEC,
    )
    r = get_redis()
    if r is not None:
        try:
            r.setex(_quota_exhausted_key(model_id), QUOTA_EXHAUSTED_TTL_SEC, "1")
            return
        except Exception as exc:
            logger.warning("Redis 写入额度用尽标记失败 model=%s: %s", model_id, exc)
    expires_at = time.time() + QUOTA_EXHAUSTED_TTL_SEC
    with _memory_lock:
        _memory_quota_exhausted[model_id] = expires_at


def is_model_quota_exhausted(model_id: str) -> bool:
    if not model_id:
        return False
    r = get_redis()
    if r is not None:
        try:
            return bool(r.get(_quota_exhausted_key(model_id)))
        except Exception as exc:
            logger.warning("Redis 读取额度用尽标记失败 model=%s: %s", model_id, exc)
    with _memory_lock:
        expires_at = _memory_quota_exhausted.get(model_id)
        if not expires_at:
            return False
        if expires_at <= time.time():
            _memory_quota_exhausted.pop(model_id, None)
            return False
        return True


def clear_model_quota_exhausted(model_id: str) -> None:
    """测试或 Admin 手动恢复默认模型时清除标记。"""
    if not model_id:
        return
    r = get_redis()
    if r is not None:
        try:
            r.delete(_quota_exhausted_key(model_id))
        except Exception as exc:
            logger.warning("Redis 清除额度用尽标记失败 model=%s: %s", model_id, exc)
    with _memory_lock:
        _memory_quota_exhausted.pop(model_id, None)


def record_usage(model_id: str, tokens: int) -> None:
    if not model_id or tokens <= 0:
        return
    r = get_redis()
    if r is not None:
        try:
            key = _usage_key(model_id)
            pipe = r.pipeline()
            pipe.incrby(key, int(tokens))
            pipe.expire(key, USAGE_TTL_SEC)
            pipe.execute()
            return
        except Exception as exc:
            logger.warning("Redis 写入 LLM 用量失败 model=%s: %s", model_id, exc)
    with _memory_lock:
        _memory_usage[model_id] = _memory_usage.get(model_id, 0) + int(tokens)


def _balanced_score(row: RegisteredModel, *, min_price: float) -> float:
    usage = float(get_usage_24h(row.id))
    price = _price_or_inf(row)
    if price == math.inf:
        price = min_price * 10.0
    ratio = price / min_price if min_price > 0 else 1.0
    return usage * ratio


def _min_price_for_rows(rows: list[RegisteredModel]) -> float:
    prices = [_price_or_inf(r) for r in rows]
    finite_prices = [p for p in prices if p < math.inf]
    return min(finite_prices) if finite_prices else 1.0


def _resolve_balanced_model(
    enabled: list[RegisteredModel],
    *,
    exclude_ids: set[str] | None = None,
) -> RegisteredModel | None:
    exclude = exclude_ids or set()
    pool = [
        r
        for r in enabled
        if r.id not in exclude and not is_model_quota_exhausted(r.id)
    ]
    if not pool:
        return None
    min_price = _min_price_for_rows(pool)
    return min(pool, key=lambda row: _balanced_score(row, min_price=min_price))


def _resolve_balanced_ranked(
    enabled: list[RegisteredModel],
    *,
    exclude_ids: set[str] | None = None,
) -> list[RegisteredModel]:
    exclude = exclude_ids or set()
    pool = [
        r
        for r in enabled
        if r.id not in exclude and not is_model_quota_exhausted(r.id)
    ]
    if not pool:
        return []
    min_price = _min_price_for_rows(pool)
    return sorted(pool, key=lambda row: _balanced_score(row, min_price=min_price))


def resolve_text_model_candidates(db: Session | None = None) -> list[RegisteredModel]:
    """按优先级返回可尝试的文本模型：fixed 下默认优先，额度用尽后均衡其余。"""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        enabled = _list_enabled_text_api(db)
        if not enabled:
            return []

        mode = get_routing_mode(db)

        if mode == "cheapest":
            priced = [r for r in enabled if _price_or_inf(r) < math.inf]
            pool = priced or list(enabled)
            ranked = sorted(pool, key=_price_or_inf)
            return ranked

        if mode == "balanced":
            # 返回完整排序列表，供调用方在超时/失败时故障转移
            return _resolve_balanced_ranked(enabled)

        candidates: list[RegisteredModel] = []
        default = _default_text_model(db, enabled)
        if default and not is_model_quota_exhausted(default.id):
            candidates.append(default)

        exclude = {row.id for row in candidates}
        for row in _resolve_balanced_ranked(enabled, exclude_ids=exclude):
            candidates.append(row)

        if candidates:
            return candidates

        # 全部标记用尽时仍返回默认，由调用方处理硬错误
        if default:
            return [default]
        return enabled
    finally:
        if own:
            db.close()


def resolve_text_model(db: Session | None = None) -> RegisteredModel | None:
    """按 Admin 配置选择下一个文本 API 模型。"""
    candidates = resolve_text_model_candidates(db)
    return candidates[0] if candidates else None


def set_default_text_model(model_id: str, db: Session | None = None) -> RegisteredModel:
    own = db is None
    if own:
        db = SessionLocal()
    try:
        row = db.get(RegisteredModel, model_id)
        if not row:
            raise ValueError(f"模型不存在: {model_id}")
        if row.category != "text" or row.type != "api":
            raise ValueError("仅 text/api 模型可设为默认 Agent LLM")
        if not row.enabled:
            raise ValueError("请先启用该模型再设为默认")

        db.query(RegisteredModel).filter(RegisteredModel.is_default_text.is_(True)).update(
            {RegisteredModel.is_default_text: False},
            synchronize_session=False,
        )
        row.is_default_text = True
        db.commit()
        db.refresh(row)
        return row
    finally:
        if own:
            db.close()


def list_routing_snapshot(db: Session | None = None) -> dict:
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = (
            db.query(RegisteredModel)
            .filter(RegisteredModel.category == "text", RegisteredModel.type == "api")
            .order_by(RegisteredModel.id)
            .all()
        )
        default_id = next((r.id for r in rows if r.is_default_text), None)
        return {
            "mode": get_routing_mode(db),
            "default_model_id": default_id,
            "models": [
                {
                    "id": r.id,
                    "display_name": r.display_name or r.id,
                    "enabled": bool(r.enabled),
                    "is_default": bool(r.is_default_text),
                    "input_price_per_million": r.input_price_per_million,
                    "usage_24h_tokens": get_usage_24h(r.id),
                }
                for r in rows
            ],
        }
    finally:
        if own:
            db.close()


RoutingMode = Literal["fixed", "cheapest", "balanced"]
