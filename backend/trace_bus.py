"""开发调试：Prompt 四层追踪事件总线。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

_trace_queue: asyncio.Queue | None = None


def get_trace_queue() -> asyncio.Queue:
    global _trace_queue
    if _trace_queue is None:
        _trace_queue = asyncio.Queue()
    return _trace_queue


async def push_trace(layer: int | str, tag: str, data: dict) -> None:
    queue = get_trace_queue()
    await queue.put(
        {
            "layer": layer,
            "tag": tag,
            "ts": time.time(),
            "data": data,
        }
    )


def extract_workflow_trace(workflow: dict, model_file: str) -> dict[str, Any]:
    """从 ComfyUI workflow 提取 L4 展示字段。"""
    positive_prompt: str | None = None
    negative_prompt: str | None = None
    clip_encode_index = 0
    steps: int | float | None = None
    cfg: int | float | None = None
    width: int | None = None
    height: int | None = None
    batch_size: int | None = None
    num_frames: int | None = None
    denoise: int | float | None = None
    ckpt_name = model_file
    reference_filename: str | None = None
    start_reference_filename: str | None = None
    end_reference_filename: str | None = None
    load_image_filenames: list[str] = []
    has_load_image = False
    has_vae_encode = False
    has_wan_flf2v = False
    has_wan_fun_inpaint = False
    has_wan_i2v = False

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}

        if class_type == "CLIPTextEncode":
            text = inputs.get("text")
            if isinstance(text, str) and text.strip():
                if clip_encode_index == 0:
                    positive_prompt = text.strip()
                elif clip_encode_index == 1 and negative_prompt is None:
                    negative_prompt = text.strip()
                clip_encode_index += 1
        elif class_type == "KSampler":
            steps = inputs.get("steps", steps)
            cfg = inputs.get("cfg", cfg)
            denoise = inputs.get("denoise", denoise)
        elif class_type == "KSamplerAdvanced":
            steps = inputs.get("steps", steps)
            cfg = inputs.get("cfg", cfg)
            denoise = inputs.get("denoise", denoise)
        elif class_type == "EmptyLatentImage":
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            batch_size = inputs.get("batch_size", batch_size)
        elif class_type == "LoadImage":
            has_load_image = True
            img = inputs.get("image")
            if isinstance(img, str) and img.strip():
                load_image_filenames.append(img.strip())
                reference_filename = img.strip()
        elif class_type == "VAEEncode":
            has_vae_encode = True
        elif class_type == "WanFirstLastFrameToVideo":
            has_wan_flf2v = True
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            num_frames = inputs.get("length", num_frames)
            batch_size = inputs.get("batch_size", batch_size)
        elif class_type == "WanFunInpaintToVideo":
            has_wan_fun_inpaint = True
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            num_frames = inputs.get("length", num_frames)
            batch_size = inputs.get("batch_size", batch_size)
        elif class_type == "WanImageToVideo":
            has_wan_i2v = True
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            num_frames = inputs.get("length", num_frames)
            batch_size = inputs.get("batch_size", batch_size)
        elif class_type == "EmptyLTXVLatentVideo":
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            batch_size = inputs.get("batch_size", batch_size)
        elif class_type == "LTXVScheduler" and steps is None:
            steps = inputs.get("steps")
        elif class_type == "CFGGuider" and cfg is None:
            cfg = inputs.get("cfg")
        elif class_type == "CheckpointLoaderSimple":
            ckpt = inputs.get("ckpt_name")
            if isinstance(ckpt, str) and ckpt.strip():
                ckpt_name = ckpt.strip()
        elif class_type == "LTXVLoader":
            ckpt = inputs.get("ckpt_name")
            if isinstance(ckpt, str) and ckpt.strip():
                ckpt_name = ckpt.strip()
        elif class_type == "UNETLoader":
            unet = inputs.get("unet_name")
            if isinstance(unet, str) and unet.strip():
                ckpt_name = unet.strip()
        elif class_type == "BasicScheduler":
            steps = inputs.get("steps", steps)
            denoise = inputs.get("denoise", denoise)
        elif class_type == "FluxGuidance" and cfg is None:
            cfg = inputs.get("guidance")
        elif class_type == "EmptySD3LatentImage":
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            batch_size = inputs.get("batch_size", batch_size)

    if has_wan_fun_inpaint:
        workflow_mode = "fun_inpaint"
        if len(load_image_filenames) >= 1:
            start_reference_filename = load_image_filenames[0]
        if len(load_image_filenames) >= 2:
            end_reference_filename = load_image_filenames[1]
    elif has_wan_flf2v:
        workflow_mode = "flf2v"
        if len(load_image_filenames) >= 1:
            start_reference_filename = load_image_filenames[0]
        if len(load_image_filenames) >= 2:
            end_reference_filename = load_image_filenames[1]
    elif has_load_image and has_vae_encode:
        workflow_mode = "img2img"
    elif has_wan_i2v or has_load_image:
        workflow_mode = "image2video"
    else:
        workflow_mode = "txt2img"

    return {
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "cfg": cfg,
        "width": width,
        "height": height,
        "batch_size": batch_size,
        "num_frames": num_frames,
        "denoise": denoise,
        "model_file": ckpt_name,
        "workflow_mode": workflow_mode,
        "reference_filename": reference_filename,
        "start_reference_filename": start_reference_filename,
        "end_reference_filename": end_reference_filename,
    }


def build_mock_workflow_trace(task_type: str, *, trace_id: str | None = None, **fields: Any) -> dict[str, Any]:
    """为 mock / 非 KSampler workflow 合成 L4 展示字段。"""
    out: dict[str, Any] = {"task_type": task_type, "workflow_mode": "mock", **fields}
    if trace_id:
        out["trace_id"] = trace_id
    return out


def extract_enhance_trace(workflow: dict, provider_id: str) -> dict[str, Any]:
    """从视频画质增强 workflow 提取 L4 字段。"""
    upscale_factor: float | None = None
    strength: str | None = None
    batch_size: int | None = None
    color_correction: str | None = None
    model_size: str | None = None

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}
        if class_type == "SeedVR2VideoUpscaler":
            upscale_factor = inputs.get("upscale_factor", upscale_factor)
            batch_size = inputs.get("batch_size", batch_size)
            color_correction = inputs.get("color_correction", color_correction)
            model_size = inputs.get("model_size", model_size)
            strength = inputs.get("strength", strength)
        elif class_type == "ImageUpscaleWithModel":
            scale = inputs.get("scale")
            if scale is not None:
                upscale_factor = float(scale) if upscale_factor is None else upscale_factor

    base = extract_workflow_trace(workflow, provider_id)
    base["task_type"] = "video_enhance"
    base["provider"] = provider_id
    base["upscale_factor"] = upscale_factor
    base["strength"] = strength
    base["batch_size"] = batch_size
    base["color_correction"] = color_correction
    base["model_size"] = model_size
    base["workflow_mode"] = "video_enhance"
    return base


def build_lut_trace(
    *,
    trace_id: str | None = None,
    lut_preset: str | None = None,
    cube_path: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """LUT 任务 L4 展示字段。"""
    out: dict[str, Any] = {
        "task_type": "video_lut",
        "workflow_mode": "ffmpeg_lut3d",
        "lut_preset": lut_preset or "custom",
        "cube_path": cube_path,
        "source_url": source_url,
        "ffmpeg_filter": "lut3d",
    }
    if trace_id:
        out["trace_id"] = trace_id
    return out
