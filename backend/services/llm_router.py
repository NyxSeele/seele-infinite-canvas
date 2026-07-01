"""文本 LLM 路由：默认模型、低价优先、均衡分流（价格 + 近 24h 用量）。"""

from __future__ import annotations

import logging
import math
import threading
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

_memory_usage: dict[str, int] = {}
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


def _list_enabled_text_api(db: Session) -> list[RegisteredModel]:
    return (
        db.query(RegisteredModel)
        .filter(
            RegisteredModel.enabled.is_(True),
            RegisteredModel.category == "text",
            RegisteredModel.type == "api",
        )
        .order_by(RegisteredModel.id)
        .all()
    )


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


def resolve_text_model(db: Session | None = None) -> RegisteredModel | None:
    """按 Admin 配置选择下一个文本 API 模型。"""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        enabled = _list_enabled_text_api(db)
        if not enabled:
            return None

        mode = get_routing_mode(db)

        if mode == "fixed":
            return _default_text_model(db, enabled)

        if mode == "cheapest":
            priced = [r for r in enabled if _price_or_inf(r) < math.inf]
            if priced:
                return min(priced, key=_price_or_inf)
            return _default_text_model(db, enabled)

        # balanced: score = usage_24h * (price / min_price)
        prices = [_price_or_inf(r) for r in enabled]
        finite_prices = [p for p in prices if p < math.inf]
        min_price = min(finite_prices) if finite_prices else 1.0

        def _balanced_score(row: RegisteredModel) -> float:
            usage = float(get_usage_24h(row.id))
            price = _price_or_inf(row)
            if price == math.inf:
                price = min_price * 10.0
            ratio = price / min_price if min_price > 0 else 1.0
            return usage * ratio

        return min(enabled, key=_balanced_score)
    finally:
        if own:
            db.close()


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
