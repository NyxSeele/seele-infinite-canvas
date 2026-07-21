"""ComfyUI 图像生成（async HTTP，供画布任务轮询）。"""

from __future__ import annotations

import base64
import json
import logging
import random
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from core.comfyui_settings import comfyui_http_url
from core.logging_setup import studio_print
from comfyui.workflow_registry import load_workflow_template
from model_registry import resolve_generation_profile
from models import User
from services.api_key_service import get_registered_model_api_key
from services.mention_context import strip_mention_tokens
from trace_bus import extract_workflow_trace

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
HTTP_TIMEOUT = 30.0
TRANSLATE_TIMEOUT = 10.0
NEGATIVE_PROMPT = "blurry, bad quality"

# 无 registry 匹配时的 KSampler 回退（与 _GEN_SD15 一致）
_FALLBACK_GEN_DEFAULTS = {
    "steps": 20,
    "cfg": 7.0,
    "sampler_name": "dpmpp_2m",
    "scheduler": "karras",
    "denoise_txt2img": 1.0,
    "denoise_img2img": 0.5,
}

TRANSLATE_SYSTEM_PROMPT = (
    "You are a translator. Translate the following Chinese text to "
    "English for use as a Stable Diffusion image generation prompt. "
    "Output only the translated text, no explanation."
)

NODE_KSAMPLER = "3"
NODE_CHECKPOINT = "4"
NODE_EMPTY_LATENT = "5"
NODE_CLIP_POSITIVE = "6"
NODE_CLIP_NEGATIVE = "7"
NODE_VAE_DECODE = "8"
NODE_SAVE_IMAGE = "9"
NODE_LOAD_IMAGE = "10"
NODE_VAE_ENCODE = "11"
NODE_IMAGE_SCALE = "12"

# Flux 专用节点 ID（与 SD 系编号隔离）
FLUX_UNET = "20"
FLUX_DUAL_CLIP = "21"
FLUX_VAE_LOADER = "22"
FLUX_CLIP_ENCODE = "23"
FLUX_GUIDANCE = "24"
FLUX_EMPTY_LATENT = "25"
FLUX_RANDOM_NOISE = "26"
FLUX_SAMPLER_SELECT = "27"
FLUX_SCHEDULER = "28"
FLUX_GUIDER = "29"
FLUX_SAMPLER = "30"
FLUX_VAE_DECODE = "31"
FLUX_SAVE_IMAGE = "32"

# Flux 伴随模型占位文件名 — 服务器就绪后按 ComfyUI models/ 实际安装名替换
_FLUX_CLIP_L = "clip_l.safetensors"
_FLUX_CLIP_T5 = "t5xxl_fp8_e4m3fn.safetensors"
_FLUX_CLIP_T5_FP16 = "t5xxl_fp16.safetensors"
_FLUX_VAE = "ae.safetensors"
_PULID_CKPT = "pulid_flux_v0.9.1.safetensors"
_PULID_EVA_CLIP = "EVA02_CLIP_L_336_psz14_s6B.pt"
_COMFY_MODELS = Path("/root/autodl-tmp/ComfyUI/models")

# HiDream 专用节点 ID（ComfyUI 原生 SD3 风格链路）
HIDREAM_UNET = "40"
HIDREAM_QUAD_CLIP = "41"
HIDREAM_VAE = "42"
HIDREAM_CLIP_POS = "43"
HIDREAM_CLIP_NEG = "43b"
HIDREAM_MODEL_SAMPLING = "44"
HIDREAM_EMPTY_LATENT = "45"
HIDREAM_SAMPLER = "46"
HIDREAM_VAE_DECODE = "47"
HIDREAM_SAVE_IMAGE = "48"

# HiDream QuadrupleCLIPLoader 伴随编码器 — 服务器就绪后按实际安装名替换
_HIDREAM_CLIP_L = "clip_l_hidream.safetensors"
_HIDREAM_CLIP_G = "clip_g_hidream.safetensors"
_HIDREAM_T5 = "t5xxl_fp8_e4m3fn_scaled.safetensors"
_HIDREAM_LLAMA = "llama_3.1_8b_instruct_fp8_scaled.safetensors"
_HIDREAM_VAE = "ae.safetensors"

# Qwen-Image 专用节点 ID（与云绘 fp4 smoke workflow 一致）
QWEN_VAE = "1"
QWEN_EMPTY_LATENT = "4"
QWEN_CLIP_NEG = "5"
QWEN_CLIP_LOADER = "7"
QWEN_AURA_FLOW = "8"
QWEN_CLIP_POS = "9"
QWEN_SAMPLER = "12"
QWEN_DIT = "13"
QWEN_VAE_DECODE = "2"
QWEN_SAVE_IMAGE = "3"

_QWEN_CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
_QWEN_VAE = "qwen_image_vae.safetensors"
_QWEN_EDIT_UNET = "qwen_image_edit_2511_fp8mixed.safetensors"
_QWEN_EDIT_LORA_LIGHTNING = "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
_QWEN_EDIT_LORA_ANGLES = "qwen-image-edit-2511-multiple-angles-lora.safetensors"

# Qwen-Image-Edit 专用节点 ID（对齐云绘 Edit 2511 fp4 结构）
QIE_LOAD = "qe1"
QIE_SCALE = "qe2"
QIE_VAE = "qe3"
QIE_CLIP = "qe4"
QIE_UNET = "qe5"
QIE_LORA = "qe6"
QIE_AURA = "qe7"
QIE_CFG = "qe8"
QIE_VAE_ENCODE = "qe9"
QIE_POS_ENCODE = "qe10"
QIE_NEG_ENCODE = "qe11"
QIE_POS_METHOD = "qe12"
QIE_NEG_METHOD = "qe13"
QIE_SAMPLER = "qe14"
QIE_VAE_DECODE = "qe15"
QIE_SAVE = "qe16"

# Qwen-Image-Restore 专用节点 ID（老照片修复：双 LoRA）
QIR_LOAD = "qr1"
QIR_SCALE = "qr2"
QIR_VAE = "qr3"
QIR_CLIP = "qr4"
QIR_UNET = "qr5"
QIR_LORA_ANGLES = "qr6"
QIR_LORA_LIGHTNING = "qr7"
QIR_AURA = "qr8"
QIR_CFG = "qr9"
QIR_VAE_ENCODE = "qr10"
QIR_POS_ENCODE = "qr11"
QIR_NEG_ENCODE = "qr12"
QIR_POS_METHOD = "qr13"
QIR_NEG_METHOD = "qr14"
QIR_SAMPLER = "qr15"
QIR_VAE_DECODE = "qr16"
QIR_SAVE = "qr17"

# Qwen-Image-Material 专用节点 ID（材质替换：三图输入）
QIM_LOAD1 = "qm1"
QIM_SCALE1 = "qm2"
QIM_LOAD2 = "qm3"
QIM_SCALE2 = "qm4"
QIM_LOAD3 = "qm5"
QIM_VAE = "qm6"
QIM_CLIP = "qm7"
QIM_UNET = "qm8"
QIM_LORA = "qm9"
QIM_AURA = "qm10"
QIM_CFG = "qm11"
QIM_VAE_ENCODE = "qm12"
QIM_POS_ENCODE = "qm13"
QIM_NEG_ENCODE = "qm14"
QIM_POS_METHOD = "qm15"
QIM_NEG_METHOD = "qm16"
QIM_SAMPLER = "qm17"
QIM_VAE_DECODE = "qm18"
QIM_SAVE = "qm19"

_QWEN_REF_WORKFLOW_TYPES = frozenset(
    {
        "flux_pulid",
        "qwen-image-edit",
        "qwen-image-restore",
        "qwen-image-material",
    }
)


class ComfyUIError(Exception):
    """ComfyUI 调用失败。"""


class ComfyUIConnectionError(ComfyUIError):
    """无法连接 ComfyUI。"""


async def _pick_reachable_comfyui_url(urls: list[str]) -> str:
    last_error: Exception | None = None
    for url in urls:
        base = url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{base}/system_stats")
                res.raise_for_status()
            return base
        except (httpx.ConnectError, httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            continue
    raise ComfyUIError("ComfyUI 服务未启动，请检查 COMFYUI_URL") from last_error


def _first_enabled_text_model_id() -> str | None:
    from db.base import SessionLocal
    from models import RegisteredModel

    db = SessionLocal()
    try:
        row = (
            db.query(RegisteredModel)
            .filter(
                RegisteredModel.category == "text",
                RegisteredModel.enabled.is_(True),
            )
            .order_by(RegisteredModel.id)
            .first()
        )
        return row.id if row else None
    finally:
        db.close()


def _comfyui_base(node_url: str | None = None) -> str:
    url = (node_url or "").strip().rstrip("/")
    if url:
        return url
    return comfyui_http_url()


async def _translate_via_http(model_id: str, prompt: str, max_tokens: int = 500) -> str:
    from db.base import SessionLocal
    from models import RegisteredModel

    db = SessionLocal()
    try:
        row = (
            db.query(RegisteredModel)
            .filter(RegisteredModel.id == model_id, RegisteredModel.enabled.is_(True))
            .first()
        )
        api_key = get_registered_model_api_key(row)
        if not row or not api_key:
            raise ValueError(f"模型 {model_id} 未配置或未启用")
        api_base = (row.api_base or "").strip()
        if not api_base:
            raise ValueError(f"模型 {model_id} 未配置 API Base")

        url = f"{api_base.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=TRANSLATE_TIMEOUT) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": (row.model_string or row.id),
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")
    finally:
        db.close()


async def translate_if_chinese(text: str) -> str:
    """含中文时调用文本模型翻译为英文 prompt；失败则抛 ComfyUIError。"""
    from services.prompt import (
        PromptTranslationError,
        _l3_fallback_translate,
        contains_cjk,
        ensure_generation_prompt_english,
    )

    text = strip_mention_tokens(text)
    if not text:
        return text
    if not contains_cjk(text):
        return text

    translated, note = await _l3_fallback_translate(
        text, mode="image", reason="comfyui_submit_fallback"
    )
    if not translated:
        raise ComfyUIError(
            note or "Prompt translation failed; configure a text LLM in admin"
        )
    try:
        ensure_generation_prompt_english(translated, "")
    except PromptTranslationError as exc:
        raise ComfyUIError(str(exc)) from exc
    return translated


def _normalize_reference_url(image_url: str) -> str:
    """将前端/API 完整 URL 规范化为本地路径或 http URL。"""
    from services.media_access import normalize_media_reference_url

    url = normalize_media_reference_url((image_url or "").strip())
    if not url:
        return url
    if url.startswith("data:") or url.startswith("blob:"):
        return url
    if url.startswith("/api/view"):
        return url  # 保留 query（filename/subfolder）
    if url.startswith("/api/uploads/") or url.startswith("/uploads/"):
        return url.split("?", 1)[0]
    return url


def _is_data_url(image_ref: str) -> bool:
    return (image_ref or "").strip().startswith("data:")


def _decode_reference_base64(image_ref: str) -> tuple[bytes, str, str]:
    """解码 data URL 或纯 base64 字符串，返回 (bytes, mime, filename)。"""
    ref = (image_ref or "").strip()
    if not ref:
        raise ComfyUIError("参考图 base64 为空")

    mime = "image/png"
    payload = ref
    if ref.startswith("data:"):
        header, _, payload = ref.partition(",")
        if not payload:
            raise ComfyUIError("参考图 data URL 格式无效")
        mime_part = header[5:].split(";", 1)[0].strip()
        if mime_part:
            mime = mime_part

    try:
        data = base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise ComfyUIError(f"参考图 base64 解码失败: {exc}") from exc

    if not data:
        raise ComfyUIError("参考图 base64 解码结果为空")

    ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
    return data, mime, f"ref_upload{ext}"


async def _upload_image_bytes(
    data: bytes, filename: str, mime: str, *, base_url: str | None = None
) -> str:
    comfy_base = _comfyui_base(base_url)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.post(
            f"{comfy_base}/upload/image",
            files={"image": (filename, data, mime)},
        )
    print(
        f"[comfyui] upload image response: {response.status_code}, "
        f"{response.text[:500]}"
    )
    if response.status_code != 200:
        raise ComfyUIError(
            f"参考图上传失败: {response.status_code} {response.text[:300]}"
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise ComfyUIError(f"参考图上传响应解析失败: {response.text[:300]}") from exc
    name = payload.get("name")
    if not name:
        raise ComfyUIError("参考图上传失败: ComfyUI 未返回 filename")
    print(f"[comfyui] upload image filename: {name}")
    return str(name)


async def _upload_image_from_base64(
    image_ref: str, *, base_url: str | None = None
) -> str:
    data, mime, filename = _decode_reference_base64(image_ref)
    return await _upload_image_bytes(data, filename, mime, base_url=base_url)


async def _upload_reference_image(
    image_ref: str,
    *,
    db: Session | None = None,
    user: User | None = None,
    base_url: str | None = None,
) -> str:
    """上传参考图到 ComfyUI，支持 data URL / base64、本地路径、http URL。"""
    image_ref = _normalize_reference_url(image_ref)
    if not image_ref:
        raise ComfyUIError("参考图为空")
    if image_ref.startswith("blob:"):
        raise ComfyUIError("参考图为 blob URL，请先上传到服务器后再生成")
    if _is_data_url(image_ref):
        return await _upload_image_from_base64(image_ref, base_url=base_url)
    return await _upload_image_from_url(
        image_ref, db=db, user=user, base_url=base_url
    )


def _resolve_local_upload_path(image_url: str, *, db: Session, user: User) -> Path:
    """解析受鉴权保护的参考图路径（uploads 或 ComfyUI 输出）。"""
    from models import User as UserModel
    from services.media_access import resolve_image_reference_path

    if not isinstance(user, UserModel):
        raise ComfyUIError("参考图鉴权失败")
    return resolve_image_reference_path(db, user, image_url)


async def _upload_image_from_url(
    image_url: str,
    *,
    db: Session | None = None,
    user: User | None = None,
    base_url: str | None = None,
) -> str:
    """将参考图 URL/本地路径上传到 ComfyUI，返回 ComfyUI 侧 filename。"""
    image_url = _normalize_reference_url(image_url)
    if image_url.startswith("blob:"):
        raise ComfyUIError("参考图为 blob URL，请先上传到服务器后再生成")
    if _is_data_url(image_url):
        return await _upload_image_from_base64(image_url, base_url=base_url)

    if image_url.startswith("/uploads/") or image_url.startswith("/api/uploads/") or (
        not image_url.startswith("http")
    ):
        if db is None or user is None:
            raise ComfyUIError("本地参考图需要鉴权上下文")
        local_path = _resolve_local_upload_path(
            image_url.replace("/api/uploads/", "/uploads/"),
            db=db,
            user=user,
        )
        data = local_path.read_bytes()
        suffix = local_path.suffix or ".jpg"
        mime = "image/jpeg" if suffix.lower() in (".jpg", ".jpeg") else "image/png"
        filename = local_path.name
        return await _upload_image_bytes(data, filename, mime, base_url=base_url)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        img_res = await client.get(image_url)
        img_res.raise_for_status()
        if len(img_res.content) > 10 * 1024 * 1024:
            raise ComfyUIError("参考图过大（最大 10MB）")
        data = img_res.content
        mime = img_res.headers.get("content-type", "image/jpeg")
        filename = image_url.split("/")[-1].split("?", 1)[0] or "ref.jpg"
    return await _upload_image_bytes(data, filename, mime, base_url=base_url)


def _build_shared_nodes(
    prompt_text: str,
    model_filename: str,
    *,
    use_negative_prompt: bool = True,
    negative_text: str | None = None,
) -> dict:
    nodes = {
        NODE_CHECKPOINT: {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model_filename},
        },
        NODE_CLIP_POSITIVE: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": str(prompt_text).strip(),
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
    if use_negative_prompt:
        neg = (negative_text or "").strip() or NEGATIVE_PROMPT
        nodes[NODE_CLIP_NEGATIVE] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": neg,
                "clip": [NODE_CHECKPOINT, 1],
            },
        }
    return nodes


def _ksampler_inputs_from_defaults(
    gen_defaults: dict,
    seed: int,
    denoise: float,
    *,
    use_negative_prompt: bool,
) -> dict:
    inputs = {
        "seed": seed,
        "steps": int(gen_defaults.get("steps", _FALLBACK_GEN_DEFAULTS["steps"])),
        "cfg": float(gen_defaults.get("cfg", _FALLBACK_GEN_DEFAULTS["cfg"])),
        "sampler_name": str(
            gen_defaults.get("sampler_name", _FALLBACK_GEN_DEFAULTS["sampler_name"])
        ),
        "scheduler": str(
            gen_defaults.get("scheduler", _FALLBACK_GEN_DEFAULTS["scheduler"])
        ),
        "denoise": float(denoise),
        "model": [NODE_CHECKPOINT, 0],
        "positive": [NODE_CLIP_POSITIVE, 0],
    }
    if use_negative_prompt:
        inputs["negative"] = [NODE_CLIP_NEGATIVE, 0]
    return inputs


def _build_text2img_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    gen_defaults: dict,
    *,
    use_negative_prompt: bool = True,
    negative_prompt: str | None = None,
) -> dict:
    workflow = _build_shared_nodes(
        prompt_text,
        model_filename,
        use_negative_prompt=use_negative_prompt,
        negative_text=negative_prompt,
    )
    denoise = float(
        gen_defaults.get("denoise_txt2img", _FALLBACK_GEN_DEFAULTS["denoise_txt2img"])
    )
    workflow[NODE_KSAMPLER] = {
        "class_type": "KSampler",
        "inputs": {
            **_ksampler_inputs_from_defaults(
                gen_defaults,
                seed,
                denoise,
                use_negative_prompt=use_negative_prompt,
            ),
            "latent_image": [NODE_EMPTY_LATENT, 0],
        },
    }
    workflow[NODE_EMPTY_LATENT] = {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": int(width),
            "height": int(height),
            "batch_size": 1,
        },
    }
    return workflow


def _finalize_img2img_workflow(workflow: dict) -> dict:
    """确保 img2img 走 VAEEncode latent，并移除 EmptyLatentImage。"""
    workflow.pop(NODE_EMPTY_LATENT, None)

    if NODE_VAE_ENCODE not in workflow:
        raise ComfyUIError("img2img workflow 缺少 VAEEncode 节点")
    if NODE_LOAD_IMAGE not in workflow:
        raise ComfyUIError("img2img workflow 缺少 LoadImage 节点")
    if NODE_KSAMPLER not in workflow:
        raise ComfyUIError("img2img workflow 缺少 KSampler 节点")

    ksampler = workflow[NODE_KSAMPLER]
    inputs = ksampler.setdefault("inputs", {})
    inputs["latent_image"] = [NODE_VAE_ENCODE, 0]

    latent_ref = inputs.get("latent_image")
    print(f"[comfyui] KSampler latent_image wired to: {latent_ref}")
    if latent_ref != [NODE_VAE_ENCODE, 0]:
        raise ComfyUIError(
            f"img2img KSampler latent_image 连线错误: {latent_ref!r}, "
            f"期望 {[NODE_VAE_ENCODE, 0]!r}"
        )
    return workflow


def _build_img2img_workflow(
    prompt_text: str,
    model_filename: str,
    reference_filename: str,
    width: int,
    height: int,
    seed: int,
    gen_defaults: dict,
    *,
    use_negative_prompt: bool = True,
    denoise: float | None = None,
    negative_prompt: str | None = None,
) -> dict:
    if denoise is None:
        denoise = float(
            gen_defaults.get("denoise_img2img", _FALLBACK_GEN_DEFAULTS["denoise_img2img"])
        )
    workflow = _build_shared_nodes(
        prompt_text,
        model_filename,
        use_negative_prompt=use_negative_prompt,
        negative_text=negative_prompt,
    )
    workflow[NODE_LOAD_IMAGE] = {
        "class_type": "LoadImage",
        "inputs": {"image": reference_filename},
    }
    workflow[NODE_IMAGE_SCALE] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": [NODE_LOAD_IMAGE, 0],
            "width": int(width),
            "height": int(height),
            "upscale_method": "lanczos",
            "crop": "disabled",
        },
    }
    workflow[NODE_VAE_ENCODE] = {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": [NODE_IMAGE_SCALE, 0],
            "vae": [NODE_CHECKPOINT, 2],
        },
    }
    workflow[NODE_KSAMPLER] = {
        "class_type": "KSampler",
        "inputs": {
            **_ksampler_inputs_from_defaults(
                gen_defaults,
                seed,
                denoise,
                use_negative_prompt=use_negative_prompt,
            ),
            "latent_image": [NODE_VAE_ENCODE, 0],
        },
    }
    return _finalize_img2img_workflow(workflow)


def _is_flux_schnell(model_filename: str, profile: dict) -> bool:
    """按 checkpoint 文件名或 generation_defaults 判断 Schnell 变体。"""
    name = (model_filename or "").lower()
    if "schnell" in name:
        return True
    defaults = profile.get("generation_defaults") or {}
    try:
        return int(defaults.get("steps", 25)) <= 4
    except (TypeError, ValueError):
        return False


def _flux_guidance_value(profile: dict, *, schnell: bool) -> float:
    """Flux Dev: guidance≤4.5；Schnell: 固定 1.0。"""
    if schnell:
        return 1.0
    defaults = profile.get("generation_defaults") or {}
    try:
        guidance = float(defaults.get("cfg", 3.5))
    except (TypeError, ValueError):
        guidance = 3.5
    return min(max(guidance, 0.0), 4.5)


def _build_flux_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
) -> dict:
    """
    Flux txt2img：UNETLoader + DualCLIPLoader + SamplerCustomAdvanced 链路。
    不支持 img2img / 负向提示词（调用方已在 _build_workflow 降级处理）。
    """
    gen_defaults = profile.get("generation_defaults") or {}
    schnell = _is_flux_schnell(model_filename, profile)
    steps = int(gen_defaults.get("steps", 4 if schnell else 25))
    sampler_name = str(gen_defaults.get("sampler_name", "euler"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    guidance = _flux_guidance_value(profile, schnell=schnell)

    print(
        f"[comfyui] Flux workflow model={model_filename!r} "
        f"variant={'schnell' if schnell else 'dev'} "
        f"size={width}x{height} steps={steps} guidance={guidance}"
    )
    studio_print(
        "comfyui-image",
        f"Flux workflow {'schnell' if schnell else 'dev'}: "
        f"{model_filename} {width}x{height} steps={steps}",
    )

    return {
        FLUX_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": model_filename,
                "weight_dtype": "default",
            },
        },
        FLUX_DUAL_CLIP: {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": _FLUX_CLIP_L,
                "clip_name2": _FLUX_CLIP_T5,
                "type": "flux",
            },
        },
        FLUX_VAE_LOADER: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _FLUX_VAE},
        },
        FLUX_CLIP_ENCODE: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": str(prompt_text).strip(),
                "clip": [FLUX_DUAL_CLIP, 0],
            },
        },
        FLUX_GUIDANCE: {
            "class_type": "FluxGuidance",
            "inputs": {
                "guidance": guidance,
                "conditioning": [FLUX_CLIP_ENCODE, 0],
            },
        },
        FLUX_EMPTY_LATENT: {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        FLUX_RANDOM_NOISE: {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": int(seed)},
        },
        FLUX_SAMPLER_SELECT: {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": sampler_name},
        },
        FLUX_SCHEDULER: {
            "class_type": "BasicScheduler",
            "inputs": {
                "scheduler": scheduler,
                "steps": steps,
                "denoise": 1.0,
                "model": [FLUX_UNET, 0],
            },
        },
        FLUX_GUIDER: {
            "class_type": "BasicGuider",
            "inputs": {
                "model": [FLUX_UNET, 0],
                "conditioning": [FLUX_GUIDANCE, 0],
            },
        },
        FLUX_SAMPLER: {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": [FLUX_RANDOM_NOISE, 0],
                "guider": [FLUX_GUIDER, 0],
                "sampler": [FLUX_SAMPLER_SELECT, 0],
                "sigmas": [FLUX_SCHEDULER, 0],
                "latent_image": [FLUX_EMPTY_LATENT, 0],
            },
        },
        FLUX_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [FLUX_SAMPLER, 0],
                "vae": [FLUX_VAE_LOADER, 0],
            },
        },
        FLUX_SAVE_IMAGE: {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": [FLUX_VAE_DECODE, 0],
            },
        },
    }


def _resolve_pulid_t5_encoder() -> str:
    te = _COMFY_MODELS / "text_encoders"
    if (te / _FLUX_CLIP_T5_FP16).exists():
        return _FLUX_CLIP_T5_FP16
    return _FLUX_CLIP_T5


_REACTOR_SWAP_MODEL = "inswapper_128.onnx"
_REACTOR_RESTORE_MODEL = "GFPGANv1.4.pth"
FLUX_PULID_REACTOR_KEY = "flux_pulid_reactor.json"


def _attach_reactor_face_swap(workflow: dict) -> dict:
    """VAEDecode(8) 后接 ReActorFaceSwap(60)；SaveImage 吃换脸输出；源脸复用 LoadImage(49)。"""
    workflow = dict(workflow)
    workflow["60"] = {
        "class_type": "ReActorFaceSwap",
        "inputs": {
            "enabled": True,
            "input_image": ["8", 0],
            "swap_model": _REACTOR_SWAP_MODEL,
            "facedetection": "retinaface_resnet50",
            "face_restore_model": _REACTOR_RESTORE_MODEL,
            "face_restore_visibility": 1.0,
            "codeformer_weight": 0.5,
            "detect_gender_input": "no",
            "detect_gender_source": "no",
            "input_faces_index": "0",
            "source_faces_index": "0",
            "console_log_level": 1,
            "source_image": ["49", 0],
        },
    }
    save = dict(workflow.get("9") or {})
    save_inputs = dict(save.get("inputs") or {})
    save_inputs["images"] = ["60", 0]
    save_inputs["filename_prefix"] = save_inputs.get("filename_prefix") or "AIStudio_pulid_reactor"
    save["class_type"] = "SaveImage"
    save["inputs"] = save_inputs
    workflow["9"] = save
    return workflow


def build_reactor_frame_workflow(
    *,
    frame_filename: str,
    face_filename: str,
    filename_prefix: str = "AIStudio_reactor_frame",
) -> dict:
    """
    G45 独立逐帧换脸工作流（不跑 PuLID）：
    LoadImage(1)=帧 · LoadImage(2)=正脸 · ReActorFaceSwap(60) · SaveImage(9)
    """
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": frame_filename},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": face_filename},
        },
        "60": {
            "class_type": "ReActorFaceSwap",
            "inputs": {
                "enabled": True,
                "input_image": ["1", 0],
                "swap_model": _REACTOR_SWAP_MODEL,
                "facedetection": "retinaface_resnet50",
                "face_restore_model": _REACTOR_RESTORE_MODEL,
                "face_restore_visibility": 1.0,
                "codeformer_weight": 0.5,
                "detect_gender_input": "no",
                "detect_gender_source": "no",
                "input_faces_index": "0",
                "source_faces_index": "0",
                "console_log_level": 1,
                "source_image": ["2", 0],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": ["60", 0],
            },
        },
    }


def _build_flux_pulid_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
    *,
    reference_face_image: str,
    pulid_weight: float | None = None,
    use_reactor: bool = False,
) -> dict:
    """
    Flux + Nunchaku PuLID：基于官方 api.json 节点链。
    reference_face_image 为 ComfyUI input 目录内文件名。
    use_reactor=True 时在出图后接 ReActorFaceSwap（源脸=节点49）。
    """
    gen_defaults = profile.get("generation_defaults") or {}
    steps = int(gen_defaults.get("steps", 20))
    sampler_name = str(gen_defaults.get("sampler_name", "euler"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    guidance = _flux_guidance_value(profile, schnell=False)
    weight = float(pulid_weight if pulid_weight is not None else gen_defaults.get("pulid_weight", 0.8))
    t5_name = _resolve_pulid_t5_encoder()
    dit_name = model_filename or "svdq-fp4_r32-flux.1-dev.safetensors"

    studio_print(
        "comfyui-image",
        f"Flux PuLID workflow: {dit_name} {width}x{height} steps={steps} "
        f"pulid={weight} use_reactor={bool(use_reactor)}",
    )

    if use_reactor:
        workflow = deepcopy(load_workflow_template(FLUX_PULID_REACTOR_KEY))
        workflow["6"]["inputs"]["text"] = str(prompt_text).strip()
        workflow["49"]["inputs"]["image"] = reference_face_image
        workflow["25"]["inputs"]["noise_seed"] = int(seed)
        workflow["27"]["inputs"]["width"] = int(width)
        workflow["27"]["inputs"]["height"] = int(height)
        workflow["30"]["inputs"]["width"] = int(width)
        workflow["30"]["inputs"]["height"] = int(height)
        workflow["50"]["inputs"]["model_path"] = dit_name
        workflow["52"]["inputs"]["weight"] = weight
        workflow["17"]["inputs"]["steps"] = steps
        workflow["17"]["inputs"]["scheduler"] = scheduler
        workflow["16"]["inputs"]["sampler_name"] = sampler_name
        workflow["26"]["inputs"]["guidance"] = guidance
        workflow["54"]["inputs"]["text_encoder2"] = t5_name
        return workflow

    # 无 ReActor 路径仍为 Python builder；sd15/flux/qwen 等待导出 JSON 后再迁 registry。
    workflow = {
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": str(prompt_text).strip(), "clip": ["54", 0]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["13", 0], "vae": ["10", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]},
        },
        "10": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _FLUX_VAE},
        },
        "13": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["25", 0],
                "guider": ["22", 0],
                "sampler": ["16", 0],
                "sigmas": ["17", 0],
                "latent_image": ["27", 0],
            },
        },
        "16": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": sampler_name},
        },
        "17": {
            "class_type": "BasicScheduler",
            "inputs": {
                "scheduler": scheduler,
                "steps": steps,
                "denoise": 1.0,
                "model": ["30", 0],
            },
        },
        "22": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["30", 0], "conditioning": ["26", 0]},
        },
        "25": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": int(seed)},
        },
        "26": {
            "class_type": "FluxGuidance",
            "inputs": {"guidance": guidance, "conditioning": ["6", 0]},
        },
        "27": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
        },
        "30": {
            "class_type": "ModelSamplingFlux",
            "inputs": {
                "max_shift": 1.15,
                "base_shift": 0.5,
                "width": int(width),
                "height": int(height),
                "model": ["52", 0],
            },
        },
        "49": {
            "class_type": "LoadImage",
            "inputs": {"image": reference_face_image},
        },
        "50": {
            "class_type": "NunchakuFluxDiTLoader",
            "inputs": {
                "model_path": dit_name,
                "cache_threshold": 0.09,
                "attention": "nunchaku-fp16",
                "cpu_offload": "auto",
                "device_id": 0,
                "data_type": "bfloat16",
                "i2f_mode": "enabled",
            },
        },
        "52": {
            "class_type": "NunchakuFluxPuLIDApplyV2",
            "inputs": {
                "weight": weight,
                "start_at": 0.0,
                "end_at": 1.0,
                "model": ["53", 0],
                "pulid_pipline": ["53", 1],
                "image": ["49", 0],
            },
        },
        "53": {
            "class_type": "NunchakuPuLIDLoaderV2",
            "inputs": {
                "pulid_file": _PULID_CKPT,
                "eva_clip_file": _PULID_EVA_CLIP,
                "insight_face_provider": "gpu",
                "model": ["50", 0],
            },
        },
        "54": {
            "class_type": "NunchakuTextEncoderLoaderV2",
            "inputs": {
                "model_type": "flux.1",
                "text_encoder1": _FLUX_CLIP_L,
                "text_encoder2": t5_name,
                "t5_min_length": 512,
            },
        },
    }
    return workflow


def _build_hidream_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
) -> dict:
    """
    HiDream txt2img：UNETLoader + QuadrupleCLIPLoader + ModelSamplingSD3 + KSampler。
    基于 ComfyUI 原生 HiDream-I1 工作流（无负向提示词 / img2img）。
    """
    gen_defaults = profile.get("generation_defaults") or {}
    steps = int(gen_defaults.get("steps", 50))
    cfg = float(gen_defaults.get("cfg", 5.0))
    sampler_name = str(gen_defaults.get("sampler_name", "uni_pc"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    shift = float(gen_defaults.get("shift", 3.0))

    print(
        f"[comfyui] HiDream workflow model={model_filename!r} "
        f"size={width}x{height} steps={steps} cfg={cfg} shift={shift}"
    )
    studio_print(
        "comfyui-image",
        f"HiDream workflow: {model_filename} {width}x{height} steps={steps}",
    )

    return {
        HIDREAM_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": model_filename,
                "weight_dtype": "default",
            },
        },
        HIDREAM_QUAD_CLIP: {
            "class_type": "QuadrupleCLIPLoader",
            "inputs": {
                "clip_name1": _HIDREAM_CLIP_L,
                "clip_name2": _HIDREAM_CLIP_G,
                "clip_name3": _HIDREAM_T5,
                "clip_name4": _HIDREAM_LLAMA,
            },
        },
        HIDREAM_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _HIDREAM_VAE},
        },
        HIDREAM_CLIP_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": str(prompt_text).strip(),
                "clip": [HIDREAM_QUAD_CLIP, 0],
            },
        },
        HIDREAM_CLIP_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "",
                "clip": [HIDREAM_QUAD_CLIP, 0],
            },
        },
        HIDREAM_MODEL_SAMPLING: {
            "class_type": "ModelSamplingSD3",
            "inputs": {
                "shift": shift,
                "model": [HIDREAM_UNET, 0],
            },
        },
        HIDREAM_EMPTY_LATENT: {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        HIDREAM_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": [HIDREAM_MODEL_SAMPLING, 0],
                "positive": [HIDREAM_CLIP_POS, 0],
                "negative": [HIDREAM_CLIP_NEG, 0],
                "latent_image": [HIDREAM_EMPTY_LATENT, 0],
            },
        },
        HIDREAM_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [HIDREAM_SAMPLER, 0],
                "vae": [HIDREAM_VAE, 0],
            },
        },
        HIDREAM_SAVE_IMAGE: {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": [HIDREAM_VAE_DECODE, 0],
            },
        },
    }


def _build_qwen_image_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
) -> dict:
    """
    Qwen-Image txt2img：NunchakuQwenImageDiTLoader + ModelSamplingAuraFlow + KSampler。
    负向固定空格（KSampler 需接 negative 输入，产品不暴露负向框）。
    """
    gen_defaults = profile.get("generation_defaults") or {}
    steps = int(gen_defaults.get("steps", 4))
    cfg = float(gen_defaults.get("cfg", 1.0))
    sampler_name = str(gen_defaults.get("sampler_name", "euler"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    aura_shift = float(gen_defaults.get("aura_shift", 3.1))
    denoise = float(gen_defaults.get("denoise_txt2img", 1.0))

    print(
        f"[comfyui] Qwen-Image workflow model={model_filename!r} "
        f"size={width}x{height} steps={steps} cfg={cfg} shift={aura_shift}"
    )
    studio_print(
        "comfyui-image",
        f"Qwen-Image workflow: {model_filename} {width}x{height} steps={steps}",
    )

    return {
        QWEN_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _QWEN_VAE},
        },
        QWEN_EMPTY_LATENT: {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        QWEN_CLIP_NEG: {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": [QWEN_CLIP_LOADER, 0], "text": " "},
        },
        QWEN_CLIP_LOADER: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": _QWEN_CLIP,
                "type": "qwen_image",
                "device": "default",
            },
        },
        QWEN_AURA_FLOW: {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": [QWEN_DIT, 0], "shift": aura_shift},
        },
        QWEN_CLIP_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": [QWEN_CLIP_LOADER, 0],
                "text": str(prompt_text).strip(),
            },
        },
        QWEN_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "model": [QWEN_AURA_FLOW, 0],
                "positive": [QWEN_CLIP_POS, 0],
                "negative": [QWEN_CLIP_NEG, 0],
                "latent_image": [QWEN_EMPTY_LATENT, 0],
                "seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        QWEN_DIT: {
            "class_type": "NunchakuQwenImageDiTLoader",
            "inputs": {
                "model_name": model_filename,
                "cpu_offload": "auto",
                "num_blocks_on_gpu": 1,
                "use_pin_memory": "disable",
            },
        },
        QWEN_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {"samples": [QWEN_SAMPLER, 0], "vae": [QWEN_VAE, 0]},
        },
        QWEN_SAVE_IMAGE: {
            "class_type": "SaveImage",
            "inputs": {
                "images": [QWEN_VAE_DECODE, 0],
                "filename_prefix": "AIStudio_QwenImage",
            },
        },
    }


def _build_qwen_image_edit_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
    reference_image: str,
) -> dict:
    """
    Qwen-Image-Edit：UNET + Lightning LoRA + TextEncodeQwenImageEditPlus。
    结构参照云绘 Edit2509/2511（单图编辑，不含多角度 LoRA）。
    """
    if not reference_image:
        raise ComfyUIError("qwen-image-edit 需要参考图 (reference_image)")

    gen_defaults = profile.get("generation_defaults") or {}
    steps = int(gen_defaults.get("steps", 4))
    cfg = float(gen_defaults.get("cfg", 1.0))
    sampler_name = str(gen_defaults.get("sampler_name", "euler"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    aura_shift = float(gen_defaults.get("aura_shift", 3.1))
    denoise = float(gen_defaults.get("denoise_img2img", 1.0))
    megapixels = float(gen_defaults.get("megapixels", 1.0))
    unet_name = model_filename or _QWEN_EDIT_UNET

    print(
        f"[comfyui] Qwen-Image-Edit workflow unet={unet_name!r} ref={reference_image!r} "
        f"steps={steps} cfg={cfg} megapixels={megapixels}"
    )
    studio_print(
        "comfyui-image",
        f"Qwen-Image-Edit workflow: {unet_name} steps={steps} ref={reference_image}",
    )

    return {
        QIE_LOAD: {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image},
        },
        QIE_SCALE: {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": [QIE_LOAD, 0],
                "upscale_method": "lanczos",
                "megapixels": megapixels,
                "resolution_steps": 1,
            },
        },
        QIE_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _QWEN_VAE},
        },
        QIE_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": _QWEN_CLIP,
                "type": "stable_diffusion",
                "device": "default",
            },
        },
        QIE_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": "default",
            },
        },
        QIE_LORA: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [QIE_UNET, 0],
                "lora_name": _QWEN_EDIT_LORA_LIGHTNING,
                "strength_model": 1.0,
            },
        },
        QIE_AURA: {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": [QIE_LORA, 0], "shift": aura_shift},
        },
        QIE_CFG: {
            "class_type": "CFGNorm",
            "inputs": {"model": [QIE_AURA, 0], "strength": 1.0},
        },
        QIE_VAE_ENCODE: {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [QIE_SCALE, 0],
                "vae": [QIE_VAE, 0],
            },
        },
        QIE_NEG_ENCODE: {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {
                "clip": [QIE_CLIP, 0],
                "vae": [QIE_VAE, 0],
                "image1": [QIE_SCALE, 0],
                "prompt": "",
            },
        },
        QIE_POS_ENCODE: {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {
                "clip": [QIE_CLIP, 0],
                "vae": [QIE_VAE, 0],
                "image1": [QIE_SCALE, 0],
                "prompt": str(prompt_text).strip(),
            },
        },
        QIE_NEG_METHOD: {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": [QIE_NEG_ENCODE, 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        QIE_POS_METHOD: {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": [QIE_POS_ENCODE, 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        QIE_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "model": [QIE_CFG, 0],
                "positive": [QIE_POS_METHOD, 0],
                "negative": [QIE_NEG_METHOD, 0],
                "latent_image": [QIE_VAE_ENCODE, 0],
                "seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        QIE_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [QIE_SAMPLER, 0],
                "vae": [QIE_VAE, 0],
            },
        },
        QIE_SAVE: {
            "class_type": "SaveImage",
            "inputs": {
                "images": [QIE_VAE_DECODE, 0],
                "filename_prefix": "AIStudio_QwenImageEdit",
            },
        },
    }


def _qwen_edit_encode_inputs(
    *,
    clip_node: str,
    vae_node: str,
    image1_node: str,
    image1_slot: int,
    prompt: str,
    image2_node: str | None = None,
    image2_slot: int = 0,
    image3_node: str | None = None,
    image3_slot: int = 0,
) -> dict:
    inputs: dict = {
        "clip": [clip_node, 0],
        "vae": [vae_node, 0],
        "image1": [image1_node, image1_slot],
        "prompt": prompt,
    }
    if image2_node is not None:
        inputs["image2"] = [image2_node, image2_slot]
    if image3_node is not None:
        inputs["image3"] = [image3_node, image3_slot]
    return inputs


def _build_qwen_image_restore_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
    reference_image: str,
) -> dict:
    """
    Qwen-Image-Restore：老照片修复。
    UNET + 多角度 LoRA + Lightning LoRA + TextEncodeQwenImageEditPlus，单图输入。
    """
    if not reference_image:
        raise ComfyUIError("qwen-image-restore 需要参考图 (reference_image)")

    gen_defaults = profile.get("generation_defaults") or {}
    steps = int(gen_defaults.get("steps", 4))
    cfg = float(gen_defaults.get("cfg", 1.0))
    sampler_name = str(gen_defaults.get("sampler_name", "euler"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    aura_shift = float(gen_defaults.get("aura_shift", 3.1))
    denoise = float(gen_defaults.get("denoise_img2img", 1.0))
    megapixels = float(gen_defaults.get("megapixels", 1.2))
    unet_name = model_filename or _QWEN_EDIT_UNET

    print(
        f"[comfyui] Qwen-Image-Restore workflow unet={unet_name!r} ref={reference_image!r} "
        f"steps={steps} cfg={cfg} megapixels={megapixels}"
    )
    studio_print(
        "comfyui-image",
        f"Qwen-Image-Restore workflow: {unet_name} steps={steps} ref={reference_image}",
    )

    return {
        QIR_LOAD: {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image},
        },
        QIR_SCALE: {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": [QIR_LOAD, 0],
                "upscale_method": "lanczos",
                "megapixels": megapixels,
                "resolution_steps": 1,
            },
        },
        QIR_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _QWEN_VAE},
        },
        QIR_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": _QWEN_CLIP,
                "type": "stable_diffusion",
                "device": "default",
            },
        },
        QIR_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": "default",
            },
        },
        QIR_LORA_ANGLES: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [QIR_UNET, 0],
                "lora_name": _QWEN_EDIT_LORA_ANGLES,
                "strength_model": 1.0,
            },
        },
        QIR_LORA_LIGHTNING: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [QIR_LORA_ANGLES, 0],
                "lora_name": _QWEN_EDIT_LORA_LIGHTNING,
                "strength_model": 1.0,
            },
        },
        QIR_AURA: {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": [QIR_LORA_LIGHTNING, 0], "shift": aura_shift},
        },
        QIR_CFG: {
            "class_type": "CFGNorm",
            "inputs": {"model": [QIR_AURA, 0], "strength": 1.0},
        },
        QIR_VAE_ENCODE: {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [QIR_SCALE, 0],
                "vae": [QIR_VAE, 0],
            },
        },
        QIR_NEG_ENCODE: {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": _qwen_edit_encode_inputs(
                clip_node=QIR_CLIP,
                vae_node=QIR_VAE,
                image1_node=QIR_SCALE,
                image1_slot=0,
                prompt="",
            ),
        },
        QIR_POS_ENCODE: {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": _qwen_edit_encode_inputs(
                clip_node=QIR_CLIP,
                vae_node=QIR_VAE,
                image1_node=QIR_SCALE,
                image1_slot=0,
                prompt=str(prompt_text).strip(),
            ),
        },
        QIR_NEG_METHOD: {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": [QIR_NEG_ENCODE, 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        QIR_POS_METHOD: {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": [QIR_POS_ENCODE, 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        QIR_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "model": [QIR_CFG, 0],
                "positive": [QIR_POS_METHOD, 0],
                "negative": [QIR_NEG_METHOD, 0],
                "latent_image": [QIR_VAE_ENCODE, 0],
                "seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        QIR_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [QIR_SAMPLER, 0],
                "vae": [QIR_VAE, 0],
            },
        },
        QIR_SAVE: {
            "class_type": "SaveImage",
            "inputs": {
                "images": [QIR_VAE_DECODE, 0],
                "filename_prefix": "AIStudio_QwenImageRestore",
            },
        },
    }


def _build_qwen_image_material_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
    *,
    image1: str,
    image2: str,
    image3: str | None = None,
) -> dict:
    """
    Qwen-Image-Material：材质替换。
    主图 image1 + 材质参考 image2 必填，image3 可选；仅 Lightning LoRA。
    """
    if not image1 or not image2:
        raise ComfyUIError("qwen-image-material 需要主图与材质参考图")

    gen_defaults = profile.get("generation_defaults") or {}
    steps = int(gen_defaults.get("steps", 4))
    cfg = float(gen_defaults.get("cfg", 1.0))
    sampler_name = str(gen_defaults.get("sampler_name", "euler"))
    scheduler = str(gen_defaults.get("scheduler", "simple"))
    aura_shift = float(gen_defaults.get("aura_shift", 3.1))
    denoise = float(gen_defaults.get("denoise_img2img", 1.0))
    megapixels = float(gen_defaults.get("megapixels", 1.0))
    unet_name = model_filename or _QWEN_EDIT_UNET

    print(
        f"[comfyui] Qwen-Image-Material workflow unet={unet_name!r} "
        f"image1={image1!r} image2={image2!r} image3={image3!r} "
        f"steps={steps} cfg={cfg}"
    )
    studio_print(
        "comfyui-image",
        f"Qwen-Image-Material workflow: {unet_name} steps={steps} "
        f"refs={1 + bool(image2) + bool(image3)}",
    )

    pos_encode_inputs = _qwen_edit_encode_inputs(
        clip_node=QIM_CLIP,
        vae_node=QIM_VAE,
        image1_node=QIM_SCALE1,
        image1_slot=0,
        image2_node=QIM_SCALE2,
        image2_slot=0,
        prompt=str(prompt_text).strip(),
    )
    neg_encode_inputs = _qwen_edit_encode_inputs(
        clip_node=QIM_CLIP,
        vae_node=QIM_VAE,
        image1_node=QIM_SCALE1,
        image1_slot=0,
        image2_node=QIM_SCALE2,
        image2_slot=0,
        prompt="",
    )
    if image3:
        pos_encode_inputs["image3"] = [QIM_LOAD3, 0]
        neg_encode_inputs["image3"] = [QIM_LOAD3, 0]

    workflow: dict = {
        QIM_LOAD1: {
            "class_type": "LoadImage",
            "inputs": {"image": image1},
        },
        QIM_SCALE1: {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": [QIM_LOAD1, 0],
                "upscale_method": "lanczos",
                "megapixels": megapixels,
                "resolution_steps": 1,
            },
        },
        QIM_LOAD2: {
            "class_type": "LoadImage",
            "inputs": {"image": image2},
        },
        QIM_SCALE2: {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": [QIM_LOAD2, 0],
                "upscale_method": "lanczos",
                "megapixels": megapixels,
                "resolution_steps": 1,
            },
        },
        QIM_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": _QWEN_VAE},
        },
        QIM_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": _QWEN_CLIP,
                "type": "stable_diffusion",
                "device": "default",
            },
        },
        QIM_UNET: {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": "default",
            },
        },
        QIM_LORA: {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [QIM_UNET, 0],
                "lora_name": _QWEN_EDIT_LORA_LIGHTNING,
                "strength_model": 1.0,
            },
        },
        QIM_AURA: {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": [QIM_LORA, 0], "shift": aura_shift},
        },
        QIM_CFG: {
            "class_type": "CFGNorm",
            "inputs": {"model": [QIM_AURA, 0], "strength": 1.0},
        },
        QIM_VAE_ENCODE: {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [QIM_SCALE1, 0],
                "vae": [QIM_VAE, 0],
            },
        },
        QIM_NEG_ENCODE: {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": neg_encode_inputs,
        },
        QIM_POS_ENCODE: {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": pos_encode_inputs,
        },
        QIM_NEG_METHOD: {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": [QIM_NEG_ENCODE, 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        QIM_POS_METHOD: {
            "class_type": "FluxKontextMultiReferenceLatentMethod",
            "inputs": {
                "conditioning": [QIM_POS_ENCODE, 0],
                "reference_latents_method": "index_timestep_zero",
            },
        },
        QIM_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "model": [QIM_CFG, 0],
                "positive": [QIM_POS_METHOD, 0],
                "negative": [QIM_NEG_METHOD, 0],
                "latent_image": [QIM_VAE_ENCODE, 0],
                "seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        QIM_VAE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [QIM_SAMPLER, 0],
                "vae": [QIM_VAE, 0],
            },
        },
        QIM_SAVE: {
            "class_type": "SaveImage",
            "inputs": {
                "images": [QIM_VAE_DECODE, 0],
                "filename_prefix": "AIStudio_QwenImageMaterial",
            },
        },
    }
    if image3:
        workflow[QIM_LOAD3] = {
            "class_type": "LoadImage",
            "inputs": {"image": image3},
        }
    return workflow


def _build_ksampler_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int,
    profile: dict,
    reference_filename: str | None = None,
    *,
    denoise_override: float | None = None,
    negative_prompt: str | None = None,
) -> tuple[dict, str]:
    """sd15 / sdxl：CheckpointLoader + KSampler 分支。"""
    gen_defaults = profile.get("generation_defaults") or _FALLBACK_GEN_DEFAULTS
    use_negative_prompt = bool(profile.get("negative_prompt", True))

    if reference_filename:
        workflow = _build_img2img_workflow(
            prompt_text,
            model_filename,
            reference_filename,
            width,
            height,
            seed,
            gen_defaults,
            use_negative_prompt=use_negative_prompt,
            denoise=denoise_override,
            negative_prompt=negative_prompt,
        )
        return workflow, "img2img"
    workflow = _build_text2img_workflow(
        prompt_text,
        model_filename,
        width,
        height,
        seed,
        gen_defaults,
        use_negative_prompt=use_negative_prompt,
        negative_prompt=negative_prompt,
    )
    return workflow, "txt2img"


def _build_workflow(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    seed: int | None = None,
    reference_filename: str | None = None,
    reference_filenames: list[str] | None = None,
    reference_images: list[str] | None = None,
    model_id: str | None = None,
    *,
    denoise_override: float | None = None,
    negative_prompt: str | None = None,
    use_reactor: bool = False,
) -> tuple[dict, str]:
    ref_count = len(reference_images) if reference_images else 0
    print(
        f"[comfyui] reference_images count: {ref_count}, "
        f"type={type(reference_images).__name__}"
    )

    profile = resolve_generation_profile(model_id, model_filename)
    workflow_type = profile.get("workflow_type", "sd15")
    print(
        f"[comfyui] workflow_type={workflow_type} "
        f"img2img_support={profile.get('img2img_support')}"
    )

    effective_reference = reference_filename
    if (
        reference_filename
        and profile.get("img2img_support") == "unsupported"
        and workflow_type not in _QWEN_REF_WORKFLOW_TYPES
    ):
        print(
            "[comfyui] 警告: 当前模型不支持传统 img2img，已降级为 txt2img "
            f"(model={model_filename!r}, workflow_type={workflow_type})"
        )
        studio_print(
            "comfyui-image",
            f"img2img 不支持，降级 txt2img: {model_filename}",
        )
        effective_reference = None

    mode = "img2img" if effective_reference else "txt2img"
    print(f"[comfyui] mode: {mode} (reference_filename={effective_reference!r})")

    if seed is None:
        seed = random.randint(0, 2**53 - 1)

    if workflow_type == "flux_pulid":
        if not effective_reference:
            raise ComfyUIError("flux-pulid 需要角色正脸参考图 (reference_image)")
        gen_defaults = profile.get("generation_defaults") or {}
        pulid_weight = gen_defaults.get("pulid_weight", 0.8)
        workflow = _build_flux_pulid_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
            reference_face_image=effective_reference,
            pulid_weight=float(pulid_weight) if pulid_weight is not None else 0.8,
            use_reactor=bool(use_reactor),
        )
        return workflow, "pulid_reactor" if use_reactor else "pulid"

    if workflow_type == "qwen-image-edit":
        if not effective_reference:
            raise ComfyUIError("qwen-image-edit 需要参考图 (reference_image)")
        workflow = _build_qwen_image_edit_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
            reference_image=effective_reference,
        )
        return workflow, "qwen_image_edit"

    if workflow_type == "qwen-image-restore":
        if not effective_reference:
            raise ComfyUIError("qwen-image-restore 需要参考图 (reference_image)")
        workflow = _build_qwen_image_restore_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
            reference_image=effective_reference,
        )
        return workflow, "qwen_image_restore"

    if workflow_type == "qwen-image-material":
        refs = [r for r in (reference_filenames or []) if r]
        if len(refs) < 2:
            raise ComfyUIError("qwen-image-material 需要主图与材质参考图")
        workflow = _build_qwen_image_material_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
            image1=refs[0],
            image2=refs[1],
            image3=refs[2] if len(refs) > 2 else None,
        )
        return workflow, "qwen_image_material"

    if workflow_type == "flux":
        workflow = _build_flux_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
        )
        return workflow, "txt2img"

    if workflow_type == "hidream":
        if effective_reference:
            print(
                "[comfyui] 警告: HiDream 不支持 img2img，已降级为 txt2img "
                f"(model={model_filename!r})"
            )
            studio_print(
                "comfyui-image",
                f"HiDream img2img 不支持，降级 txt2img: {model_filename}",
            )
        workflow = _build_hidream_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
        )
        return workflow, "txt2img"

    if workflow_type == "qwen-image":
        if effective_reference:
            print(
                "[comfyui] 警告: Qwen-Image 不支持 img2img，已降级为 txt2img "
                f"(model={model_filename!r})"
            )
            studio_print(
                "comfyui-image",
                f"Qwen-Image img2img 不支持，降级 txt2img: {model_filename}",
            )
        workflow = _build_qwen_image_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
        )
        return workflow, "txt2img"

    if workflow_type in ("sd15", "sdxl"):
        return _build_ksampler_workflow(
            prompt_text,
            model_filename,
            width,
            height,
            seed,
            profile,
            reference_filename=effective_reference,
            denoise_override=denoise_override,
            negative_prompt=negative_prompt,
        )

    print(f"[comfyui] 未知 workflow_type={workflow_type!r}，回退 sd15 KSampler 分支")
    return _build_ksampler_workflow(
        prompt_text,
        model_filename,
        width,
        height,
        seed,
        profile,
        reference_filename=effective_reference,
        denoise_override=denoise_override,
        negative_prompt=negative_prompt,
    )


async def submit_image_prompt(
    prompt_text: str,
    model_filename: str,
    width: int,
    height: int,
    reference_image: str | None = None,
    reference_images: list[str] | None = None,
    model_id: str | None = None,
    *,
    skip_translate: bool = False,
    denoise: float | None = None,
    negative_prompt: str | None = None,
    use_reactor: bool = False,
    db: Session | None = None,
    user: User | None = None,
    task_id: str | None = None,
) -> tuple[str, dict, str]:
    """提交 ComfyUI 工作流，返回 (prompt_id, trace_meta, node_url)。"""
    from services.gpu_pool import CAP_IMAGE, get_gpu_pool

    pool = get_gpu_pool()
    # 生图仅走具备 image capability 的节点（本机 5090）；禁止落到仅视频的 H800
    preferred = pool.get_available_node(
        required_vram=16, prefer_short=True, capability=CAP_IMAGE
    )
    candidate_urls = [preferred.comfyui_url.rstrip("/")]
    for node in pool.nodes:
        if CAP_IMAGE not in node.capabilities:
            continue
        url = node.comfyui_url.rstrip("/")
        if url not in candidate_urls:
            candidate_urls.append(url)

    node_url = await _pick_reachable_comfyui_url(candidate_urls)
    original_prompt = prompt_text
    if skip_translate:
        translated_prompt = prompt_text
    else:
        translated_prompt = await translate_if_chinese(prompt_text)
    prompt_text = translated_prompt

    ref_urls = [u.strip() for u in (reference_images or []) if u and str(u).strip()]
    primary_ref = (reference_image or "").strip() or (ref_urls[0] if ref_urls else None)
    unique_ref_urls: list[str] = []
    seen_refs: set[str] = set()
    for candidate in ([primary_ref] if primary_ref else []) + ref_urls:
        if candidate and candidate not in seen_refs:
            seen_refs.add(candidate)
            unique_ref_urls.append(candidate)
    reference_count = len(unique_ref_urls)

    profile = resolve_generation_profile(model_id, model_filename)
    workflow_type = profile.get("workflow_type", "sd15")
    upload_targets = (
        unique_ref_urls
        if workflow_type == "qwen-image-material"
        else unique_ref_urls[:1]
    )

    print(
        f"[comfyui] submit_image_prompt reference_image="
        f"{'set' if primary_ref else 'none'} "
        f"reference_images count: {len(ref_urls)} workflow_type={workflow_type}"
    )
    print(
        f"[comfyui] mode: {'img2img' if primary_ref else 'txt2img'} "
        f"(before upload)"
    )

    reference_filenames: list[str] = []
    for ref_url in upload_targets:
        try:
            uploaded = await _upload_reference_image(
                ref_url, db=db, user=user, base_url=node_url
            )
            reference_filenames.append(uploaded)
            studio_print(
                "comfyui-image",
                f"参考图已上传 filename={uploaded} ({len(reference_filenames)}/{len(upload_targets)})",
            )
        except ComfyUIError:
            raise
        except Exception as exc:
            raise ComfyUIError(f"参考图上传失败: {exc}") from exc

    reference_filename = reference_filenames[0] if reference_filenames else None
    workflow_mode = "img2img" if reference_filename else "txt2img"
    print(f"[comfyui] mode: {workflow_mode} (after upload)")

    logger.info(
        "submit_image_prompt inputs: model=%s width=%s height=%s prompt_len=%s "
        "reference_count=%s workflow_mode=%s",
        model_filename,
        width,
        height,
        len(prompt_text or ""),
        reference_count,
        workflow_mode,
    )
    denoise_override = float(denoise) if denoise is not None else None
    workflow, workflow_mode = _build_workflow(
        prompt_text,
        model_filename,
        width,
        height,
        reference_filename=reference_filename,
        reference_filenames=reference_filenames,
        reference_images=unique_ref_urls or None,
        model_id=model_id,
        denoise_override=denoise_override,
        negative_prompt=negative_prompt,
        use_reactor=bool(use_reactor),
    )
    workflow_trace = extract_workflow_trace(workflow, model_filename)
    workflow_trace["reference_count"] = reference_count
    workflow_trace["workflow_mode"] = workflow_mode
    workflow_trace["width"] = workflow_trace.get("width") or int(width)
    workflow_trace["height"] = workflow_trace.get("height") or int(height)
    workflow_trace["batch_size"] = workflow_trace.get("batch_size") or 1
    if reference_filename:
        ksampler_inputs = workflow.get(NODE_KSAMPLER, {}).get("inputs", {})
        workflow_trace["reference_filename"] = reference_filename
        workflow_trace["ksampler_latent"] = ksampler_inputs.get("latent_image")
        workflow_trace["denoise"] = ksampler_inputs.get("denoise")
    trace_meta = {
        "original_prompt": original_prompt,
        "translated_prompt": translated_prompt,
        "workflow": workflow_trace,
    }
    print(
        f"[comfyui] full workflow:\n"
        f"{json.dumps(workflow, indent=2, ensure_ascii=False)}"
    )
    logger.info("submit_image_prompt workflow nodes=%s mode=%s", len(workflow), workflow_mode)
    studio_print(
        "comfyui-image",
        f"workflow 已构造 model={model_filename} {width}x{height} nodes={len(workflow)}",
    )

    studio_print("comfyui-image", f"POST {node_url}/prompt …")
    response = None
    last_error: Exception | None = None
    last_http_error: ComfyUIError | None = None
    for idx, try_url in enumerate(candidate_urls):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{try_url}/prompt",
                    json={"prompt": workflow},
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            studio_print("comfyui-image", f"连接失败 {try_url}: {exc}")
            response = None
            continue
        if response.status_code == 200:
            node_url = try_url
            break
        studio_print(
            "comfyui-image",
            f"HTTP {response.status_code} @ {try_url}: {response.text[:500]}",
        )
        last_http_error = ComfyUIError(
            f"ComfyUI 返回错误: {response.status_code} {response.text}"
        )
        # 权重缺失 / 校验失败时尝试下一个生图节点，避免卡在错误节点
        if response.status_code == 400 and idx < len(candidate_urls) - 1:
            studio_print(
                "comfyui-image",
                f"节点 {try_url} 校验失败，尝试下一候选…",
            )
            response = None
            continue
        raise last_http_error
    if response is None:
        if last_http_error is not None:
            raise last_http_error
        if isinstance(last_error, httpx.TimeoutException):
            studio_print("comfyui-image", f"请求超时: {last_error}")
            raise ComfyUIError("ComfyUI 请求超时") from last_error
        studio_print("comfyui-image", f"连接失败: {last_error}")
        raise ComfyUIError("ComfyUI 服务未启动，请检查 COMFYUI_URL") from last_error

    try:
        data = response.json()
    except Exception as exc:
        studio_print("comfyui-image", f"无效 JSON: {response.text[:300]}")
        raise ComfyUIError(f"ComfyUI 返回无效 JSON: {response.text[:500]}") from exc

    if data.get("error"):
        studio_print("comfyui-image", f"拒绝: {data['error']}")
        raise ComfyUIError(f"ComfyUI 拒绝工作流: {data['error']}")

    prompt_id = data.get("prompt_id")
    if not prompt_id:
        studio_print("comfyui-image", f"无 prompt_id: {data}")
        raise ComfyUIError("ComfyUI 未返回 prompt_id")
    studio_print("comfyui-image", f"ComfyUI 返回 prompt_id={prompt_id} node={node_url}")
    occupy_task_id = task_id or str(prompt_id)
    pool.mark_busy_by_url(node_url, occupy_task_id, 30)
    try:
        from services import comfyui_progress
        from comfyui.client import count_workflow_sampler_stages

        stages = count_workflow_sampler_stages(workflow)
        comfyui_progress.set_expected_stages(str(prompt_id), stages)
    except Exception:
        pass
    return str(prompt_id), trace_meta, node_url


async def get_image_result(
    prompt_id: str, node_url: str | None = None
) -> str | None | dict:
    """
    查询 ComfyUI 历史记录。
    - 未完成: None
    - 成功: 第一张图片 filename
    - 失败: {"error": "..."}
    """
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{_comfyui_base(node_url)}/history/{prompt_id}"
            )
    except httpx.ConnectError:
        return {"error": "ComfyUI 连接失败"}
    except httpx.TimeoutException:
        return {"error": "查询超时"}

    if response.status_code != 200:
        return {
            "error": f"ComfyUI 返回错误: {response.status_code} {response.text[:500]}"
        }

    try:
        payload = response.json()
    except Exception:
        return {"error": "ComfyUI 历史记录解析失败"}

    try:
        if not payload or prompt_id not in payload:
            return None

        entry = payload[prompt_id]
        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            messages = status.get("messages") or []
            err_text = "ComfyUI 执行失败"
            for msg in messages:
                if (
                    isinstance(msg, (list, tuple))
                    and len(msg) >= 2
                    and msg[0] == "execution_error"
                ):
                    err_text = str(msg[1])
                    break
            return {"error": err_text}

        outputs = entry.get("outputs") or {}
        for node_output in outputs.values():
            images = node_output.get("images") or []
            if images:
                filename = images[0].get("filename")
                if filename:
                    return str(filename)

        if status.get("completed") is True:
            return {"error": "任务已完成但未找到输出图片"}

        return None
    except KeyError:
        return None


def get_image_url(filename: str, *, node_url: str | None = None) -> str:
    """ComfyUI 标准图片访问 URL（经 backend /api/view 代理）。"""
    from comfyui.client import _view_url_for_media

    return _view_url_for_media({"filename": filename, "type": "output"}, node_url=node_url)
