"""Tests for ComfyUI workflow registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comfyui import workflow_registry


@pytest.fixture(autouse=True)
def _reset_override_dir(monkeypatch, tmp_path):
  override_dir = tmp_path / "override_workflows"
  override_dir.mkdir(parents=True, exist_ok=True)
  monkeypatch.setenv(workflow_registry._OVERRIDE_ENV, str(override_dir))
  return override_dir


def test_list_workflows_includes_ltx2_t2v():
    keys = [item["key"] for item in workflow_registry.list_workflows()]
    assert "ltx2_fp4_t2v_api.json" in keys


def test_load_workflow_returns_comfy_nodes():
    payload = workflow_registry.load_workflow("ltx2_fp4_t2v_api.json")
    assert isinstance(payload, dict)
    assert payload
    assert any(isinstance(node, dict) and "class_type" in node for node in payload.values())


def test_unknown_key_raises_with_available_keys():
    with pytest.raises(workflow_registry.WorkflowNotFoundError) as exc:
        workflow_registry.load_workflow("missing_workflow.json")
    assert exc.value.available_keys
    assert "ltx2_fp4_t2v_api.json" in exc.value.available_keys


def test_override_directory_takes_priority(_reset_override_dir: Path):
    override_path = _reset_override_dir / "ltx2_fp4_t2v_api.json"
    override_payload = {
        "_meta": {"capability": "video"},
        "999": {"class_type": "OverrideNode", "inputs": {}},
    }
    override_path.write_text(json.dumps(override_payload), encoding="utf-8")

    info = workflow_registry.resolve("ltx2_fp4_t2v_api.json")
    assert info.source == "override"
    assert info.path == override_path

    listed = {item["key"]: item for item in workflow_registry.list_workflows()}
    assert listed["ltx2_fp4_t2v_api.json"]["source"] == "override"

    loaded = workflow_registry.load_workflow("ltx2_fp4_t2v_api.json")
    assert loaded["999"]["class_type"] == "OverrideNode"
    assert "_meta" not in loaded


def test_load_workflow_template_alias():
    payload = workflow_registry.load_workflow_template("ltx2_fp4_i2v_api.json")
    assert isinstance(payload, dict)
    assert payload
