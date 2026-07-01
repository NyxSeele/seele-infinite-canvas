import base64
import json
import logging
import random
import uuid
from pathlib import Path

import httpx

from core.logging_setup import studio_print
from core.comfyui_settings import comfyui_http_url, comfyui_ws_url

logger = logging.getLogger(__name__)

COMFYUI_URL = comfyui_http_url()
COMFYUI_WS_URL = comfyui_ws_url()
HTTP_TIMEOUT = 5.0
COMFYUI_UNREACHABLE_MSG = (
    "ComfyUI 服务未启动或无法连接，请先启动 ComfyUI"
)
HISTORY_LIMIT = 50
DEFAULT_IMAGE_MODEL = "v1-5-pruned-emaonly.safetensors"
DEFAULT_VIDEO_MODEL = "ltx-video-2b-v0.9.5.safetensors"
DEFAULT_CKPT = DEFAULT_IMAGE_MODEL
LTX_CKPT = DEFAULT_VIDEO_MODEL
WAN_CKPT = "wan2.6.safetensors"
HUNYUAN_CKPT = "hunyuan_video_t2v_720p_bf16.safetensors"
HUNYUAN_VAE = "hunyuan_video_vae_bf16.safetensors"
HUNYUAN_CLIP_L = "clip_l.safetensors"
HUNYUAN_CLIP_LLAVA = "llava_llama3_fp8_scaled.safetensors"
WAN_T5_ENCODER = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
LTX_T5_ENCODER = "t5xxl_fp16.safetensors"
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
    "EmptyHunyuanLatentVideo",
    "HunyuanVideoModelLoader",
    "HunyuanVideoSampler",
}

STYLE_SUFFIXES = {
    "realistic": "photorealistic, high quality, detailed",
    "anime": "anime style, illustration, vibrant colors",
    "oil": "oil painting, artistic, textured",
}

DEFAULT_VIDEO_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted"
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
    "hunyuan",
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

# Wan 2.6 视频节点（ComfyUI-WanVideoWrapper）
WAN_MODEL_LOADER = "50"
WAN_TEXT_ENCODE = "51"
WAN_SAMPLER = "52"
WAN_DECODE = "53"
WAN_SAVE = "54"

# HunyuanVideo 原生 T2V 节点
HY_UNET = "60"
HY_DUAL_CLIP = "61"
HY_VAE = "62"
HY_CLIP_POS = "63"
HY_CLIP_NEG = "64"
HY_EMPTY_LATENT = "65"
HY_MODEL_SAMPLING = "66"
HY_SCHEDULER = "67"
HY_NOISE = "68"
HY_SAMPLER_SEL = "69"
HY_GUIDER = "70"
HY_SAMPLER = "71"
HY_DECODE = "72"
HY_SAVE = "73"

_object_info_cache: dict | None = None


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


async def _fetch_object_info() -> dict:
    global _object_info_cache
    if _object_info_cache is not None:
        return _object_info_cache
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        res = await client.get(f"{COMFYUI_URL}/object_info")
        res.raise_for_status()
        _object_info_cache = res.json()
    return _object_info_cache


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


async def ensure_video_mp4_capable() -> None:
    info = await _fetch_object_info()
    if _can_output_mp4(info):
        return
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
    """通用视频宽高对齐（Wan / Hunyuan 等）。"""
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

    return {
        V_LOADER: {
            "class_type": "LTXVLoader",
            "inputs": {
                "ckpt_name": LTX_CKPT,
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


def build_ltx_video_workflow_compat(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 512,
    height: int = 512,
    duration_sec: int = 5,
    seed: int | None = None,
    info: dict | None = None,
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

    node_info = info if info is not None else (_object_info_cache or {})
    workflow = {
        VC_CKPT: {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": LTX_CKPT},
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
) -> dict:
    workflow = build_ltx_video_workflow_compat(
        positive_prompt, negative_prompt, width, height, duration_sec, seed, info=info
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
) -> dict:
    """
    Wan 2.6 T2V：WanVideoModelLoader + LoadWanVideoT5TextEncoder + WanVideoEmptyEmbeds
    + WanVideoSampler + WanVideoDecode + VHS_VideoCombine。
    依赖 ComfyUI-WanVideoWrapper 自定义节点。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    ckpt = (model_filename or WAN_CKPT).strip() or WAN_CKPT
    num_frames = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE

    studio_print(
        "comfyui-video",
        f"Wan workflow: {ckpt} {width}x{height} frames={num_frames}",
    )

    return {
        WAN_MODEL_LOADER: {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": ckpt,
                "base_precision": "bf16",
                "quantization": "disabled",
                "load_device": "main_device",
            },
        },
        "55": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": WAN_T5_ENCODER,
                "precision": "bf16",
                "load_device": "main_device",
                "quantization": "disabled",
            },
        },
        "56": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": "wan_2.1_vae.safetensors",
                "precision": "bf16",
            },
        },
        WAN_TEXT_ENCODE: {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": positive,
                "negative_prompt": negative,
                "t5": ["55", 0],
                "force_offload": True,
                "model_to_offload": [WAN_MODEL_LOADER, 0],
                "use_disk_cache": False,
                "device": "gpu",
            },
        },
        "57": {
            "class_type": "WanVideoEmptyEmbeds",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "num_frames": num_frames,
            },
        },
        WAN_SAMPLER: {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": [WAN_MODEL_LOADER, 0],
                "image_embeds": ["57", 0],
                "text_embeds": [WAN_TEXT_ENCODE, 0],
                "steps": 30,
                "cfg": 6.0,
                "shift": 5.0,
                "seed": int(seed),
                "force_offload": True,
                "scheduler": "unipc",
                "riflex_freq_index": 0,
            },
        },
        WAN_DECODE: {
            "class_type": "WanVideoDecode",
            "inputs": {
                "vae": ["56", 0],
                "samples": [WAN_SAMPLER, 0],
                "enable_vae_tiling": False,
                "tile_x": 272,
                "tile_y": 272,
                "tile_stride_x": 144,
                "tile_stride_y": 128,
                "normalization": "default",
            },
        },
        WAN_SAVE: {
            "class_type": "VHS_VideoCombine",
            "inputs": _vhs_video_combine_inputs(WAN_DECODE),
        },
    }


def build_hunyuan_video_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 848,
    height: int = 480,
    duration_sec: int = 5,
    seed: int | None = None,
    *,
    model_filename: str | None = None,
) -> dict:
    """
    HunyuanVideo T2V：UNETLoader + DualCLIPLoader + EmptyHunyuanLatentVideo
    + KSampler + VAEDecode + VHS_VideoCombine（ComfyUI 原生节点）。
    """
    if seed is None:
        seed = random.randint(0, 2**32)

    ckpt = (model_filename or HUNYUAN_CKPT).strip() or HUNYUAN_CKPT
    length = video_frame_length(duration_sec)
    positive = str(positive_prompt).strip()
    negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE

    studio_print(
        "comfyui-video",
        f"Hunyuan workflow: {ckpt} {width}x{height} length={length}",
    )

    return {
        HY_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": ckpt,
                "weight_dtype": "default",
            },
        },
        HY_DUAL_CLIP: {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": HUNYUAN_CLIP_L,
                "clip_name2": HUNYUAN_CLIP_LLAVA,
                "type": "hunyuan_video",
            },
        },
        HY_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": HUNYUAN_VAE},
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
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "length": int(length),
                "batch_size": 1,
            },
        },
        HY_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(seed),
                "steps": 25,
                "cfg": 6.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": [HY_UNET, 0],
                "positive": [HY_CLIP_POS, 0],
                "negative": [HY_CLIP_NEG, 0],
                "latent_image": [HY_EMPTY_LATENT, 0],
            },
        },
        HY_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [HY_SAMPLER, 0],
                "vae": [HY_VAE, 0],
            },
        },
        HY_SAVE: {
            "class_type": "VHS_VideoCombine",
            "inputs": _vhs_video_combine_inputs(HY_DECODE),
        },
    }


async def _log_and_post_video_workflow(
    workflow: dict,
    *,
    client_id: str | None,
    backend: str,
    width: int,
    height: int,
    duration: int,
    mode: str,
) -> tuple[str, str, dict]:
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
    prompt_id, used_client = await _post_workflow(workflow, client_id)
    studio_print(
        "comfyui-video",
        f"[{backend}] 已提交 prompt_id={prompt_id} client_id={used_client}",
    )
    return prompt_id, used_client, workflow


async def _resolve_video_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    duration_sec: int,
    mode: str,
    image_filename: str | None,
) -> dict:
    global _object_info_cache
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
            positive_prompt, negative_prompt, width, height, duration_sec
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
        )

    return build_ltx_video_workflow_compat(
        positive_prompt, negative_prompt, width, height, duration_sec, info=info
    )


async def upload_image_from_url(image_url: str) -> str:
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
                f"{COMFYUI_URL}/upload/image",
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
            f"{COMFYUI_URL}/upload/image",
            files={"image": (fname, data, ct)},
        )
        res.raise_for_status()
        return res.json().get("name") or ""


async def upload_image_base64(image_b64: str) -> str:
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    data = base64.b64decode(image_b64)
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{COMFYUI_URL}/upload/image",
            files={"image": ("upload.png", data, "image/png")},
        )
        res.raise_for_status()
        payload = res.json()
    name = payload.get("name")
    if not name:
        raise ValueError("图片上传失败")
    return name


async def _post_workflow(workflow: dict, client_id: str | None) -> tuple[str, str]:
    if client_id is None:
        client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.post(f"{COMFYUI_URL}/prompt", json=payload)
        res.raise_for_status()
        data = res.json()
    if data.get("node_errors"):
        raise ValueError(f"工作流节点错误: {data['node_errors']}")
    if data.get("error"):
        raise ValueError(f"ComfyUI 拒绝工作流: {data['error']}")
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise ValueError("ComfyUI 未返回 prompt_id")
    return prompt_id, client_id


async def submit_prompt(
    prompt: str,
    negative_prompt: str = "模糊, 低质量, 水印, 文字",
    style: str = "realistic",
    steps: int = DEFAULT_STEPS,
    width: int = 512,
    height: int = 512,
    client_id: str | None = None,
    raw_prompt: bool = False,
    reference_image: str | None = None,
) -> tuple[str, str]:
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
            ref_filename = await upload_image_from_url(reference_image)
            if ref_filename:
                # Inject LoadImage node + IPAdapterSimple if available, else just log
                workflow["ref_load"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": ref_filename, "upload": "image"},
                }
        except Exception as e:
            print(f"[comfyui] 参考图上传失败，跳过: {e}")
    return await _post_workflow(workflow, client_id)


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
) -> tuple[str, str, dict]:
    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_ltx_dimensions(width, height)

    image_filename = None
    if mode == "image2video":
        if not image_b64:
            raise ValueError("图生视频需要上传图片")
        image_filename = await upload_image_base64(image_b64)

    await ensure_video_mp4_capable()

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
        positive, negative, width, height, duration, mode, image_filename
    )
    prompt_id, used_client, workflow = await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="ltx",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
    )
    return prompt_id, used_client, workflow


async def submit_wan_video_prompt(
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
) -> tuple[str, str, dict]:
    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_video_dimensions(width, height)

    if mode == "image2video":
        raise ValueError("Wan 2.6 workflow 暂不支持图生视频")

    await ensure_video_mp4_capable()

    logger.info(
        "submit_wan_video_prompt inputs: duration=%s width=%s height=%s prompt_len=%s",
        duration,
        width,
        height,
        len(positive or ""),
    )
    workflow = build_wan_video_workflow(
        positive,
        negative,
        width,
        height,
        duration,
        model_filename=model_filename,
    )
    return await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="wan",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
    )


async def submit_hunyuan_video_prompt(
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
) -> tuple[str, str, dict]:
    positive = prompt.strip()
    if raw_prompt:
        negative = str(negative_prompt).strip() or DEFAULT_VIDEO_NEGATIVE
    else:
        negative = normalize_video_negative(negative_prompt)
    width, height = align_video_dimensions(width, height)

    if mode == "image2video":
        raise ValueError("HunyuanVideo workflow 暂不支持图生视频")

    await ensure_video_mp4_capable()

    logger.info(
        "submit_hunyuan_video_prompt inputs: duration=%s width=%s height=%s prompt_len=%s",
        duration,
        width,
        height,
        len(positive or ""),
    )
    workflow = build_hunyuan_video_workflow(
        positive,
        negative,
        width,
        height,
        duration,
        model_filename=model_filename,
    )
    return await _log_and_post_video_workflow(
        workflow,
        client_id=client_id,
        backend="hunyuan",
        width=width,
        height=height,
        duration=duration,
        mode=mode,
    )


async def get_comfyui_output_dir() -> Path:
    """从 ComfyUI system_stats 解析 output 目录。"""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        res = await client.get(f"{COMFYUI_URL}/system_stats")
        res.raise_for_status()
        data = res.json()

    argv = data.get("system", {}).get("argv", [])
    for i, arg in enumerate(argv):
        if arg == "--output-directory" and i + 1 < len(argv):
            return Path(argv[i + 1])

    return Path(r"D:\ComfyUI\ComfyUI\output")


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
    output_dir = await get_comfyui_output_dir()
    stats = _scan_output_storage(output_dir)
    return {
        "comfyui_output": str(output_dir.resolve()),
        **stats,
    }


async def cancel_task(task_id: str) -> None:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        res = await client.post(
            f"{COMFYUI_URL}/queue",
            json={"delete": [task_id]},
        )
        res.raise_for_status()


def _view_url_for_media(entry: dict) -> str:
    from urllib.parse import quote

    filename = entry.get("filename") or ""
    media_type = entry.get("type") or "output"
    subfolder = entry.get("subfolder") or ""
    params = f"filename={quote(filename, safe='')}&type={media_type}"
    if subfolder:
        params += f"&subfolder={quote(subfolder, safe='')}"
    return f"/api/view?{params}"


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
            return str(msg[1])
    return "ComfyUI 执行失败"


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


async def get_prompt_execution_status(prompt_id: str) -> dict:
    """
    查询单个 ComfyUI prompt 的执行状态（队列 + history + WS 进度缓存）。
    返回: status (pending|running|completed|failed), progress (0-100), result, error
    """
    from services import comfyui_progress

    cached = comfyui_progress.get_progress(prompt_id) or {}
    progress = int(cached.get("progress") or 0)
    stage = cached.get("stage") or cached.get("node")
    message = None
    if cached.get("max"):
        message = f"step {cached.get('value', 0)}/{cached.get('max', 0)}"

    in_running = False
    in_pending = False
    hist_res = None
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            queue_res = await client.get(f"{COMFYUI_URL}/queue")
            hist_res = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
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
        return _execution_status_failed(COMFYUI_UNREACHABLE_MSG)
    except httpx.TimeoutException:
        studio_print("comfyui", f"连接 ComfyUI 超时 prompt_id={prompt_id}")
        return _execution_status_failed("ComfyUI 请求超时，请检查服务是否正常运行")
    except Exception as exc:
        logger.exception("get_prompt_execution_status error prompt_id=%s", prompt_id)
        studio_print("comfyui", f"查询 ComfyUI 异常 prompt_id={prompt_id}: {exc}")
        return _execution_status_failed(f"ComfyUI 查询失败: {exc}")

    if hist_res is not None and hist_res.status_code == 200:
        try:
            payload = hist_res.json()
        except Exception:
            payload = {}
        if prompt_id in payload:
            entry = payload[prompt_id]
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
                    "result": _view_url_for_media(videos[0]),
                    "error": None,
                }
            if images:
                comfyui_progress.clear_progress(prompt_id)
                return {
                    "status": "completed",
                    "progress": 100,
                    "stage": "done",
                    "message": "completed",
                    "result": _view_url_for_media(images[0]),
                    "error": None,
                }

            if status.get("completed") is True:
                return {
                    "status": "failed",
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "result": None,
                    "error": "任务已完成但未找到输出",
                }

    if in_running:
        return {
            "status": "running",
            "progress": progress,
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
        "progress": progress,
        "stage": stage or "running",
        "message": message,
        "result": None,
        "error": None,
    }


async def get_progress():
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            res = await client.get(f"{COMFYUI_URL}/queue")
            data = res.json()
            running = data.get("queue_running", [])
            if running:
                prompt_id = running[0][1]
                cached = None
                try:
                    from services import comfyui_progress

                    cached = comfyui_progress.get_progress(prompt_id)
                except Exception:
                    pass
                return {
                    "running": True,
                    "prompt_id": prompt_id,
                    "progress": (cached or {}).get("progress", 0),
                }
            return {"running": False}
        except Exception:
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


async def get_tasks() -> list:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        queue_res = await client.get(f"{COMFYUI_URL}/queue")
        history_res = await client.get(f"{COMFYUI_URL}/history")

        try:
            queue_data = queue_res.json()
        except Exception:
            queue_data = {}

        try:
            history_data = history_res.json()
        except Exception:
            history_data = {}

        tasks = []

        for item in queue_data.get("queue_running", []):
            prompt_id = item[1]
            workflow = item[2] if len(item) > 2 else None
            tasks.append(
                _base_task(prompt_id, "running", "生成中", workflow=workflow)
            )

        for item in queue_data.get("queue_pending", []):
            prompt_id = item[1]
            workflow = item[2] if len(item) > 2 else None
            tasks.append(
                _base_task(prompt_id, "pending", "排队中", workflow=workflow)
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
                )
            )

        status_order = {"running": 0, "pending": 1, "done": 2}
        tasks.sort(
            key=lambda t: (
                status_order.get(t["status"], 9),
                -(t.get("completed_at") or t.get("started_at") or t.get("timestamp") or 0),
            )
        )

        return tasks
