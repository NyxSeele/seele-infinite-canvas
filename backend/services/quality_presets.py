"""分镜表画风预设：prompt suffix 与画质增强 profile（与前端 scriptQualityPresets id 对齐）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EnhanceProfile = Literal["cinematic", "generic"]

CINEMATIC_POSITIVE_SUFFIX = (
    "photorealistic, cinematic photography, 35mm film, natural lighting, "
    "film grain, shallow depth of field, professional color grading, "
    "ultra detailed skin texture, realistic facial features, "
    "anamorphic lens, movie still"
)
CINEMATIC_NEGATIVE_SUFFIX = (
    "anime, cartoon, illustration, painting, drawing, 3d render, "
    "cgi, artificial, plastic skin, oversaturated, neon colors, "
    "watermark, signature, blurry, low quality, deformed face"
)

DOCUMENTARY_POSITIVE_SUFFIX = (
    "documentary photography, natural lighting, handheld camera feel, "
    "authentic skin texture, realistic environment, neutral color grading, "
    "subtle film grain, candid moment"
)
DOCUMENTARY_NEGATIVE_SUFFIX = (
    "anime, cartoon, illustration, cgi, oversaturated, artificial lighting, "
    "plastic skin, watermark, blurry, low quality"
)

COMMERCIAL_POSITIVE_SUFFIX = (
    "commercial advertising photography, clean studio lighting, high sharpness, "
    "vibrant but natural colors, crisp details, professional product shot quality"
)
COMMERCIAL_NEGATIVE_SUFFIX = (
    "grainy, muddy colors, low contrast, blurry, watermark, amateur, "
    "oversharpened halos, low quality"
)

RETRO_ATOMIC_POSITIVE_SUFFIX = (
    "1960s retro futurism, atompunk aesthetic, warm yellow and teal contrast, "
    "vintage film texture, desaturated retro sci-fi color grade"
)
RETRO_ATOMIC_NEGATIVE_SUFFIX = (
    "modern digital look, flat lighting, anime, cartoon, watermark, blurry"
)

DARK_DRAMA_POSITIVE_SUFFIX = (
    "low key lighting, high contrast, dramatic shadows, moody atmosphere, "
    "cinematic drama, chiaroscuro, emotional tension, film noir influence"
)
DARK_DRAMA_NEGATIVE_SUFFIX = (
    "flat lighting, overexposed, cheerful, cartoon, anime, watermark, blurry"
)

URBAN_NOIR_POSITIVE_SUFFIX = (
    "urban night scene, cool color temperature, neon reflections, "
    "rain-slick streets, cinematic cityscape, melancholic atmosphere, "
    "realistic urban photography"
)
URBAN_NOIR_NEGATIVE_SUFFIX = (
    "daylight, warm sunny, cartoon, anime, oversaturated, watermark, blurry"
)

VINTAGE_FILM_POSITIVE_SUFFIX = (
    "vintage film stock, faded colors, film grain, nostalgic tone, "
    "analog photography, soft contrast, retro color palette, 1970s cinema look"
)
VINTAGE_FILM_NEGATIVE_SUFFIX = (
    "digital sharpness, hdr, neon, cartoon, anime, watermark, blurry"
)


@dataclass(frozen=True)
class QualityPreset:
    id: str
    enhance_profile: EnhanceProfile
    positive_suffix: str = ""
    negative_suffix: str = ""


QUALITY_PRESETS: dict[str, QualityPreset] = {
    "auto": QualityPreset(id="auto", enhance_profile="generic"),
    "cinematic": QualityPreset(
        id="cinematic",
        enhance_profile="cinematic",
        positive_suffix=CINEMATIC_POSITIVE_SUFFIX,
        negative_suffix=CINEMATIC_NEGATIVE_SUFFIX,
    ),
    "documentary": QualityPreset(
        id="documentary",
        enhance_profile="cinematic",
        positive_suffix=DOCUMENTARY_POSITIVE_SUFFIX,
        negative_suffix=DOCUMENTARY_NEGATIVE_SUFFIX,
    ),
    "commercial": QualityPreset(
        id="commercial",
        enhance_profile="generic",
        positive_suffix=COMMERCIAL_POSITIVE_SUFFIX,
        negative_suffix=COMMERCIAL_NEGATIVE_SUFFIX,
    ),
    "anime": QualityPreset(id="anime", enhance_profile="generic"),
    "retro_atomic": QualityPreset(
        id="retro_atomic",
        enhance_profile="generic",
        positive_suffix=RETRO_ATOMIC_POSITIVE_SUFFIX,
        negative_suffix=RETRO_ATOMIC_NEGATIVE_SUFFIX,
    ),
    "dark_drama": QualityPreset(
        id="dark_drama",
        enhance_profile="cinematic",
        positive_suffix=DARK_DRAMA_POSITIVE_SUFFIX,
        negative_suffix=DARK_DRAMA_NEGATIVE_SUFFIX,
    ),
    "urban_noir": QualityPreset(
        id="urban_noir",
        enhance_profile="cinematic",
        positive_suffix=URBAN_NOIR_POSITIVE_SUFFIX,
        negative_suffix=URBAN_NOIR_NEGATIVE_SUFFIX,
    ),
    "vintage_film": QualityPreset(
        id="vintage_film",
        enhance_profile="cinematic",
        positive_suffix=VINTAGE_FILM_POSITIVE_SUFFIX,
        negative_suffix=VINTAGE_FILM_NEGATIVE_SUFFIX,
    ),
}

CINEMATIC_PRESET_IDS = frozenset(
    pid for pid, p in QUALITY_PRESETS.items() if p.enhance_profile == "cinematic"
)


def normalize_quality_preset_id(value: str | None) -> str:
    pid = (value or "auto").strip()
    if pid in QUALITY_PRESETS:
        return pid
    return "auto"


def get_quality_preset(preset_id: str | None) -> QualityPreset:
    return QUALITY_PRESETS[normalize_quality_preset_id(preset_id)]


def get_suffixes(preset_id: str | None) -> tuple[str, str]:
    """返回 (positive_suffix, negative_suffix)；auto 或无 suffix 时为空串。"""
    preset = get_quality_preset(preset_id)
    return preset.positive_suffix, preset.negative_suffix


def is_cinematic_enhance_preset(preset_id: str | None) -> bool:
    return get_quality_preset(preset_id).enhance_profile == "cinematic"


def migrate_content_style_to_preset(
    content_style: str | None,
    default_quality_preset_id: str | None,
) -> str:
    """旧 contentStyle 字段 → defaultQualityPresetId 兼容迁移。"""
    current = normalize_quality_preset_id(default_quality_preset_id)
    if current != "auto":
        return current
    cs = (content_style or "").strip()
    if cs == "generic":
        return "auto"
    if cs == "photorealistic_cinema" or not cs:
        return "cinematic"
    return current
