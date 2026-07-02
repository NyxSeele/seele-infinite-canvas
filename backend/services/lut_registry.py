"""内置 LUT 预设注册表。"""

from __future__ import annotations

from pathlib import Path

LUT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "luts"

BUILTIN_LUT_PRESETS: dict[str, dict[str, str]] = {
    "cool_teal": {
        "name": "冷青电影",
        "filename": "cool_teal.cube",
        "description": "科幻/惊悚/都市",
    },
    "warm_orange_film": {
        "name": "暖橙胶片",
        "filename": "warm_orange_film.cube",
        "description": "剧情/年代/文艺",
    },
    "natural_realistic": {
        "name": "自然写实",
        "filename": "natural_realistic.cube",
        "description": "纪录片/现实主义",
    },
    "high_contrast_commercial": {
        "name": "高对比商业",
        "filename": "high_contrast_commercial.cube",
        "description": "动作/商业大片",
    },
    "vintage_fade": {
        "name": "复古褪色",
        "filename": "vintage_fade.cube",
        "description": "文艺/回忆/年代",
    },
    "none": {
        "name": "无调色",
        "filename": "",
        "description": "保持原始输出",
    },
}


def list_builtin_presets() -> list[dict[str, str]]:
    out = []
    for preset_id, meta in BUILTIN_LUT_PRESETS.items():
        out.append(
            {
                "id": preset_id,
                "name": meta["name"],
                "description": meta.get("description", ""),
            }
        )
    return out


def resolve_builtin_lut_path(preset_id: str | None) -> Path | None:
    pid = (preset_id or "").strip()
    if not pid or pid == "none":
        return None
    meta = BUILTIN_LUT_PRESETS.get(pid)
    if not meta or not meta.get("filename"):
        return None
    path = LUT_ASSETS_DIR / meta["filename"]
    return path if path.is_file() else None


def preset_display_name(preset_id: str | None) -> str:
    pid = (preset_id or "").strip()
    if not pid or pid == "none":
        return BUILTIN_LUT_PRESETS["none"]["name"]
    if pid == "custom":
        return "自定义 LUT"
    meta = BUILTIN_LUT_PRESETS.get(pid)
    return meta["name"] if meta else pid
