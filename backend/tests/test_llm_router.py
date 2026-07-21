from types import SimpleNamespace

from services.llm_router import (
    clear_model_quota_exhausted,
    is_model_quota_exhausted,
    mark_model_quota_exhausted,
    resolve_text_model,
    resolve_text_model_candidates,
)


def test_fixed_mode_prefers_default_when_quota_available(monkeypatch):
    default = SimpleNamespace(id="qwen3-6-35b-a3b", is_default_text=True)
    other = SimpleNamespace(id="qwen3-6-flash", is_default_text=False)
    enabled = [other, default]

    monkeypatch.setattr(
        "services.llm_router._list_enabled_text_api", lambda db: enabled
    )
    monkeypatch.setattr("services.llm_router.get_routing_mode", lambda db: "fixed")
    monkeypatch.setattr(
        "services.llm_router._default_text_model", lambda db, rows: default
    )
    monkeypatch.setattr(
        "services.llm_router.is_model_quota_exhausted", lambda model_id: False
    )
    monkeypatch.setattr(
        "services.llm_router._resolve_balanced_ranked",
        lambda enabled, exclude_ids=None: [other],
    )

    candidates = resolve_text_model_candidates()
    assert [row.id for row in candidates] == ["qwen3-6-35b-a3b", "qwen3-6-flash"]
    assert resolve_text_model().id == "qwen3-6-35b-a3b"


def test_fixed_mode_skips_exhausted_default_and_uses_balanced(monkeypatch):
    default = SimpleNamespace(id="qwen3-6-35b-a3b", is_default_text=True)
    flash = SimpleNamespace(id="qwen3-6-flash", is_default_text=False)
    enabled = [default, flash]

    monkeypatch.setattr(
        "services.llm_router._list_enabled_text_api", lambda db: enabled
    )
    monkeypatch.setattr("services.llm_router.get_routing_mode", lambda db: "fixed")
    monkeypatch.setattr(
        "services.llm_router._default_text_model", lambda db, rows: default
    )

    def _quota_exhausted(model_id: str) -> bool:
        return model_id == "qwen3-6-35b-a3b"

    monkeypatch.setattr(
        "services.llm_router.is_model_quota_exhausted", _quota_exhausted
    )
    monkeypatch.setattr(
        "services.llm_router._resolve_balanced_ranked",
        lambda enabled, exclude_ids=None: [flash],
    )

    candidates = resolve_text_model_candidates()
    assert candidates[0].id == "qwen3-6-flash"
    assert "qwen3-6-35b-a3b" not in [row.id for row in candidates]
    assert resolve_text_model().id == "qwen3-6-flash"


def test_balanced_mode_returns_failover_list(monkeypatch):
    a = SimpleNamespace(id="slow", is_default_text=False, input_price_per_million=1.0)
    b = SimpleNamespace(id="fast", is_default_text=False, input_price_per_million=2.0)
    enabled = [a, b]

    monkeypatch.setattr(
        "services.llm_router._list_enabled_text_api", lambda db: enabled
    )
    monkeypatch.setattr("services.llm_router.get_routing_mode", lambda db: "balanced")
    monkeypatch.setattr(
        "services.llm_router.is_model_quota_exhausted", lambda model_id: False
    )
    monkeypatch.setattr("services.llm_router.get_usage_24h", lambda model_id: 0)

    candidates = resolve_text_model_candidates()
    assert len(candidates) == 2
    assert {row.id for row in candidates} == {"slow", "fast"}


def test_quota_exhausted_memory_fallback(monkeypatch):
    monkeypatch.setattr("services.llm_router.get_redis", lambda: None)
    clear_model_quota_exhausted("qwen3-6-35b-a3b")
    assert not is_model_quota_exhausted("qwen3-6-35b-a3b")
    mark_model_quota_exhausted("qwen3-6-35b-a3b")
    assert is_model_quota_exhausted("qwen3-6-35b-a3b")
