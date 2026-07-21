"""Tests for agent skills (option 2) + manifest skill wiring."""

from pathlib import Path

import pytest
import yaml

from services.agent_service import SYSTEM_PROMPT, SYSTEM_PROMPT_PIPELINE
from services.pipeline_manifest import (
    BACKEND_ROOT,
    PipelineManifestError,
    build_skills_prompt_section,
    load_pipeline,
    load_skill_text,
)


EXPECTED_STEPS = [
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


def test_all_stage_skill_files_exist():
    manifest = load_pipeline("velora_canvas")
    assert manifest.shared_skill
    assert (BACKEND_ROOT / manifest.shared_skill).is_file()
    for stage in manifest.stages:
        path = BACKEND_ROOT / stage.skill
        assert path.is_file(), f"missing skill for {stage.name}: {stage.skill}"


def test_build_skills_prompt_contains_steps_and_titles():
    manifest = load_pipeline("velora_canvas")
    section = build_skills_prompt_section(manifest)
    for step in EXPECTED_STEPS:
        assert step in section or f"Skill: {step}" in section or step.replace("_", " ") in section.lower()
        # Each skill file starts with "# Skill: <name>" or shared header
        assert step in SYSTEM_PROMPT
    assert "单步执行" in section or "Stage Skills" in section
    assert "create_text_note" in SYSTEM_PROMPT
    assert "manage_cast" in SYSTEM_PROMPT


def test_system_prompt_includes_skills_content():
    assert "Stage Skills" in SYSTEM_PROMPT
    assert "Skill: create_text_note" in SYSTEM_PROMPT
    assert "Skill: generate_outline" in SYSTEM_PROMPT
    assert "Stage Skills" in SYSTEM_PROMPT_PIPELINE


def test_missing_skill_file_raises(tmp_path: Path):
    skill_dir = tmp_path / "agent_skills" / "t"
    skill_dir.mkdir(parents=True)
    # Point skill outside BACKEND_ROOT by writing a fake manifest under pipelines_dir
    # that references a missing skill under BACKEND_ROOT.
    data = {
        "name": "broken",
        "version": "1",
        "description": "x",
        "stages": [
                {
                    "name": "create_text_note",
                    "order": 1,
                    "phase": "script_structure",
                    "optional": False,
                    "skill": "agent_skills/velora_canvas/__missing_skill__.md",
                    "executor": "canvas.create_text_note",
                    "capabilities": ["canvas.nodes.create"],
                    "ui_label": "a",
                    "preconditions": [],
                    "produces": [],
                    "prompt_label": "a",
                }
        ],
    }
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(PipelineManifestError, match="skill file not found"):
        load_pipeline("broken", pipelines_dir=tmp_path)


def test_load_skill_text_reads_markdown():
    text = load_skill_text("agent_skills/velora_canvas/create_text_note.md")
    assert "create_text_note" in text
    assert "data" in text.lower() or "prompt" in text
