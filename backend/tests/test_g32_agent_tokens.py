"""G32: staged system prompt + slim canvas context."""
from services.agent_service import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_CORE,
    SYSTEM_PROMPT_PIPELINE,
    _build_canvas_context,
    _build_pipeline_context,
    _select_system_prompt,
    _should_use_pipeline_prompt,
)
from schemas.agent_schemas import AgentMessage, CanvasSnapshot, CanvasNodeSnapshot


def _msg(role: str, content: str) -> AgentMessage:
    return AgentMessage(role=role, content=content)


def _node(nid: str, ntype: str, **extra) -> CanvasNodeSnapshot:
    payload = {
        "id": nid,
        "type": ntype,
        "position": {"x": 0, "y": 0},
        "content_preview": extra.pop("content_preview", ""),
        **extra,
    }
    return CanvasNodeSnapshot(**payload)


def _snap(nodes=None) -> CanvasSnapshot:
    if nodes is None:
        nodes = [_node("n1", "text_note", content_preview="test")]
    return CanvasSnapshot(
        nodes=nodes,
        edges=[],
        total_node_count=len(nodes),
    )


def test_pipeline_continue_uses_short_prompt():
    messages = [_msg("user", "继续")]
    snap = _snap()
    ctx = _build_pipeline_context(snap, messages)
    assert _should_use_pipeline_prompt(messages, ctx) is True
    selected = _select_system_prompt(messages, ctx)
    assert selected == SYSTEM_PROMPT_CORE + SYSTEM_PROMPT_PIPELINE
    assert len(selected) < len(SYSTEM_PROMPT) * 0.55


def test_brainstorm_uses_full_prompt():
    messages = [_msg("user", "我想做一段重庆宣传片")]
    ctx = _build_pipeline_context(_snap([]), messages)
    assert _should_use_pipeline_prompt(messages, ctx) is False
    assert _select_system_prompt(messages, ctx) == SYSTEM_PROMPT


def test_pipeline_canvas_context_omits_full_json():
    messages = [_msg("user", "继续")]
    snap = _snap(
        [
            _node(
                "st1",
                "script_table",
                content_preview="分镜表",
                rows_summary=[{"id": "001", "description": "雨中漫步"}],
            )
        ]
    )
    ctx = _build_canvas_context(snap, messages, pipeline_mode=True)
    assert "## 当前画布状态" not in ctx
    assert "可用节点 id" in ctx
    assert "雨中漫步" in ctx or "分镜" in ctx
