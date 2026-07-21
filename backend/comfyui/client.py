import base64
import json
import logging
import random
import time
import uuid
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Callable

import httpx

from comfyui.workflow_registry import load_workflow_template
from core.logging_setup import studio_print
from core.comfyui_settings import comfyui_http_url, comfyui_nodes_list, comfyui_node_port, comfyui_ws_url

logger = logging.getLogger(__name__)

COMFYUI_URL = comfyui_http_url()
COMFYUI_WS_URL = comfyui_ws_url()
HTTP_TIMEOUT = 5.0
COMFY_POLL_CACHE_FRESH_SEC = 4.0
COMFY_POLL_THROTTLE_SEC = 2.5
_poll_fetch_lock = Lock()
_last_comfy_fetch: dict[str, float] = {}
COMFYUI_UNREACHABLE_MSG = (
    "ComfyUI 服务未启动或无法连接，请先启动 ComfyUI"
)


def _resolve_comfyui_base(node_url: str | None = None) -> str:
    """优先使用任务绑定的 ComfyUI 实例 URL。"""
    url = (node_url or "").strip().rstrip("/")
    if url:
        return url
    return comfyui_http_url().rstrip("/")


def _acquire_gpu_node_url(
    *,
    task_id: str | None = None,
    estimated_duration_sec: int = 120,
    required_vram: int = 0,
    prefer_short: bool = True,
) -> str:
    """从 GPUPool 选取可达节点（上传与 prompt 须使用同一 URL）。"""
    from services.gpu_pool import get_gpu_pool

    pool = get_gpu_pool()
    preferred = pool.get_available_node(
        required_vram=required_vram,
        prefer_short=prefer_short,
        estimated_duration_sec=estimated_duration_sec,
    )
    candidates = [preferred.comfyui_url.rstrip("/")]
    for node in pool.nodes:
        url = node.comfyui_url.rstrip("/")
        if url in candidates:
            continue
        # 高显存任务禁止回落到不满足 required_vram 的节点
        if required_vram > 0 and node.available_vram < required_vram:
            continue
        candidates.append(url)

    last_error: Exception | None = None
    for url in candidates:
        try:
            res = httpx.get(f"{url}/system_stats", timeout=5.0)
            if res.status_code == 200:
                return url
        except (httpx.ConnectError, httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("无可用 ComfyUI 节点")


HISTORY_LIMIT = 50
DEFAULT_IMAGE_MODEL = "v1-5-pruned-emaonly.safetensors"
DEFAULT_VIDEO_MODEL = "ltx-video-2b-v0.9.5.safetensors"
DEFAULT_CKPT = DEFAULT_IMAGE_MODEL
LTX_CKPT = DEFAULT_VIDEO_MODEL
WAN_CKPT = "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"
WAN22_T2V_HIGH = "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"
WAN22_T2V_LOW = "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"
WAN22_LORA_HIGH = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors"
WAN22_LORA_LOW = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"
WAN22_I2V_HIGH = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
WAN22_I2V_LOW = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
WAN22_I2V_LORA_HIGH = "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
WAN22_I2V_LORA_LOW = "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
WAN22_FUN_INPAINT_HIGH = "wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors"
WAN22_FUN_INPAINT_LOW = "wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors"
WAN_VAE = "wan_2.1_vae.safetensors"
WAN22_MODEL_SAMPLING_SHIFT = 5.0
WAN22_T2V_STEPS = 4
WAN22_T2V_CFG = 1.0
WAN22_QUALITY_STEPS = 8  # G31 sampling_profile=quality


def resolve_wan_steps(sampling_profile: str | None = None, steps: int | None = None) -> int:
    """fast→4，quality→8；未指定默认 quality；显式 steps 优先。"""
    if steps is not None:
        return max(2, int(steps))
    profile = (sampling_profile or "quality").strip().lower()
    if profile == "fast":
        return int(WAN22_T2V_STEPS)
    return int(WAN22_QUALITY_STEPS)


def _wan_sampler_split(steps: int) -> tuple[int, int]:
    """KSamplerAdvanced 高低噪分段：0→mid, mid→steps。"""
    s = max(2, int(steps))
    mid = max(1, s // 2)
    return mid, s


WAN_T5_ENCODER = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
LTX_T5_ENCODER = "t5xxl_fp16.safetensors"
LTX2_CKPT = "ltx-2-19b-dev-fp4.safetensors"
LTX2_GEMMA_ENCODER = "gemma_3_12B_it_fp4_mixed.safetensors"
LTX2_UPSCALER = "ltx-2-spatial-upscaler-x2-1.0.safetensors"
LTX2_DISTILLED_LORA = "ltx-2-19b-distilled-lora-384.safetensors"
LTX2_CAMERA_LORA = "ltx-2-19b-lora-camera-control-dolly-left.safetensors"
LTX23_UNET = "ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors"
LTX23_TEXT_PROJ = "ltx-2.3_text_projection_bf16.safetensors"
LTX23_DISTILLED_LORA = "ltx-2.3-22b-distilled-lora-384.safetensors"
LTX23_AUDIO_VAE = "LTX23_audio_vae_bf16.safetensors"
LTX23_VIDEO_VAE = "LTX23_video_vae_bf16.safetensors"
LTX23_WORKFLOW_KEY = "ltx23_i2av_api.json"
LTX2_WORKFLOW_KEY = "ltx2_fp4_t2v_api.json"
LTX2_I2V_WORKFLOW_KEY = "ltx2_fp4_i2v_api.json"
LTX_T5_DOWNLOAD_HINT = (
    "LTX 视频需要 T5 文本编码器。请将 t5xxl_fp16.safetensors 放入 "
    "ComfyUI/models/text_encoders/ 目录后重试。"
    " 下载: https://huggingface.co/Comfy-Org/mochi_preview_repackaged/"
    "resolve/main/split_files/text_encoders/t5xxl_fp16.safetensors"
)

DEFAULT_STEPS = 20
VIDEO_FPS = 24
VIDEO_STEPS = 25

# SD1.5 图像节点
NODE_KSAMPLER = "3"
NODE_CHECKPOINT = "4"
NODE_EMPTY_LATENT = "5"
NODE_CLIP_POSITIVE = "6"
NODE_CLIP_NEGATIVE = "7"
NODE_VAE_DECODE = "8"
NODE_SAVE_IMAGE = "9"

# LTX 视频节点（官方 LTXVLoader 工作流，节点 1–12）
V_LOADER = "1"
V_CLIP_POS = "2"
V_CLIP_NEG = "3"
V_LATENT = "4"
V_COND = "5"
V_SCHEDULER = "6"
V_SAMPLER = "7"
V_NOISE = "8"
V_GUIDER = "9"
V_SAMPLER_SEL = "10"
V_DECODER = "11"
V_SAVE = "12"

# 兼容工作流（无 LTXVLoader 时：Checkpoint + CLIPLoader）
VC_CKPT = "1"
VC_CLIP = "2"
VC_POS = "3"
VC_NEG = "4"
VC_LATENT = "5"
VC_COND = "6"
VC_SCHEDULER = "7"
VC_NOISE = "8"
VC_GUIDER = "9"
VC_SAMPLER_SEL = "10"
VC_SAMPLER = "11"
VC_DECODE = "12"
VC_SAVE = "13"

VIDEO_SAVE_CLASS = {
    "SaveAnimatedWEBP",
    "SaveAnimatedPNG",
    "VHS_VideoCombine",
    "SaveWEBM",
    "SaveVideo",
    "CreateVideo",
}
VIDEO_WORKFLOW_CLASS = VIDEO_SAVE_CLASS | {
    "EmptyLTXVLatentVideo",
    "LTXVConditioning",
    "LTXVImgToVideo",
    "ModelSamplingLTXV",
    "LTXVLoader",
    "LTXVDecoder",
    "LTXAVTextEncoderLoader",
    "CLIPLoader",
    "WanVideoModelLoader",
    "WanVideoSampler",
    "WanVideoDecode",
    "WanVideoTextEncode",
    "WanImageToVideo",
    "WanFirstLastFrameToVideo",
    "WanFunInpaintToVideo",
    "LoadImage",
    "SeedVR2LoadDiTModel",
    "SeedVR2LoadVAEModel",
    "SeedVR2VideoUpscaler",
    "UpscaleModelLoader",
    "ImageUpscaleWithModel",
    "VHS_LoadVideo",
}

STYLE_SUFFIXES = {
    "realistic": "photorealistic, high quality, detailed",
    "anime": "anime style, illustration, vibrant colors",
    "oil": "oil painting, artistic, textured",
}

DEFAULT_VIDEO_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, "
    "bad anatomy, extra hands, extra fingers, extra limbs, "
    "deformed hands, malformed arms"
)

COMFY_MODELS_BASE = Path(r"D:\ComfyUI\ComfyUI\models")
MODEL_CONFIG_PATH = Path(__file__).resolve().parent.parent / "model_config.json"
MODEL_EXTENSIONS = {".safetensors", ".ckpt"}
MODEL_SCAN_CATEGORIES = {
    "checkpoints": "checkpoints",
    "loras": "loras",
    "vae": "vae",
    "text_encoders": "text_encoders",
}

# checkpoint 文件名关键词 → 自动归类（视频优先匹配）
VIDEO_CKPT_KEYWORDS = (
    "ltx",
    "ltxv",
    "video",
    "svd",
    "animatediff",
    "mochi",
    "cogvideo",
    "wan2",
    "genmo",
    "stable-video",
    "sora",
)
VHS_PLUGIN_PATH = Path(
    r"D:\ComfyUI\ComfyUI\custom_nodes\ComfyUI-VideoHelperSuite"
)
VHS_INSTALL_HINT = (
    "视频 MP4 输出需要 ComfyUI-VideoHelperSuite 插件（VHS_VideoCombine 节点）。\n"
    f"请安装到：{VHS_PLUGIN_PATH}\n"
    "安装后重启 ComfyUI Desktop，再提交视频任务。"
    " 仓库: https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
)

VC_CREATE_VIDEO = "16"

# Wan 2.2 T2V 四步（原生 ComfyUI 节点链，对齐云绘 Wan2.2-14B文生视频-4步）
W22_CLIP = "w22_clip"
W22_POS = "w22_pos"
W22_NEG = "w22_neg"
W22_VAE = "w22_vae"
W22_EMPTY = "w22_empty"
W22_UNET_H = "w22_unet_h"
W22_UNET_L = "w22_unet_l"
W22_LORA_H = "w22_lora_h"
W22_LORA_L = "w22_lora_l"
W22_MS_H = "w22_ms_h"
W22_MS_L = "w22_ms_l"
W22_SAMPLE_H = "w22_sample_h"
W22_SAMPLE_L = "w22_sample_l"
W22_DECODE = "w22_decode"
W22_CREATE = "w22_create"
W22_SAVE = "w22_save"

# Wan 2.2 I2V 四步（LoadImage + WanImageToVideo + 双 KSamplerAdvanced）
W22I_CLIP = "w22i_clip"
W22I_POS = "w22i_pos"
W22I_NEG = "w22i_neg"
W22I_VAE = "w22i_vae"
W22I_LOAD = "w22i_load"
W22I_I2V = "w22i_i2v"
W22I_UNET_H = "w22i_unet_h"
W22I_UNET_L = "w22i_unet_l"
W22I_LORA_H = "w22i_lora_h"
W22I_LORA_L = "w22i_lora_l"
W22I_MS_H = "w22i_ms_h"
W22I_MS_L = "w22i_ms_l"
W22I_SAMPLE_H = "w22i_sample_h"
W22I_SAMPLE_L = "w22i_sample_l"
W22I_DECODE = "w22i_decode"
W22I_CREATE = "w22i_create"
W22I_SAVE = "w22i_save"

# Wan 2.2 FLF2V 四步（双 LoadImage + WanFirstLastFrameToVideo + 双 KSamplerAdvanced）
W22F_CLIP = "w22f_clip"
W22F_POS = "w22f_pos"
W22F_NEG = "w22f_neg"
W22F_VAE = "w22f_vae"
W22F_LOAD_START = "w22f_load_start"
W22F_LOAD_END = "w22f_load_end"
W22F_FLF2V = "w22f_flf2v"
W22F_UNET_H = "w22f_unet_h"
W22F_UNET_L = "w22f_unet_l"
W22F_LORA_H = "w22f_lora_h"
W22F_LORA_L = "w22f_lora_l"
W22F_MS_H = "w22f_ms_h"
W22F_MS_L = "w22f_ms_l"
W22F_SAMPLE_H = "w22f_sample_h"
W22F_SAMPLE_L = "w22f_sample_l"
W22F_DECODE = "w22f_decode"
W22F_CREATE = "w22f_create"
W22F_SAVE = "w22f_save"

# Wan 2.2 Fun Inpaint（双 LoadImage + WanFunInpaintToVideo + fun_inpaint UNET）
W22N_CLIP = "w22n_clip"
W22N_POS = "w22n_pos"
W22N_NEG = "w22n_neg"
W22N_VAE = "w22n_vae"
W22N_LOAD_START = "w22n_load_start"
W22N_LOAD_END = "w22n_load_end"
W22N_FUN = "w22n_fun"
W22N_UNET_H = "w22n_unet_h"
W22N_UNET_L = "w22n_unet_l"
W22N_LORA_H = "w22n_lora_h"
W22N_LORA_L = "w22n_lora_l"
W22N_MS_H = "w22n_ms_h"
W22N_MS_L = "w22n_ms_l"
W22N_SAMPLE_H = "w22n_sample_h"
W22N_SAMPLE_L = "w22n_sample_l"
W22N_DECODE = "w22n_decode"
W22N_CREATE = "w22n_create"
W22N_SAVE = "w22n_save"

# 兼容旧探针常量名
WAN_MODEL_LOADER = W22_UNET_H
WAN_TEXT_ENCODE = W22_POS
WAN_SAMPLER = W22_SAMPLE_L
WAN_DECODE = W22_DECODE
WAN_SAVE = W22_SAVE

_object_info_cache_by_node: dict[str, dict] = {}


def get_active_models() -> dict[str, str]:
    return {"image_model": DEFAULT_CKPT, "video_model": LTX_CKPT}


def _default_model_config() -> dict[str, str]:
    return {
        "image_model": DEFAULT_IMAGE_MODEL,
        "video_model": DEFAULT_VIDEO_MODEL,
    }


def load_model_config(config_path: Path | None = None) -> dict[str, str]:
    path = config_path or MODEL_CONFIG_PATH
    defaults = _default_model_config()
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults
    image = (data.get("image_model") or defaults["image_model"]).strip()
    video = (data.get("video_model") or defaults["video_model"]).strip()
    return {"image_model": image, "video_model": video}


def save_model_config(
    config: dict[str, str], config_path: Path | None = None
) -> None:
    path = config_path or MODEL_CONFIG_PATH
    payload = {
        "image_model": config.get("image_model", DEFAULT_IMAGE_MODEL),
        "video_model": config.get("video_model", DEFAULT_VIDEO_MODEL),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def apply_active_models(image_model: str | None = None, video_model: str | None = None) -> dict[str, str]:
    """热更新模块级 checkpoint 变量，立即作用于后续工作流。"""
    global DEFAULT_CKPT, LTX_CKPT
    if image_model:
        DEFAULT_CKPT = image_model
    if video_model:
        LTX_CKPT = video_model
    return get_active_models()


def init_model_config(config_path: Path | None = None) -> dict[str, str]:
    path = config_path or MODEL_CONFIG_PATH
    config = _sanitize_model_config(load_model_config(path))
    save_model_config(config, path)
    apply_active_models(config["image_model"], config["video_model"])
    return get_active_models()


def classify_checkpoint(filename: str) -> str:
    """
    根据文件名推断 checkpoint 用途。
    返回 "image" 或 "video"（含 ltx/svd 等视频模型关键词的归为视频）。
    """
    lower = (filename or "").lower()
    for kw in VIDEO_CKPT_KEYWORDS:
        if kw in lower:
            return "video"
    return "image"


def _scan_category_models(subdir: str) -> list[str]:
    folder = COMFY_MODELS_BASE / subdir
    if not folder.is_dir():
        return []
    names = []
    for entry in sorted(folder.iterdir()):
        if entry.is_file() and entry.suffix.lower() in MODEL_EXTENSIONS:
            names.append(entry.name)
    return names


def get_checkpoints_by_type(model_type: str) -> list[str]:
    """仅返回适用于 image 或 video 工作流的 checkpoint 列表。"""
    if model_type not in ("image", "video"):
        raise ValueError("model_type 必须为 image 或 video")
    all_ckpts = _scan_category_models("checkpoints")
    return [n for n in all_ckpts if classify_checkpoint(n) == model_type]


def _sanitize_model_config(config: dict[str, str]) -> dict[str, str]:
    """校正配置：图像槽位不能用视频模型，反之亦然；无效时回退到同类首个可用模型。"""
    image_ckpts = get_checkpoints_by_type("image")
    video_ckpts = get_checkpoints_by_type("video")

    image = (config.get("image_model") or DEFAULT_IMAGE_MODEL).strip()
    video = (config.get("video_model") or DEFAULT_VIDEO_MODEL).strip()

    if classify_checkpoint(image) != "image" or image not in image_ckpts:
        image = image_ckpts[0] if image_ckpts else DEFAULT_IMAGE_MODEL

    if classify_checkpoint(video) != "video" or video not in video_ckpts:
        video = video_ckpts[0] if video_ckpts else DEFAULT_VIDEO_MODEL

    return {"image_model": image, "video_model": video}


def scan_models_directory() -> dict:
    all_ckpts = _scan_category_models("checkpoints")
    image_ckpts = [n for n in all_ckpts if classify_checkpoint(n) == "image"]
    video_ckpts = [n for n in all_ckpts if classify_checkpoint(n) == "video"]
    checkpoint_kinds = {name: classify_checkpoint(name) for name in all_ckpts}

    result = {
        key: _scan_category_models(subdir)
        for key, subdir in MODEL_SCAN_CATEGORIES.items()
    }
    result["checkpoints_image"] = image_ckpts
    result["checkpoints_video"] = video_ckpts
    result["checkpoint_kinds"] = checkpoint_kinds
    return result


def _checkpoint_exists(filename: str) -> bool:
    path = COMFY_MODELS_BASE / "checkpoints" / filename
    return path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS


def select_model(model_type: str, model_filename: str, config_path: Path | None = None) -> dict:
    name = (model_filename or "").strip()
    if not name:
        raise ValueError("模型文件名不能为空")
    if model_type not in ("image", "video"):
        raise ValueError("type 必须为 image 或 video")
    if not _checkpoint_exists(name):
        raise ValueError(f"checkpoint 中未找到模型: {name}")

    kind = classify_checkpoint(name)
    if kind != model_type:
        type_label = "视频" if kind == "video" else "图像"
        use_label = "图像" if model_type == "image" else "视频"
        raise ValueError(
            f"「{name}」属于{type_label}模型，不能用于{use_label}生成，请在对应页面选择"
        )

    path = config_path or MODEL_CONFIG_PATH
    config = load_model_config(path)
    if model_type == "image":
        config["image_model"] = name
        apply_active_models(image_model=name)
    else:
        config["video_model"] = name
        apply_active_models(video_model=name)
    save_model_config(config, path)
    return {
        "success": True,
        "type": model_type,
        "model": name,
        "current": get_active_models(),
    }


async def _fetch_object_info(node_url: str | None = None) -> dict:
    base = _resolve_comfyui_base(node_url)
    cached = _object_info_cache_by_node.get(base)
    if cached is not None:
        return cached
    # 远程 H800 object_info 体积大，放宽超时
    timeout = 30.0 if base.startswith("https://") else HTTP_TIMEOUT
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.get(f"{base}/object_info")
        res.raise_for_status()
        _object_info_cache_by_node[base] = res.json()
    return _object_info_cache_by_node[base]


def _has_node(class_type: str, info: dict | None = None) -> bool:
    if info is None:
        return False
    return class_type in info


def _vhs_video_combine_inputs(images_ref: str) -> dict:
    """VHS_VideoCombine：输出 h264 MP4（需 VideoHelperSuite）。"""
    return {
        "images": [images_ref, 0],
        "frame_rate": float(VIDEO_FPS),
        "loop_count": 0,
        "filename_prefix": "AIStudio_video",
        "format": "video/h264-mp4",
        "pix_fmt": "yuv420p",
        "crf": 19,
        "save_metadata": True,
        "trim_to_audio": False,
        "pingpong": False,
        "save_output": True,
    }


def _can_output_mp4(info: dict) -> bool:
    if _has_node("VHS_VideoCombine", info):
        return True
    return _has_node("CreateVideo", info) and _has_node("SaveVideo", info)


async def ensure_video_mp4_capable(node_url: str | None = None) -> None:
    nodes = (
        [_resolve_comfyui_base(node_url)]
        if node_url
        else comfyui_nodes_list()
    )
    last_error: Exception | None = None
    for url in nodes:
        try:
            info = await _fetch_object_info(url)
        except (httpx.ConnectError, httpx.HTTPError) as exc:
            last_error = exc
            logger.warning("ensure_video_mp4_capable skip unreachable node %s: %s", url, exc)
            continue
        if _can_output_mp4(info):
            return
    if last_error is not None and len(nodes) == 1:
        raise last_error
    extra = ""
    if not VHS_PLUGIN_PATH.is_dir():
        extra = f"\n未检测到插件目录：{VHS_PLUGIN_PATH}"
    raise ValueError(VHS_INSTALL_HINT + extra)


def _build_video_save_nodes(decode_ref: str, info: dict) -> dict[str, dict]:
    """为 VAEDecode/LTXVDecoder 输出追加保存节点，优先 MP4。"""
    if _has_node("VHS_VideoCombine", info):
        return {
            VC_SAVE: {
                "class_type": "VHS_VideoCombine",
                "inputs": _vhs_video_combine_inputs(decode_ref),
            }
        }

    if _has_node("CreateVideo", info) and _has_node("SaveVideo", info):
        save_inputs = {
            "video": [VC_CREATE_VIDEO, 0],
            "filename_prefix": "AIStudio_video",
            "format": "auto",
            "codec": "auto",
        }

        return {
            VC_CREATE_VIDEO: {
                "class_type": "CreateVideo",
                "inputs": {
                    "images": [decode_ref, 0],
                    "fps": float(VIDEO_FPS),
                },
            },
            VC_SAVE: {
                "class_type": "SaveVideo",
                "inputs": save_inputs,
            },
        }

    raise ValueError(VHS_INSTALL_HINT)


def guess_media_type(filename: str, fallback: str = "application/octet-stream") -> str:
    lower = (filename or "").lower()
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".webm"):
        return "video/webm"
    if lower.endswith(".mov"):
        return "video/quicktime"
    if lower.endswith(".mkv"):
        return "video/x-matroska"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    return fallback


def _t5_encoder_installed() -> bool:
    for folder in ("text_encoders", "clip"):
        path = COMFY_MODELS_BASE / folder / LTX_T5_ENCODER
        if path.is_file():
            return True
    return False


def apply_style_prompt(prompt: str, style: str = "realistic") -> str:
    base = prompt.strip()
    suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["realistic"])
    if not base:
        return suffix
    return f"{base}, {suffix}"


def normalize_negative_prompt(negative: str) -> str:
    user = negative.strip()
    base_en = "blurry, low quality, watermark, text, ugly, bad anatomy"
    if not user:
        return base_en
    return f"{user}, {base_en}"


def normalize_video_negative(negative: str) -> str:
    user = negative.strip()
    if not user:
        return DEFAULT_VIDEO_NEGATIVE
    return f"{user}, {DEFAULT_VIDEO_NEGATIVE}"


def ltx_video_length(duration_sec: int, fps: int = VIDEO_FPS) -> int:
    """LTX 帧数：duration 秒 × fps + 1（例如 5 秒 → 121，3 秒 → 73）。"""
    return int(duration_sec) * fps + 1


def align_ltx_dimensions(width: int, height: int) -> tuple[int, int]:
    """LTX-Video 要求宽高为 32 的倍数。"""
    w = max(32, int(width))
    h = max(32, int(height))
    return (w // 32) * 32, (h // 32) * 32


def align_video_dimensions(width: int, height: int, *, multiple: int = 16) -> tuple[int, int]:
    """通用视频宽高对齐（Wan 等）。"""
    m = max(8, int(multiple))
    w = max(m, int(width))
    h = max(m, int(height))
    return (w // m) * m, (h // m) * m


def video_frame_length(duration_sec: int, fps: int = VIDEO_FPS) -> int:
    """通用视频帧数：duration 秒 × fps + 1。"""
    return int(duration_sec) * fps + 1


IMAGE_FILE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}


def _detect_task_type(workflow: dict | None) -> str:
    if not workflow:
        return "image"
    for node in workflow.values():
        if node.get("class_type") in VIDEO_WORKFLOW_CLASS:
            return "video"
    return "image"


def _extract_workflow_meta(workflow: dict | None) -> dict:
    if not workflow or not isinstance(workflow, dict):
        return {
            "prompt_text": None,
            "negative_text": None,
            "width": None,
            "height": None,
            "video_duration": None,
        }

    pos_text = None
    neg_text = None
    width = None
    height = None
    video_duration = None

    for node in workflow.values():
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "CLIPTextEncode":
            text = inputs.get("text")
            if pos_text is None:
                pos_text = text
            else:
                neg_text = text

    for key in (NODE_CLIP_POSITIVE, V_CLIP_POS, VC_POS):
        if key in workflow:
            pos_text = workflow[key].get("inputs", {}).get("text", pos_text)

    for key in (NODE_CLIP_NEGATIVE, V_CLIP_NEG, VC_NEG):
        if key in workflow:
            neg_text = workflow[key].get("inputs", {}).get("text", neg_text)

    for key in (NODE_EMPTY_LATENT, V_LATENT, VC_LATENT):
        if key in workflow:
            latent = workflow[key].get("inputs", {})
            width = latent.get("width")
            height = latent.get("height")
            length = latent.get("length")
            if length and VIDEO_FPS:
                video_duration = round((length - 1) / VIDEO_FPS, 1)

    for node in workflow.values():
        if node.get("class_type") == "LTXVImgToVideo":
            latent = node.get("inputs", {})
            width = latent.get("width", width)
            height = latent.get("height", height)
            length = latent.get("length")
            if length and VIDEO_FPS:
                video_duration = round((length - 1) / VIDEO_FPS, 1)

    return {
        "prompt_text": pos_text,
        "negative_text": neg_text,
        "width": width,
        "height": height,
        "video_duration": video_duration,
    }


def _extract_timestamps(data: dict) -> tuple[int | None, int | None, float | None]:
    started_at = None
    completed_at = None

    if data.get("timestamp") is not None:
        completed_at = data["timestamp"]

    for msg_type, msg_data in data.get("status", {}).get("messages", []):
        if not isinstance(msg_data, dict):
            continue
        ts = msg_data.get("timestamp")
        if ts is None:
            continue
        if msg_type == "execution_start":
            started_at = ts
        elif msg_type == "execution_success":
            completed_at = ts

    duration = None
    if started_at is not None and completed_at is not None:
        duration = round((completed_at - started_at) / 1000.0, 1)

    return started_at, completed_at, duration


def _base_task(
    prompt_id: str,
    status: str,
    status_text: str,
    workflow: dict | None = None,
    history_data: dict | None = None,
    images: list | None = None,
    videos: list | None = None,
    comfyui_node_url: str | None = None,
) -> dict:
    meta = _extract_workflow_meta(workflow)
    started_at, completed_at, duration = (None, None, None)
    if history_data:
        started_at, completed_at, duration = _extract_timestamps(history_data)

    timestamp = completed_at or started_at
    video_list = videos or []
    image_list = images or []
    is_video = len(video_list) > 0
    task_type = "video" if is_video else (_detect_task_type(workflow) if workflow else "image")
    primary = video_list[0] if video_list else (image_list[0] if image_list else None)
    result_media_type = (
        primary.get("media_kind", "video" if is_video else "image")
        if isinstance(primary, dict)
        else ("video" if is_video else "image")
    )

    return {
        "id": prompt_id,
        "status": status,
        "status_text": status_text,
        "task_type": task_type,
        "is_video": is_video,
        "result_media_type": result_media_type,
        "images": image_list,
        "videos": video_list,
        "timestamp": timestamp,
        "prompt_text": meta["prompt_text"],
        "negative_text": meta["negative_text"],
        "width": meta["width"],
        "height": meta["height"],
        "video_duration": meta["video_duration"],
        "duration": duration,
        "started_at": started_at,
        "completed_at": completed_at,
        "comfyui_node_url": comfyui_node_url,
    }


def build_sd15_workflow(
    positive_prompt: str,
    negative_prompt: str,
    steps: int = DEFAULT_STEPS,
    width: int = 512,
    height: int = 512,
    seed: int | None = None,
) -> dict:
    if seed is None:
        seed = random.randint(0, 2**53 - 1)

    positive_text = str(positive_prompt).strip()
    negative_text = str(negative_prompt).strip()

    return {
        NODE_KSAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": int(steps),
                "cfg": 8.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": [NODE_CHECKPOINT, 0],
                "positive": [NODE_CLIP_POSITIVE, 0],
                "negative": [NODE_CLIP_NEGATIVE, 0],
                "latent_image": [NODE_EMPTY_LATENT, 0],
            },
        },
        NODE_CHECKPOINT: {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": DEFAULT_CKPT},
        },
        NODE_EMPTY_LATENT: {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        NODE_CLIP_POSITIVE: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive_text,
                "clip": [NODE_CHECKPOINT, 1],
            },
        },
        NODE_CLIP_NEGATIVE: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_text,
                "clip": [NODE_CHECKPOINT, 1],
            },
        },
        NODE_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [NODE_KSAMPLER, 0],
                "vae": [NODE_CHECKPOINT, 2],
            },
        },
        NODE_SAVE_IMAGE: {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": [NODE_VAE_DECODE, 0],
            },
        },
    }


def build_ltx_video_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 512,
    height: int = 512,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
) -> dict:
    """
    LTX-Video 官方节点链（LTXVLoader + SamplerCustomAdvanced + LTXVDecoder + VHS_VideoCombine）。
    需要 ComfyUI 已注册 LTXVLoader / LTXVDecoder / VHS_VideoCombine 节点。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    length = ltx_video_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip()
    ckpt = (model_filename or LTX_CKPT).strip() or LTX_CKPT

    return {
        V_LOADER: {
            "class_type": "LTXVLoader",
            "inputs": {
                "ckpt_name": ckpt,
                "dtype": "bfloat16",
            },
        },
        V_CLIP_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [V_LOADER, 1],
            },
        },
        V_CLIP_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [V_LOADER, 1],
            },
        },
        V_LATENT: {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "length": length,
                "batch_size": 1,
            },
        },
        V_COND: {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": [V_CLIP_POS, 0],
                "negative": [V_CLIP_NEG, 0],
                "vae": [V_LOADER, 2],
                "latent": [V_LATENT, 0],
                "frame_rate": float(VIDEO_FPS),
            },
        },
        V_SCHEDULER: {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": VIDEO_STEPS,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": [V_LATENT, 0],
            },
        },
        V_NOISE: {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        V_SAMPLER_SEL: {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        V_GUIDER: {
            "class_type": "CFGGuider",
            "inputs": {
                "model": [V_LOADER, 0],
                "positive": [V_COND, 0],
                "negative": [V_COND, 2],
                "cfg": 3.0,
            },
        },
        V_SAMPLER: {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": [V_NOISE, 0],
                "guider": [V_GUIDER, 0],
                "sampler": [V_SAMPLER_SEL, 0],
                "sigmas": [V_SCHEDULER, 0],
                "latent_image": [V_COND, 1],
            },
        },
        V_DECODER: {
            "class_type": "LTXVDecoder",
            "inputs": {
                "samples": [V_SAMPLER, 0],
                "vae": [V_LOADER, 2],
                "enable_vae_tiling": False,
            },
        },
        V_SAVE: {
            "class_type": "VHS_VideoCombine",
            "inputs": _vhs_video_combine_inputs(V_DECODER),
        },
    }


def _load_ltx2_fp4_template() -> dict:
    return load_workflow_template(LTX2_WORKFLOW_KEY)


def _load_ltx2_fp4_i2v_template() -> dict:
    return load_workflow_template(LTX2_I2V_WORKFLOW_KEY)


def _load_ltx23_i2av_template() -> dict:
    return load_workflow_template(LTX23_WORKFLOW_KEY)


def _strip_ltx2_audio_branch(workflow: dict) -> None:
    """Remove AV concat/separate/audio VAE nodes and rewire video-only sampling."""
    # Drop audio-only + AV glue nodes (IDs from ltx2_fp4_t2v_api.json).
    for node_id in ("106", "109", "116", "117", "123", "124", "127"):
        workflow.pop(node_id, None)

    # I2V templates condition empty latents via 203/204; fall back to 108/118 for T2V.
    stage1_latent = ["203", 0] if "203" in workflow else ["108", 0]
    stage2_latent = ["204", 0] if "204" in workflow else ["118", 0]

    if "98" in workflow:
        workflow["98"]["inputs"]["latent"] = stage1_latent
    if "113" in workflow:
        workflow["113"]["inputs"]["latent_image"] = stage1_latent
    if "102" in workflow:
        workflow["102"]["inputs"]["latent"] = ["113", 0]
    if "119" in workflow:
        workflow["119"]["inputs"]["latent_image"] = stage2_latent
    if "125" in workflow:
        workflow["125"]["inputs"]["samples"] = ["119", 1]
    if "126" in workflow:
        workflow["126"]["inputs"]["samples"] = ["119", 1]
    if "122" in workflow:
        workflow["122"]["inputs"].pop("audio", None)
        workflow["122"]["inputs"]["audio"] = None


# LTX2 quality profiles（反馈调优：默认关 camera LoRA、quality 加步数）
LTX2_QUALITY_PROFILES: dict[str, dict] = {
    "fast": {
        "steps": 20,
        "cfg_stage1": 4.0,
        "cfg_stage2": 1.0,
        "stage2_sigmas": "0.909375, 0.725, 0.421875, 0.0",
        "distilled_strength": 1.0,
        "camera_lora_strength": 0.0,
    },
    "quality": {
        "steps": 28,
        "cfg_stage1": 4.5,
        "cfg_stage2": 1.2,
        "stage2_sigmas": "1.0, 0.909375, 0.725, 0.5, 0.25, 0.0",
        "distilled_strength": 0.85,
        "camera_lora_strength": 0.0,
        "i2v_img_compression": 20,
    },
}


def _normalize_ltx2_sampling_profile(sampling_profile: str | None) -> str:
    profile = (sampling_profile or "quality").strip().lower()
    return profile if profile in LTX2_QUALITY_PROFILES else "quality"


def _apply_ltx2_quality_tuning(
    workflow: dict,
    *,
    sampling_profile: str | None = "quality",
    camera_lora_strength: float | None = None,
    distilled_strength: float | None = None,
) -> str:
    """写入 steps/CFG/LoRA；默认关闭 dolly-left camera LoRA（模板硬编码 strength=1 会毁镜头）。"""
    profile_key = _normalize_ltx2_sampling_profile(sampling_profile)
    cfg = LTX2_QUALITY_PROFILES[profile_key]
    cam = (
        float(camera_lora_strength)
        if camera_lora_strength is not None
        else float(cfg["camera_lora_strength"])
    )
    dist = (
        float(distilled_strength)
        if distilled_strength is not None
        else float(cfg["distilled_strength"])
    )

    if "98" in workflow:
        workflow["98"]["inputs"]["steps"] = int(cfg["steps"])
    if "128" in workflow:
        workflow["128"]["inputs"]["cfg"] = float(cfg["cfg_stage1"])
    if "103" in workflow:
        workflow["103"]["inputs"]["cfg"] = float(cfg["cfg_stage2"])
    if "100" in workflow:
        workflow["100"]["inputs"]["sigmas"] = str(cfg["stage2_sigmas"])
    if "132" in workflow:
        workflow["132"]["inputs"]["strength_model"] = dist
    # 133/134 = camera control LoRA（默认 0，避免所有镜头被强制 dolly-left）
    for node_id in ("133", "134"):
        if node_id in workflow:
            workflow[node_id]["inputs"]["strength_model"] = cam

    # I2V：quality 档降低 img_compression，减轻首帧糊化
    i2v_comp = cfg.get("i2v_img_compression")
    if i2v_comp is not None and "202" in workflow:
        workflow["202"]["inputs"]["img_compression"] = int(i2v_comp)

    return profile_key


def build_ltx2_fp4_t2v_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    ckpt_name: str | None = None,
    audio: bool = False,
    sampling_profile: str | None = "quality",
    camera_lora_strength: float | None = None,
) -> dict:
    """
    LTX-2 19B fp4 文生视频（云绘 fp4 工作流 API 平坦子图）。
    两阶段采样 + 空间 2x 上采样；输出 SaveVideo MP4。
    audio=False 时旁路删除音画支路，仅输出静音视频。
    """
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    workflow = _load_ltx2_fp4_template()
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip()
    out_w, out_h = align_ltx_dimensions(width, height)
    latent_w, latent_h = align_ltx_dimensions(out_w // 2, out_h // 2)
    length = ltx_video_length(duration_sec)
    ckpt = (ckpt_name or model_filename or LTX2_CKPT).strip() or LTX2_CKPT

    workflow["121"]["inputs"]["text"] = positive
    workflow["110"]["inputs"]["text"] = negative
    workflow["111"]["inputs"]["width"] = out_w
    workflow["111"]["inputs"]["height"] = out_h
    workflow["108"]["inputs"]["width"] = latent_w
    workflow["108"]["inputs"]["height"] = latent_h
    workflow["108"]["inputs"]["length"] = length
    if "106" in workflow:
        workflow["106"]["inputs"]["frames_number"] = length
        workflow["106"]["inputs"]["frame_rate"] = VIDEO_FPS
    workflow["107"]["inputs"]["frame_rate"] = float(VIDEO_FPS)
    workflow["122"]["inputs"]["fps"] = float(VIDEO_FPS)
    workflow["115"]["inputs"]["noise_seed"] = int(seed)
    workflow["114"]["inputs"]["noise_seed"] = 0

    for node_id in ("99", "123", "138"):
        if node_id in workflow:
            workflow[node_id]["inputs"]["ckpt_name"] = ckpt
    if "99" in workflow:
        workflow["99"]["inputs"]["text_encoder"] = LTX2_GEMMA_ENCODER

    _apply_ltx2_quality_tuning(
        workflow,
        sampling_profile=sampling_profile,
        camera_lora_strength=camera_lora_strength,
    )

    if not audio:
        _strip_ltx2_audio_branch(workflow)

    return workflow



def build_ltx2_fp4_i2v_workflow(
    positive_prompt: str,
    negative_prompt: str,
    image_filename: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    ckpt_name: str | None = None,
    audio: bool = False,
    sampling_profile: str | None = "quality",
    camera_lora_strength: float | None = None,
) -> dict:
    """
    LTX-2 19B fp4 图生视频（云绘 fp4 I2V 工作流 API 平坦子图）。
    基于 T2V 模板，经 LTXVImgToVideoInplace 将首帧条件写入两阶段 latent。
    audio=False 时旁路删除音画支路，仅输出静音视频。
    """
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    workflow = _load_ltx2_fp4_i2v_template()
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip()
    out_w, out_h = align_ltx_dimensions(width, height)
    latent_w, latent_h = align_ltx_dimensions(out_w // 2, out_h // 2)
    length = ltx_video_length(duration_sec)
    ckpt = (ckpt_name or model_filename or LTX2_CKPT).strip() or LTX2_CKPT
    image_name = str(image_filename or "").strip()
    if not image_name:
        raise ValueError("LTX-2 I2V 需要 image_filename")

    workflow["121"]["inputs"]["text"] = positive
    workflow["110"]["inputs"]["text"] = negative
    workflow["111"]["inputs"]["width"] = out_w
    workflow["111"]["inputs"]["height"] = out_h
    workflow["108"]["inputs"]["width"] = latent_w
    workflow["108"]["inputs"]["height"] = latent_h
    workflow["108"]["inputs"]["length"] = length
    if "106" in workflow:
        workflow["106"]["inputs"]["frames_number"] = length
        workflow["106"]["inputs"]["frame_rate"] = VIDEO_FPS
    workflow["107"]["inputs"]["frame_rate"] = float(VIDEO_FPS)
    workflow["122"]["inputs"]["fps"] = float(VIDEO_FPS)
    workflow["115"]["inputs"]["noise_seed"] = int(seed)
    workflow["114"]["inputs"]["noise_seed"] = 0
    workflow["200"]["inputs"]["image"] = image_name

    for node_id in ("99", "123", "138"):
        if node_id in workflow:
            workflow[node_id]["inputs"]["ckpt_name"] = ckpt
    if "99" in workflow:
        workflow["99"]["inputs"]["text_encoder"] = LTX2_GEMMA_ENCODER

    _apply_ltx2_quality_tuning(
        workflow,
        sampling_profile=sampling_profile,
        camera_lora_strength=camera_lora_strength,
    )

    if not audio:
        _strip_ltx2_audio_branch(workflow)

    return workflow


def _normalize_resize_image_mask_inputs(inputs: dict) -> None:
    """ComfyUI V3 ResizeImageMaskNode 使用 resize_type.* 嵌套字段名。"""
    if inputs.get("resize_type") != "scale dimensions":
        return
    for key in ("width", "height", "crop"):
        if key in inputs:
            inputs[f"resize_type.{key}"] = inputs.pop(key)


def build_ltx23_i2av_workflow(
    positive_prompt: str,
    negative_prompt: str,
    image_filename: str,
    audio_filename: str | None = None,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    sampling_profile: str | None = "quality",
) -> dict:
    """LTX-2.3 图+音生视频（云绘 I2AV 模板，Kijai 分片权重）。"""
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    workflow = deepcopy(_load_ltx23_i2av_template())
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip()
    image_name = str(image_filename or "").strip()
    if not image_name:
        raise ValueError("LTX-2.3 I2AV 需要 image_filename")

    out_w, out_h = align_ltx_dimensions(width, height)
    length = int(duration_sec) * 25 + 1

    workflow["42"]["inputs"]["unet_name"] = LTX23_UNET
    workflow["43"]["inputs"]["clip_name1"] = LTX2_GEMMA_ENCODER
    workflow["43"]["inputs"]["clip_name2"] = LTX23_TEXT_PROJ
    workflow["46"]["inputs"]["lora_name"] = LTX23_DISTILLED_LORA
    workflow["51"]["inputs"]["vae_name"] = LTX23_AUDIO_VAE
    workflow["52"]["inputs"]["vae_name"] = LTX23_VIDEO_VAE
    workflow["35"]["inputs"]["text"] = negative
    workflow["36"]["inputs"]["text"] = positive
    workflow["48"]["inputs"]["image"] = image_name
    workflow["32"]["inputs"]["noise_seed"] = int(seed)
    workflow["22"]["inputs"]["width"] = out_w
    workflow["22"]["inputs"]["height"] = out_h
    workflow["22"]["inputs"]["length"] = length
    workflow.pop("62", None)

    if audio_filename:
        workflow["60"]["inputs"]["audio"] = str(audio_filename).strip()
        workflow["60"]["inputs"]["duration"] = int(duration_sec)
        workflow["60"]["inputs"]["start_time"] = 0
    else:
        for node_id in ("60", "61", "70", "15", "10"):
            workflow.pop(node_id, None)
        workflow["8"]["inputs"]["latent_image"] = ["23", 0]
        workflow["74"]["inputs"]["samples"] = ["8", 0]
        workflow["38"]["inputs"].pop("audio", None)

    if "33" in workflow:
        _normalize_resize_image_mask_inputs(workflow["33"]["inputs"])

    profile = (sampling_profile or "quality").strip().lower()
    if profile == "fast" and "59" in workflow:
        workflow["59"]["inputs"]["sigmas"] = (
            "1., 0.975, 0.909375, 0.725, 0.421875, 0.0"
        )
        if "46" in workflow:
            workflow["46"]["inputs"]["strength_model"] = 0.85
    elif "46" in workflow:
        workflow["46"]["inputs"]["strength_model"] = 0.7

    return workflow


def build_ltx_video_workflow_compat(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 512,
    height: int = 512,
    duration_sec: int = 5,
    seed: int | None = None,
    info: dict | None = None,
    *,
    model_filename: str | None = None,
) -> dict:
    """
    当前 ComfyUI 桌面版可用链：Checkpoint + CLIPLoader(T5) + SamplerCustomAdvanced。
    ltx-video-2b checkpoint 不含 CLIP 权重，必须单独提供 T5 文本编码器文件。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    length = ltx_video_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip()
    ckpt = (model_filename or LTX_CKPT).strip() or LTX_CKPT

    node_info = info if info is not None else {}
    workflow = {
        VC_CKPT: {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        VC_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": LTX_T5_ENCODER,
                "type": "ltxv",
            },
        },
        VC_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [VC_CLIP, 0],
            },
        },
        VC_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [VC_CLIP, 0],
            },
        },
        VC_LATENT: {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "length": length,
                "batch_size": 1,
            },
        },
        VC_COND: {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": [VC_POS, 0],
                "negative": [VC_NEG, 0],
                "frame_rate": float(VIDEO_FPS),
            },
        },
        VC_SCHEDULER: {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": VIDEO_STEPS,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": [VC_LATENT, 0],
            },
        },
        VC_NOISE: {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        VC_SAMPLER_SEL: {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        VC_GUIDER: {
            "class_type": "CFGGuider",
            "inputs": {
                "model": [VC_CKPT, 0],
                "positive": [VC_COND, 0],
                "negative": [VC_COND, 1],
                "cfg": 3.0,
            },
        },
        VC_SAMPLER: {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": [VC_NOISE, 0],
                "guider": [VC_GUIDER, 0],
                "sampler": [VC_SAMPLER_SEL, 0],
                "sigmas": [VC_SCHEDULER, 0],
                "latent_image": [VC_LATENT, 0],
            },
        },
        VC_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [VC_SAMPLER, 0],
                "vae": [VC_CKPT, 2],
            },
        },
    }

    workflow.update(_build_video_save_nodes(VC_DECODE, node_info))
    return workflow


def build_ltx_image2video_workflow_compat(
    positive_prompt: str,
    negative_prompt: str,
    image_filename: str,
    width: int = 512,
    height: int = 512,
    duration_sec: int = 5,
    seed: int | None = None,
    info: dict | None = None,
    *,
    model_filename: str | None = None,
) -> dict:
    workflow = build_ltx_video_workflow_compat(
        positive_prompt,
        negative_prompt,
        width,
        height,
        duration_sec,
        seed,
        info=info,
        model_filename=model_filename,
    )
    length = workflow[VC_LATENT]["inputs"]["length"]
    del workflow[VC_LATENT]

    workflow["14"] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_filename},
    }
    workflow["15"] = {
        "class_type": "LTXVImgToVideo",
        "inputs": {
            "positive": [VC_COND, 0],
            "negative": [VC_COND, 1],
            "vae": [VC_CKPT, 2],
            "image": ["14", 0],
            "width": int(width),
            "height": int(height),
            "length": length,
            "batch_size": 1,
            "strength": 1.0,
        },
    }
    workflow[VC_SAMPLER]["inputs"]["latent_image"] = ["15", 0]
    return workflow


def build_wan_video_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
) -> dict:
    """
    Wan 2.2 T2V：双 UNET + Lightx2v LoRA + 双 KSamplerAdvanced。
    默认 4 步；G31 quality 可传 steps=8（分段按 steps//2）。
    model_filename 保留兼容，当前忽略（固定使用 WAN22_T2V_* 权重名）。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    num_frames = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    shift = float(WAN22_MODEL_SAMPLING_SHIFT)
    steps = resolve_wan_steps(steps=steps)
    cfg = float(WAN22_T2V_CFG)
    mid, end = _wan_sampler_split(steps)

    studio_print(
        "comfyui-video",
        f"Wan2.2 T2V workflow: {width}x{height} frames={num_frames} seed={seed} steps={steps}",
    )

    return {
        W22_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": WAN_T5_ENCODER,
                "type": "wan",
                "device": "default",
            },
        },
        W22_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [W22_CLIP, 0],
            },
        },
        W22_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [W22_CLIP, 0],
            },
        },
        W22_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": WAN_VAE},
        },
        W22_EMPTY: {
            # ComfyUI 上游节点类名（Wan 2.2 T2V 复用；与已下线 Hunyuan 产品无关）
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "length": int(num_frames),
                "batch_size": 1,
            },
        },
        W22_UNET_H: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_T2V_HIGH,
                "weight_dtype": "default",
            },
        },
        W22_UNET_L: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_T2V_LOW,
                "weight_dtype": "default",
            },
        },
        W22_LORA_H: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22_UNET_H, 0],
                "lora_name": WAN22_LORA_HIGH,
                "strength_model": 1.0,
            },
        },
        W22_LORA_L: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22_UNET_L, 0],
                "lora_name": WAN22_LORA_LOW,
                "strength_model": 1.0,
            },
        },
        W22_MS_H: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22_LORA_H, 0],
                "shift": shift,
            },
        },
        W22_MS_L: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22_LORA_L, 0],
                "shift": shift,
            },
        },
        W22_SAMPLE_H: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22_MS_H, 0],
                "positive": [W22_POS, 0],
                "negative": [W22_NEG, 0],
                "latent_image": [W22_EMPTY, 0],
                "add_noise": "enable",
                "noise_seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": mid,
                "return_with_leftover_noise": "enable",
            },
        },
        W22_SAMPLE_L: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22_MS_L, 0],
                "positive": [W22_POS, 0],
                "negative": [W22_NEG, 0],
                "latent_image": [W22_SAMPLE_H, 0],
                "add_noise": "disable",
                "noise_seed": 0,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": mid,
                "end_at_step": end,
                "return_with_leftover_noise": "disable",
            },
        },
        W22_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [W22_SAMPLE_L, 0],
                "vae": [W22_VAE, 0],
            },
        },
        W22_CREATE: {
            "class_type": "CreateVideo",
            "inputs": {
                "images": [W22_DECODE, 0],
                "fps": float(VIDEO_FPS),
            },
        },
        W22_SAVE: {
            "class_type": "SaveVideo",
            "inputs": {
                "video": [W22_CREATE, 0],
                "filename_prefix": "AIStudio_video",
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def build_wan_i2v_workflow(
    positive_prompt: str,
    negative_prompt: str,
    image_filename: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
) -> dict:
    """
    Wan 2.2 I2V：LoadImage + WanImageToVideo + 双 UNET/Lightx2v LoRA。
    默认 4 步；G31 quality 可传 steps=8。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    image_name = str(image_filename or "").strip()
    if not image_name:
        raise ValueError("图生视频需要参考图文件名")

    num_frames = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    shift = float(WAN22_MODEL_SAMPLING_SHIFT)
    steps = resolve_wan_steps(steps=steps)
    cfg = float(WAN22_T2V_CFG)
    mid, end = _wan_sampler_split(steps)

    studio_print(
        "comfyui-video",
        f"Wan2.2 I2V workflow: {width}x{height} frames={num_frames} seed={seed} steps={steps}",
    )

    return {
        W22I_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": WAN_T5_ENCODER,
                "type": "wan",
                "device": "default",
            },
        },
        W22I_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [W22I_CLIP, 0],
            },
        },
        W22I_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [W22I_CLIP, 0],
            },
        },
        W22I_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": WAN_VAE},
        },
        W22I_LOAD: {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        W22I_I2V: {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": [W22I_POS, 0],
                "negative": [W22I_NEG, 0],
                "vae": [W22I_VAE, 0],
                "width": int(width),
                "height": int(height),
                "length": int(num_frames),
                "batch_size": 1,
                "start_image": [W22I_LOAD, 0],
            },
        },
        W22I_UNET_H: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_I2V_HIGH,
                "weight_dtype": "default",
            },
        },
        W22I_UNET_L: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_I2V_LOW,
                "weight_dtype": "default",
            },
        },
        W22I_LORA_H: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22I_UNET_H, 0],
                "lora_name": WAN22_I2V_LORA_HIGH,
                "strength_model": 1.0,
            },
        },
        W22I_LORA_L: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22I_UNET_L, 0],
                "lora_name": WAN22_I2V_LORA_LOW,
                "strength_model": 1.0,
            },
        },
        W22I_MS_H: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22I_LORA_H, 0],
                "shift": shift,
            },
        },
        W22I_MS_L: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22I_LORA_L, 0],
                "shift": shift,
            },
        },
        W22I_SAMPLE_H: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22I_MS_H, 0],
                "positive": [W22I_I2V, 0],
                "negative": [W22I_I2V, 1],
                "latent_image": [W22I_I2V, 2],
                "add_noise": "enable",
                "noise_seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": mid,
                "return_with_leftover_noise": "enable",
            },
        },
        W22I_SAMPLE_L: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22I_MS_L, 0],
                "positive": [W22I_I2V, 0],
                "negative": [W22I_I2V, 1],
                "latent_image": [W22I_SAMPLE_H, 0],
                "add_noise": "disable",
                "noise_seed": 0,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": mid,
                "end_at_step": end,
                "return_with_leftover_noise": "disable",
            },
        },
        W22I_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [W22I_SAMPLE_L, 0],
                "vae": [W22I_VAE, 0],
            },
        },
        W22I_CREATE: {
            "class_type": "CreateVideo",
            "inputs": {
                "images": [W22I_DECODE, 0],
                "fps": float(VIDEO_FPS),
            },
        },
        W22I_SAVE: {
            "class_type": "SaveVideo",
            "inputs": {
                "video": [W22I_CREATE, 0],
                "filename_prefix": "AIStudio_video",
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def build_wan_flf2v_workflow(
    positive_prompt: str,
    negative_prompt: str,
    start_image_filename: str,
    end_image_filename: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
) -> dict:
    """
    Wan 2.2 FLF2V：双 LoadImage + WanFirstLastFrameToVideo + 双 UNET/Lightx2v i2v LoRA。
    默认 4 步；G31 quality 可传 steps=8。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    start_name = str(start_image_filename or "").strip()
    end_name = str(end_image_filename or "").strip()
    if not start_name or not end_name:
        raise ValueError("首尾帧视频需要首帧与尾帧图片")

    num_frames = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    shift = float(WAN22_MODEL_SAMPLING_SHIFT)
    steps = resolve_wan_steps(steps=steps)
    cfg = float(WAN22_T2V_CFG)
    mid, end = _wan_sampler_split(steps)

    studio_print(
        "comfyui-video",
        f"Wan2.2 FLF2V workflow: {width}x{height} frames={num_frames} seed={seed} steps={steps}",
    )

    return {
        W22F_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": WAN_T5_ENCODER,
                "type": "wan",
                "device": "default",
            },
        },
        W22F_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [W22F_CLIP, 0],
            },
        },
        W22F_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [W22F_CLIP, 0],
            },
        },
        W22F_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": WAN_VAE},
        },
        W22F_LOAD_START: {
            "class_type": "LoadImage",
            "inputs": {"image": start_name},
        },
        W22F_LOAD_END: {
            "class_type": "LoadImage",
            "inputs": {"image": end_name},
        },
        W22F_FLF2V: {
            "class_type": "WanFirstLastFrameToVideo",
            "inputs": {
                "positive": [W22F_POS, 0],
                "negative": [W22F_NEG, 0],
                "vae": [W22F_VAE, 0],
                "width": int(width),
                "height": int(height),
                "length": int(num_frames),
                "batch_size": 1,
                "start_image": [W22F_LOAD_START, 0],
                "end_image": [W22F_LOAD_END, 0],
            },
        },
        W22F_UNET_H: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_I2V_HIGH,
                "weight_dtype": "default",
            },
        },
        W22F_UNET_L: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_I2V_LOW,
                "weight_dtype": "default",
            },
        },
        W22F_LORA_H: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22F_UNET_H, 0],
                "lora_name": WAN22_I2V_LORA_HIGH,
                "strength_model": 1.0,
            },
        },
        W22F_LORA_L: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22F_UNET_L, 0],
                "lora_name": WAN22_I2V_LORA_LOW,
                "strength_model": 1.0,
            },
        },
        W22F_MS_H: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22F_LORA_H, 0],
                "shift": shift,
            },
        },
        W22F_MS_L: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22F_LORA_L, 0],
                "shift": shift,
            },
        },
        W22F_SAMPLE_H: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22F_MS_H, 0],
                "positive": [W22F_FLF2V, 0],
                "negative": [W22F_FLF2V, 1],
                "latent_image": [W22F_FLF2V, 2],
                "add_noise": "enable",
                "noise_seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": mid,
                "return_with_leftover_noise": "enable",
            },
        },
        W22F_SAMPLE_L: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22F_MS_L, 0],
                "positive": [W22F_FLF2V, 0],
                "negative": [W22F_FLF2V, 1],
                "latent_image": [W22F_SAMPLE_H, 0],
                "add_noise": "disable",
                "noise_seed": 0,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": mid,
                "end_at_step": end,
                "return_with_leftover_noise": "disable",
            },
        },
        W22F_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [W22F_SAMPLE_L, 0],
                "vae": [W22F_VAE, 0],
            },
        },
        W22F_CREATE: {
            "class_type": "CreateVideo",
            "inputs": {
                "images": [W22F_DECODE, 0],
                "fps": float(VIDEO_FPS),
            },
        },
        W22F_SAVE: {
            "class_type": "SaveVideo",
            "inputs": {
                "video": [W22F_CREATE, 0],
                "filename_prefix": "AIStudio_video",
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def build_wan_fun_inpaint_workflow(
    positive_prompt: str,
    negative_prompt: str,
    start_image_filename: str,
    end_image_filename: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
) -> dict:
    """
    Wan 2.2 Fun Inpaint：双 LoadImage + WanFunInpaintToVideo + fun_inpaint 双 UNET + i2v Lightx2v LoRA。
    对齐官方 video_wan2_2_14B_fun_inpaint 四步组；默认 steps=4。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    start_name = str(start_image_filename or "").strip()
    end_name = str(end_image_filename or "").strip()
    if not start_name or not end_name:
        raise ValueError("Fun Inpaint 需要首帧与尾帧图片")

    num_frames = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    shift = float(WAN22_MODEL_SAMPLING_SHIFT)
    steps = resolve_wan_steps(steps=steps)
    cfg = float(WAN22_T2V_CFG)
    mid, end = _wan_sampler_split(steps)

    studio_print(
        "comfyui-video",
        f"Wan2.2 FunInpaint workflow: {width}x{height} frames={num_frames} "
        f"seed={seed} steps={steps}",
    )

    return {
        W22N_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": WAN_T5_ENCODER,
                "type": "wan",
                "device": "default",
            },
        },
        W22N_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [W22N_CLIP, 0],
            },
        },
        W22N_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [W22N_CLIP, 0],
            },
        },
        W22N_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": WAN_VAE},
        },
        W22N_LOAD_START: {
            "class_type": "LoadImage",
            "inputs": {"image": start_name},
        },
        W22N_LOAD_END: {
            "class_type": "LoadImage",
            "inputs": {"image": end_name},
        },
        W22N_FUN: {
            "class_type": "WanFunInpaintToVideo",
            "inputs": {
                "positive": [W22N_POS, 0],
                "negative": [W22N_NEG, 0],
                "vae": [W22N_VAE, 0],
                "width": int(width),
                "height": int(height),
                "length": int(num_frames),
                "batch_size": 1,
                "start_image": [W22N_LOAD_START, 0],
                "end_image": [W22N_LOAD_END, 0],
            },
        },
        W22N_UNET_H: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_FUN_INPAINT_HIGH,
                "weight_dtype": "default",
            },
        },
        W22N_UNET_L: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN22_FUN_INPAINT_LOW,
                "weight_dtype": "default",
            },
        },
        W22N_LORA_H: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22N_UNET_H, 0],
                "lora_name": WAN22_I2V_LORA_HIGH,
                "strength_model": 1.0,
            },
        },
        W22N_LORA_L: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [W22N_UNET_L, 0],
                "lora_name": WAN22_I2V_LORA_LOW,
                "strength_model": 1.0,
            },
        },
        W22N_MS_H: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22N_LORA_H, 0],
                "shift": shift,
            },
        },
        W22N_MS_L: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "model": [W22N_LORA_L, 0],
                "shift": shift,
            },
        },
        W22N_SAMPLE_H: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22N_MS_H, 0],
                "positive": [W22N_FUN, 0],
                "negative": [W22N_FUN, 1],
                "latent_image": [W22N_FUN, 2],
                "add_noise": "enable",
                "noise_seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": mid,
                "return_with_leftover_noise": "enable",
            },
        },
        W22N_SAMPLE_L: {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": [W22N_MS_L, 0],
                "positive": [W22N_FUN, 0],
                "negative": [W22N_FUN, 1],
                "latent_image": [W22N_SAMPLE_H, 0],
                "add_noise": "disable",
                "noise_seed": 0,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": mid,
                "end_at_step": end,
                "return_with_leftover_noise": "disable",
            },
        },
        W22N_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [W22N_SAMPLE_L, 0],
                "vae": [W22N_VAE, 0],
            },
        },
        W22N_CREATE: {
            "class_type": "CreateVideo",
            "inputs": {
                "images": [W22N_DECODE, 0],
                "fps": float(VIDEO_FPS),
            },
        },
        W22N_SAVE: {
            "class_type": "SaveVideo",
            "inputs": {
                "video": [W22N_CREATE, 0],
                "filename_prefix": "AIStudio_video",
                "format": "auto",
                "codec": "auto",
            },
        },
    }


HUNYUAN_DEFAULT_WIDTH = 1280
HUNYUAN_DEFAULT_HEIGHT = 720


def resolve_hunyuan_cache_backend(info: dict | None) -> str | None:
    """优先 MagCache（专支持 hunyuan_video1.5），否则 EasyCache。"""
    if _has_node("MagCache", info):
        return "magcache"
    if _has_node("EasyCache", info):
        return "easycache"
    return None


def build_hunyuan_video_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int = HUNYUAN_DEFAULT_WIDTH,
    height: int = HUNYUAN_DEFAULT_HEIGHT,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
    use_distilled: bool = False,
    cfg_distilled: bool = False,
    use_cache: bool = False,
    cache_backend: str | None = None,
) -> dict:
    """
    HunyuanVideo 1.5 T2V：UNET + DualCLIP(hunyuan_video_15) + EmptyHunyuanVideo15Latent。
    use_distilled=True → steps=12；cfg_distilled=True → cfg=1.0；
    use_cache=True → MagCache / EasyCache 接在 KSampler 前（cache_backend 可显式指定）。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    raw_ckpt = (model_filename or "").strip()
    # 仅支持 1.5；旧 13B 文件名一律回退到 1.5 权重
    if raw_ckpt and (
        "hunyuanvideo1.5" in raw_ckpt.lower()
        or "hunyuanvideo15" in raw_ckpt.lower()
        or "1.5" in raw_ckpt.lower()
    ):
        ckpt = raw_ckpt
    else:
        ckpt = HUNYUAN15_CKPT

    length = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE

    if use_distilled and steps is None:
        sample_steps = HUNYUAN15_DISTILLED_STEPS
    else:
        sample_steps = int(steps) if steps is not None else HUNYUAN15_DEFAULT_STEPS
    if sample_steps < 1:
        sample_steps = (
            HUNYUAN15_DISTILLED_STEPS if use_distilled else HUNYUAN15_DEFAULT_STEPS
        )
    sample_steps = min(sample_steps, HUNYUAN15_MAX_STEPS)

    cfg_value = HUNYUAN15_CFG_DISTILLED if cfg_distilled else HUNYUAN15_CFG_DEFAULT

    effective_backend = (cache_backend or "").strip().lower() if use_cache else ""
    if use_cache and not effective_backend:
        # 单测 / 未探测时默认 MagCache；线上 submit 会传入探测结果
        effective_backend = "magcache"

    studio_print(
        "comfyui-video",
        f"Hunyuan workflow: {ckpt} v=1.5 "
        f"{width}x{height} length={length} steps={sample_steps} cfg={cfg_value} "
        f"cache={use_cache} backend={effective_backend or '-'} distilled={use_distilled}",
    )

    dual_clip = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": HUNYUAN15_CLIP_QWEN,
            "clip_name2": HUNYUAN15_CLIP_BYT5,
            "type": "hunyuan_video_15",
        },
    }
    vae_name = HUNYUAN15_VAE
    latent_type = "EmptyHunyuanVideo15Latent"

    model_src = HY_UNET
    workflow: dict = {
        HY_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": ckpt,
                "weight_dtype": "default",
            },
        },
        HY_DUAL_CLIP: dual_clip,
        HY_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        },
        HY_CLIP_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive,
                "clip": [HY_DUAL_CLIP, 0],
            },
        },
        HY_CLIP_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative,
                "clip": [HY_DUAL_CLIP, 0],
            },
        },
        HY_EMPTY_LATENT: {
            "class_type": latent_type,
            "inputs": {
                "width": int(width),
                "height": int(height),
                "length": int(length),
                "batch_size": 1,
            },
        },
    }

    if use_cache and effective_backend == "magcache":
        workflow[HY_CACHE] = {
            "class_type": "MagCache",
            "inputs": {
                "model": [HY_UNET, 0],
                "model_type": "hunyuan_video1.5",
                "magcache_thresh": 0.06,
                "retention_ratio": 0.2,
                "magcache_K": 2,
                "start_step": 0,
                "end_step": -1,
            },
        }
        model_src = HY_CACHE
    elif use_cache and effective_backend == "easycache":
        workflow[HY_CACHE] = {
            "class_type": "EasyCache",
            "inputs": {
                "model": [HY_UNET, 0],
                "reuse_threshold": 0.2,
                "start_percent": 0.15,
                "end_percent": 0.95,
                "verbose": False,
            },
        }
        model_src = HY_CACHE

    # 官方 720p T2V flow shift=9
    workflow[HY_MODEL_SAMPLING] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": [model_src, 0],
            "shift": float(HUNYUAN_T2V_SHIFT),
        },
    }
    model_src = HY_MODEL_SAMPLING

    workflow[HY_SAMPLER] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": int(seed),
            "steps": sample_steps,
            "cfg": float(cfg_value),
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": [model_src, 0],
            "positive": [HY_CLIP_POS, 0],
            "negative": [HY_CLIP_NEG, 0],
            "latent_image": [HY_EMPTY_LATENT, 0],
        },
    }
    workflow[HY_DECODE] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [HY_SAMPLER, 0],
            "vae": [HY_VAE, 0],
        },
    }
    workflow[HY_SAVE] = {
        "class_type": "VHS_VideoCombine",
        "inputs": _vhs_video_combine_inputs(HY_DECODE),
    }
    return workflow


# Hunyuan 1.5 I2V 节点（与 T2V 共用部分 ID，独立工作流勿混用）
HY15I_CLIP_VISION = "50"
HY15I_CLIP_VISION_ENCODE = "51"
HY15I_LOAD = "52"
HY15I_I2V = "53"


def build_hunyuan_i2v_workflow(
    positive_prompt: str,
    negative_prompt: str,
    image_filename: str,
    width: int = HUNYUAN_DEFAULT_WIDTH,
    height: int = HUNYUAN_DEFAULT_HEIGHT,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
    use_distilled: bool = False,
    cfg_distilled: bool = False,
    use_cache: bool = False,
    cache_backend: str | None = None,
) -> dict:
    """
    HunyuanVideo 1.5 单帧 I2V：CLIPVision + HunyuanVideo15ImageToVideo。
    官方 720p：shift=7；非首尾帧 / 非全能参考。
    """
    if seed is None:
        seed = random.randint(0, 2**32)
    image_name = str(image_filename or "").strip()
    if not image_name:
        raise ValueError("图生视频需要参考图文件名")

    ckpt = (model_filename or "").strip() or HUNYUAN15_I2V_CKPT
    length = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE

    if use_distilled and steps is None:
        sample_steps = HUNYUAN15_DISTILLED_STEPS
    else:
        sample_steps = int(steps) if steps is not None else HUNYUAN15_DEFAULT_STEPS
    if sample_steps < 1:
        sample_steps = (
            HUNYUAN15_DISTILLED_STEPS if use_distilled else HUNYUAN15_DEFAULT_STEPS
        )
    sample_steps = min(sample_steps, HUNYUAN15_MAX_STEPS)
    cfg_value = HUNYUAN15_CFG_DISTILLED if cfg_distilled else HUNYUAN15_CFG_DEFAULT

    effective_backend = (cache_backend or "").strip().lower() if use_cache else ""
    if use_cache and not effective_backend:
        effective_backend = "magcache"

    studio_print(
        "comfyui-video",
        f"Hunyuan I2V workflow: {ckpt} {width}x{height} length={length} "
        f"steps={sample_steps} cfg={cfg_value} shift={HUNYUAN_I2V_SHIFT} "
        f"cache={use_cache} backend={effective_backend or '-'}",
    )

    model_src = HY_UNET
    workflow: dict = {
        HY_UNET: {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": ckpt, "weight_dtype": "default"},
        },
        HY_DUAL_CLIP: {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": HUNYUAN15_CLIP_QWEN,
                "clip_name2": HUNYUAN15_CLIP_BYT5,
                "type": "hunyuan_video_15",
            },
        },
        HY_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": HUNYUAN15_VAE},
        },
        HY_CLIP_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": [HY_DUAL_CLIP, 0]},
        },
        HY_CLIP_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": [HY_DUAL_CLIP, 0]},
        },
        HY15I_CLIP_VISION: {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": HUNYUAN15_CLIP_VISION},
        },
        HY15I_LOAD: {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        HY15I_CLIP_VISION_ENCODE: {
            "class_type": "CLIPVisionEncode",
            "inputs": {
                "clip_vision": [HY15I_CLIP_VISION, 0],
                "image": [HY15I_LOAD, 0],
                "crop": "center",
            },
        },
        HY15I_I2V: {
            "class_type": "HunyuanVideo15ImageToVideo",
            "inputs": {
                "positive": [HY_CLIP_POS, 0],
                "negative": [HY_CLIP_NEG, 0],
                "vae": [HY_VAE, 0],
                "width": int(width),
                "height": int(height),
                "length": int(length),
                "batch_size": 1,
                "start_image": [HY15I_LOAD, 0],
                "clip_vision_output": [HY15I_CLIP_VISION_ENCODE, 0],
            },
        },
    }

    if use_cache and effective_backend == "magcache":
        workflow[HY_CACHE] = {
            "class_type": "MagCache",
            "inputs": {
                "model": [HY_UNET, 0],
                "model_type": "hunyuan_video1.5",
                "magcache_thresh": 0.06,
                "retention_ratio": 0.2,
                "magcache_K": 2,
                "start_step": 0,
                "end_step": -1,
            },
        }
        model_src = HY_CACHE
    elif use_cache and effective_backend == "easycache":
        workflow[HY_CACHE] = {
            "class_type": "EasyCache",
            "inputs": {
                "model": [HY_UNET, 0],
                "reuse_threshold": 0.2,
                "start_percent": 0.15,
                "end_percent": 0.95,
                "verbose": False,
            },
        }
        model_src = HY_CACHE

    workflow[HY_MODEL_SAMPLING] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": [model_src, 0],
            "shift": float(HUNYUAN_I2V_SHIFT),
        },
    }
    model_src = HY_MODEL_SAMPLING

    # HunyuanVideo15ImageToVideo 输出：positive, negative, latent
    workflow[HY_SAMPLER] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": int(seed),
            "steps": sample_steps,
            "cfg": float(cfg_value),
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": [model_src, 0],
            "positive": [HY15I_I2V, 0],
            "negative": [HY15I_I2V, 1],
            "latent_image": [HY15I_I2V, 2],
        },
    }
    workflow[HY_DECODE] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": [HY_SAMPLER, 0], "vae": [HY_VAE, 0]},
    }
    workflow[HY_SAVE] = {
        "class_type": "VHS_VideoCombine",
        "inputs": _vhs_video_combine_inputs(HY_DECODE),
    }
    return workflow


# 会通过 ComfyUI progress 事件上报步数的采样节点
_SAMPLER_PROGRESS_TYPES = frozenset({
    "KSampler",
    "KSamplerAdvanced",
    "SamplerCustom",
    "SamplerCustomAdvanced",
})


def count_workflow_sampler_stages(workflow: dict | None) -> int:
    """统计工作流中会分段上报 progress 的采样器数量。"""
    if not isinstance(workflow, dict):
        return 1
    n = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in _SAMPLER_PROGRESS_TYPES:
            n += 1
    return max(1, n)


async def _log_and_post_video_workflow(
    workflow: dict,
    *,
    client_id: str | None,
    backend: str,
    width: int,
    height: int,
    duration: int,
    mode: str,
    task_id: str | None = None,
    estimated_duration_sec: int = 180,
    required_vram: int = 0,
    node_url: str | None = None,
) -> tuple[str, str, dict, str]:
    workflow_json = json.dumps(workflow, ensure_ascii=False, indent=2)
    logger.info(
        "submit_%s_video_prompt workflow (truncated): %s",
        backend,
        workflow_json[:4000],
    )
    studio_print(
        "comfyui-video",
        f"[{backend}] workflow 节点数={len(workflow)} size={width}x{height} "
        f"duration={duration}s mode={mode}",
    )
    studio_print("comfyui-video", "── workflow JSON 开始 ──")
    for line in workflow_json.splitlines():
        print(f"[AIStudio:comfyui-video] {line}", flush=True)
    studio_print("comfyui-video", "── workflow JSON 结束 ──")
    prompt_id, used_client, posted_node = await _post_workflow(
        workflow,
        client_id,
        task_id=task_id,
        estimated_duration_sec=estimated_duration_sec,
        required_vram=required_vram,
        node_url=node_url,
    )
    try:
        from services import comfyui_progress

        stages = count_workflow_sampler_stages(workflow)
        # 兼容：旧 LTX 官方链也可能双段；至少按 backend 保底
        if backend in ("wan", "ltx2") and stages < 2:
            stages = 2
        comfyui_progress.set_expected_stages(prompt_id, stages)
        studio_print(
            "comfyui-video",
            f"[{backend}] progress stages={stages} prompt_id={prompt_id}",
        )
    except Exception:
        pass
    studio_print(
        "comfyui-video",
        f"[{backend}] 已提交 prompt_id={prompt_id} client_id={used_client} node={posted_node}",
    )
    return prompt_id, used_client, workflow, posted_node


async def submit_by_workflow_key(
    key: str,
    *,
    patch_fn: Callable[[dict], dict] | None = None,
    workflow: dict | None = None,
    client_id: str | None = None,
    node_url: str | None = None,
    estimated_duration_sec: int = 120,
    required_vram: int = 0,
    prefer_short: bool = True,
    as_video: bool = False,
    backend: str = "workflow_key",
    task_id: str | None = None,
    width: int = 0,
    height: int = 0,
    duration: int = 0,
    mode: str = "workflow",
) -> tuple:
    """Load workflow by registry key, optionally patch, then submit via existing gpu_pool paths."""
    wf = deepcopy(workflow) if workflow is not None else deepcopy(load_workflow_template(key))
    if patch_fn is not None:
        wf = patch_fn(wf)
    if as_video:
        return await _log_and_post_video_workflow(
            wf,
            client_id=client_id,
            backend=backend,
            width=width,
            height=height,
            duration=duration,
            mode=mode,
            task_id=task_id,
            estimated_duration_sec=estimated_duration_sec,
            required_vram=required_vram,
            node_url=node_url,
        )
    prompt_id, used_client, posted_node = await _post_workflow(
        wf,
        client_id,
        task_id=task_id,
        estimated_duration_sec=estimated_duration_sec,
        required_vram=required_vram,
        prefer_short=prefer_short,
        node_url=node_url,
    )
    return prompt_id, used_client, posted_node


async def _resolve_video_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    duration_sec: int,
    mode: str,
    image_filename: str | None,
    *,
    model_filename: str | None = None,
) -> dict:
    ckpt = (model_filename or LTX_CKPT).strip() or LTX_CKPT
    info = await _fetch_object_info()

    use_official = (
        _has_node("LTXVLoader", info)
        and _has_node("LTXVDecoder", info)
        and _has_node("VHS_VideoCombine", info)
    )

    if use_official:
        if mode == "image2video" and image_filename:
            raise ValueError("官方 LTXVLoader 工作流暂不支持图生视频，请使用兼容模式")
        return build_ltx_video_workflow(
            positive_prompt,
            negative_prompt,
            width,
            height,
            duration_sec,
            model_filename=ckpt,
        )

    if not _t5_encoder_installed():
        raise ValueError(LTX_T5_DOWNLOAD_HINT)

    if mode == "image2video":
        if not image_filename:
            raise ValueError("图生视频需要上传图片")
        return build_ltx_image2video_workflow_compat(
            positive_prompt,
            negative_prompt,
            image_filename,
            width,
            height,
            duration_sec,
            info=info,
            model_filename=ckpt,
        )

    return build_ltx_video_workflow_compat(
        positive_prompt,
        negative_prompt,
        width,
        height,
        duration_sec,
        info=info,
        model_filename=ckpt,
    )


async def upload_image_from_url(image_url: str, *, node_url: str | None = None) -> str:
    """
    将服务器本地路径或 http URL 的图片上传到 ComfyUI，返回 ComfyUI filename。
    支持:
      - /uploads/images/xxx.jpg  (本地文件路径)
      - http://127.0.0.1:7788/uploads/images/xxx.jpg
    """
    # 本地文件路径
    if image_url.startswith("/uploads/") or (not image_url.startswith("http")):
        # 尝试从磁盘读取
        local_path = Path(image_url.lstrip("/"))
        if not local_path.is_file():
            raise ValueError(f"参考图文件不存在: {local_path}")
        data = local_path.read_bytes()
        suffix = local_path.suffix or ".jpg"
        mime = "image/jpeg" if suffix.lower() in (".jpg", ".jpeg") else "image/png"
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{_resolve_comfyui_base(node_url)}/upload/image",
                files={"image": (local_path.name, data, mime)},
            )
            res.raise_for_status()
            return res.json().get("name") or ""
    # HTTP URL
    async with httpx.AsyncClient(timeout=30.0) as client:
        img_res = await client.get(image_url)
        img_res.raise_for_status()
        data = img_res.content
        ct = img_res.headers.get("content-type", "image/jpeg")
        fname = image_url.split("/")[-1] or "ref.jpg"
        res = await client.post(
            f"{_resolve_comfyui_base(node_url)}/upload/image",
            files={"image": (fname, data, ct)},
        )
        res.raise_for_status()
        return res.json().get("name") or ""


async def upload_image_base64(image_b64: str, *, node_url: str | None = None) -> str:
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    data = base64.b64decode(image_b64)
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{_resolve_comfyui_base(node_url)}/upload/image",
            files={"image": ("upload.png", data, "image/png")},
        )
        res.raise_for_status()
        payload = res.json()
    name = payload.get("name")
    if not name:
        raise ValueError("图片上传失败")
    return name


async def _post_workflow(
    workflow: dict,
    client_id: str | None,
    *,
    task_id: str | None = None,
    estimated_duration_sec: int = 120,
    required_vram: int = 0,
    prefer_short: bool = True,
    node_url: str | None = None,
) -> tuple[str, str, str]:
    if client_id is None:
        client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    from services.gpu_pool import get_gpu_pool

    pool = get_gpu_pool()
    candidate_urls: list[str]
    if node_url:
        candidate_urls = [node_url.rstrip("/")]
    else:
        node = pool.get_available_node(
            required_vram=required_vram,
            prefer_short=prefer_short,
            estimated_duration_sec=estimated_duration_sec,
        )
        candidate_urls = [node.comfyui_url.rstrip("/")]
        for n in pool.nodes:
            url = n.comfyui_url.rstrip("/")
            if url in candidate_urls:
                continue
            if required_vram > 0 and n.available_vram < required_vram:
                continue
            candidate_urls.append(url)

    last_error: Exception | None = None
    for base_url in candidate_urls:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{base_url}/prompt", json=payload)
                res.raise_for_status()
                data = res.json()
            break
        except (httpx.ConnectError, httpx.HTTPError) as exc:
            last_error = exc
            logger.warning("_post_workflow retry next node after %s: %s", base_url, exc)
    else:
        if last_error is not None:
            raise last_error
        raise RuntimeError("无可用 ComfyUI 节点")
    if data.get("node_errors"):
        raise ValueError(f"工作流节点错误: {data['node_errors']}")
    if data.get("error"):
        raise ValueError(f"ComfyUI 拒绝工作流: {data['error']}")
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise ValueError("ComfyUI 未返回 prompt_id")
    occupy_task_id = task_id or str(prompt_id)
    pool.mark_busy_by_url(base_url, occupy_task_id, estimated_duration_sec)
    return str(prompt_id), client_id, base_url


async def submit_prompt(
    prompt: str,
    negative_prompt: str = "blurry, low quality, watermark, text",
    style: str = "realistic",
    steps: int = DEFAULT_STEPS,
    width: int = 512,
    height: int = 512,
    client_id: str | None = None,
    raw_prompt: bool = False,
    reference_image: str | None = None,
) -> tuple[str, str, str]:
    if raw_prompt:
        positive = str(prompt).strip()
        negative = str(negative_prompt).strip()
    else:
        positive = apply_style_prompt(prompt, style)
        negative = normalize_negative_prompt(negative_prompt)
    workflow = build_sd15_workflow(
        positive_prompt=positive,
        negative_prompt=negative,
        steps=steps,
        width=width,
        height=height,
    )
    if reference_image:
        try:
            reserved_node = _acquire_gpu_node_url()
            ref_filename = await upload_image_from_url(
                reference_image, node_url=reserved_node
            )
            if ref_filename:
                workflow["ref_load"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": ref_filename, "upload": "image"},
                }
        except Exception as e:
            print(f"[comfyui] 参考图上传失败，跳过: {e}")
            reserved_node = None
    else:
        reserved_node = None
    return await _post_workflow(workflow, client_id, node_url=reserved_node)


async def submit_video_prompt(
    prompt: str,
    negative_prompt: str = "",
    duration: int = 5,
    width: int = 848,
    height: int = 480,
    mode: str = "text2video",
    image_b64: str | None = None,
    client_id: str | None = None,
    raw_prompt: bool = False,
    *,
    model_filename: str | None = None,
) -> tuple[str, str, dict, str]:
    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_ltx_dimensions(width, height)

    image_filename = None
    reserved_node = None
    if mode == "image2video":
        if not image_b64:
            raise ValueError("图生视频需要上传图片")
        reserved_node = _acquire_gpu_node_url(
            estimated_duration_sec=max(120, duration * 30), required_vram=16
        )
        image_filename = await upload_image_base64(image_b64, node_url=reserved_node)

    await ensure_video_mp4_capable(reserved_node)

    logger.info(
        "submit_video_prompt inputs: mode=%s duration=%s width=%s height=%s "
        "raw_prompt=%s has_image=%s prompt_len=%s",
        mode,
        duration,
        width,
        height,
        raw_prompt,
        bool(image_filename),
        len(positive or ""),
    )
    workflow = await _resolve_video_workflow(
        positive,
        negative,
        width,
        height,
        duration,
        mode,
        image_filename,
        model_filename=model_filename,
    )
    prompt_id, used_client, workflow, _node_url = await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="ltx",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
        node_url=reserved_node,
    )
    return prompt_id, used_client, workflow, _node_url


async def submit_wan_video_prompt(
    prompt: str,
    negative_prompt: str = "",
    duration: int = 5,
    width: int = 848,
    height: int = 480,
    mode: str = "text2video",
    image_b64: str | None = None,
    start_image_b64: str | None = None,
    end_image_b64: str | None = None,
    client_id: str | None = None,
    raw_prompt: bool = False,
    *,
    model_filename: str | None = None,
    sampling_profile: str | None = None,
    steps: int | None = None,
) -> tuple[str, str, dict, str]:
    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_video_dimensions(width, height)
    wan_steps = resolve_wan_steps(sampling_profile=sampling_profile, steps=steps)

    image_filename = None
    start_image_filename = None
    end_image_filename = None
    reserved_node = None
    if mode in ("flf2v", "fun_inpaint"):
        if not start_image_b64 or not end_image_b64:
            raise ValueError("首尾帧视频需要首帧与尾帧图片")
        reserved_node = _acquire_gpu_node_url(
            estimated_duration_sec=max(120, duration * 30), required_vram=16
        )
        start_image_filename = await upload_image_base64(
            start_image_b64, node_url=reserved_node
        )
        end_image_filename = await upload_image_base64(
            end_image_b64, node_url=reserved_node
        )
    elif mode == "image2video":
        if not image_b64:
            raise ValueError("图生视频需要上传图片")
        reserved_node = _acquire_gpu_node_url(
            estimated_duration_sec=max(120, duration * 30), required_vram=16
        )
        image_filename = await upload_image_base64(image_b64, node_url=reserved_node)

    await ensure_video_mp4_capable(reserved_node)

    logger.info(
        "submit_wan_video_prompt inputs: mode=%s duration=%s width=%s height=%s "
        "prompt_len=%s steps=%s profile=%s",
        mode,
        duration,
        width,
        height,
        len(positive or ""),
        wan_steps,
        sampling_profile or "fast",
    )
    if mode == "fun_inpaint":
        workflow = build_wan_fun_inpaint_workflow(
            positive,
            negative,
            start_image_filename,
            end_image_filename,
            width,
            height,
            duration,
            model_filename=model_filename,
            steps=wan_steps,
        )
    elif mode == "flf2v":
        workflow = build_wan_flf2v_workflow(
            positive,
            negative,
            start_image_filename,
            end_image_filename,
            width,
            height,
            duration,
            model_filename=model_filename,
            steps=wan_steps,
        )
    elif mode == "image2video":
        workflow = build_wan_i2v_workflow(
            positive,
            negative,
            image_filename,
            width,
            height,
            duration,
            model_filename=model_filename,
            steps=wan_steps,
        )
    else:
        workflow = build_wan_video_workflow(
            positive,
            negative,
            width,
            height,
            duration,
            model_filename=model_filename,
            steps=wan_steps,
        )
    return await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="wan",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
        node_url=reserved_node,
    )


async def submit_hunyuan_video_prompt(
    prompt: str,
    negative_prompt: str = "",
    duration: int = 5,
    width: int = HUNYUAN_DEFAULT_WIDTH,
    height: int = HUNYUAN_DEFAULT_HEIGHT,
    mode: str = "text2video",
    image_b64: str | None = None,
    client_id: str | None = None,
    raw_prompt: bool = False,
    *,
    model_filename: str | None = None,
    steps: int | None = None,
    use_distilled: bool = False,
    cfg_distilled: bool = False,
    use_cache: bool = True,
) -> tuple[str, str, dict, str]:
    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_video_dimensions(width, height)

    if mode not in ("text2video", "image2video"):
        raise ValueError(f"HunyuanVideo 不支持 mode={mode}（首尾帧请用 wan-i2v）")
    if mode == "image2video" and not image_b64:
        raise ValueError("图生视频需要上传图片")

    reserved_node = _acquire_gpu_node_url(
        estimated_duration_sec=480,
        required_vram=HUNYUAN_REQUIRED_VRAM,
        prefer_short=False,
    )
    await ensure_video_mp4_capable(reserved_node)

    cache_backend: str | None = None
    effective_cache = bool(use_cache)
    info: dict | None = None
    try:
        info = await _fetch_object_info(reserved_node)
    except (httpx.ConnectError, httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("hunyuan object_info probe failed on %s: %s", reserved_node, exc)
    if effective_cache:
        cache_backend = resolve_hunyuan_cache_backend(info)
        if not cache_backend:
            logger.warning(
                "H800 无 MagCache/EasyCache，禁用 cache 继续生成 node=%s",
                reserved_node,
            )
            effective_cache = False

    image_filename: str | None = None
    if mode == "image2video":
        if info is not None and not _has_node("HunyuanVideo15ImageToVideo", info):
            raise ValueError("当前 ComfyUI 缺少 HunyuanVideo15ImageToVideo 节点")
        image_filename = await upload_image_base64(image_b64, node_url=reserved_node)

    default_ckpt = HUNYUAN15_I2V_CKPT if mode == "image2video" else HUNYUAN15_CKPT
    # registry 里 hunyuan-video-1.5 登记的是 T2V 文件名；图生时忽略，强制 I2V 权重
    if mode == "image2video":
        resolved_ckpt = HUNYUAN15_I2V_CKPT
    else:
        resolved_ckpt = (model_filename or "").strip() or default_ckpt
    logger.info(
        "submit_hunyuan_video_prompt inputs: mode=%s duration=%s width=%s height=%s "
        "prompt_len=%s steps=%s distilled=%s cfg_distilled=%s cache=%s backend=%s "
        "ckpt=%s node=%s",
        mode,
        duration,
        width,
        height,
        len(positive or ""),
        steps
        if steps is not None
        else (HUNYUAN15_DISTILLED_STEPS if use_distilled else HUNYUAN15_DEFAULT_STEPS),
        use_distilled,
        cfg_distilled,
        effective_cache,
        cache_backend or "-",
        resolved_ckpt,
        reserved_node,
    )
    if mode == "image2video":
        workflow = build_hunyuan_i2v_workflow(
            positive,
            negative,
            image_filename or "",
            width,
            height,
            duration,
            model_filename=resolved_ckpt,
            steps=steps,
            use_distilled=use_distilled,
            cfg_distilled=cfg_distilled,
            use_cache=effective_cache,
            cache_backend=cache_backend,
        )
    else:
        workflow = build_hunyuan_video_workflow(
            positive,
            negative,
            width,
            height,
            duration,
            model_filename=resolved_ckpt,
            steps=steps,
            use_distilled=use_distilled,
            cfg_distilled=cfg_distilled,
            use_cache=effective_cache,
            cache_backend=cache_backend,
        )
    return await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="hunyuan",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
        estimated_duration_sec=480,
        required_vram=HUNYUAN_REQUIRED_VRAM,
        node_url=reserved_node,
    )


async def submit_ltx2_video_prompt(
    prompt: str,
    negative_prompt: str = "",
    duration: int = 5,
    width: int = 848,
    height: int = 480,
    mode: str = "text2video",
    image_b64: str | None = None,
    client_id: str | None = None,
    raw_prompt: bool = False,
    *,
    model_filename: str | None = None,
    audio: bool = False,
    sampling_profile: str | None = "quality",
    camera_lora_strength: float | None = None,
    **_ignored,
) -> tuple[str, str, dict, str]:
    """LTX-2 19B fp4 文生/图生视频（ComfyUI SaveVideo MP4）。"""
    if mode not in ("text2video", "image2video"):
        raise ValueError("LTX-2 fp4 workflow 仅支持文生视频或图生视频")

    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_ltx_dimensions(width, height)
    profile = _normalize_ltx2_sampling_profile(sampling_profile)

    image_filename = None
    reserved_node = None
    if mode == "image2video":
        if not image_b64:
            raise ValueError("图生视频需要上传图片")
        reserved_node = _acquire_gpu_node_url(
            estimated_duration_sec=max(120, duration * 30), required_vram=16
        )
        image_filename = await upload_image_base64(image_b64, node_url=reserved_node)

    await ensure_video_mp4_capable(reserved_node)

    logger.info(
        "submit_ltx2_video_prompt inputs: mode=%s duration=%s width=%s height=%s "
        "audio=%s profile=%s prompt_len=%s",
        mode,
        duration,
        width,
        height,
        bool(audio),
        profile,
        len(positive or ""),
    )
    common_kw = dict(
        model_filename=model_filename,
        audio=bool(audio),
        sampling_profile=profile,
        camera_lora_strength=camera_lora_strength,
    )
    if mode == "image2video":
        workflow = build_ltx2_fp4_i2v_workflow(
            positive,
            negative,
            image_filename,
            width,
            height,
            duration,
            **common_kw,
        )
    else:
        workflow = build_ltx2_fp4_t2v_workflow(
            positive,
            negative,
            width,
            height,
            duration,
            **common_kw,
        )
    return await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="ltx2",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
        node_url=reserved_node,
    )


async def get_comfyui_output_dir(node_url: str | None = None) -> Path:
    """从 ComfyUI system_stats 解析 output 目录。"""
    base = _resolve_comfyui_base(node_url)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        res = await client.get(f"{base}/system_stats")
        res.raise_for_status()
        data = res.json()

    argv = data.get("system", {}).get("argv", [])
    for i, arg in enumerate(argv):
        if arg == "--output-directory" and i + 1 < len(argv):
            return Path(argv[i + 1])

    return Path("/root/autodl-tmp/ComfyUI/output")


def _scan_output_storage(output_dir: Path) -> dict:
    images_count = 0
    videos_count = 0
    total_bytes = 0

    if not output_dir.is_dir():
        return {
            "images_count": 0,
            "videos_count": 0,
            "total_size_mb": 0.0,
        }

    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        size = path.stat().st_size
        total_bytes += size
        if _is_video_file(path.name):
            videos_count += 1
        elif ext in IMAGE_FILE_EXTENSIONS:
            images_count += 1

    return {
        "images_count": images_count,
        "videos_count": videos_count,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
    }


async def get_storage_info() -> dict:
    nodes = comfyui_nodes_list()
    output_dir = await get_comfyui_output_dir(nodes[0] if nodes else None)
    stats = _scan_output_storage(output_dir)
    return {
        "comfyui_output": str(output_dir.resolve()),
        "comfyui_nodes": nodes,
        **stats,
    }


async def cancel_task(task_id: str, node_url: str | None = None) -> None:
    base = _resolve_comfyui_base(node_url)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        res = await client.post(
            f"{base}/queue",
            json={"delete": [task_id]},
        )
        res.raise_for_status()
    from services.gpu_pool import release_gpu_node

    release_gpu_node(base)


async def interrupt_execution(node_url: str | None = None) -> None:
    """中断指定 ComfyUI 节点上当前正在执行的 workflow。"""
    base = _resolve_comfyui_base(node_url)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        res = await client.post(f"{base}/interrupt")
        res.raise_for_status()


def _view_url_for_media(entry: dict, node_url: str | None = None) -> str:
    from urllib.parse import quote

    filename = entry.get("filename") or ""
    media_type = entry.get("type") or "output"
    subfolder = entry.get("subfolder") or ""
    params = f"filename={quote(filename, safe='')}&type={media_type}"
    if subfolder:
        params += f"&subfolder={quote(subfolder, safe='')}"
    port = comfyui_node_port(node_url)
    if port:
        params += f"&node={quote(port, safe='')}"
    return f"/api/view?{params}"


def _extract_execution_error_text(payload) -> str:
    """从 ComfyUI execution_error 载荷提取可读异常文本（避免把整段 dict/traceback 塞给前端）。"""
    if payload is None:
        return ""
    if isinstance(payload, dict):
        msg = payload.get("exception_message") or payload.get("message") or ""
        exc_type = payload.get("exception_type") or ""
        text = str(msg).strip()
        if exc_type and text and str(exc_type) not in text:
            return f"{exc_type}: {text}"
        return text or str(exc_type).strip()
    return str(payload).strip()


def _history_error_message(entry: dict) -> str:
    status = entry.get("status") or {}
    if status.get("status_str") != "error":
        return "ComfyUI 执行失败"
    messages = status.get("messages") or []
    for msg in messages:
        if (
            isinstance(msg, (list, tuple))
            and len(msg) >= 2
            and msg[0] == "execution_error"
        ):
            return map_comfy_execution_error(_extract_execution_error_text(msg[1]))
    return "ComfyUI 执行失败"


def map_comfy_execution_error(message: str) -> str:
    """将 ComfyUI 执行/提交异常映射为面向用户的短文案。"""
    raw = (message or "").strip()
    lower = raw.lower()
    if not raw:
        return "生成失败，请稍后重试"
    if (
        "out of memory" in lower
        or "outofmemory" in lower
        or "cuda oom" in lower
        or "torch.cuda.outofmemoryerror" in lower
        or "allocation on device" in lower
    ):
        return "显存不足（GPU OOM）。此模型最高支持 720P，请降低清晰度后重试；也可先停止其他生成任务释放显存。"
    if "非法上传路径" in raw or "视频源无效" in raw:
        return "视频源无效或无权访问"
    if "vhs" in lower or "video helper suite" in lower:
        return "缺少 Video Helper Suite 插件，无法处理视频"
    if "not found" in lower or "does not exist" in lower or "找不到" in raw:
        if "seedvr" in lower or "realesrgan" in lower or "safetensors" in lower or ".pth" in lower:
            return f"缺少画质增强模型或插件：{raw[:180]}"
        return f"缺少所需模型或节点：{raw[:180]}"
    if "node_errors" in lower or "工作流节点错误" in raw:
        return f"工作流配置错误：{raw[:180]}"
    # 截断超长英文堆栈，避免卡片里出现「乱码墙」
    if len(raw) > 240:
        return raw[:240].rstrip() + "…"
    return raw


def map_enhance_submit_error(message: str) -> str:
    """将提交阶段异常映射为面向用户的画质增强错误文案。"""
    return map_comfy_execution_error(message)


def map_enhance_execution_error(message: str) -> str:
    """将 ComfyUI 执行错误映射为友好文案。"""
    return map_comfy_execution_error(message)


def _execution_status_failed(
    error: str,
    *,
    progress: int = 0,
    stage: str = "error",
) -> dict:
    return {
        "status": "failed",
        "progress": progress,
        "stage": stage,
        "message": None,
        "result": None,
        "error": error,
    }


def _execution_status_running(
    *,
    progress: int = 0,
    stage: str | None = "running",
    message: str | None = None,
) -> dict:
    shown = progress if progress > 0 else 3
    return {
        "status": "running",
        "progress": shown,
        "stage": stage or "running",
        "message": message,
        "result": None,
        "error": None,
    }


def _cache_age_seconds(cached: dict) -> float:
    updated_at = cached.get("updated_at")
    if not updated_at:
        return float("inf")
    try:
        return max(0.0, time.time() - float(updated_at))
    except (TypeError, ValueError):
        return float("inf")


def _should_fetch_comfy_http(prompt_id: str, *, force: bool = False) -> bool:
    if force:
        now = time.time()
        with _poll_fetch_lock:
            _last_comfy_fetch[str(prompt_id)] = now
        return True
    now = time.time()
    pid = str(prompt_id)
    with _poll_fetch_lock:
        last = _last_comfy_fetch.get(pid, 0.0)
        if now - last < COMFY_POLL_THROTTLE_SEC:
            return False
        _last_comfy_fetch[pid] = now
        return True


def reset_comfy_poll_throttle_for_tests() -> None:
    with _poll_fetch_lock:
        _last_comfy_fetch.clear()


async def probe_comfy_prompt_liveness(
    prompt_id: str,
    node_url: str | None = None,
) -> dict:
    """
    超时/僵尸回收专用：强制查 Comfy 队列与 history，不走轮询节流短路。

    返回:
      state: busy | idle | unreachable
      status/result/error: 便于回收时直接 completed/failed
    """
    from services import comfyui_progress

    pid = str(prompt_id or "").strip()
    if not pid:
        return {"state": "idle", "status": "failed", "result": None, "error": "缺少 prompt_id"}

    base = _resolve_comfyui_base(node_url)
    cached = comfyui_progress.get_progress(pid) or {}
    progress = int(cached.get("progress") or 0)
    cache_age = _cache_age_seconds(cached)

    # 近期仍有 sampler 进度 → 视为仍在跑（即使 /queue 瞬时空）
    if progress > 0 and progress < 100 and cache_age <= max(COMFY_POLL_CACHE_FRESH_SEC, 30.0):
        return {
            "state": "busy",
            "status": "running",
            "progress": progress,
            "result": None,
            "error": None,
        }

    in_running = False
    in_pending = False
    hist_res = None
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            queue_res = await client.get(f"{base}/queue")
            hist_res = await client.get(f"{base}/history/{pid}")
        queue_data = queue_res.json()
        for item in queue_data.get("queue_running", []) or []:
            if len(item) > 1 and str(item[1]) == pid:
                in_running = True
                break
        for item in queue_data.get("queue_pending", []) or []:
            if len(item) > 1 and str(item[1]) == pid:
                in_pending = True
                break
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        studio_print("comfyui", f"liveness 不可达 prompt_id={pid}: {exc}")
        return {
            "state": "unreachable",
            "status": "running",
            "progress": progress,
            "result": None,
            "error": None,
        }
    except Exception as exc:
        logger.exception("probe_comfy_prompt_liveness error prompt_id=%s", pid)
        studio_print("comfyui", f"liveness 查询异常 prompt_id={pid}: {exc}")
        return {
            "state": "unreachable",
            "status": "running",
            "progress": progress,
            "result": None,
            "error": None,
        }

    if in_running or in_pending:
        return {
            "state": "busy",
            "status": "running" if in_running else "pending",
            "progress": progress if progress > 0 else (3 if in_running else 0),
            "result": None,
            "error": None,
        }

    if hist_res is not None and hist_res.status_code == 200:
        try:
            payload = hist_res.json()
        except Exception:
            payload = {}
        if pid in payload:
            # 复用完整状态解析（含 result / error）
            exec_info = await get_prompt_execution_status(
                pid, node_url=node_url, force_http=True
            )
            status = exec_info.get("status") or "failed"
            if status in ("pending", "queued", "running"):
                return {
                    "state": "busy",
                    "status": status,
                    "progress": exec_info.get("progress") or progress,
                    "result": None,
                    "error": None,
                }
            return {
                "state": "idle",
                "status": status,
                "progress": exec_info.get("progress"),
                "result": exec_info.get("result"),
                "error": exec_info.get("error"),
            }

    # 可达、不在队列、无 history → 后端已不持有该任务
    return {
        "state": "idle",
        "status": "failed",
        "progress": progress,
        "result": None,
        "error": "ComfyUI 中未找到该任务，可能已过期",
    }


async def get_prompt_execution_status(
    prompt_id: str,
    node_url: str | None = None,
    *,
    force_http: bool = False,
) -> dict:
    """
    查询单个 ComfyUI prompt 的执行状态（队列 + history + WS 进度缓存）。
    返回: status (pending|running|completed|failed), progress (0-100), result, error
    """
    from services import comfyui_progress

    base = _resolve_comfyui_base(node_url)
    cached = comfyui_progress.get_progress(prompt_id) or {}
    progress = int(cached.get("progress") or 0)
    stage = cached.get("stage") or cached.get("node")
    message = None
    if cached.get("max"):
        message = f"step {cached.get('value', 0)}/{cached.get('max', 0)}"

    cache_age = _cache_age_seconds(cached)
    if (
        not force_http
        and progress > 0
        and progress < 95
        and cache_age <= COMFY_POLL_CACHE_FRESH_SEC
    ):
        return _execution_status_running(
            progress=progress,
            stage=stage,
            message=message,
        )
    if not force_http and not _should_fetch_comfy_http(
        prompt_id, force=progress >= 95
    ):
        return _execution_status_running(
            progress=progress,
            stage=stage,
            message=message,
        )

    in_running = False
    in_pending = False
    hist_res = None
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            queue_res = await client.get(f"{base}/queue")
            hist_res = await client.get(f"{base}/history/{prompt_id}")
        queue_data = queue_res.json()
        for item in queue_data.get("queue_running", []):
            if len(item) > 1 and str(item[1]) == str(prompt_id):
                in_running = True
                break
        for item in queue_data.get("queue_pending", []):
            if len(item) > 1 and str(item[1]) == str(prompt_id):
                in_pending = True
                break
    except httpx.ConnectError as exc:
        studio_print("comfyui", f"无法连接 ComfyUI prompt_id={prompt_id}: {exc}")
        return _execution_status_running(
            progress=progress,
            stage=stage or "running",
            message=message,
        )
    except httpx.TimeoutException:
        studio_print("comfyui", f"连接 ComfyUI 超时 prompt_id={prompt_id}")
        return _execution_status_running(
            progress=progress,
            stage=stage or "running",
            message=message,
        )
    except Exception as exc:
        logger.exception("get_prompt_execution_status error prompt_id=%s", prompt_id)
        studio_print("comfyui", f"查询 ComfyUI 异常 prompt_id={prompt_id}: {exc}")
        return _execution_status_running(
            progress=progress,
            stage=stage or "running",
            message=message,
        )

    if hist_res is not None and hist_res.status_code == 200:
        try:
            payload = hist_res.json()
        except Exception:
            payload = {}
        if prompt_id in payload:
            entry = payload[prompt_id]
            _, _, generation_seconds = _extract_timestamps(entry)
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                comfyui_progress.clear_progress(prompt_id)
                return {
                    "status": "failed",
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "result": None,
                    "error": _history_error_message(entry),
                    "generation_seconds": generation_seconds,
                }

            workflow = None
            prompt_field = entry.get("prompt")
            if isinstance(prompt_field, list) and len(prompt_field) > 2:
                workflow = prompt_field[2]
            elif isinstance(prompt_field, dict):
                workflow = prompt_field

            images, videos = _collect_media(entry.get("outputs", {}), workflow)
            if videos:
                comfyui_progress.clear_progress(prompt_id)
                return {
                    "status": "completed",
                    "progress": 100,
                    "stage": "done",
                    "message": "completed",
                    "result": _view_url_for_media(videos[0], node_url=base),
                    "error": None,
                    "generation_seconds": generation_seconds,
                }
            if images:
                comfyui_progress.clear_progress(prompt_id)
                return {
                    "status": "completed",
                    "progress": 100,
                    "stage": "done",
                    "message": "completed",
                    "result": _view_url_for_media(images[0], node_url=base),
                    "error": None,
                    "generation_seconds": generation_seconds,
                }

            if status.get("completed") is True:
                return {
                    "status": "failed",
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "result": None,
                    "error": "任务已完成但未找到输出",
                    "generation_seconds": generation_seconds,
                }

    if in_running:
        # 模型加载阶段尚无 sampler progress 时给一点基线，避免长时间停在 0%
        shown = progress if progress > 0 else 3
        return {
            "status": "running",
            "progress": shown,
            "stage": stage or "running",
            "message": message,
            "result": None,
            "error": None,
        }
    if in_pending:
        return {
            "status": "pending",
            "progress": 0,
            "stage": "queued",
            "message": "queued",
            "result": None,
            "error": None,
        }

    if progress > 0:
        return {
            "status": "running",
            "progress": progress,
            "stage": stage or "running",
            "message": message,
            "result": None,
            "error": None,
        }

    return {
        "status": "running",
        "progress": 3 if in_running else progress,
        "stage": stage or "running",
        "message": message,
        "result": None,
        "error": None,
    }


async def get_progress():
    from services import comfyui_progress

    nodes = comfyui_nodes_list()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for node_url in nodes:
            base = node_url.rstrip("/")
            try:
                res = await client.get(f"{base}/queue")
                data = res.json()
            except Exception:
                continue
            running = data.get("queue_running", [])
            if running:
                prompt_id = running[0][1]
                cached = comfyui_progress.get_progress(prompt_id) or {}
                return {
                    "running": True,
                    "prompt_id": prompt_id,
                    "progress": cached.get("progress", 0),
                    "comfyui_node_url": base,
                }
    return {"running": False}


def _is_video_file(filename: str) -> bool:
    """可在 <video> 中播放的容器格式（不含 Animated WebP）。"""
    lower = filename.lower()
    return lower.endswith((".mp4", ".webm", ".mov", ".mkv", ".avi"))


def _media_entry(item: dict) -> dict:
    filename = item["filename"]
    return {
        "filename": filename,
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
        "media_format": guess_media_type(filename),
        "media_kind": (
            "video"
            if _is_video_file(filename)
            else "image"
        ),
    }


def _is_output_type(item: dict) -> bool:
    media_type = item.get("type", "output")
    return media_type in (None, "output")


def _collect_media(outputs: dict, workflow: dict | None = None) -> tuple[list, list]:
    images = []
    videos = []
    seen_images = set()
    seen_videos = set()

    video_node_ids = set()
    if workflow:
        for nid, node in workflow.items():
            ct = node.get("class_type", "")
            if (
                "VideoCombine" in ct
                or "SaveAnimated" in ct
                or ct in VIDEO_SAVE_CLASS
            ):
                video_node_ids.add(str(nid))

    for node_id, node_output in outputs.items():
        node_id_str = str(node_id)
        from_video_node = node_id_str in video_node_ids

        for key in ("gifs", "videos", "video"):
            if key not in node_output:
                continue
            raw = node_output[key]
            items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
            for item in items:
                if not _is_output_type(item):
                    continue
                entry = _media_entry(item)
                fname = entry["filename"]
                if fname not in seen_videos:
                    seen_videos.add(fname)
                    videos.append(entry)

        if "images" in node_output:
            for item in node_output["images"]:
                if not _is_output_type(item):
                    continue
                entry = _media_entry(item)
                fname = entry["filename"]
                if from_video_node or _is_video_file(fname):
                    if fname not in seen_videos:
                        seen_videos.add(fname)
                        videos.append(entry)
                elif fname not in seen_images:
                    seen_images.add(fname)
                    images.append(entry)

    return images, videos


async def _collect_tasks_from_node(
    client: httpx.AsyncClient,
    node_url: str,
) -> list:
    base = node_url.rstrip("/")
    try:
        queue_res = await client.get(f"{base}/queue")
        history_res = await client.get(f"{base}/history")
    except Exception:
        return []

    try:
        queue_data = queue_res.json()
    except Exception:
        queue_data = {}

    try:
        history_data = history_res.json()
    except Exception:
        history_data = {}

    tasks: list = []

    for item in queue_data.get("queue_running", []):
        prompt_id = item[1]
        workflow = item[2] if len(item) > 2 else None
        tasks.append(
            _base_task(
                prompt_id,
                "running",
                "生成中",
                workflow=workflow,
                comfyui_node_url=base,
            )
        )

    for item in queue_data.get("queue_pending", []):
        prompt_id = item[1]
        workflow = item[2] if len(item) > 2 else None
        tasks.append(
            _base_task(
                prompt_id,
                "pending",
                "排队中",
                workflow=workflow,
                comfyui_node_url=base,
            )
        )

    history_items = list(history_data.items())

    def _sort_key(item):
        _, data = item
        _, completed_at, _ = _extract_timestamps(data)
        return completed_at or 0

    history_items.sort(key=_sort_key, reverse=True)
    history_items = history_items[:HISTORY_LIMIT]

    for prompt_id, data in history_items:
        workflow = None
        prompt_field = data.get("prompt")
        if isinstance(prompt_field, list) and len(prompt_field) > 2:
            workflow = prompt_field[2]
        elif isinstance(prompt_field, dict):
            workflow = prompt_field

        images, videos = _collect_media(data.get("outputs", {}), workflow)
        tasks.append(
            _base_task(
                prompt_id,
                "done",
                "已完成",
                workflow=workflow,
                history_data=data,
                images=images,
                videos=videos,
                comfyui_node_url=base,
            )
        )

    return tasks


async def get_tasks() -> list:
    nodes = comfyui_nodes_list()
    tasks: list = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for node_url in nodes:
            tasks.extend(await _collect_tasks_from_node(client, node_url))

    status_order = {"running": 0, "pending": 1, "done": 2}
    tasks.sort(
        key=lambda t: (
            status_order.get(t["status"], 9),
            -(t.get("completed_at") or t.get("started_at") or t.get("timestamp") or 0),
        )
    )
    return tasks


# ── Video enhance (SeedVR2 / Real-ESRGAN) ─────────────────────────────────────

SEEDVR2_DIT_NORMAL = "seedvr2_ema_7b_fp16.safetensors"
SEEDVR2_DIT_SHARP = "seedvr2_ema_7b_sharp_fp16.safetensors"
SEEDVR2_DIT_3B = "seedvr2_ema_3b_fp8_e4m3fn.safetensors"
SEEDVR2_DIT_3B_SHARP = "seedvr2_ema_3b_fp8_e4m3fn.safetensors"
SEEDVR2_VAE = "ema_vae_fp16.safetensors"
REALESRGAN_MODEL = "RealESRGAN_x4plus.pth"
VIDEO_ENHANCE_SEEDVR2_KEY = "video_enhance_seedvr2.json"
VIDEO_ENHANCE_REALESRGAN_KEY = "video_enhance_realesrgan.json"

VE_LOAD = "1"
VE_DIT = "2"
VE_VAE = "3"
VE_UPSCALE = "4"
VE_SAVE = "5"

IE_LOAD = "1"
IE_DIT = "2"
IE_VAE = "3"
IE_UPSCALE = "4"
IE_SAVE = "5"

RE_LOAD = "1"
RE_UPMODEL = "2"
RE_UPSCALE = "3"
RE_SAVE = "4"


def _seedvr2_dit_model(strength: str, model_size: str = "7b") -> str:
    """选型：默认 7B FP16（H800 顶配）；3B 仅作轻量/5090 降级。"""
    size = (model_size or "7b").strip().lower()
    sharp = (strength or "").strip().lower() == "sharp"
    if size == "3b":
        # HF 无独立 3B sharp；sharp 与 normal 共用 3B fp8
        return SEEDVR2_DIT_3B_SHARP if sharp else SEEDVR2_DIT_3B
    return SEEDVR2_DIT_SHARP if sharp else SEEDVR2_DIT_NORMAL


def _clamp_upscale_factor(value: float) -> float:
    try:
        factor = float(value)
    except (TypeError, ValueError):
        factor = 2.0
    if factor <= 1.0:
        return 1.0
    if factor <= 1.5:
        return 1.5
    if factor >= 3.0:
        return 3.0
    if factor <= 2.0:
        return 2.0
    return factor


def _seedvr2_target_resolution(upscale_factor: float, source_height: int | None = None) -> int:
    factor = _clamp_upscale_factor(upscale_factor)
    if factor <= 1.0:
        base = int(source_height) if source_height and source_height > 0 else 480
        return max(480, base)
    return int(480 * factor)


def build_seedvr2_enhance_workflow(
    video_filename: str,
    *,
    upscale_factor: float = 2.0,
    model_variant: str | None = None,
    batch_size: int = 8,
    block_swap: int = 0,
    input_noise_scale: float = 0.25,
    color_correction: str = "lab",
    strength: str = "normal",
    model_size: str = "7b",
    source_height: int | None = None,
) -> dict:
    """SeedVR2 视频画质增强 workflow（ComfyUI-SeedVR2_VideoUpscaler 自定义节点）。"""
    factor = _clamp_upscale_factor(upscale_factor)
    dit_model = model_variant or _seedvr2_dit_model(strength, model_size)
    target_resolution = _seedvr2_target_resolution(factor, source_height)
    color_mode = (color_correction or "lab").strip().lower()
    if color_mode not in ("lab", "none"):
        color_mode = "lab"
    batch = int(batch_size) if int(batch_size) % 4 == 1 else 5
    workflow = deepcopy(load_workflow_template(VIDEO_ENHANCE_SEEDVR2_KEY))
    workflow[VE_LOAD]["inputs"]["video"] = video_filename
    workflow[VE_LOAD]["inputs"]["force_rate"] = float(VIDEO_FPS)
    workflow[VE_DIT]["inputs"]["model"] = dit_model
    workflow[VE_DIT]["inputs"]["blocks_to_swap"] = int(block_swap)
    workflow[VE_VAE]["inputs"]["model"] = SEEDVR2_VAE
    workflow[VE_UPSCALE]["inputs"]["resolution"] = target_resolution
    workflow[VE_UPSCALE]["inputs"]["batch_size"] = batch
    workflow[VE_UPSCALE]["inputs"]["color_correction"] = color_mode
    workflow[VE_UPSCALE]["inputs"]["input_noise_scale"] = float(input_noise_scale)
    return workflow


def build_realesrgan_enhance_workflow(
    video_filename: str,
    *,
    upscale_factor: float = 2.0,
) -> dict:
    """Real-ESRGAN 逐帧视频超分 fallback workflow。"""
    _clamp_upscale_factor(upscale_factor)
    workflow = deepcopy(load_workflow_template(VIDEO_ENHANCE_REALESRGAN_KEY))
    workflow[RE_LOAD]["inputs"]["video"] = video_filename
    workflow[RE_LOAD]["inputs"]["force_rate"] = float(VIDEO_FPS)
    workflow[RE_UPMODEL]["inputs"]["model_name"] = REALESRGAN_MODEL
    return workflow


async def upload_video_from_url(
    video_url: str,
    *,
    db=None,
    user=None,
    node_url: str | None = None,
) -> str:
    """将服务器本地路径或 http URL 的视频上传到 ComfyUI input，返回 filename。"""
    from services.media_access import normalize_media_reference_url, resolve_video_source_for_enhance

    raw = normalize_media_reference_url((video_url or "").strip())
    if not raw:
        raise ValueError("视频地址为空")

    data: bytes
    fname = "input.mp4"

    if raw.startswith("http://") or raw.startswith("https://"):
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.get(raw)
            res.raise_for_status()
            data = res.content
            fname = raw.split("/")[-1].split("?", 1)[0] or "input.mp4"
    elif db is not None and user is not None:
        local_path = resolve_video_source_for_enhance(db, user, raw)
        if local_path is None:
            raise ValueError("视频源无效或无权访问")
        data = local_path.read_bytes()
        fname = local_path.name or "input.mp4"
    else:
        local_path = Path(raw.replace("/api/uploads/", "/uploads/").lstrip("/"))
        if not local_path.is_file():
            local_path = Path(raw.lstrip("/"))
        if not local_path.is_file():
            raise ValueError(f"视频文件不存在: {local_path}")
        data = local_path.read_bytes()
        fname = local_path.name or "input.mp4"

    if not fname.lower().endswith(".mp4"):
        fname = f"{Path(fname).stem}.mp4"

    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(
            f"{_resolve_comfyui_base(node_url)}/upload/image",
            files={"image": (fname, data, "video/mp4")},
        )
        res.raise_for_status()
        name = res.json().get("name")
    if not name:
        raise ValueError("视频上传 ComfyUI 失败")
    return name


async def _submit_video_enhance_workflow(
    workflow: dict,
    *,
    backend: str,
    client_id: str | None = None,
    node_url: str | None = None,
) -> tuple[str, str, dict, str]:
    await ensure_video_mp4_capable(node_url)
    return await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend=backend,
        width=0,
        height=0,
        duration=0,
        mode="enhance",
        node_url=node_url,
    )


async def submit_seedvr2_enhance_prompt(
    video_url: str,
    *,
    db,
    user,
    upscale_factor: float = 2.0,
    strength: str = "normal",
    input_noise_scale: float = 0.25,
    batch_size: int = 8,
    color_correction: str = "lab",
    model_size: str = "7b",
    client_id: str | None = None,
) -> tuple[str, str, dict, str]:
    source_height: int | None = None
    try:
        from services.media_access import resolve_video_source_for_enhance
        from services.video_enhance_probe import probe_video_info

        local_path = resolve_video_source_for_enhance(db, user, video_url)
        if local_path is not None:
            info = probe_video_info(local_path)
            source_height = int(info.get("height") or 0) or None
    except Exception:
        source_height = None

    reserved_node = _acquire_gpu_node_url(estimated_duration_sec=300, required_vram=40)
    video_filename = await upload_video_from_url(
        video_url, db=db, user=user, node_url=reserved_node
    )
    workflow = build_seedvr2_enhance_workflow(
        video_filename,
        upscale_factor=upscale_factor,
        strength=strength,
        input_noise_scale=input_noise_scale,
        batch_size=batch_size,
        color_correction=color_correction,
        model_size=model_size,
        source_height=source_height,
    )
    return await _submit_video_enhance_workflow(
        workflow,
        backend="seedvr2_enhance",
        client_id=client_id,
        node_url=reserved_node,
    )


async def submit_realesrgan_enhance_prompt(
    video_url: str,
    *,
    db,
    user,
    upscale_factor: float = 2.0,
    client_id: str | None = None,
) -> tuple[str, str, dict, str]:
    reserved_node = _acquire_gpu_node_url(estimated_duration_sec=180, required_vram=12)
    video_filename = await upload_video_from_url(
        video_url, db=db, user=user, node_url=reserved_node
    )
    workflow = build_realesrgan_enhance_workflow(
        video_filename,
        upscale_factor=upscale_factor,
    )
    return await _submit_video_enhance_workflow(
        workflow,
        backend="realesrgan_enhance",
        client_id=client_id,
        node_url=reserved_node,
    )


def build_seedvr2_image_enhance_workflow(
    image_filename: str,
    *,
    upscale_factor: float = 2.0,
    model_variant: str | None = None,
    batch_size: int = 1,
    block_swap: int = 0,
    input_noise_scale: float = 0.25,
    color_correction: str = "lab",
    strength: str = "normal",
    model_size: str = "7b",
    source_height: int | None = None,
) -> dict:
    """SeedVR2 静帧画质增强（复用 SeedVR2VideoUpscaler，单帧 batch）。"""
    factor = _clamp_upscale_factor(upscale_factor)
    dit_model = model_variant or _seedvr2_dit_model(strength, model_size)
    target_resolution = _seedvr2_target_resolution(factor, source_height)
    color_mode = (color_correction or "lab").strip().lower()
    if color_mode not in ("lab", "none"):
        color_mode = "lab"
    bs = int(batch_size) if int(batch_size) % 4 == 1 else 1
    return {
        IE_LOAD: {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename},
        },
        IE_DIT: {
            "class_type": "SeedVR2LoadDiTModel",
            "inputs": {
                "model": dit_model,
                "device": "cuda:0",
                "blocks_to_swap": int(block_swap),
                "swap_io": False,
            },
        },
        IE_VAE: {
            "class_type": "SeedVR2LoadVAEModel",
            "inputs": {
                "model": SEEDVR2_VAE,
                "device": "cuda:0",
                "encode_tiled": True,
                "encode_tile_size": 1024,
                "decode_tiled": True,
                "decode_tile_size": 1024,
            },
        },
        IE_UPSCALE: {
            "class_type": "SeedVR2VideoUpscaler",
            "inputs": {
                "image": [IE_LOAD, 0],
                "dit": [IE_DIT, 0],
                "vae": [IE_VAE, 0],
                "seed": 42,
                "resolution": target_resolution,
                "max_resolution": 0,
                "batch_size": bs,
                "color_correction": color_mode,
                "input_noise_scale": float(input_noise_scale),
                "uniform_batch_size": False,
                "temporal_overlap": 0,
                "prepend_frames": 0,
            },
        },
        IE_SAVE: {
            "class_type": "SaveImage",
            "inputs": {
                "images": [IE_UPSCALE, 0],
                "filename_prefix": "AIStudio_seedvr2_image",
            },
        },
    }


async def submit_seedvr2_image_enhance_prompt(
    image_url: str,
    *,
    db,
    user,
    upscale_factor: float = 2.0,
    strength: str = "normal",
    input_noise_scale: float = 0.25,
    color_correction: str = "lab",
    model_size: str = "7b",
    client_id: str | None = None,
) -> tuple[str, str, dict, str]:
    reserved_node = _acquire_gpu_node_url(estimated_duration_sec=120, required_vram=40)
    resolved_url = (image_url or "").strip()
    if db is not None and user is not None:
        from services.media_access import resolve_image_reference_path

        try:
            local_path = resolve_image_reference_path(db, user, resolved_url)
            resolved_url = str(local_path)
        except Exception:
            pass
    image_filename = await upload_image_from_url(
        resolved_url, node_url=reserved_node
    )
    workflow = build_seedvr2_image_enhance_workflow(
        image_filename,
        upscale_factor=upscale_factor,
        strength=strength,
        input_noise_scale=input_noise_scale,
        color_correction=color_correction,
        model_size=model_size,
    )
    prompt_id, used_client, posted_node = await _post_workflow(
        workflow,
        client_id,
        estimated_duration_sec=120,
        required_vram=40,
        node_url=reserved_node,
    )
    return prompt_id, used_client, workflow, posted_node