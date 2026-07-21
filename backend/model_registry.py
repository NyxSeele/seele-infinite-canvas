"""
model_registry.py
静态模型注册表 — 所有支持模型的元信息。

comfyui_model_file / LOCAL_MODEL_PRESETS.comfyui_file / COMFYUI_LOCAL_PROVIDERS：
  代码注册表为源；启动时 services.registered_model_sync 会 upsert 到 registered_models。
  当前值为社区常见命名占位符；GPU 服务器到位后须与 ComfyUI models/ 目录
  实际文件名核对并替换（见 backend/docs/COMFYUI_CUTOVER_RUNBOOK.md）。
  结构化 provider 见 COMFYUI_LOCAL_PROVIDERS（含 endpoint env、workflow 模块、checkpoint）。
  未确认前勿在 registered_models 中启用对应本地模型。
"""

# ── capabilities 预设 ─────────────────────────────────────────────────────
# 图像清晰度：产品侧统一 480 / 720 / 1080（内部带 P 后缀）
_IMAGE_QUALITY_TIERS = ("480P", "720P", "1080P")
_IMAGE_TIER_SHORT_SIDE = {
    "480P": 480,
    "720P": 720,
    "1080P": 1080,
    # 旧值兼容
    "2K": 720,
    "3K": 1080,
}
_COMMON_IMAGE_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4")


def _snap_dim(n: int, multiple: int = 8) -> int:
    return max(multiple, int(round(n / multiple) * multiple))


def _dims_from_ratio(ratio: str, short_side: int) -> tuple[int, int]:
    """按精确宽高比生成像素；短边≈short_side，并对齐到 8 的倍数。"""
    # 常见档位直接用标准像素，避免 snap 漂移（如 1080→1088）
    exact = {
        ("1:1", 480): (480, 480),
        ("1:1", 720): (720, 720),
        ("1:1", 1080): (1080, 1080),
        ("16:9", 480): (854, 480),
        ("16:9", 720): (1280, 720),
        ("16:9", 1080): (1920, 1080),
        ("9:16", 480): (480, 854),
        ("9:16", 720): (720, 1280),
        ("9:16", 1080): (1080, 1920),
        ("4:3", 480): (640, 480),
        ("4:3", 720): (960, 720),
        ("4:3", 1080): (1440, 1080),
        ("3:4", 480): (480, 640),
        ("3:4", 720): (720, 960),
        ("3:4", 1080): (1080, 1440),
    }
    key = (str(ratio), int(short_side))
    if key in exact:
        return exact[key]

    try:
        rw_s, rh_s = str(ratio).split(":", 1)
        rw, rh = float(rw_s), float(rh_s)
    except (TypeError, ValueError):
        rw, rh = 1.0, 1.0
    if rw <= 0 or rh <= 0:
        rw, rh = 1.0, 1.0
    if rw >= rh:
        h = float(short_side)
        w = h * rw / rh
    else:
        w = float(short_side)
        h = w * rh / rw
    return _snap_dim(w), _snap_dim(h)


def _recommended_for_ratios(ratios: tuple[str, ...] | list[str], short_side: int = 720) -> dict:
    return {r: list(_dims_from_ratio(r, short_side)) for r in ratios}


# 720P 基线（精确比例）；480/1080 由短边缩放推导
_RES_SDXL = _recommended_for_ratios(_COMMON_IMAGE_RATIOS, 720)
_RES_FLUX = _recommended_for_ratios(_COMMON_IMAGE_RATIOS, 720)
_RES_HIDREAM = _recommended_for_ratios(_COMMON_IMAGE_RATIOS, 720)
_RES_QWEN_IMAGE = _recommended_for_ratios(_COMMON_IMAGE_RATIOS, 720)


_CAP_SDXL = {
    "aspect_ratios": list(_COMMON_IMAGE_RATIOS),
    "resolutions": list(_IMAGE_QUALITY_TIERS),
    "recommended_resolutions": _RES_SDXL,
    "steps_range": [1, 50],
    "cfg_range": [1, 20],
}
_CAP_FLUX_DEV = {
    "aspect_ratios": list(_COMMON_IMAGE_RATIOS),
    "resolutions": list(_IMAGE_QUALITY_TIERS),
    "recommended_resolutions": _RES_FLUX,
    "steps_range": [1, 50],
    "cfg_range": None,
}
_CAP_FLUX_SCHNELL = {
    "aspect_ratios": list(_COMMON_IMAGE_RATIOS),
    "resolutions": list(_IMAGE_QUALITY_TIERS),
    "recommended_resolutions": _RES_FLUX,
    "steps_range": [1, 8],
    "cfg_range": None,
}
_CAP_HIDREAM = {
    "aspect_ratios": list(_COMMON_IMAGE_RATIOS),
    "resolutions": list(_IMAGE_QUALITY_TIERS),
    "recommended_resolutions": _RES_HIDREAM,
    "steps_range": [1, 50],
    "cfg_range": [1, 10],
}
_CAP_QWEN_IMAGE = {
    "aspect_ratios": list(_COMMON_IMAGE_RATIOS),
    "resolutions": list(_IMAGE_QUALITY_TIERS),
    "recommended_resolutions": _RES_QWEN_IMAGE,
    "steps_range": [1, 8],
    "cfg_range": [1, 2],
}
_CAP_JIMENG = {
    "aspect_ratios": list(_COMMON_IMAGE_RATIOS),
    "resolutions": list(_IMAGE_QUALITY_TIERS),
    "recommended_resolutions": _RES_FLUX,
    "steps_range": None,
    "cfg_range": None,
}
# ── generation 预设（workflow_type / generation_defaults 等）────────────────
# 内部仍保留 sd15 workflow_type 供 comfyui provider 兼容旧 checkpoint；无产品模型入口
_GEN_SD15 = {
    "workflow_type": "sd15",
    "generation_defaults": {
        "steps": 20,
        "cfg": 7.0,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras",
        "denoise_txt2img": 1.0,
        "denoise_img2img": 0.5,
    },
    "img2img_support": "native",
    "native_resolution": 512,
    "max_resolution": 768,
    "negative_prompt": True,
}
_GEN_SDXL = {
    "workflow_type": "sdxl",
    "generation_defaults": {
        "steps": 25,
        "cfg": 7.0,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras",
        "denoise_txt2img": 1.0,
        "denoise_img2img": 0.6,
    },
    "img2img_support": "native",
    "native_resolution": 1024,
    "max_resolution": 1536,
    "negative_prompt": True,
}
_GEN_FLUX_DEV = {
    "workflow_type": "flux",
    "generation_defaults": {
        "steps": 25,
        "cfg": 3.5,
        "sampler_name": "euler",
        "scheduler": "simple",
        "denoise_txt2img": 1.0,
        "denoise_img2img": None,
    },
    "img2img_support": "unsupported",
    "native_resolution": 1024,
    "max_resolution": 2048,
    "negative_prompt": False,
}
_GEN_FLUX_SCHNELL = {
    "workflow_type": "flux",
    "generation_defaults": {
        "steps": 4,
        "cfg": 1.0,
        "sampler_name": "euler",
        "scheduler": "simple",
        "denoise_txt2img": 1.0,
        "denoise_img2img": None,
    },
    "img2img_support": "unsupported",
    "native_resolution": 1024,
    "max_resolution": 2048,
    "negative_prompt": False,
}
_GEN_FLUX_PULID = {
    "workflow_type": "flux_pulid",
    "generation_defaults": {
        "steps": 20,
        "cfg": 3.5,
        "sampler_name": "euler",
        "scheduler": "simple",
        "pulid_weight": 0.8,
        "denoise_txt2img": 1.0,
        "denoise_img2img": None,
    },
    "img2img_support": "pulid",
    "native_resolution": 1024,
    "max_resolution": 2048,
    "negative_prompt": False,
}
_GEN_HIDREAM = {
    "workflow_type": "hidream",
    "generation_defaults": {
        "steps": 28,
        "cfg": 1.0,
        "sampler_name": "lcm",
        "scheduler": "simple",
        "shift": 6.0,
        "denoise_txt2img": 1.0,
        "denoise_img2img": None,
    },
    "img2img_support": "unsupported",
    "native_resolution": 1024,
    "max_resolution": 1280,
    "negative_prompt": False,
}
_GEN_QWEN_IMAGE = {
    "workflow_type": "qwen-image",
    "generation_defaults": {
        "steps": 4,
        "cfg": 1.0,
        "sampler_name": "euler",
        "scheduler": "simple",
        "aura_shift": 3.1,
        "denoise_txt2img": 1.0,
        "denoise_img2img": None,
    },
    "img2img_support": "unsupported",
    "native_resolution": 1328,
    "max_resolution": 2048,
    "negative_prompt": False,
}
_GEN_QWEN_IMAGE_EDIT = {
    "workflow_type": "qwen-image-edit",
    "generation_defaults": {
        "steps": 4,
        "cfg": 1.0,
        "sampler_name": "euler",
        "scheduler": "simple",
        "aura_shift": 3.1,
        "denoise_txt2img": 1.0,
        "denoise_img2img": 1.0,
        "megapixels": 1.0,
    },
    "img2img_support": "required",
    "native_resolution": 1024,
    "max_resolution": 2048,
    "negative_prompt": False,
}
_GEN_QWEN_IMAGE_RESTORE = {
    **_GEN_QWEN_IMAGE_EDIT,
    "workflow_type": "qwen-image-restore",
    "generation_defaults": {
        **_GEN_QWEN_IMAGE_EDIT["generation_defaults"],
        "megapixels": 1.2,
    },
}
_GEN_QWEN_IMAGE_MATERIAL = {
    **_GEN_QWEN_IMAGE_EDIT,
    "workflow_type": "qwen-image-material",
}

_CAP_WAN = {
    "aspect_ratios": ["16:9", "9:16", "1:1"],
    "durations": [3, 5, 10, 15],
    # 5090 32GB 上 Wan 原生 1080P 易 OOM，产品侧仅开放 480P/720P
    "resolutions": ["480P", "720P"],
    "supports_audio": False,
}
_CAP_LTX = {
    "aspect_ratios": ["16:9", "9:16"],
    "durations": [5, 10, 15],
    "resolutions": ["480P", "720P", "1080P"],
    "supports_audio": False,
}
_CAP_LTX2 = {
    "aspect_ratios": ["16:9", "9:16"],
    "durations": [5, 10, 15],
    "resolutions": ["480P", "720P", "1080P"],
    "supports_audio": True,
    "supports_image2video": True,
}
_CAP_LTX23 = {
    "aspect_ratios": ["16:9", "9:16"],
    "durations": [5, 10, 15],
    "resolutions": ["480P", "720P", "1080P"],
    "supports_audio": True,
    "supports_image2video": True,
}
_CAP_VIDEO_ENHANCE = {
    "upscale_factors": [1.0, 1.5, 2.0, 3.0],
    "strengths": ["normal", "sharp"],
}

VIDEO_ENHANCE_SEEDVR2_ID = "video-enhance-seedvr2"
VIDEO_ENHANCE_REALESRGAN_ID = "video-enhance-realesrgan"
IMAGE_ENHANCE_SEEDVR2_ID = "image-enhance-seedvr2"

ALL_MODELS: list[dict] = [
    # ── 文本生成 ──────────────────────────────────────────────────────────
    {
        "id": "qwen-turbo",
        "name": "千问 Turbo",
        "category": "text",
        "type": "api",
        "api_key_env": "DASHSCOPE_API_KEY",
        "provider": "qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_enabled": False,
        "summary": "对话与剧本扩写（更快）",
    },
    {
        "id": "qwen-plus",
        "name": "千问 Plus",
        "category": "text",
        "type": "api",
        "api_key_env": "DASHSCOPE_API_KEY",
        "provider": "qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_enabled": False,
        "summary": "对话与剧本扩写（推荐）",
    },
    {
        "id": "qwen-max",
        "name": "千问 Max",
        "category": "text",
        "type": "api",
        "api_key_env": "DASHSCOPE_API_KEY",
        "provider": "qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_enabled": False,
        "summary": "对话与剧本扩写（更强）",
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "category": "text",
        "type": "api",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
        "default_enabled": False,
        "summary": "对话与剧本扩写",
    },
    {
        "id": "claude-sonnet-4",
        "name": "Claude Sonnet 4",
        "category": "text",
        "type": "api",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "default_enabled": False,
        "summary": "对话与剧本扩写",
    },
    {
        "id": "claude-opus-4",
        "name": "Claude Opus 4",
        "category": "text",
        "type": "api",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "default_enabled": False,
        "summary": "对话与剧本扩写",
    },
    # ── 图像生成 ──────────────────────────────────────────────────────────
    {
        "id": "sdxl",
        "name": "SDXL",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "sd_xl_base_1.0.safetensors",  # 占位；服务器确认后替换
        "default_enabled": False,
        "capabilities": _CAP_SDXL,
        "summary": "经典文生图",
        **_GEN_SDXL,
    },
    {
        "id": "flux-pulid",
        "name": "Flux + PuLID 人物一致性",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "svdq-fp4_r32-flux.1-dev.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_FLUX_DEV,
        "summary": "让角色长相保持一致",
        **_GEN_FLUX_PULID,
    },
    {
        "id": "hidream",
        "name": "HiDream",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "hidream_i1_dev_fp8.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_HIDREAM,
        "summary": "另一种画面风格",
        **_GEN_HIDREAM,
    },
    {
        "id": "qwen-image",
        "name": "Qwen-Image",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "svdq-fp4_r128-qwen-image-lightningv1.0-4steps.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_QWEN_IMAGE,
        "summary": "输入文字，生成图片",
        **_GEN_QWEN_IMAGE,
    },
    {
        "id": "qwen-image-edit",
        "name": "Qwen-Image Edit",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "qwen_image_edit_2511_fp8mixed.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_QWEN_IMAGE,
        "summary": "上传图片，按描述修改",
        **_GEN_QWEN_IMAGE_EDIT,
    },
    {
        "id": "qwen-image-restore",
        "name": "Qwen-Image Restore",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "qwen_image_edit_2511_fp8mixed.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_QWEN_IMAGE,
        "summary": "修复老旧模糊的照片",
        **_GEN_QWEN_IMAGE_RESTORE,
    },
    {
        "id": "qwen-image-material",
        "name": "Qwen-Image Material",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "qwen_image_edit_2511_fp8mixed.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_QWEN_IMAGE,
        "summary": "把画面材质换成另一张图",
        **_GEN_QWEN_IMAGE_MATERIAL,
    },
    {
        "id": "jimeng-5.0-lite",
        "name": "即梦 5.0 Lite",
        "category": "image",
        "type": "api",
        "api_key_env": "JIMENG_API_KEY",
        "provider": "jimeng",
        "default_enabled": False,
        "capabilities": _CAP_JIMENG,
        "summary": "云端出图",
    },
    # ── 视频生成 ──────────────────────────────────────────────────────────
    {
        "id": "wan-2.6",
        "name": "Wan 2.6",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_WAN,
        "workflow_type": "wan",
        "video_backend": "wan",
        "summary": "只用文字生成视频",
    },
    {
        "id": "wan-i2v",
        "name": "Wan 2.6 I2V",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        "default_enabled": False,
        "capabilities": _CAP_WAN,
        "workflow_type": "wan",
        "video_backend": "wan",
        "summary": "首尾两张图生成过渡视频",
    },
    {
        "id": "wan-fun-inpaint",
        "name": "Wan Fun Inpaint",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_WAN,
        "workflow_type": "wan",
        "video_backend": "wan",
        "summary": "首尾帧专用",
    },
    {
        "id": "ltx-video",
        "name": "LTX Video",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "ltx-video-2b-v0.9.5.safetensors",
        "default_enabled": False,
        "capabilities": _CAP_LTX,
        "workflow_type": "ltx",
        "video_backend": "ltx",
        "summary": "轻量文生视频",
    },
    {
        "id": "ltx2-fp4",
        "name": "LTX-2 fp4",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "ltx-2-19b-dev-fp4.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_LTX2,
        "workflow_type": "ltx2",
        "video_backend": "ltx2",
        "summary": "文字或图片都能生成视频",
    },
    {
        "id": "ltx23-i2av",
        "name": "LTX-2.3 I2AV",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors",
        "default_enabled": True,
        "capabilities": _CAP_LTX23,
        "workflow_type": "ltx23-i2av",
        "video_backend": "ltx23",
        "img2img_support": "required",
        "summary": "生成带声音的视频",
    },
    {
        "id": "seedance-2.0",
        "name": "Seedance 2.0",
        "category": "video",
        "type": "api",
        "api_key_env": "SEEDANCE_API_KEY",
        "provider": "seedance",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "default_enabled": False,
        "capabilities": {
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "durations": [5, 10, 15],
            "resolutions": ["480P", "720P", "1080P"],
            "supports_audio": False,
        },
        "video_backend": "seedance",
        "summary": "云端生成视频",
    },
]

MODEL_MAP: dict[str, dict] = {m["id"]: m for m in ALL_MODELS}

# 用户向简述 + 推荐星标（画布模型选择器 SSOT）
MODEL_CATALOG: dict[str, dict] = {
    # ── 图像 ──
    "qwen-image": {
        "summary": "输入文字，生成图片",
        "recommended": True,
        "sort_rank": 10,
    },
    "qwen-image-edit": {
        "summary": "上传图片，按描述修改",
        "sort_rank": 20,
    },
    "hidream": {
        "summary": "另一种画面风格",
        "sort_rank": 30,
    },
    "flux-pulid": {
        "summary": "让角色长相保持一致",
        "recommended": True,
        "sort_rank": 25,
    },
    "qwen-image-restore": {
        "summary": "修复老旧模糊的照片",
        "sort_rank": 60,
    },
    "qwen-image-material": {
        "summary": "把画面材质换成另一张图",
        "sort_rank": 70,
    },
    "sdxl": {
        "summary": "经典文生图",
        "sort_rank": 90,
    },
    "jimeng-5.0-lite": {
        "summary": "云端出图",
        "sort_rank": 100,
    },
    # ── 视频 ──
    "ltx2-fp4": {
        "summary": "开源文/图生视频（实验向）；人物戏请用参考图，默认关音频",
        "recommended_modes": ["i2v", "t2v"],
        "sort_rank": 40,
    },
    "wan-i2v": {
        "summary": "首尾两张图生成过渡视频（推荐图生）",
        "recommended": True,
        "recommended_modes": ["keyframe"],
        "sort_rank": 15,
    },
    "wan-2.6": {
        "summary": "只用文字生成视频",
        "recommended": True,
        "recommended_modes": ["t2v"],
        "sort_rank": 10,
    },
    "ltx23-i2av": {
        "summary": "生成带声音的视频",
        "sort_rank": 35,
    },
    "wan-fun-inpaint": {
        "summary": "首尾帧专用",
        "sort_rank": 45,
    },
    "ltx-video": {
        "summary": "轻量文生视频",
        "sort_rank": 90,
    },
    "seedance-2.0": {
        "summary": "云端生成视频",
        "sort_rank": 100,
    },
    # ── 文本（画布扩写） ──
    "qwen-plus": {
        "summary": "写作与剧本扩写",
        "recommended": True,
        "sort_rank": 10,
    },
    "qwen-turbo": {
        "summary": "写作扩写，回复更快",
        "sort_rank": 20,
    },
    "qwen-max": {
        "summary": "写作扩写，效果更好",
        "sort_rank": 30,
    },
}

_CATALOG_KEYS = frozenset({"summary", "recommended", "recommended_modes", "sort_rank"})


def get_model_catalog_meta(model_id: str) -> dict:
    """返回用户向 catalog 字段；summary 可回退 MODEL_MAP / provider。"""
    key = (model_id or "").strip()
    meta = dict(MODEL_CATALOG.get(key) or {})
    if not meta.get("summary"):
        entry = MODEL_MAP.get(key) or COMFYUI_PROVIDER_MAP.get(key) or {}
        summary = (entry.get("summary") or "").strip()
        if summary:
            meta["summary"] = summary
    meta.setdefault("recommended", False)
    meta.setdefault("recommended_modes", [])
    meta.setdefault("sort_rank", 100)
    return meta


def _apply_catalog_to_entry(entry: dict) -> None:
    cat = MODEL_CATALOG.get(entry.get("id") or "")
    if not cat:
        return
    for k in _CATALOG_KEYS:
        if k in cat:
            entry[k] = cat[k]


for _m in ALL_MODELS:
    _apply_catalog_to_entry(_m)

# Admin 写入的 MaaS 文本模型不在 ALL_MODELS；仅补用户可见 summary
MODEL_SUMMARY_OVERRIDES: dict[str, str] = {
    "glm-5-1": "对话与剧本扩写",
    "qwen3-6-27b": "对话与剧本扩写",
    "qwen3-6-35b-a3b": "对话与剧本扩写",
    "qwen3-6-flash": "对话与剧本扩写（更快）",
    "qwen3-6-flash-2026-04-16": "对话与剧本扩写（更快）",
}

# 无 recommended_resolutions 时的 quality 缩放回退（2K / 3K）
_FALLBACK_2K: dict[str, tuple[int, int]] = {
    "1:1": (2048, 2048),
    "4:3": (2560, 1920),
    "3:4": (1920, 2560),
    "16:9": (2730, 1536),
    "9:16": (1536, 2730),
    "3:2": (2730, 1820),
    "2:3": (1820, 2730),
    "21:9": (3072, 1318),
}
_FALLBACK_CANVAS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
}


def _lookup_model_entry(model_id: str) -> dict | None:
    key = (model_id or "").strip()
    if not key:
        return None
    return MODEL_MAP.get(key) or MODEL_MAP.get(key.lower())


def _match_comfyui_filename(preset_file: str, actual_file: str) -> bool:
    """与 local_model_sync 一致：按去掉扩展名后的前缀模糊匹配。"""
    if not preset_file or not actual_file:
        return False
    base_name = preset_file.rsplit(".", 1)[0]
    return base_name in actual_file


def _infer_profile_by_filename(comfyui_filename: str) -> dict | None:
    """按 checkpoint 文件名推断 generation 配置。"""
    name = (comfyui_filename or "").strip().lower()
    if not name:
        return None
    if "qwen_image_edit" in name or "qwen-image-edit" in name:
        return dict(_GEN_QWEN_IMAGE_EDIT)
    if "qwen-image" in name or "qwen_image" in name or "nunchaku-qwen" in name:
        return dict(_GEN_QWEN_IMAGE)
    if "flux1-schnell" in name or "flux-schnell" in name:
        return dict(_GEN_FLUX_SCHNELL)
    if "flux1-dev" in name or "flux-dev" in name:
        return dict(_GEN_FLUX_DEV)
    if "svdq-int4" in name or "svdq-fp4" in name or "flux-pulid" in name:
        return dict(_GEN_FLUX_PULID)
    if "hidream" in name:
        return dict(_GEN_HIDREAM)
    if "sd_xl" in name or "sdxl" in name or "juggernaut" in name or "dreamshaper" in name:
        return dict(_GEN_SDXL)
    # SD 1.5 产品入口已移除；遗留权重若出现则按内部 sd15 workflow 处理（无 registry id）
    if "v1-5" in name or "sd15" in name or "stable-diffusion-v1" in name:
        return dict(_GEN_SD15)
    for preset in LOCAL_MODEL_PRESETS:
        preset_file = preset.get("comfyui_file") or ""
        if _match_comfyui_filename(preset_file, comfyui_filename):
            return {
                k: v
                for k, v in preset.items()
                if k
                in (
                    "workflow_type",
                    "generation_defaults",
                    "img2img_support",
                    "native_resolution",
                    "max_resolution",
                    "negative_prompt",
                )
            }
    return None


def resolve_video_backend(model_id: str | None = None) -> str:
    """解析视频模型分派后端：wan / ltx / ltx2 / seedance（默认 ltx）。"""
    entry = _lookup_model_entry(model_id or "")
    if entry:
        backend = (entry.get("video_backend") or entry.get("workflow_type") or "").strip().lower()
        if backend in ("wan", "ltx", "ltx2", "ltx23", "seedance"):
            return backend
    return "ltx"


def resolve_generation_profile(
    model_id: str | None = None,
    comfyui_filename: str | None = None,
) -> dict:
    """
    解析模型的 workflow_type / generation_defaults 等。
    优先 model_id，其次按 comfyui checkpoint 文件名匹配。
    未匹配时回退 Flux Dev 预设。
    """
    entry = _lookup_model_entry(model_id or "")
    if entry and entry.get("workflow_type"):
        return {
            "workflow_type": entry.get("workflow_type"),
            "generation_defaults": dict(entry.get("generation_defaults") or {}),
            "img2img_support": entry.get("img2img_support", "native"),
            "native_resolution": entry.get("native_resolution"),
            "max_resolution": entry.get("max_resolution"),
            "negative_prompt": entry.get("negative_prompt", True),
        }
    inferred = _infer_profile_by_filename(comfyui_filename or "")
    if inferred:
        defaults = inferred.get("generation_defaults") or {}
        return {
            "workflow_type": inferred.get("workflow_type", "flux"),
            "generation_defaults": dict(defaults),
            "img2img_support": inferred.get("img2img_support", "native"),
            "native_resolution": inferred.get("native_resolution"),
            "max_resolution": inferred.get("max_resolution"),
            "negative_prompt": inferred.get("negative_prompt", True),
        }
    return {
        "workflow_type": "flux",
        "generation_defaults": dict(_GEN_FLUX_DEV["generation_defaults"]),
        "img2img_support": _GEN_FLUX_DEV["img2img_support"],
        "native_resolution": _GEN_FLUX_DEV["native_resolution"],
        "max_resolution": _GEN_FLUX_DEV["max_resolution"],
        "negative_prompt": _GEN_FLUX_DEV["negative_prompt"],
    }


def _parse_wxh(value: str | None) -> tuple[int, int] | None:
    """解析 '1344x768' / '1344×768' 为宽高。"""
    if not value:
        return None
    text = str(value).strip().lower().replace("×", "x")
    if "x" not in text:
        return None
    left, _, right = text.partition("x")
    try:
        w, h = int(left.strip()), int(right.strip())
    except ValueError:
        return None
    if w < 64 or h < 64 or w > 4096 or h > 4096:
        return None
    return w, h


def _normalize_image_quality(quality: str | None) -> str:
    """归一化图像清晰度：480P / 720P / 1080P。"""
    raw = str(quality or "720P").strip().upper().replace(" ", "")
    if raw in ("480", "720", "1080"):
        raw = f"{raw}P"
    if raw in _IMAGE_TIER_SHORT_SIDE:
        # 2K/3K 映射到短边档位
        if raw == "2K":
            return "720P"
        if raw == "3K":
            return "1080P"
        return raw if raw.endswith("P") else f"{raw}P"
    if _parse_wxh(raw):
        return "720P"
    return "720P"


def resolve_image_dimensions_for_model(
    model_id: str,
    ratio: str,
    quality: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> tuple[int, int]:
    """按模型 capabilities 解析画布图像宽高。

    优先级：显式 width/height > quality 中的 WxH >
    清晰度档位(480/720/1080)×比例 > recommended_resolutions 回退。
    """
    entry = _lookup_model_entry(model_id)
    caps = (entry or {}).get("capabilities") or {}
    rec = caps.get("recommended_resolutions") or {}
    allowed_ratios = caps.get("aspect_ratios") or list(rec.keys()) or list(_COMMON_IMAGE_RATIOS)

    if width is not None and height is not None:
        w, h = int(width), int(height)
        if w < 64 or h < 64 or w > 4096 or h > 4096:
            raise ValueError(f"宽高超出范围: {w}x{h}")
        return w, h

    parsed = _parse_wxh(quality)
    if parsed:
        return parsed

    if allowed_ratios and ratio not in allowed_ratios and ratio not in rec:
        raise ValueError(f"模型不支持宽高比: {ratio}（model={model_id}）")

    q = _normalize_image_quality(quality)
    short = _IMAGE_TIER_SHORT_SIDE.get(q, 720)
    # 优先按精确比例 + 清晰度短边计算（避免旧表比例漂移）
    if ratio in allowed_ratios or ratio in rec or ratio in _FALLBACK_CANVAS:
        return _dims_from_ratio(ratio, short)

    if ratio in rec:
        pair = rec[ratio]
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            base_w, base_h = int(pair[0]), int(pair[1])
            base_short = min(base_w, base_h) or 720
            scale = short / base_short
            return _snap_dim(base_w * scale), _snap_dim(base_h * scale)

    base = _FALLBACK_2K.get(ratio) or _FALLBACK_CANVAS.get(ratio)
    if base:
        return _dims_from_ratio(ratio, short)
    raise ValueError(f"不支持的宽高比: {ratio}（model={model_id}, quality={q}）")


def get_video_allowed_resolutions(model_id: str) -> list[str]:
    """返回视频模型允许的清晰度标签（如 720P）。"""
    entry = _lookup_model_entry(model_id)
    caps = (entry or {}).get("capabilities") or {}
    raw = caps.get("resolutions") or ["720P", "1080P"]
    return [str(x).upper() for x in raw]


def _comfyui_local_provider(
    *,
    id: str,
    display_name: str,
    category: str,
    comfyui_checkpoint: str,
    workflow_type: str,
    workflow_module: str,
    workflow_builder: str,
    workflow_impl: str,
    capabilities: dict,
    gen_preset: dict | None = None,
    companion_files: dict[str, str] | None = None,
    notes: str = "",
    summary: str = "",
    recommended: bool = False,
    recommended_modes: list[str] | None = None,
    sort_rank: int = 100,
    enabled: bool = False,
) -> dict:
    """
    真实 ComfyUI 本地 provider 结构化条目（默认 enabled=False）。
    服务器到位当天：核对 comfyui_checkpoint / companion_files → registered_models.enabled=true。
    endpoint 统一读 COMFYUI_URL，workflow 在代码中动态构建（无独立 JSON 模板路径）。
    """
    entry: dict = {
        "id": id,
        "display_name": display_name,
        "category": category,
        "type": "local",
        "provider": "comfyui",
        "enabled": enabled,
        "comfyui_endpoint_env": "COMFYUI_URL",
        "comfyui_checkpoint": comfyui_checkpoint,
        "comfyui_file": comfyui_checkpoint,
        "workflow_type": workflow_type,
        "workflow_module": workflow_module,
        "workflow_builder": workflow_builder,
        "workflow_impl": workflow_impl,
        "capabilities": capabilities,
    }
    if gen_preset:
        entry.update(gen_preset)
    if companion_files:
        entry["companion_files"] = companion_files
    if notes:
        entry["notes"] = notes
    if summary:
        entry["summary"] = summary
    if recommended:
        entry["recommended"] = True
    if recommended_modes:
        entry["recommended_modes"] = list(recommended_modes)
    if sort_rank != 100:
        entry["sort_rank"] = sort_rank
    _apply_catalog_to_entry(entry)
    return entry


# 真实 ComfyUI provider 注册表 — 切换日只改 checkpoint/伴随文件名 + enabled，无需改代码结构
COMFYUI_LOCAL_PROVIDERS: list[dict] = [
    _comfyui_local_provider(
        id="sdxl",
        display_name="SDXL",
        category="image",
        comfyui_checkpoint="sd_xl_base_1.0.safetensors",
        workflow_type="sdxl",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_workflow",
        workflow_impl="ready",
        capabilities=_CAP_SDXL,
        gen_preset=_GEN_SDXL,
        notes="图像 workflow 早期已实现（KSampler + CheckpointLoader）",
        summary="经典文生图",
    ),
    _comfyui_local_provider(
        id="flux-pulid",
        display_name="Flux + PuLID",
        category="image",
        comfyui_checkpoint="svdq-fp4_r32-flux.1-dev.safetensors",
        workflow_type="flux_pulid",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_flux_pulid_workflow",
        workflow_impl="ready",
        capabilities=_CAP_FLUX_DEV,
        gen_preset=_GEN_FLUX_PULID,
        companion_files={
            "dit": "svdq-fp4_r32-flux.1-dev.safetensors",
            "pulid": "pulid_flux_v0.9.1.safetensors",
            "eva_clip": "EVA02_CLIP_L_336_psz14_s6B.pt",
            "clip_l": "clip_l.safetensors",
            "clip_t5": "t5xxl_fp16.safetensors",
            "vae": "ae.safetensors",
        },
        notes="Nunchaku int4 FLUX + PuLID 人物一致性；需正脸参考图",
        summary="让角色长相保持一致",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="hidream",
        display_name="HiDream",
        category="image",
        comfyui_checkpoint="hidream_i1_dev_fp8.safetensors",
        workflow_type="hidream",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_hidream_workflow",
        workflow_impl="ready",
        capabilities=_CAP_HIDREAM,
        gen_preset=_GEN_HIDREAM,
        companion_files={
            "clip_l": "clip_l_hidream.safetensors",
            "clip_g": "clip_g_hidream.safetensors",
            "clip_t5": "t5xxl_fp8_e4m3fn_scaled.safetensors",
            "clip_llama": "llama_3.1_8b_instruct_fp8_scaled.safetensors",
            "vae": "ae.safetensors",
        },
        notes="2026-07-07 对齐 Comfy-Org/HiDream-I1_ComfyUI dev fp8 + 云绘工作流采样参数",
        summary="另一种画面风格",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="qwen-image",
        display_name="Qwen-Image",
        category="image",
        comfyui_checkpoint="svdq-fp4_r128-qwen-image-lightningv1.0-4steps.safetensors",
        workflow_type="qwen-image",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_qwen_image_workflow",
        workflow_impl="ready",
        capabilities=_CAP_QWEN_IMAGE,
        gen_preset=_GEN_QWEN_IMAGE,
        companion_files={
            "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "vae": "qwen_image_vae.safetensors",
        },
        notes="云绘双截棍 Qwen-Image fp4；Nunchaku DiT + Lightning 4步；无负向提示词",
        summary="输入文字，生成图片",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="qwen-image-edit",
        display_name="Qwen-Image Edit",
        category="image",
        comfyui_checkpoint="qwen_image_edit_2511_fp8mixed.safetensors",
        workflow_type="qwen-image-edit",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_qwen_image_edit_workflow",
        workflow_impl="ready",
        capabilities=_CAP_QWEN_IMAGE,
        gen_preset=_GEN_QWEN_IMAGE_EDIT,
        companion_files={
            "dit": "qwen_image_edit_2511_fp8mixed.safetensors",
            "lora_angles": "qwen-image-edit-2511-multiple-angles-lora.safetensors",
            "lora_lightning": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "vae": "qwen_image_vae.safetensors",
        },
        notes="Qwen-Image-Edit 2511；UNET+Lightning LoRA+TextEncodeQwenImageEditPlus；需参考图",
        summary="上传图片，按描述修改",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="qwen-image-restore",
        display_name="Qwen-Image Restore",
        category="image",
        comfyui_checkpoint="qwen_image_edit_2511_fp8mixed.safetensors",
        workflow_type="qwen-image-restore",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_qwen_image_restore_workflow",
        workflow_impl="ready",
        capabilities=_CAP_QWEN_IMAGE,
        gen_preset=_GEN_QWEN_IMAGE_RESTORE,
        companion_files={
            "dit": "qwen_image_edit_2511_fp8mixed.safetensors",
            "lora_angles": "qwen-image-edit-2511-multiple-angles-lora.safetensors",
            "lora_lightning": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "vae": "qwen_image_vae.safetensors",
        },
        notes="老照片修复；UNET+多角度 LoRA+Lightning LoRA；单图输入",
        summary="修复老旧模糊的照片",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="qwen-image-material",
        display_name="Qwen-Image Material",
        category="image",
        comfyui_checkpoint="qwen_image_edit_2511_fp8mixed.safetensors",
        workflow_type="qwen-image-material",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_qwen_image_material_workflow",
        workflow_impl="ready",
        capabilities=_CAP_QWEN_IMAGE,
        gen_preset=_GEN_QWEN_IMAGE_MATERIAL,
        companion_files={
            "dit": "qwen_image_edit_2511_fp8mixed.safetensors",
            "lora_lightning": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "vae": "qwen_image_vae.safetensors",
        },
        notes="材质替换；主图+材质参考图（可选第三张）；Lightning 4步",
        summary="把画面材质换成另一张图",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="wan-2.6",
        display_name="Wan 2.6",
        category="video",
        comfyui_checkpoint="wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
        workflow_type="wan",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_wan_video_prompt",
        workflow_impl="ready",
        capabilities=_CAP_WAN,
        notes="Wan 2.2 T2V 四步；双 UNET fp8 + Lightx2v LoRA；API id 保持 wan-2.6",
        summary="只用文字生成视频",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="wan-i2v",
        display_name="Wan 2.6 I2V",
        category="video",
        comfyui_checkpoint="wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        workflow_type="wan",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_wan_video_prompt",
        workflow_impl="ready",
        capabilities=_CAP_WAN,
        notes="Wan 2.2 I2V 四步；需 mode=image2video + 参考图",
        summary="首尾两张图生成过渡视频",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="wan-fun-inpaint",
        display_name="Wan Fun Inpaint",
        category="video",
        comfyui_checkpoint="wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors",
        workflow_type="wan",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_wan_video_prompt",
        workflow_impl="ready",
        capabilities=_CAP_WAN,
        notes="Wan 2.2 Fun Inpaint 首尾帧；需双帧 + mode=fun_inpaint；fun_inpaint 双 UNET + i2v Lightx2v LoRA",
        summary="首尾帧专用",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="ltx-video",
        display_name="LTX Video",
        category="video",
        comfyui_checkpoint="ltx-video-2b-v0.9.5.safetensors",
        workflow_type="ltx",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_video_prompt",
        workflow_impl="ready",
        capabilities=_CAP_LTX,
        companion_files={
            "t5_encoder": "t5xxl_fp16.safetensors",
            "runtime_default_ckpt": "ltx-video-2b-v0.9.5.safetensors",
        },
        notes="视频 workflow 早期已实现；画布 POST /api/tasks/video 当前固定走 LTX 链路",
        summary="轻量文生视频",
    ),
    _comfyui_local_provider(
        id="ltx2-fp4",
        display_name="LTX-2 fp4",
        category="video",
        comfyui_checkpoint="ltx-2-19b-dev-fp4.safetensors",
        workflow_type="ltx2",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="build_ltx2_fp4_t2v_workflow|build_ltx2_fp4_i2v_workflow",
        workflow_impl="ready",
        capabilities=_CAP_LTX2,
        companion_files={
            "text_encoder": "gemma_3_12B_it_fp4_mixed.safetensors",
            "upscaler": "ltx-2-spatial-upscaler-x2-1.0.safetensors",
            "distilled_lora": "ltx-2-19b-distilled-lora-384.safetensors",
            "camera_lora": "ltx-2-19b-lora-camera-control-dolly-left.safetensors",
            "runtime_default_ckpt": "ltx-2-19b-dev-fp4.safetensors",
        },
        notes="LTX-2 19B fp4 T2V/I2V；两阶段采样 + 空间上采样；24GB VRAM 建议降分辨率",
        summary="文字或图片都能生成视频",
        enabled=True,
    ),
    _comfyui_local_provider(
        id="ltx23-i2av",
        display_name="LTX-2.3 I2AV",
        category="video",
        comfyui_checkpoint="ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors",
        workflow_type="ltx23-i2av",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="build_ltx23_i2av_workflow",
        workflow_impl="ready",
        capabilities=_CAP_LTX23,
        gen_preset={"img2img_support": "required"},
        companion_files={
            "unet": "ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors",
            "text_projection": "ltx-2.3_text_projection_bf16.safetensors",
            "text_encoder": "gemma_3_12B_it_fp4_mixed.safetensors",
            "distilled_lora": "ltx-2.3-22b-distilled-lora-384.safetensors",
            "audio_vae": "LTX23_audio_vae_bf16.safetensors",
            "video_vae": "LTX23_video_vae_bf16.safetensors",
            "runtime_default_ckpt": "ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors",
        },
        notes="LTX-2.3 22B 图+音生视频；权重下载完成后启用",
        summary="生成带声音的视频",
        enabled=True,
    ),
    _comfyui_local_provider(
        id=VIDEO_ENHANCE_SEEDVR2_ID,
        display_name="SeedVR2 Video Enhance",
        category="video_enhance",
        comfyui_checkpoint="seedvr2_ema_7b_fp16.safetensors",
        workflow_type="seedvr2_enhance",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_seedvr2_enhance_prompt",
        workflow_impl="ready",
        capabilities=_CAP_VIDEO_ENHANCE,
        notes="SeedVR2 7B FP16 顶配视频画质增强（H800）；权重在 models/SEEDVR2/",
        summary="成片画质增强，非生成模型",
        enabled=True,
    ),
    _comfyui_local_provider(
        id=VIDEO_ENHANCE_REALESRGAN_ID,
        display_name="Real-ESRGAN Video Enhance",
        category="video_enhance",
        comfyui_checkpoint="RealESRGAN_x4plus.pth",
        workflow_type="realesrgan_enhance",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_realesrgan_enhance_prompt",
        workflow_impl="ready",
        capabilities=_CAP_VIDEO_ENHANCE,
        notes="Real-ESRGAN 逐帧超分 fallback；较短镜头可用",
        summary="成片超分增强，非生成模型",
    ),
    _comfyui_local_provider(
        id=IMAGE_ENHANCE_SEEDVR2_ID,
        display_name="SeedVR2 Image Enhance",
        category="image_enhance",
        comfyui_checkpoint="seedvr2_ema_7b_fp16.safetensors",
        workflow_type="seedvr2_image_enhance",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_seedvr2_image_enhance_prompt",
        workflow_impl="ready",
        capabilities=_CAP_VIDEO_ENHANCE,
        notes="SeedVR2 7B FP16 静帧画质增强；权重与视频版共用",
        summary="静帧画质增强，非生成模型",
        enabled=True,
    ),
]

COMFYUI_PROVIDER_MAP: dict[str, dict] = {p["id"]: p for p in COMFYUI_LOCAL_PROVIDERS}

_VIDEO_ENHANCE_ORDER = (VIDEO_ENHANCE_SEEDVR2_ID, VIDEO_ENHANCE_REALESRGAN_ID)


def _video_enhance_provider_available(provider_id: str) -> bool:
    entry = COMFYUI_PROVIDER_MAP.get(provider_id)
    if not entry:
        return False
    return bool(entry.get("enabled")) and entry.get("workflow_impl") == "ready"


def resolve_video_enhance_workflow(
    preferred: str | None = None,
) -> tuple[str, dict] | None:
    """
    解析可用的视频画质增强 workflow。
    preferred: auto | seedvr2 | realesrgan；auto 时 SeedVR2 优先。
    返回 (provider_id, provider_entry) 或 None。
    """
    key = (preferred or "auto").strip().lower()
    if key == "realesrgan":
        candidates = (VIDEO_ENHANCE_REALESRGAN_ID,)
    elif key == "seedvr2":
        candidates = (VIDEO_ENHANCE_SEEDVR2_ID,)
    else:
        candidates = _VIDEO_ENHANCE_ORDER

    for provider_id in candidates:
        if _video_enhance_provider_available(provider_id):
            return provider_id, COMFYUI_PROVIDER_MAP[provider_id]
    return None


def get_comfyui_provider(model_id: str) -> dict | None:
    """按 model_id 取 ComfyUI 本地 provider 结构化配置。"""
    key = (model_id or "").strip()
    if not key:
        return None
    return COMFYUI_PROVIDER_MAP.get(key) or COMFYUI_PROVIDER_MAP.get(key.lower())


# 与 registered_models 同步用（由 COMFYUI_LOCAL_PROVIDERS 派生，避免双份维护）
LOCAL_MODEL_PRESETS: list[dict] = [
    {
        "id": p["id"],
        "display_name": p["display_name"],
        "category": p["category"],
        "type": p["type"],
        "provider": p["provider"],
        "comfyui_file": p["comfyui_file"],
        "capabilities": p["capabilities"],
        **{
            k: p[k]
            for k in (
                "workflow_type",
                "generation_defaults",
                "img2img_support",
                "native_resolution",
                "max_resolution",
                "negative_prompt",
            )
            if k in p
        },
    }
    for p in COMFYUI_LOCAL_PROVIDERS
]
