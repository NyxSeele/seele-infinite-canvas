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


async def push_trace(layer: int, tag: str, data: dict) -> None:
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
    steps: int | float | None = None
    cfg: int | float | None = None
    width: int | None = None
    height: int | None = None
    batch_size: int | None = None
    denoise: int | float | None = None
    ckpt_name = model_file
    has_load_image = False
    has_vae_encode = False

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}

        if class_type == "CLIPTextEncode" and positive_prompt is None:
            text = inputs.get("text")
            if isinstance(text, str) and text.strip():
                positive_prompt = text.strip()
        elif class_type == "KSampler":
            steps = inputs.get("steps", steps)
            cfg = inputs.get("cfg", cfg)
            denoise = inputs.get("denoise", denoise)
        elif class_type == "EmptyLatentImage":
            width = inputs.get("width", width)
            height = inputs.get("height", height)
            batch_size = inputs.get("batch_size", batch_size)
        elif class_type == "LoadImage":
            has_load_image = True
        elif class_type == "VAEEncode":
            has_vae_encode = True
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

    workflow_mode = "img2img" if has_load_image and has_vae_encode else "txt2img"

    return {
        "positive_prompt": positive_prompt,
        "steps": steps,
        "cfg": cfg,
        "width": width,
        "height": height,
        "batch_size": batch_size,
        "denoise": denoise,
        "model_file": ckpt_name,
        "workflow_mode": workflow_mode,
    }
