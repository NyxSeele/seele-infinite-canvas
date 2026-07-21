"""Velora pipeline manifest loader.

Load name convention:
  load_pipeline("velora_canvas") reads backend/pipelines/velora_canvas.yaml
  The YAML ``name`` field (e.g. velora_canvas_screenplay) is the logical pipeline id.

Skills (option 2):
  Each stage may declare ``skill: agent_skills/velora_canvas/<step>.md``
  relative to the backend root. Missing skill files raise PipelineManifestError.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PIPELINES_DIR = BACKEND_ROOT / "pipelines"

# Soft cap per skill file injected into the system prompt (chars).
SKILL_MAX_CHARS = 4096

REQUIRED_STAGE_FIELDS = (
    "name",
    "order",
    "phase",
    "optional",
    "preconditions",
    "produces",
    "prompt_label",
    "skill",
    "executor",
    "capabilities",
)

PHASE_TITLES = {
    "script_structure": "阶段一 — 剧本结构",
    "storyboard": "阶段二 — 分镜制作（分镜表就绪后，**按镜号单线程、一镜一步**）",
    "library": "设定库管理",
}

PHASE_SLIM_TITLES = {
    "script_structure": "阶段一 — 剧本结构",
    "storyboard": "阶段二 — 分镜制作（按镜号单线程、一镜一步）",
}


class PipelineManifestError(Exception):
    """Raised when a pipeline manifest cannot be loaded or validated."""


@dataclass(frozen=True)
class PipelineStage:
    name: str
    order: int
    phase: str
    optional: bool
    preconditions: tuple[str, ...]
    produces: tuple[str, ...]
    prompt_label: str
    skill: str
    executor: str
    capabilities: tuple[str, ...]
    ui_label: str = ""


@dataclass(frozen=True)
class PipelineManifest:
    name: str
    version: str
    description: str
    stages: tuple[PipelineStage, ...]
    shared_skill: str | None = None


def _resolve_skill_path(rel: str) -> Path:
    path = (BACKEND_ROOT / rel).resolve()
    if not str(path).startswith(str(BACKEND_ROOT.resolve())):
        raise PipelineManifestError(f"skill path escapes backend root: {rel}")
    return path


def _parse_stage(raw: dict[str, Any], index: int) -> PipelineStage:
    if not isinstance(raw, dict):
        raise PipelineManifestError(f"stages[{index}] must be a mapping")
    missing = [field for field in REQUIRED_STAGE_FIELDS if field not in raw]
    if missing:
        raise PipelineManifestError(
            f"stages[{index}] missing required fields: {', '.join(missing)}"
        )
    name = str(raw["name"]).strip()
    if not name:
        raise PipelineManifestError(f"stages[{index}].name must be non-empty")
    skill = str(raw["skill"]).strip()
    if not skill:
        raise PipelineManifestError(f"stages[{index}].skill must be non-empty")
    skill_path = _resolve_skill_path(skill)
    if not skill_path.is_file():
        raise PipelineManifestError(f"skill file not found: {skill}")
    executor = str(raw["executor"]).strip()
    if not executor:
        raise PipelineManifestError(f"stages[{index}].executor must be non-empty")
    capabilities = raw.get("capabilities") or []
    if not isinstance(capabilities, list) or not capabilities:
        raise PipelineManifestError(f"stages[{index}].capabilities must be a non-empty list")
    preconditions = raw.get("preconditions") or []
    produces = raw.get("produces") or []
    if not isinstance(preconditions, list) or not isinstance(produces, list):
        raise PipelineManifestError(f"stages[{index}] preconditions/produces must be lists")
    ui_label = str(raw.get("ui_label") or raw.get("prompt_label") or name).strip()
    return PipelineStage(
        name=name,
        order=int(raw["order"]),
        phase=str(raw["phase"]).strip(),
        optional=bool(raw["optional"]),
        preconditions=tuple(str(p) for p in preconditions),
        produces=tuple(str(p) for p in produces),
        prompt_label=str(raw["prompt_label"]).strip(),
        skill=skill,
        executor=executor,
        capabilities=tuple(str(c) for c in capabilities),
        ui_label=ui_label,
    )


def _validate_manifest(data: dict[str, Any]) -> PipelineManifest:
    if not isinstance(data, dict):
        raise PipelineManifestError("manifest root must be a mapping")
    for field in ("name", "version", "description", "stages"):
        if field not in data:
            raise PipelineManifestError(f"manifest missing required field: {field}")
    stages_raw = data["stages"]
    if not isinstance(stages_raw, list) or not stages_raw:
        raise PipelineManifestError("manifest stages must be a non-empty list")
    stages = [_parse_stage(item, idx) for idx, item in enumerate(stages_raw)]
    names = [stage.name for stage in stages]
    if len(names) != len(set(names)):
        raise PipelineManifestError("duplicate stage name in manifest")
    orders = [stage.order for stage in stages]
    if len(orders) != len(set(orders)):
        raise PipelineManifestError("duplicate stage order in manifest")

    shared_skill = data.get("shared_skill")
    shared_rel = str(shared_skill).strip() if shared_skill else None
    if shared_rel:
        shared_path = _resolve_skill_path(shared_rel)
        if not shared_path.is_file():
            raise PipelineManifestError(f"shared skill file not found: {shared_rel}")

    return PipelineManifest(
        name=str(data["name"]),
        version=str(data["version"]),
        description=str(data["description"]),
        stages=tuple(sorted(stages, key=lambda s: s.order)),
        shared_skill=shared_rel,
    )


def load_pipeline(name: str, pipelines_dir: Path | None = None) -> PipelineManifest:
    """Load ``backend/pipelines/{name}.yaml`` and validate structure + skill files."""
    root = pipelines_dir or PIPELINES_DIR
    path = root / f"{name}.yaml"
    if not path.is_file():
        raise PipelineManifestError(f"pipeline manifest not found: {path}")
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise PipelineManifestError(f"invalid YAML in {path}: {exc}") from exc
    if not data:
        raise PipelineManifestError(f"empty pipeline manifest: {path}")
    return _validate_manifest(data)


@lru_cache(maxsize=8)
def load_pipeline_cached(name: str) -> PipelineManifest:
    return load_pipeline(name)


def get_stage_order(manifest: PipelineManifest) -> list[str]:
    return [stage.name for stage in manifest.stages]


def get_stage_preconditions(manifest: PipelineManifest, step: str) -> list[str]:
    for stage in manifest.stages:
        if stage.name == step:
            return list(stage.preconditions)
    return []


def get_force_steps(manifest: PipelineManifest) -> frozenset[str]:
    return frozenset(stage.name for stage in manifest.stages if not stage.optional)


def get_all_steps(manifest: PipelineManifest) -> frozenset[str]:
    return frozenset(stage.name for stage in manifest.stages)


def is_known_step(manifest: PipelineManifest, step: str) -> bool:
    return step in get_all_steps(manifest)


def load_skill_text(rel_path: str, *, max_chars: int = SKILL_MAX_CHARS) -> str:
    """Load a skill markdown file; truncate soft-cap with an ellipsis marker."""
    path = _resolve_skill_path(rel_path)
    if not path.is_file():
        raise PipelineManifestError(f"skill file not found: {rel_path}")
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20].rstrip() + "\n\n…(skill truncated)"
    return text


def get_stage_skill(manifest: PipelineManifest, step: str) -> str | None:
    for stage in manifest.stages:
        if stage.name == step:
            return stage.skill
    return None


def build_skills_prompt_section(
    manifest: PipelineManifest,
    *,
    include_stages: bool = True,
    slim: bool = False,
) -> str:
    """Assemble markdown skills block for system prompt injection."""
    parts: list[str] = ["## Stage Skills（阶段执行指南）\n"]
    if manifest.shared_skill:
        parts.append(load_skill_text(manifest.shared_skill))
        parts.append("")
    if include_stages:
        for stage in manifest.stages:
            # Slim pipeline prompt: skip long library skills to save tokens.
            if slim and stage.phase == "library":
                continue
            parts.append(load_skill_text(stage.skill))
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _stage_display_name(stage: PipelineStage) -> str:
    if stage.optional and stage.phase == "storyboard":
        return f"{stage.name}（可选）"
    return stage.name


def _stages_for_phase(manifest: PipelineManifest, phase: str) -> list[PipelineStage]:
    return [stage for stage in manifest.stages if stage.phase == phase]


def _render_table_header(*, slim: bool) -> str:
    if slim:
        return "| 步骤 | step 值 |\n|------|---------|"
    return "| 步骤 | step 值 | 前置条件 |\n|------|---------|----------|"


def _render_stage_rows(stages: list[PipelineStage], *, slim: bool) -> list[str]:
    rows: list[str] = []
    for stage in stages:
        step_cell = _stage_display_name(stage) if slim else stage.name
        if slim:
            rows.append(f"| {stage.order} | {step_cell} |")
        else:
            rows.append(f"| {stage.order} | {step_cell} | {stage.prompt_label} |")
    return rows


def build_prompt_stage_table(manifest: PipelineManifest, *, slim: bool = False) -> str:
    """Build markdown stage tables for SYSTEM_PROMPT (full) or SYSTEM_PROMPT_PIPELINE (slim)."""
    titles = PHASE_SLIM_TITLES if slim else PHASE_TITLES
    sections: list[str] = []

    script_stages = _stages_for_phase(manifest, "script_structure")
    if script_stages:
        sections.append(f"### {titles['script_structure']}\n")
        sections.append(_render_table_header(slim=slim))
        sections.extend(_render_stage_rows(script_stages, slim=slim))

    storyboard_stages = _stages_for_phase(manifest, "storyboard")
    if storyboard_stages:
        sections.append(f"\n### {titles['storyboard']}\n")
        sections.append(_render_table_header(slim=slim))
        sections.extend(_render_stage_rows(storyboard_stages, slim=slim))
        if not slim:
            next_order = max(stage.order for stage in storyboard_stages) + 1
            sections.append(
                f"| {next_order} | 下一镜 | **仅当当前镜视频已完成**后，才进入下一镜出图 |"
            )
            sections.append(
                "\n**单画布单线程**：禁止同时推进多镜或多步骤；某镜分镜图/视频生成中必须等待（wait），禁止 multitask。"
            )
            sections.append("**禁止**在阶段二未完成时说「剧本链路已完成」！")

    if not slim:
        library_stages = _stages_for_phase(manifest, "library")
        if library_stages:
            sections.append(f"\n### {titles['library']}\n")
            sections.append(_render_table_header(slim=slim))
            sections.extend(_render_stage_rows(library_stages, slim=slim))

    if slim:
        sections.append(
            "\n当前镜视频完成前禁止下一镜；分镜图/视频生成中必须 wait，禁止 multitask。"
        )
        sections.append(
            "**禁止**用 create_node 手写 outline / script_table。大纲与分镜必须由 pipeline_step 调用后端。"
        )

    return "\n".join(sections)


def build_step_enum(manifest: PipelineManifest) -> str:
    return " | ".join(f'"{name}"' for name in get_stage_order(manifest))


def manifest_to_api_dict(manifest: PipelineManifest) -> dict[str, Any]:
    return {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "shared_skill": manifest.shared_skill,
        "stages": [
            {
                "name": stage.name,
                "order": stage.order,
                "phase": stage.phase,
                "optional": stage.optional,
                "skill": stage.skill,
                "executor": stage.executor,
                "capabilities": list(stage.capabilities),
                "ui_label": stage.ui_label,
                "preconditions": list(stage.preconditions),
                "produces": list(stage.produces),
                "prompt_label": stage.prompt_label,
            }
            for stage in manifest.stages
        ],
    }
