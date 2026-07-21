"""Tests for pipeline manifest loader and agent_service integration."""

from pathlib import Path

import pytest
import yaml

from services.agent_service import (
    SYSTEM_PROMPT,
    _PIPELINE_FORCE_STEPS,
    _PIPELINE_KNOWN_STEPS,
    _drop_unknown_pipeline_steps,
)
from services.pipeline_manifest import (
    PipelineManifestError,
    build_prompt_stage_table,
    get_force_steps,
    get_stage_order,
    is_known_step,
    load_pipeline,
)


EXPECTED_ORDER = [
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

OPTIONAL_STEPS = frozenset({"split_shot_beats", "manage_cast", "manage_scene"})
FORCE_STEPS = frozenset(step for step in EXPECTED_ORDER if step not in OPTIONAL_STEPS)


def test_load_velora_canvas_has_nine_stages_in_order():
    manifest = load_pipeline("velora_canvas")
    assert get_stage_order(manifest) == EXPECTED_ORDER
    assert manifest.name == "velora_canvas_screenplay"


def test_missing_manifest_raises(tmp_path: Path):
    with pytest.raises(PipelineManifestError, match="not found"):
        load_pipeline("missing", pipelines_dir=tmp_path)


def test_invalid_manifest_missing_stages_raises(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"name": "x", "version": "1", "description": "y"}), encoding="utf-8")
    with pytest.raises(PipelineManifestError, match="stages"):
        load_pipeline("bad", pipelines_dir=tmp_path)


def test_duplicate_stage_name_raises(tmp_path: Path):
    data = {
        "name": "dup",
        "version": "1.0",
        "description": "dup",
        "stages": [
            {
                "name": "create_text_note",
                "order": 1,
                "phase": "script_structure",
                "optional": False,
                "skill": "agent_skills/velora_canvas/create_text_note.md",
                "executor": "canvas.create_text_note",
                "capabilities": ["canvas.nodes.create"],
                "ui_label": "a",
                "preconditions": [],
                "produces": [],
                "prompt_label": "a",
            },
            {
                "name": "create_text_note",
                "order": 2,
                "phase": "script_structure",
                "optional": False,
                "skill": "agent_skills/velora_canvas/create_text_note.md",
                "executor": "canvas.create_text_note",
                "capabilities": ["canvas.nodes.create"],
                "ui_label": "b",
                "preconditions": [],
                "produces": [],
                "prompt_label": "b",
            },
        ],
    }
    path = tmp_path / "dup.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(PipelineManifestError, match="duplicate stage name"):
        load_pipeline("dup", pipelines_dir=tmp_path)


def test_build_prompt_stage_table_contains_all_steps():
    manifest = load_pipeline("velora_canvas")
    table = build_prompt_stage_table(manifest, slim=False)
    for step in EXPECTED_ORDER:
        assert step in table


def test_get_force_steps_optional_semantics():
    manifest = load_pipeline("velora_canvas")
    force = get_force_steps(manifest)
    assert force == FORCE_STEPS
    assert "split_shot_beats" not in force
    assert "manage_cast" not in force
    assert "manage_scene" not in force
    assert "generate_video" in force


def test_is_known_step_unknown():
    manifest = load_pipeline("velora_canvas")
    assert is_known_step(manifest, "foo") is False
    assert is_known_step(manifest, "create_text_note") is True


def test_agent_service_derives_constants_from_manifest():
    assert _PIPELINE_KNOWN_STEPS == frozenset(EXPECTED_ORDER)
    assert _PIPELINE_FORCE_STEPS == FORCE_STEPS


def test_system_prompt_stage_names_match_manifest():
    manifest = load_pipeline("velora_canvas")
    for step in get_stage_order(manifest):
        assert step in SYSTEM_PROMPT


def test_drop_unknown_pipeline_steps_filters_and_warns(caplog):
    actions = [
        {"type": "pipeline_step", "step": "not_a_real_step", "data": {}},
        {"type": "done", "summary": "ok"},
    ]
    filtered = _drop_unknown_pipeline_steps(actions)
    assert all(a.get("step") != "not_a_real_step" for a in filtered if a.get("type") == "pipeline_step")
    assert any(a.get("type") == "done" for a in filtered)
    assert "unknown pipeline_step rejected" in caplog.text


def test_drop_unknown_pipeline_steps_only_unknown_adds_done():
    actions = [{"type": "pipeline_step", "step": "bogus_step", "data": {}}]
    filtered = _drop_unknown_pipeline_steps(actions)
    assert filtered == [
        {
            "type": "done",
            "summary": "上一步包含无效的链路步骤，已跳过。请根据当前进度重新发送「继续」。",
            "suggestions": ["继续"],
        }
    ]
