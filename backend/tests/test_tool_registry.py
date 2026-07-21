"""Tests for lightweight tool registry (option 3)."""

import pytest

from services.pipeline_manifest import load_pipeline
from services.tool_registry import (
    ToolRegistryError,
    build_tool_registry,
    get_tool,
    list_tools,
    support_envelope,
)


EXPECTED = [
    "create_text_note",
    "start_text_generation",
    "generate_outline",
    "generate_script_table",
    "split_shot_beats",
    "generate_storyboard",
    "generate_video",
    "manage_cast",
    "manage_scene",
]


def test_registry_has_nine_tools_with_executor_and_caps():
    manifest = load_pipeline("velora_canvas")
    registry = build_tool_registry(manifest)
    assert set(registry.keys()) == set(EXPECTED)
    for name, tool in registry.items():
        assert tool.executor, name
        assert tool.capabilities, name
        assert tool.ui_label, name
        assert tool.skill, name


def test_list_tools_order_and_fields():
    manifest = load_pipeline("velora_canvas")
    tools = list_tools(manifest)
    assert [t["name"] for t in tools] == EXPECTED
    assert tools[0]["executor"] == "canvas.create_text_note"
    assert "canvas.nodes.create" in tools[0]["capabilities"]


def test_support_envelope():
    manifest = load_pipeline("velora_canvas")
    env = support_envelope(manifest)
    assert env["steps"] == EXPECTED
    assert "split_shot_beats" in env["optional_steps"]
    assert "manage_cast" in env["optional_steps"]
    assert "api.tasks.text" in env["capabilities_union"]
    assert len(env["tools"]) == 9


def test_get_tool_unknown_raises():
    manifest = load_pipeline("velora_canvas")
    with pytest.raises(ToolRegistryError, match="unknown"):
        get_tool(manifest, "not_a_step")


def test_manifest_api_dict_includes_executor():
    from services.pipeline_manifest import manifest_to_api_dict

    manifest = load_pipeline("velora_canvas")
    payload = manifest_to_api_dict(manifest)
    stage0 = payload["stages"][0]
    assert stage0["executor"]
    assert stage0["capabilities"]
    assert stage0["ui_label"]
