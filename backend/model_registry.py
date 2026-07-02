"""
model_registry.py
静态模型注册表 — 所有支持模型的元信息。

comfyui_model_file / LOCAL_MODEL_PRESETS.comfyui_file / COMFYUI_LOCAL_PROVIDERS：
  当前值为社区常见命名占位符；GPU 服务器到位后须与 ComfyUI models/ 目录
  实际文件名核对并替换（见 backend/docs/COMFYUI_CUTOVER_RUNBOOK.md）。
  结构化 provider 见 COMFYUI_LOCAL_PROVIDERS（含 endpoint env、workflow 模块、checkpoint）。
  未确认前勿在 registered_models 中启用对应本地模型。
"""

# ── capabilities 预设 ─────────────────────────────────────────────────────
# SD 1.5 单边最长 768px
_RES_SD15 = {
    "1:1": [512, 512],
    "4:3": [768, 576],
    "3:4": [576, 768],
    "16:9": [768, 432],
    "9:16": [432, 768],
}
_RES_SDXL = {
    "1:1": [1024, 1024],
    "4:3": [1152, 896],
    "3:4": [896, 1152],
    "16:9": [1216, 832],
    "9:16": [832, 1216],
}
_RES_FLUX = {
    "1:1": [1024, 1024],
    "4:3": [1152, 896],
    "3:4": [896, 1152],
    "16:9": [1344, 768],
    "9:16": [768, 1344],
}
_RES_HIDREAM = {
    "1:1": [1024, 1024],
    "16:9": [1280, 720],
    "9:16": [720, 1280],
    "4:3": [1152, 896],
    "3:4": [896, 1152],
}

_CAP_SD15 = {
    "aspect_ratios": list(_RES_SD15.keys()),
    "resolutions": ["512x512", "768x576", "576x768", "768x432", "432x768"],
    "recommended_resolutions": _RES_SD15,
    "steps_range": [1, 50],
    "cfg_range": [1, 20],
}
_CAP_SDXL = {
    "aspect_ratios": list(_RES_SDXL.keys()),
    "resolutions": ["1024x1024", "1152x896", "896x1152", "1216x832", "832x1216"],
    "recommended_resolutions": _RES_SDXL,
    "steps_range": [1, 50],
    "cfg_range": [1, 20],
}
_CAP_FLUX_DEV = {
    "aspect_ratios": list(_RES_FLUX.keys()),
    "resolutions": ["1024x1024", "1344x768", "768x1344"],
    "recommended_resolutions": _RES_FLUX,
    "steps_range": [1, 50],
    "cfg_range": None,
}
_CAP_FLUX_SCHNELL = {
    "aspect_ratios": list(_RES_FLUX.keys()),
    "resolutions": ["1024x1024", "1344x768", "768x1344"],
    "recommended_resolutions": _RES_FLUX,
    "steps_range": [1, 8],
    "cfg_range": None,
}
_CAP_HIDREAM = {
    "aspect_ratios": list(_RES_HIDREAM.keys()),
    "resolutions": ["1024x1024", "1280x720"],
    "recommended_resolutions": _RES_HIDREAM,
    "steps_range": [1, 50],
    "cfg_range": [1, 10],
}
_CAP_JIMENG = {
    "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
    "resolutions": ["1024x1024", "1280x720", "720x1280"],
    "recommended_resolutions": _RES_FLUX,
    "steps_range": None,
    "cfg_range": None,
}
# ── generation 预设（workflow_type / generation_defaults 等）────────────────
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
_GEN_HIDREAM = {
    "workflow_type": "hidream",
    "generation_defaults": {
        "steps": 50,
        "cfg": 5.0,
        "sampler_name": "uni_pc",
        "scheduler": "simple",
        "shift": 3.0,
        "denoise_txt2img": 1.0,
        "denoise_img2img": None,
    },
    "img2img_support": "unsupported",
    "native_resolution": 1024,
    "max_resolution": 1280,
    "negative_prompt": False,
}

_CAP_WAN = {
    "aspect_ratios": ["16:9", "9:16", "1:1"],
    "durations": [3, 5],
}
_CAP_LTX = {
    "aspect_ratios": ["16:9", "9:16"],
    "durations": [5, 10, 15],
}
_CAP_HUNYUAN = {
    "aspect_ratios": ["16:9", "9:16", "1:1"],
    "durations": [5, 10],
}
_CAP_VIDEO_ENHANCE = {
    "upscale_factors": [1.0, 1.5, 2.0, 3.0],
    "strengths": ["normal", "sharp"],
}

VIDEO_ENHANCE_SEEDVR2_ID = "video-enhance-seedvr2"
VIDEO_ENHANCE_REALESRGAN_ID = "video-enhance-realesrgan"

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
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "category": "text",
        "type": "api",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
        "default_enabled": False,
    },
    {
        "id": "claude-sonnet-4",
        "name": "Claude Sonnet 4",
        "category": "text",
        "type": "api",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "default_enabled": False,
    },
    {
        "id": "claude-opus-4",
        "name": "Claude Opus 4",
        "category": "text",
        "type": "api",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "default_enabled": False,
    },
    # ── 图像生成 ──────────────────────────────────────────────────────────
    {
        "id": "stable-diffusion",
        "name": "SD 1.5",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "v1-5-pruned-emaonly.safetensors",  # 占位；服务器确认后替换
        "default_enabled": True,
        "capabilities": _CAP_SD15,
        **_GEN_SD15,
    },
    {
        "id": "sdxl",
        "name": "SDXL",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "sd_xl_base_1.0.safetensors",  # 占位；服务器确认后替换
        "default_enabled": True,
        "capabilities": _CAP_SDXL,
        **_GEN_SDXL,
    },
    {
        "id": "flux-dev",
        "name": "Flux Dev",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "flux1-dev.safetensors",  # 占位；服务器确认后替换
        "default_enabled": False,
        "capabilities": _CAP_FLUX_DEV,
        **_GEN_FLUX_DEV,
    },
    {
        "id": "flux-schnell",
        "name": "Flux Schnell",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "flux1-schnell.safetensors",  # 占位；服务器确认后替换
        "default_enabled": False,
        "capabilities": _CAP_FLUX_SCHNELL,
        **_GEN_FLUX_SCHNELL,
    },
    {
        "id": "hidream",
        "name": "HiDream",
        "category": "image",
        "type": "local",
        "comfyui_model_file": "hidream_i1_full.safetensors",  # 占位；服务器确认后替换
        "default_enabled": False,
        "capabilities": _CAP_HIDREAM,
        **_GEN_HIDREAM,
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
    },
    # ── 视频生成 ──────────────────────────────────────────────────────────
    {
        "id": "wan-2.6",
        "name": "Wan 2.6",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "wan2.6.safetensors",  # 占位；服务器确认后替换
        "default_enabled": True,
        "capabilities": _CAP_WAN,
        "workflow_type": "wan",
        "video_backend": "wan",
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
    },
    {
        "id": "hunyuan-video",
        "name": "HunyuanVideo",
        "category": "video",
        "type": "local",
        "comfyui_model_file": "hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors",  # 占位；服务器确认后替换
        "default_enabled": False,
        "capabilities": _CAP_HUNYUAN,
        "workflow_type": "hunyuan",
        "video_backend": "hunyuan",
    },
]

MODEL_MAP: dict[str, dict] = {m["id"]: m for m in ALL_MODELS}

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
    """按 checkpoint 文件名推断 generation 配置（含 v1-5-*.safetensors 等变体）。"""
    name = (comfyui_filename or "").strip().lower()
    if not name:
        return None
    if "flux1-schnell" in name or "flux-schnell" in name:
        return dict(_GEN_FLUX_SCHNELL)
    if "flux1-dev" in name or "flux-dev" in name:
        return dict(_GEN_FLUX_DEV)
    if "hidream" in name:
        return dict(_GEN_HIDREAM)
    if "sd_xl" in name or "sdxl" in name or "juggernaut" in name or "dreamshaper" in name:
        return dict(_GEN_SDXL)
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
    """解析视频模型的 ComfyUI 分派后端：wan / hunyuan / ltx（默认）。"""
    entry = _lookup_model_entry(model_id or "")
    if entry:
        backend = (entry.get("video_backend") or entry.get("workflow_type") or "").strip().lower()
        if backend in ("wan", "hunyuan", "ltx"):
            return backend
    return "ltx"


def resolve_generation_profile(
    model_id: str | None = None,
    comfyui_filename: str | None = None,
) -> dict:
    """
    解析模型的 workflow_type / generation_defaults 等。
    优先 model_id，其次按 comfyui checkpoint 文件名匹配（含 SD 1.5 变体）。
    未匹配时回退 SD 1.5 预设以保持兼容。
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
            "workflow_type": inferred.get("workflow_type", "sd15"),
            "generation_defaults": dict(defaults),
            "img2img_support": inferred.get("img2img_support", "native"),
            "native_resolution": inferred.get("native_resolution"),
            "max_resolution": inferred.get("max_resolution"),
            "negative_prompt": inferred.get("negative_prompt", True),
        }
    return {
        "workflow_type": "sd15",
        "generation_defaults": dict(_GEN_SD15["generation_defaults"]),
        "img2img_support": _GEN_SD15["img2img_support"],
        "native_resolution": _GEN_SD15["native_resolution"],
        "max_resolution": _GEN_SD15["max_resolution"],
        "negative_prompt": _GEN_SD15["negative_prompt"],
    }


def resolve_image_dimensions_for_model(
    model_id: str,
    ratio: str,
    quality: str | None = None,
) -> tuple[int, int]:
    """按模型 capabilities.recommended_resolutions 解析画布图像宽高。"""
    entry = _lookup_model_entry(model_id)
    caps = (entry or {}).get("capabilities") or {}
    rec = caps.get("recommended_resolutions") or {}
    if ratio in rec:
        pair = rec[ratio]
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            return int(pair[0]), int(pair[1])

    q = (quality or "2K").strip().upper()
    if q not in ("2K", "3K"):
        q = "2K"
    base = _FALLBACK_2K.get(ratio)
    if base:
        w, h = base
        if q == "3K":
            w, h = int(w * 1.5), int(h * 1.5)
        return w, h
    if ratio in _FALLBACK_CANVAS:
        return _FALLBACK_CANVAS[ratio]
    raise ValueError(f"不支持的宽高比: {ratio}（model={model_id}, quality={q}）")


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
    return entry


# 真实 ComfyUI provider 注册表 — 切换日只改 checkpoint/伴随文件名 + enabled，无需改代码结构
COMFYUI_LOCAL_PROVIDERS: list[dict] = [
    _comfyui_local_provider(
        id="stable-diffusion",
        display_name="Stable Diffusion 1.5",
        category="image",
        comfyui_checkpoint="v1-5-pruned-emaonly.safetensors",
        workflow_type="sd15",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_workflow",
        workflow_impl="ready",
        capabilities=_CAP_SD15,
        gen_preset=_GEN_SD15,
        notes="图像 workflow 早期已实现（KSampler + CheckpointLoader）",
    ),
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
        notes="图像 workflow 早期已实现（同 SD1.5 分支，generation_defaults 不同）",
    ),
    _comfyui_local_provider(
        id="flux-dev",
        display_name="Flux Dev",
        category="image",
        comfyui_checkpoint="flux1-dev.safetensors",
        workflow_type="flux",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_flux_workflow",
        workflow_impl="ready",
        capabilities=_CAP_FLUX_DEV,
        gen_preset=_GEN_FLUX_DEV,
        companion_files={
            "clip_l": "clip_l.safetensors",
            "clip_t5": "t5xxl_fp16.safetensors",
            "vae": "ae.safetensors",
        },
        notes="2026-06-25 预案补全；guidance≤4.5，无负向提示词，无 img2img",
    ),
    _comfyui_local_provider(
        id="flux-schnell",
        display_name="Flux Schnell",
        category="image",
        comfyui_checkpoint="flux1-schnell.safetensors",
        workflow_type="flux",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_flux_workflow",
        workflow_impl="ready",
        capabilities=_CAP_FLUX_SCHNELL,
        gen_preset=_GEN_FLUX_SCHNELL,
        companion_files={
            "clip_l": "clip_l.safetensors",
            "clip_t5": "t5xxl_fp16.safetensors",
            "vae": "ae.safetensors",
        },
        notes="2026-06-25 预案补全；steps=4 guidance=1.0，无负向提示词",
    ),
    _comfyui_local_provider(
        id="hidream",
        display_name="HiDream",
        category="image",
        comfyui_checkpoint="hidream_i1_full.safetensors",
        workflow_type="hidream",
        workflow_module="backend/providers/comfyui.py",
        workflow_builder="_build_hidream_workflow",
        workflow_impl="ready",
        capabilities=_CAP_HIDREAM,
        gen_preset=_GEN_HIDREAM,
        companion_files={
            "clip_l": "clip_l.safetensors",
            "clip_g": "clip_g.safetensors",
            "clip_t5": "t5xxl_fp16.safetensors",
            "clip_llama": "llama_3.1_8b_instruct_fp8_scaled.safetensors",
            "vae": "ae.safetensors",
        },
        notes="2026-06-25 预案补全；QuadrupleCLIPLoader + ModelSamplingSD3 + KSampler",
    ),
    _comfyui_local_provider(
        id="wan-2.6",
        display_name="Wan 2.6",
        category="video",
        comfyui_checkpoint="wan2.6.safetensors",
        workflow_type="wan",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_wan_video_prompt",
        workflow_impl="ready",
        capabilities=_CAP_WAN,
        notes="WanVideoWrapper 节点链；画布视频按 video_backend=wan 分派",
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
    ),
    _comfyui_local_provider(
        id="hunyuan-video",
        display_name="HunyuanVideo",
        category="video",
        comfyui_checkpoint="hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors",
        workflow_type="hunyuan",
        workflow_module="backend/comfyui/client.py",
        workflow_builder="submit_hunyuan_video_prompt",
        workflow_impl="ready",
        capabilities=_CAP_HUNYUAN,
        companion_files={
            "clip_l": "clip_l.safetensors",
            "clip_llava": "llava_llama3_fp8_scaled.safetensors",
            "vae": "hunyuan_video_vae_bf16.safetensors",
            "runtime_default_ckpt": "hunyuan_video_t2v_720p_bf16.safetensors",
        },
        notes="ComfyUI 原生 HunyuanVideo 节点链；画布视频按 video_backend=hunyuan 分派",
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
        notes="SeedVR2 7B 视频画质增强；需 ComfyUI-SeedVR2_VideoUpscaler 自定义节点",
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
