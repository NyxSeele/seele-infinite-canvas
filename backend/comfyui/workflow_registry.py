"""ComfyUI workflow registry: scan builtin + override dirs, load by key."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Capability = Literal["image", "video", "tts", "other"]
Source = Literal["builtin", "override"]

_BUILTIN_DIR = Path(__file__).resolve().parent / "workflows"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OVERRIDE_DIR = _PROJECT_ROOT / "data" / "workflows"
_OVERRIDE_ENV = "VELORA_WORKFLOW_OVERRIDE_DIR"


@dataclass(frozen=True)
class WorkflowInfo:
    key: str
    path: Path
    source: Source
    capability: Capability


class WorkflowNotFoundError(KeyError):
    def __init__(self, key: str, available_keys: list[str]) -> None:
        self.key = key
        self.available_keys = available_keys
        preview = ", ".join(available_keys[:20])
        if len(available_keys) > 20:
            preview += ", ..."
        super().__init__(f"Workflow '{key}' not found. Available keys: {preview}")


def get_override_dir() -> Path:
    raw = (os.environ.get(_OVERRIDE_ENV) or "").strip()
    override_dir = Path(raw) if raw else _DEFAULT_OVERRIDE_DIR
    override_dir.mkdir(parents=True, exist_ok=True)
    return override_dir


def _normalize_key(relative_path: Path) -> str:
    return relative_path.as_posix()


def _scan_dir(root: Path, source: Source) -> dict[str, WorkflowInfo]:
    if not root.is_dir():
        return {}
    found: dict[str, WorkflowInfo] = {}
    for path in sorted(root.rglob("*.json")):
        if not path.is_file():
            continue
        key = _normalize_key(path.relative_to(root))
        found[key] = WorkflowInfo(
            key=key,
            path=path,
            source=source,
            capability=_infer_capability_from_name(key),
        )
    return found


def _infer_capability_from_name(key: str) -> Capability:
    name = key.lower()
    if "tts" in name:
        return "tts"
    if any(token in name for token in ("t2v", "i2v", "video", "ltx", "hunyuan")):
        return "video"
    if any(token in name for token in ("image", "flux", "pulid", "reactor")):
        return "image"
    return "other"


def _read_capability(path: Path, fallback: Capability) -> Capability:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(payload, dict):
        return fallback
    meta = payload.get("_meta")
    if not isinstance(meta, dict):
        return fallback
    raw = str(meta.get("capability") or "").strip().lower()
    if raw in ("image", "video", "tts", "other"):
        return raw  # type: ignore[return-value]
    return fallback


def _merge_workflows() -> dict[str, WorkflowInfo]:
    merged = _scan_dir(_BUILTIN_DIR, "builtin")
    merged.update(_scan_dir(get_override_dir(), "override"))
    enriched: dict[str, WorkflowInfo] = {}
    for key, info in merged.items():
        capability = _read_capability(info.path, info.capability)
        enriched[key] = WorkflowInfo(
            key=info.key,
            path=info.path,
            source=info.source,
            capability=capability,
        )
    return enriched


def list_workflows() -> list[dict[str, Any]]:
    workflows = sorted(_merge_workflows().values(), key=lambda item: item.key)
    return [
        {
            "key": item.key,
            "path": str(item.path),
            "source": item.source,
            "capability": item.capability,
        }
        for item in workflows
    ]


def resolve(key: str) -> WorkflowInfo:
    normalized = key.replace("\\", "/").lstrip("/")
    workflows = _merge_workflows()
    info = workflows.get(normalized)
    if info is None:
        raise WorkflowNotFoundError(normalized, sorted(workflows.keys()))
    return info


def _strip_meta(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("_meta", None)
    return cleaned


def load_workflow(key: str) -> dict[str, Any]:
    info = resolve(key)
    try:
        payload = json.loads(info.path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkflowNotFoundError(key, [item["key"] for item in list_workflows()]) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Workflow '{key}' must be a JSON object")
    return _strip_meta(payload)


def load_workflow_template(key: str) -> dict[str, Any]:
    """Public alias used by comfyui.client template loaders."""
    return load_workflow(key)
