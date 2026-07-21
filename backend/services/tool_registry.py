"""Lightweight Velora tool registry (self-written; not OpenMontage code).

Maps pipeline steps → executor ids + capability envelopes for API/UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.pipeline_manifest import PipelineManifest, PipelineManifestError


@dataclass(frozen=True)
class ToolSpec:
    name: str
    executor: str
    capabilities: tuple[str, ...]
    optional: bool
    phase: str
    ui_label: str
    skill: str
    order: int = 0


class ToolRegistryError(Exception):
    """Unknown step or invalid registry state."""


def build_tool_registry(manifest: PipelineManifest) -> dict[str, ToolSpec]:
    registry: dict[str, ToolSpec] = {}
    for stage in manifest.stages:
        if not stage.executor:
            raise PipelineManifestError(f"stage {stage.name!r} missing executor")
        if not stage.capabilities:
            raise PipelineManifestError(f"stage {stage.name!r} missing capabilities")
        registry[stage.name] = ToolSpec(
            name=stage.name,
            executor=stage.executor,
            capabilities=tuple(stage.capabilities),
            optional=stage.optional,
            phase=stage.phase,
            ui_label=stage.ui_label or stage.prompt_label or stage.name,
            skill=stage.skill,
            order=stage.order,
        )
    return registry


def list_tools(manifest: PipelineManifest) -> list[dict[str, Any]]:
    registry = build_tool_registry(manifest)
    tools = sorted(registry.values(), key=lambda t: t.order)
    return [
        {
            "name": t.name,
            "executor": t.executor,
            "capabilities": list(t.capabilities),
            "optional": t.optional,
            "phase": t.phase,
            "ui_label": t.ui_label,
            "skill": t.skill,
            "order": t.order,
        }
        for t in tools
    ]


def get_tool(manifest: PipelineManifest, step: str) -> ToolSpec:
    registry = build_tool_registry(manifest)
    tool = registry.get(step)
    if tool is None:
        raise ToolRegistryError(f"unknown pipeline step: {step}")
    return tool


def support_envelope(manifest: PipelineManifest) -> dict[str, Any]:
    """Compact capability envelope for orchestrator / UI (not OM copy)."""
    registry = build_tool_registry(manifest)
    tools = sorted(registry.values(), key=lambda t: t.order)
    caps: set[str] = set()
    for tool in tools:
        caps.update(tool.capabilities)
    return {
        "pipeline": manifest.name,
        "steps": [t.name for t in tools],
        "optional_steps": [t.name for t in tools if t.optional],
        "capabilities_union": sorted(caps),
        "tools": list_tools(manifest),
    }
